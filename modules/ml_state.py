# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Central prediction-analysis state shared by Predict / Inspect / Report.

One instance of :class:`PredictionState` is owned by the Model Prediction
page controller. The three tabs read from it and react to its signals -
nothing is duplicated per tab:

    load models   -> models_changed  -> all tabs refresh model info
    load dataset  -> dataset_changed -> all tabs refresh dataset info
    (both also re-run the compatibility validation -> validation_changed)
    run           -> run_started / run_finished / run_failed
    select record -> selection_changed (Inspect updates its visualisation)

The prediction itself runs the ported ``modules/predict_worker.py`` in a
subprocess via a worker QThread (same architecture as the MVP), so the
model stack is never imported into the GUI process.
"""
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd

from PySide6.QtCore import QObject, QThread, Signal

_WORKER     = Path(__file__).parent / "predict_worker.py"
_MODELS_DIR = Path(__file__).parent.parent / "models"

# ground truth: overall_passage_type values counted as a strike
# (same set the Dataset creation page uses for its annotation figure)
STRIKE_TYPES = {"leading_edge", "other"}

_DEFAULT_LOW_CONF = 0.70


# ── worker thread (ported from the MVP's _WorkerThread) ──────────────────────
class _WorkerThread(QThread):
    finished_ok = Signal(str)
    failed      = Signal(str)

    def __init__(self, bin_model, bin_metrics, mc_model, mc_metrics,
                 data_path, out_dir, threshold=None, df_to_write=None):
        super().__init__()
        self._bin_model, self._bin_metrics = bin_model, bin_metrics
        self._mc_model,  self._mc_metrics  = mc_model,  mc_metrics
        self._data, self._out = data_path, out_dir
        self._threshold = threshold
        self._df_to_write = df_to_write   # in-memory dataset -> temp CSV

    def run(self):
        try:
            if self._df_to_write is not None:
                # write the in-memory dataset off the GUI thread
                self._df_to_write.to_csv(self._data, index=False)
        except Exception as e:
            self.failed.emit(f"Could not write dataset for the worker: {e}")
            return

        cmd = [sys.executable, str(_WORKER),
               "--bin-model",   str(self._bin_model),
               "--bin-metrics", str(self._bin_metrics),
               "--data",        str(self._data),
               "--out",         str(self._out)]
        if self._mc_model and self._mc_metrics:
            cmd += ["--mc-model",   str(self._mc_model),
                    "--mc-metrics", str(self._mc_metrics)]
        if self._threshold is not None:
            cmd += ["--threshold", str(self._threshold)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if r.returncode != 0:
                self.failed.emit(
                    (r.stderr + r.stdout).strip() or "Worker exited non-zero")
            else:
                self.finished_ok.emit(str(self._out))
        except subprocess.TimeoutExpired:
            self.failed.emit("Prediction timed out (>5 min)")
        except Exception as e:
            self.failed.emit(str(e))


# ═════════════════════════════════════════════════════════════════════════════
class PredictionState(QObject):
    """Everything the Predict / Inspect / Report tabs share."""

    models_changed     = Signal()
    dataset_changed    = Signal()
    validation_changed = Signal()
    config_changed     = Signal()
    run_started        = Signal()
    run_finished       = Signal()
    run_failed         = Signal(str)
    selection_changed  = Signal(str)   # recording id, "" = cleared
    treatment_selected = Signal(str)   # treatment picked in the results table
    status             = Signal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)

        # models
        self.models_dir       = _MODELS_DIR
        self.bin_model_path   = None
        self.bin_metrics_path = None
        self.bin_metrics      = None
        self.mc_model_path    = None
        self.mc_metrics_path  = None
        self.mc_metrics       = None
        self.class_names      = []

        # dataset
        self.dataset_df     = None
        self.dataset_path   = None      # CSV on disk, if loaded from file
        self.dataset_source = None      # human-readable origin
        self.dataset_meta   = {}

        # validation
        self.checks = []                # list of (state, label, detail)
        self.ready  = False

        # configuration
        self.mode                 = "binary"     # "binary" | "multiclass"
        self.threshold_overridden = False
        self.threshold_override   = 0.5
        self.low_conf_threshold   = _DEFAULT_LOW_CONF

        # run / results
        self.running        = False
        self.run_id         = None
        self.run_time       = None      # datetime of last successful run
        self.out_dir        = None
        self.predictions    = None      # per-recording DataFrame
        self.summary        = None      # treatment-level DataFrame
        self.region_summary = None
        self.run_meta       = {}

        # selection
        self.selected_file      = None
        self.selected_treatment = None

        self.app_version = ""
        self._thread = None

    # ── models ───────────────────────────────────────────────────────────────
    @staticmethod
    def _metrics_for(model_path):
        """Find the metrics JSON beside a model joblib (MVP rules)."""
        p = Path(model_path)
        cand = p.parent / (p.stem + "performance_metrics.json")
        if cand.exists():
            return cand
        cand = p.parent / "performance_metrics.json"
        if cand.exists():
            return cand
        hits = list(p.parent.glob(f"{p.stem}*metrics*.json")) or \
               list(p.parent.glob("*metrics*.json"))
        return hits[0] if hits else None

    def load_models_from_dir(self, d):
        """Auto-discover binary*.joblib / multiclass*.joblib as in the MVP.

        Returns (ok, message). On success the models_changed signal fires and
        validation is re-run.
        """
        d = Path(d)
        bins = sorted(d.glob("binary*.joblib"))
        mcs  = sorted(d.glob("multiclass*.joblib"))
        if not bins:
            return False, f"No binary*.joblib found in {d}"

        bin_model   = bins[0]
        bin_metrics = self._metrics_for(bin_model)
        if bin_metrics is None:
            return False, "No metrics JSON found beside the binary model."
        try:
            with open(bin_metrics) as f:
                parsed = json.load(f)
        except Exception as e:
            return False, f"Could not read {bin_metrics.name}: {e}"

        self.models_dir       = d
        self.bin_model_path   = bin_model
        self.bin_metrics_path = bin_metrics
        self.bin_metrics      = parsed

        # multiclass model is optional; a failure to read it degrades to
        # binary-only rather than failing the whole load
        self.mc_model_path = self.mc_metrics_path = self.mc_metrics = None
        self.class_names = []
        mc_note = ""
        if mcs:
            mc_model   = mcs[0]
            mc_metrics = self._metrics_for(mc_model)
            if mc_metrics is not None:
                try:
                    with open(mc_metrics) as f:
                        self.mc_metrics = json.load(f)
                    self.mc_model_path   = mc_model
                    self.mc_metrics_path = mc_metrics
                    self.class_names = list(self.mc_metrics.get("class_names", []))
                except Exception as e:
                    mc_note = f" (multiclass metrics unreadable: {e})"
            else:
                mc_note = " (multiclass model has no metrics JSON - ignored)"

        # default mode: use the full two-stage pipeline when available
        self.mode = "multiclass" if self.mc_model_path else "binary"
        self.threshold_overridden = False

        self.models_changed.emit()
        self.config_changed.emit()
        self.validate()
        return True, f"Models loaded from {d}{mc_note}"

    @property
    def deployed_threshold(self):
        try:
            return float(
                self.bin_metrics["out_of_fold_performance"]["optimal_threshold"])
        except (TypeError, KeyError, ValueError):
            return None

    @property
    def effective_threshold(self):
        if self.threshold_overridden:
            return float(self.threshold_override)
        return self.deployed_threshold

    @property
    def available_modes(self):
        modes = []
        if self.bin_model_path is not None:
            modes.append("binary")
            if self.mc_model_path is not None:
                modes.append("multiclass")
        return modes

    def bin_channels(self):
        if self.bin_metrics:
            return list(self.bin_metrics.get("channels", []))
        return []

    def mc_channels(self):
        if self.mc_metrics:
            return list(self.mc_metrics.get("channels", []))
        return []

    def required_channels(self):
        chans = list(self.bin_channels())
        if self.mode == "multiclass":
            for c in self.mc_channels():
                if c not in chans:
                    chans.append(c)
        return chans

    # ── dataset ──────────────────────────────────────────────────────────────
    def set_dataset(self, df, path=None, source=None):
        """Install a dataset (in-memory DataFrame, optionally backed by a CSV)."""
        self.dataset_df     = df
        self.dataset_path   = Path(path) if path else None
        self.dataset_source = source or (
            f"CSV file: {self.dataset_path.name}" if self.dataset_path
            else "In-memory dataset")
        self.dataset_meta = self._compute_dataset_meta()
        self.dataset_changed.emit()
        self.validate()

    def load_dataset_csv(self, path):
        """Load a dataset CSV from disk. Returns (ok, message)."""
        path = Path(path)
        try:
            peek = pd.read_csv(path, low_memory=False, nrows=5)
        except Exception as e:
            return False, f"Dataset load failed: {e}"
        for col in ("file", "time_s"):
            if col not in peek.columns:
                return False, f"CSV must have a '{col}' column."
        try:
            df = pd.read_csv(path, low_memory=False)
        except Exception as e:
            return False, f"Dataset load failed: {e}"
        self.set_dataset(df, path=path, source=f"CSV file: {path.name}")
        return True, f"Dataset loaded: {path.name}"

    def _compute_dataset_meta(self):
        df = self.dataset_df
        if df is None:
            return {}
        meta = {}
        meta["name"] = (self.dataset_path.name if self.dataset_path
                        else "Sensor Processing dataset")
        meta["n_rows"] = int(len(df))

        if "file" in df.columns:
            per_file = df.groupby("file").size()
            meta["n_files"]     = int(per_file.shape[0])
            meta["seq_len_min"] = int(per_file.min())
            meta["seq_len_max"] = int(per_file.max())
        if "treatment" in df.columns:
            tx = df["treatment"].dropna().astype(str).unique().tolist()
            meta["treatments"] = sorted(tx)
        if "deployment_id" in df.columns:
            meta["deployments"] = sorted(
                df["deployment_id"].dropna().astype(str).unique().tolist())

        # sampling rate estimated from the time axis of the first recording
        if "time_s" in df.columns and "file" in df.columns and len(df):
            first = df[df["file"] == df["file"].iloc[0]]["time_s"]
            dt = first.diff().median()
            if pd.notna(dt) and dt > 0:
                meta["sampling_rate_hz"] = round(1.0 / float(dt))

        meta["columns"]   = list(df.columns)
        meta["annotated"] = "overall_passage_type" in df.columns
        return meta

    def has_ground_truth(self):
        return bool(self.dataset_meta.get("annotated")) or (
            self.predictions is not None
            and "overall_passage_type" in self.predictions.columns)

    # ── validation ───────────────────────────────────────────────────────────
    def validate(self):
        """Model-dataset compatibility check. Runs before the subprocess can
        be launched; self.ready gates the Run button."""
        checks = []
        hard_fail = False

        def add(state, label, detail=""):
            nonlocal hard_fail
            if state == "fail":
                hard_fail = True
            checks.append((state, label, detail))

        # model
        if self.bin_model_path is None:
            add("fail", "Model loaded", "No binary model - set the models folder.")
        else:
            names = self.bin_model_path.name
            if self.mode == "multiclass" and self.mc_model_path is not None:
                names += f" + {self.mc_model_path.name}"
            add("ok", "Model loaded", names)
            if self.deployed_threshold is None:
                add("warn", "Deployed threshold",
                    "optimal_threshold missing from the metrics file.")

        if self.mode == "multiclass" and self.mc_model_path is None:
            add("fail", "Multiclass model", "Multiclass mode selected but no "
                "multiclass model is loaded.")

        # dataset
        df = self.dataset_df
        if df is None:
            add("fail", "Dataset loaded",
                "Create a dataset in Sensor Processing or load a CSV.")
        else:
            add("ok", "Dataset loaded",
                f"{self.dataset_meta.get('n_files', '?')} recordings")
            for col in ("file", "time_s"):
                if col not in df.columns:
                    add("fail", f"'{col}' column present",
                        "Required by the prediction worker.")

            # channels
            if self.bin_metrics:
                req = self.required_channels()
                missing = [c for c in req if c not in df.columns]
                if missing:
                    add("fail", "Required channels present",
                        "Missing: " + ", ".join(missing))
                else:
                    add("ok", "Required channels present",
                        f"All {len(req)} model channels found")

                # sequence length
                max_len = self.bin_metrics.get("max_sequence_length")
                have = self.dataset_meta.get("seq_len_max")
                if max_len and have:
                    if have <= max_len:
                        add("ok", "Sequence length compatible",
                            f"{have} samples per recording "
                            f"(model input {max_len}; shorter is padded)")
                    else:
                        add("warn", "Sequence length compatible",
                            f"Recordings have {have} samples; the model input "
                            f"is {max_len} - extra samples are truncated.")

        self.checks = checks
        self.ready = (not hard_fail
                      and self.bin_model_path is not None
                      and self.dataset_df is not None
                      and not self.running)
        self.validation_changed.emit()

    # ── configuration ────────────────────────────────────────────────────────
    def set_mode(self, mode):
        if mode not in ("binary", "multiclass") or mode == self.mode:
            return
        self.mode = mode
        self.config_changed.emit()
        self.validate()

    def set_threshold_override(self, enabled, value=None):
        self.threshold_overridden = bool(enabled)
        if value is not None:
            self.threshold_override = float(value)
        self.config_changed.emit()

    # ── run ──────────────────────────────────────────────────────────────────
    def run_prediction(self):
        """Launch the worker subprocess. Emits run_started immediately and
        run_finished / run_failed later on the GUI thread."""
        if self.running:
            return
        self.validate()
        if not self.ready:
            self.run_failed.emit("Prediction is not ready - resolve the "
                                 "compatibility checks first.")
            return

        self.run_id  = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = Path(tempfile.mkdtemp(prefix=f"strikeworks_pred_{self.run_id}_"))

        # dataset on disk if we have an unmodified CSV, else write a temp copy
        df_to_write = None
        if self.dataset_path is not None and self.dataset_path.exists():
            data_path = self.dataset_path
        else:
            data_path = out_dir / "dataset.csv"
            df_to_write = self.dataset_df

        use_mc = self.mode == "multiclass" and self.mc_model_path is not None
        threshold = (float(self.threshold_override)
                     if self.threshold_overridden else None)

        self.running = True
        self.validate()          # ready -> False while running
        self.run_started.emit()

        self._thread = _WorkerThread(
            self.bin_model_path, self.bin_metrics_path,
            self.mc_model_path if use_mc else None,
            self.mc_metrics_path if use_mc else None,
            data_path, out_dir, threshold=threshold, df_to_write=df_to_write)
        self._thread.finished_ok.connect(self._on_worker_done)
        self._thread.failed.connect(self._on_worker_failed)
        self._thread.start()

    def _on_worker_done(self, out_dir):
        self.running = False
        try:
            self._apply_results(Path(out_dir))
        except Exception as e:
            self.validate()
            self.run_failed.emit(f"Reading worker results failed: {e}")
            return
        self.run_time = datetime.now()
        self.validate()
        self.run_finished.emit()

    def _on_worker_failed(self, msg):
        self.running = False
        self.validate()
        self.run_failed.emit(msg)

    def _apply_results(self, out_dir):
        self.out_dir     = out_dir
        self.predictions = pd.read_csv(out_dir / "predictions.csv")
        self.summary     = pd.read_csv(out_dir / "summary.csv")
        region = out_dir / "region_summary.csv"
        self.region_summary = pd.read_csv(region) if region.exists() else None
        meta = out_dir / "run_meta.json"
        try:
            with open(meta) as f:
                self.run_meta = json.load(f)
        except Exception:
            self.run_meta = {}
        # clear any stale selection from a previous run
        self.selected_file = None
        self.selection_changed.emit("")

    # ── selection ────────────────────────────────────────────────────────────
    def select_file(self, file_id):
        file_id = file_id or None
        if file_id == self.selected_file:
            return
        self.selected_file = file_id
        self.selection_changed.emit(file_id or "")

    def select_treatment(self, treatment):
        self.selected_treatment = treatment or None
        self.treatment_selected.emit(treatment or "")

    def selected_row(self):
        """The predictions.csv row for the selected recording, or None."""
        if self.predictions is None or not self.selected_file:
            return None
        rows = self.predictions[self.predictions["file"] == self.selected_file]
        return rows.iloc[0] if len(rows) else None

    def file_signal(self, file_id):
        """Time-ordered dataset rows for one recording (the model input)."""
        if self.dataset_df is None or not file_id:
            return None
        rows = self.dataset_df[self.dataset_df["file"] == file_id]
        if not len(rows):
            return None
        return rows.sort_values("time_s")

    # ── ground truth ─────────────────────────────────────────────────────────
    def ground_truth_for(self, row):
        """(gt_strike, gt_label, gt_region_class) for a predictions row.

        Returns (None, None, None) when the dataset carries no annotations.
        gt_region_class is the collapsed class name matching the multiclass
        model's classes, when the mapping is available.
        """
        if row is None or "overall_passage_type" not in row.index:
            return None, None, None
        gt_type = row.get("overall_passage_type")
        if pd.isna(gt_type) or str(gt_type).strip() == "":
            return None, None, None
        gt_type = str(gt_type)
        gt_strike = gt_type in STRIKE_TYPES

        gt_region_class = None
        region = row.get("concentric_pump_region")
        if (gt_strike and pd.notna(region) and self.mc_metrics
                and self.class_names):
            mapping = self.mc_metrics.get("region_to_class", {})
            try:
                idx = mapping.get(str(int(float(region))))
                if idx is not None and 0 <= int(idx) < len(self.class_names):
                    gt_region_class = self.class_names[int(idx)]
            except (ValueError, TypeError):
                pass
        return gt_strike, gt_type, gt_region_class

    # ── provenance ───────────────────────────────────────────────────────────
    def provenance(self):
        """Everything needed to reproduce the analysis. Only real values -
        anything unavailable is reported as 'Not available'."""
        na = "Not available"
        meta = self.run_meta or {}

        def _s(v):
            return str(v) if v not in (None, "", []) else na

        ds = {
            "name":        _s(self.dataset_meta.get("name")),
            "path":        _s(str(self.dataset_path) if self.dataset_path else None),
            "source":      _s(self.dataset_source),
            "n_recordings": self.dataset_meta.get("n_files", na),
            "n_rows":      self.dataset_meta.get("n_rows", na),
            "treatments":  self.dataset_meta.get("treatments", na),
            "sampling_rate_hz": self.dataset_meta.get("sampling_rate_hz", na),
            "annotated":   self.dataset_meta.get("annotated", na),
        }
        model = {
            "binary_model":   _s(self.bin_model_path.name if self.bin_model_path else None),
            "binary_metrics": _s(self.bin_metrics_path.name if self.bin_metrics_path else None),
            "binary_model_path": _s(str(self.bin_model_path) if self.bin_model_path else None),
            "model_type":     _s((self.bin_metrics or {}).get("model")),
            "multiclass_model": _s(self.mc_model_path.name if self.mc_model_path else None),
            "multiclass_metrics": _s(self.mc_metrics_path.name if self.mc_metrics_path else None),
            "multiclass_model_path": _s(str(self.mc_model_path) if self.mc_model_path else None),
            "class_names":    self.class_names or na,
            "mode":           _s(meta.get("mode") or self.mode),
            "threshold":      meta.get("threshold", self.effective_threshold or na),
            "deployed_threshold": meta.get("deployed_threshold",
                                           self.deployed_threshold or na),
            "threshold_overridden": meta.get("threshold_overridden",
                                             self.threshold_overridden),
        }
        analysis = {
            "run_id":          _s(self.run_id),
            "timestamp":       _s(meta.get("timestamp")),
            "elapsed_s":       meta.get("elapsed_s", na),
            "application":     f"StrikeWorks {self.app_version}".strip(),
            "python_version":  _s(meta.get("python_version")),
            "package_versions": meta.get("package_versions", na),
        }
        outputs = {
            "run_directory": _s(str(self.out_dir) if self.out_dir else None),
            "files": ([p.name for p in sorted(self.out_dir.glob("*"))]
                      if self.out_dir and self.out_dir.exists() else na),
        }
        return {"dataset": ds, "model": model,
                "analysis": analysis, "outputs": outputs}
