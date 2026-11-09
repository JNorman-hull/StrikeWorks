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

The prediction itself runs ``modules/predict_worker.py`` in a subprocess
(watched by a QThread), so the model stack is never imported into the GUI
process.
"""
import json
import subprocess

import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd

from PySide6.QtCore import QObject, QThread, Signal

from . import hig_peaks, model_labels, recording_rate, settings
from .worker_launch import worker_command

_DEFAULT_LOW_CONF = 0.70


# the settings file's section holding HIG peak analysis's detection settings
HIG_SECTION = "hig_peak_analysis"


# ── worker thread ────────────────────────────────────────────────────────────
class _WorkerThread(QThread):
    finished_ok = Signal(str)
    failed      = Signal(str)

    def __init__(self, bin_model, bin_metrics, mc_model, mc_metrics,
                 data_path, out_dir, threshold=None, df_to_write=None,
                 hig_peaks=False, hig_settings=None):
        super().__init__()
        self._bin_model, self._bin_metrics = bin_model, bin_metrics
        self._mc_model,  self._mc_metrics  = mc_model,  mc_metrics
        self._data, self._out = data_path, out_dir
        self._threshold = threshold
        self._hig_peaks = hig_peaks
        self._hig_settings = hig_settings
        self._df_to_write = df_to_write   # in-memory dataset -> temp CSV

    def run(self):
        try:
            if self._df_to_write is not None:
                # write the in-memory dataset off the GUI thread
                self._df_to_write.to_csv(self._data, index=False)
        except Exception as e:
            self.failed.emit(f"Could not write dataset for the worker: {e}")
            return

        cmd = worker_command("predict") + [
               "--bin-model",   str(self._bin_model),
               "--bin-metrics", str(self._bin_metrics),
               "--data",        str(self._data),
               "--out",         str(self._out)]
        if self._mc_model and self._mc_metrics:
            cmd += ["--mc-model",   str(self._mc_model),
                    "--mc-metrics", str(self._mc_metrics)]
        if self._threshold is not None:
            cmd += ["--threshold", str(self._threshold)]
        if self._hig_peaks:
            cmd.append("--hig-peaks")
            if self._hig_settings:
                cmd += ["--hig-settings", json.dumps(self._hig_settings)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            # the worker's own output, for the console (dev_console.py
            # mirrors print) - captured above, so it went nowhere before
            for line in (r.stdout + r.stderr).splitlines():
                if line.strip():
                    print(f"[predict-worker] {line}")
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
        self.models_dir       = settings.get_models_dir()
        self.bin_model_path   = None
        self.bin_metrics_path = None
        self.bin_metrics      = None
        self.mc_model_path    = None
        self.mc_metrics_path  = None
        self.mc_metrics       = None
        self.class_names      = []
        # every binary*/multiclass*.joblib found in models_dir, for
        # switching between variants (binary1_1, binary1_2, ...) without
        # re-browsing the folder
        self._bin_candidates  = []
        self._mc_candidates   = []

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
        self.hig_peaks            = True         # HIG peak analysis (hig_peaks.py)
        # its detection settings - Advanced features, kept in the settings
        # file (defaults: config/default_settings.json)
        self.hig_settings = hig_peaks.detection(settings.read_section(HIG_SECTION))

        # run / results
        self.running        = False
        self.run_id         = None
        self.run_time       = None      # datetime of last successful run
        self.out_dir        = None
        self.predictions    = None      # per-recording DataFrame
        self.summary        = None      # treatment-level DataFrame
        self.region_summary = None
        self.severity_summary = None    # treatment x HIG threshold (severity.py)
        self.peak_events    = None      # HIG peak analysis: one row per event
        self.acc_summary    = None      # ... and the acceleration table
        self.run_meta       = {}

        # selection
        self.selected_file      = None
        self.selected_treatment = None

        self.app_version = ""
        self._thread = None
        self._traces = None
        self._traces_key = None

    # ── models ───────────────────────────────────────────────────────────────
    @staticmethod
    def _metrics_for(model_path):
        """Find the metrics JSON beside a model joblib: `<stem>performance_
        metrics.json`, then `performance_metrics.json`, then any
        `*metrics*.json`."""
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

    @staticmethod
    def _default_model(candidates, pinned, stem):
        """The model pinned in Settings when it's among `candidates`, else
        `stem` ('binary1' / 'multiclass1'), else the newest."""
        if pinned is not None and Path(pinned) in candidates:
            return Path(pinned)
        return (next((p for p in candidates if p.stem == stem), None)
                or max(candidates, key=lambda p: p.stat().st_mtime))

    def load_models_from_dir(self, d):
        """Find the binary*.joblib / multiclass*.joblib models in `d` and
        select one of each: the one already selected if it's there (a
        rescan, e.g. after a deploy), else the default (`_default_model`).
        `bin_candidates` / `mc_candidates` expose the rest so a caller
        (Predict's model selector) can switch via `select_bin_model`/
        `select_mc_model` without re-browsing the folder.

        Returns (ok, message). On success the models_changed signal fires and
        validation is re-run.
        """
        d = Path(d)
        self._bin_candidates = sorted(d.glob("binary*.joblib"))
        self._mc_candidates  = sorted(d.glob("multiclass*.joblib"))
        if not self._bin_candidates:
            return False, f"No binary*.joblib found in {d}"

        def pick(candidates, current, pinned, stem):
            if current is not None and Path(current) in candidates:
                return Path(current)
            return self._default_model(candidates, pinned, stem)

        self.models_dir = d
        ok, msg = self._apply_bin_model(pick(
            self._bin_candidates, self.bin_model_path,
            settings.get_default_model(), "binary1"))
        if not ok:
            return False, msg

        # multiclass model is optional; a failure to read it degrades to
        # binary-only rather than failing the whole load
        mc_note = ""
        if self._mc_candidates:
            ok, msg = self._apply_mc_model(pick(
                self._mc_candidates, self.mc_model_path,
                settings.get_default_mc_model(), "multiclass1"))
            if not ok:
                mc_note = f" ({msg})"
        else:
            self._clear_mc_model()

        # default mode: use the full two-stage pipeline when available
        self.mode = "multiclass" if self.mc_model_path else "binary"
        self.threshold_overridden = False

        self.models_changed.emit()
        self.config_changed.emit()
        self.validate()
        return True, f"Models loaded from {d}{mc_note}"

    def _apply_bin_model(self, path):
        metrics = self._metrics_for(path)
        if metrics is None:
            return False, "No metrics JSON found beside the binary model."
        try:
            with open(metrics) as f:
                parsed = json.load(f)
        except Exception as e:
            return False, f"Could not read {metrics.name}: {e}"
        self.bin_model_path   = Path(path)
        self.bin_metrics_path = metrics
        self.bin_metrics      = parsed
        return True, ""

    def _clear_mc_model(self):
        self.mc_model_path = self.mc_metrics_path = self.mc_metrics = None
        self.class_names = []

    def _apply_mc_model(self, path):
        metrics = self._metrics_for(path)
        if metrics is None:
            self._clear_mc_model()
            return False, "multiclass model has no metrics JSON - ignored"
        try:
            with open(metrics) as f:
                parsed = json.load(f)
        except Exception as e:
            self._clear_mc_model()
            return False, f"multiclass metrics unreadable: {e}"
        self.mc_model_path   = Path(path)
        self.mc_metrics_path = metrics
        self.mc_metrics      = parsed
        self.class_names     = list(parsed.get("class_names", []))
        return True, ""

    @property
    def bin_candidates(self):
        """Every binary*.joblib found in models_dir, for a model picker."""
        return list(self._bin_candidates)

    @property
    def mc_candidates(self):
        """Every multiclass*.joblib found in models_dir, for a model picker."""
        return list(self._mc_candidates)

    def use_default_models(self):
        """Load the models folder (Settings) and select its default models
        (`_default_model`) - a model pinned in Settings from another folder
        is used too, and joins the candidates. Rescans every time, since an
        earlier load may have pointed `models_dir` elsewhere. Returns the
        folder load's (ok, message)."""
        result = self.load_models_from_dir(settings.get_models_dir())
        for candidates, pinned, stem, current, select in (
                (self._bin_candidates, settings.get_default_model(), "binary1",
                 self.bin_model_path, self.select_bin_model),
                (self._mc_candidates, settings.get_default_mc_model(),
                 "multiclass1", self.mc_model_path, self.select_mc_model)):
            if (pinned is not None and Path(pinned).exists()
                    and Path(pinned) not in candidates):
                candidates.append(Path(pinned))
            if not candidates:
                continue
            chosen = self._default_model(candidates, pinned, stem)
            if current != chosen:
                select(chosen)
        return result

    def select_bin_model(self, path):
        """Switch to a different binary model already found in models_dir."""
        ok, msg = self._apply_bin_model(path)
        if ok:
            self.threshold_overridden = False
            self.models_changed.emit()
            self.config_changed.emit()
            self.validate()
        return ok, msg

    def select_mc_model(self, path):
        """Switch to a different multiclass model, or None for binary-only."""
        if path is None:
            self._clear_mc_model()
            ok, msg = True, ""
        else:
            ok, msg = self._apply_mc_model(path)
        if self.mode == "multiclass" and self.mc_model_path is None:
            self.mode = "binary"
        self.models_changed.emit()
        self.config_changed.emit()
        self.validate()
        return ok, msg

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
        meta["data_problem"] = recording_rate.dataset_problem(df)
        meta["identity"] = recording_rate.identity(df)
        return meta

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

            # one sensor at one rate, the one the models were trained on
            if self.dataset_meta.get("data_problem"):
                add("fail", "One sensor and frequency",
                    self.dataset_meta["data_problem"])
            elif self.bin_metrics:
                used = [("Binary model", self.bin_metrics)]
                if self.mode == "multiclass" and self.mc_metrics:
                    used.append(("Multiclass model", self.mc_metrics))
                for label, metrics in used:
                    problem = recording_rate.model_problem(
                        metrics, self.dataset_meta["identity"])
                    if problem:
                        add("fail", f"{label} matches the dataset", problem)
                    else:
                        add("ok", f"{label} matches the dataset", recording_rate.describe(
                            *recording_rate.model_identity(metrics)))

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

    def set_hig_peaks(self, enabled):
        self.hig_peaks = bool(enabled)
        self.config_changed.emit()

    def set_hig_setting(self, name, value):
        """One detection setting (a hig_peaks.DETECTION_DEFAULTS name)."""
        self.hig_settings = hig_peaks.detection({**self.hig_settings, name: value})
        settings.write_section(HIG_SECTION, dict(self.hig_settings))
        self.config_changed.emit()

    def reset_hig_settings(self):
        """The shipped defaults back."""
        self.hig_settings = hig_peaks.detection(settings.default_section(HIG_SECTION))
        settings.write_section(HIG_SECTION, dict(self.hig_settings))
        self.config_changed.emit()

    def set_threshold_override(self, enabled, value=None):
        self.threshold_overridden = bool(enabled)
        if value is not None:
            self.threshold_override = float(value)
        self.config_changed.emit()

    # ── run ──────────────────────────────────────────────────────────────────
    def run_prediction(self):
        """Launch the worker subprocess. Emits run_started immediately and
        run_finished / run_failed later on the GUI thread.

        Runs `validate()` first; a failure reports every failed check."""
        if self.running:
            return
        self.status.emit(
            "Checking model, dataset, channels, sequence length…", 3000)
        self.validate()
        if not self.ready:
            failed = [f"{label}: {detail}" if detail else label
                      for state, label, detail in self.checks if state == "fail"]
            msg = ("Prediction is not ready.\n" + "\n".join(failed)
                   if failed else
                   "Prediction is not ready - resolve the compatibility "
                   "checks first.")
            self.run_failed.emit(msg)
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
            data_path, out_dir, threshold=threshold, df_to_write=df_to_write,
            hig_peaks=self.hig_peaks, hig_settings=self.hig_settings)
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
        # class names stay text: read as numbers, classes called "2" and "3"
        # (a pump region's levels, say) would no longer match the model's own
        self.predictions = pd.read_csv(out_dir / "predictions.csv",
                                       dtype={"predicted_region": str})
        self.summary     = pd.read_csv(out_dir / "summary.csv")
        region = out_dir / "region_summary.csv"
        self.region_summary = (pd.read_csv(region, dtype={"region": str})
                               if region.exists() else None)
        sev = out_dir / "severity_summary.csv"
        self.severity_summary = pd.read_csv(sev) if sev.exists() else None
        peaks = out_dir / "hig_peaks.csv"
        self.peak_events = pd.read_csv(peaks) if peaks.exists() else None
        acc = out_dir / "acceleration_summary.csv"
        self.acc_summary = pd.read_csv(acc) if acc.exists() else None
        meta = out_dir / "run_meta.json"
        try:
            with open(meta, encoding="utf-8") as f:
                self.run_meta = json.load(f)
        except (OSError, ValueError):
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

    def collision_traces(self):
        """The HIG traces of the recordings with a collision, on the
        acceleration-centred figures' normalised time axes, one facet per
        treatment, as the prediction summary - `hig_peaks.centred_traces`.
        None without a peak analysis, or once the dataset has been
        replaced."""
        preds, df = self.predictions, self.dataset_df
        if (self.acc_summary is None or preds is None or df is None
                or "collision" not in preds.columns):
            return None
        key = (self.run_id, id(df))
        if self._traces_key != key:
            files = preds.loc[preds["collision"] == 1, "file"].tolist()
            self._traces = hig_peaks.centred_traces(df, files, "treatment")
            self._traces_key = key
        return self._traces

    # ── ground truth ─────────────────────────────────────────────────────────
    # Predictions are compared with the annotations only as the binary
    # model was trained: its own target column, holding its own "no strike"
    # value (model_labels - read from its metrics). Anything else - no
    # target column, or one without that value - is not compared rather
    # than guessed at.
    def ground_truth_column(self, df=None):
        """The model's target column, when `df` (the predictions by
        default) has it holding the model's "no strike" value; else None."""
        df = self.predictions if df is None else df
        target = model_labels.target_column(self.bin_metrics)
        negative = model_labels.negative_class(self.bin_metrics)
        if df is None or not target or negative is None \
                or target not in df.columns:
            return None
        # asked once per row by ground_truth_for: remembered per frame
        key = (id(df), len(df), target, negative)
        if getattr(self, "_gt_key", None) != key:
            values = df[target].dropna().astype(str)
            self._gt_key = key
            self._gt_column = target if (values == negative).any() else None
        return self._gt_column

    def annotation_status(self, df=None):
        """One line on whether `df` (the dataset by default) can be
        compared with the loaded model's predictions, and why not."""
        df = self.dataset_df if df is None else df
        target = model_labels.target_column(self.bin_metrics)
        negative = model_labels.negative_class(self.bin_metrics)
        if df is None:
            return "none"
        if not target:
            return "no model loaded" if not self.bin_metrics \
                else "the model doesn't record its target column"
        if target not in df.columns:
            return f"none for this model ({target})"
        if self.ground_truth_column(df) is None:
            return (f"{target} present, but not the model's no-strike value "
                    f"\"{negative}\" - not compared")
        return f"{target} - compared with the predictions"

    def ground_truth_for(self, row):
        """(gt_strike, gt_label, gt_region_class) for a predictions row.

        Returns (None, None, None) when there is nothing to compare
        (`ground_truth_column`) or this recording isn't annotated. Read the
        way the models were trained (model_labels): the binary model's own
        target column and "no strike" value, and the region model's own
        class column and level grouping for gt_region_class.
        """
        col = self.ground_truth_column()
        if row is None or col is None or col not in row.index:
            return None, None, None
        gt_type = row.get(col)
        if pd.isna(gt_type) or str(gt_type).strip() == "":
            return None, None, None
        gt_type = str(gt_type)
        gt_strike = gt_type != model_labels.negative_class(self.bin_metrics)

        gt_region_class = None
        rcol = model_labels.region_column(self.mc_metrics)
        region = row.get(rcol) if rcol else None
        if gt_strike and region is not None and pd.notna(region) \
                and self.class_names:
            gt_region_class = model_labels.region_class(
                region, self.mc_metrics, self.class_names)
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
            "annotations": self.annotation_status(),
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
