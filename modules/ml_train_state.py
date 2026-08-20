# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Central training state shared by the Model Training tabs.

One TrainingState instance is owned by the Model Training page controller;
the Configure / Cross-validate / Evaluate / Deploy tabs read from it and
react to its signals. It builds the JSON configuration for
``modules/train_worker.py``, streams the worker's console output, loads the
cross-validation results, and performs the final-model deployment step.

Training follows the deployed prediction pipeline: a binary strike model is
always trained, and (when the dataset carries pump-region labels) the
multiclass region model for predicted strikes is trained alongside it in
the same run. Results are held per model in ``self.results``.

The scientific workflow is enforced here: cross-validation first, then an
explicit user decision, then the final deployment models, then deployment.
"""
import json
import re
import shutil
import subprocess
import sys
from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from PySide6.QtCore import QObject, QThread, Signal

from . import settings

_WORKER = Path(__file__).parent / "train_worker.py"
_APP_ROOT = Path(__file__).parent.parent
_RUNS_DIR = _APP_ROOT / "training_runs"
DEFAULT_MODELS_DIR = _APP_ROOT / "models"

MODEL_KINDS = ("binary", "multiclass")

# canonical model input channels (the deployed models' channel set)
DEFAULT_CHANNELS = [
    "higacc_x_g", "higacc_y_g", "higacc_z_g",
    "inacc_x_ms", "inacc_y_ms", "inacc_z_ms",
    "rot_x_degs", "rot_y_degs", "rot_z_degs",
    "pressure_kpa",
]

# collapse schemes ported from 05_multiclass_collapsed.py
COLLAPSE_SCHEMES = {
    "model_1_1": {
        "desc":            "region_1 | region_2+3 | region_4+5",
        "region_to_class": {1: 0, 2: 1, 3: 1, 4: 2, 5: 2},
        "class_names":     ["region_1", "region_2_3", "region_4_5"],
    },
    "model_1_2": {
        "desc":            "region_1 | region_2+3+4+5",
        "region_to_class": {1: 0, 2: 1, 3: 1, 4: 1, 5: 1},
        "class_names":     ["region_1", "region_2_5"],
    },
}

# preferred target columns, in order
_TARGET_PREFERENCE = ["passage_type", "overall_passage_type"]
_NON_TARGET_COLS = {"file", "deployment_id", "run", "time_s"}
_NON_CHANNEL_COLS = {"time_s", "run", "concentric_pump_region"}


class _StreamThread(QThread):
    """Runs the training worker subprocess and streams stdout lines."""

    line = Signal(str)
    done = Signal(int, str)   # returncode, tail of output

    def __init__(self, cmd):
        super().__init__()
        self._cmd = cmd

    def run(self):
        try:
            proc = subprocess.Popen(
                self._cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1)
            tail = deque(maxlen=60)
            for raw in proc.stdout:
                ln = raw.rstrip("\n")
                tail.append(ln)
                self.line.emit(ln)
            proc.wait()
            self.done.emit(proc.returncode, "\n".join(tail))
        except Exception as e:
            self.done.emit(-1, str(e))


# ═════════════════════════════════════════════════════════════════════════════
class TrainingState(QObject):
    """Everything the Configure / Cross-validate / Evaluate / Deploy tabs share."""

    dataset_changed    = Signal()
    config_changed     = Signal()
    validation_changed = Signal()
    cv_started         = Signal()
    cv_line            = Signal(str)
    cv_progress        = Signal(int, int, str)   # fold, total, model kind
    cv_finished        = Signal()
    cv_failed          = Signal(str)
    final_started      = Signal()
    final_finished     = Signal()
    final_failed       = Signal(str)
    deployed           = Signal(str)             # deployed binary model path
    status             = Signal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)

        # dataset
        self.dataset_df = None
        self.dataset_path = None
        self.dataset_meta = {}

        # labels / target - the binary stage defines strike vs no-contact;
        # the multiclass stage classifies ground-truth strikes by region
        self.target_column = None
        self.negative_class = None
        self.include_values = None           # None = all values included
        self.train_multiclass = True         # stage 2 on/off
        self.region_column = None
        self.collapse_scheme = "model_1_1"
        self.include_surface = False

        # variables
        self.channels = list(DEFAULT_CHANNELS)
        self.seq_auto = True
        self.seq_length = 400

        # validation config
        self.split_mode = "cv_only"          # "cv_only" | "holdout_cv"
        self.test_size = 0.20
        self.n_folds = 10
        self.shuffle = True
        self.random_seed = 42

        # class balancing + model
        self.class_weighting = "balanced"    # "balanced" | "none"
        self.mr_seed = 42
        self.mr_n_jobs = -1
        self.alpha_min_exp = -3
        self.alpha_max_exp = 3
        self.n_alphas = 100

        # run/output
        self.out_dir = None                  # set when a run starts
        self.running = False
        self.stage = None                    # "cv" | "final" while running
        self._current_model = "binary"       # parsed from ##MODEL markers

        # results, per pipeline stage:
        # {"binary": {"metrics":…, "cv_predictions":…, "curves":…}, …}
        self.results = {}
        self.cv_done = False
        self.final_done = False
        self.deployed_path = None
        self.deploy_version = None

        # readiness
        self.checks = []
        self.ready = False

        self.app_version = ""
        self._thread = None

    # ── result access ────────────────────────────────────────────────────────
    def model_results(self, kind):
        """{"metrics", "cv_predictions", "curves"} for one stage, or None."""
        return self.results.get(kind)

    def trained_kinds(self):
        return [k for k in MODEL_KINDS if k in self.results]

    # ── dataset ──────────────────────────────────────────────────────────────
    def load_dataset_csv(self, path):
        """Load a training dataset CSV. Returns (ok, message)."""
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

        self.dataset_df = df
        self.dataset_path = path
        settings.add_recent_training_dataset(path)

        self._autodetect_columns()
        self.dataset_meta = self._compute_meta()
        # a fresh dataset invalidates any previous run
        self._reset_results()
        self.dataset_changed.emit()
        self.config_changed.emit()
        self.validate()
        return True, f"Training dataset loaded: {path.name}"

    def _reset_results(self):
        self.results = {}
        self.cv_done = False
        self.final_done = False
        self.deployed_path = None
        self.deploy_version = None
        self.out_dir = None

    def _autodetect_columns(self):
        df = self.dataset_df
        cands = self.target_candidates()
        if self.target_column not in cands:
            self.target_column = None
        if self.target_column is None:
            for pref in _TARGET_PREFERENCE:
                if pref in cands:
                    self.target_column = pref
                    break
            if self.target_column is None and cands:
                self.target_column = cands[0]

        self.include_values = None
        self._autodetect_negative()

        self.region_column = next(
            (c for c in df.columns if "region" in c.lower()), None)
        # the full pipeline (binary + region model) is the default whenever
        # the dataset can support it
        self.train_multiclass = self.region_column is not None

        # keep only channels that exist; fall back to the canonical defaults
        present = [c for c in self.channels if c in df.columns]
        if not present:
            present = [c for c in DEFAULT_CHANNELS if c in df.columns]
        self.channels = present

    def _autodetect_negative(self):
        vals = self.target_values()
        self.negative_class = next(
            (v for v in vals
             if "no" in v.lower() and "contact" in v.lower()),
            vals[0] if vals else None)

    def target_candidates(self):
        """Categorical columns that could define the target."""
        df = self.dataset_df
        if df is None:
            return []
        per_file = df.groupby("file").first()
        out = []
        for col in per_file.columns:
            if col in _NON_TARGET_COLS or col == "treatment":
                continue
            series = per_file[col]
            if series.dtype == object and 2 <= series.dropna().nunique() <= 15:
                out.append(col)
        # preferred names first
        out.sort(key=lambda c: (c not in _TARGET_PREFERENCE, c))
        return out

    def target_values(self):
        """Distinct file-level values of the target column."""
        df = self.dataset_df
        if df is None or not self.target_column \
                or self.target_column not in df.columns:
            return []
        vals = (df.groupby("file")[self.target_column].first()
                .dropna().astype(str).unique().tolist())
        return sorted(vals)

    def leading_type_column(self):
        df = self.dataset_df
        if df is None:
            return None
        for c in ("leading_type", "leading_edge_type"):
            if c in df.columns:
                return c
        return None

    def other_type_column(self):
        df = self.dataset_df
        return "other_type" if df is not None \
            and "other_type" in df.columns else None

    def channel_candidates(self):
        """Numeric sensor columns usable as model input channels."""
        df = self.dataset_df
        if df is None:
            return []
        out = []
        for col in df.columns:
            if col in _NON_CHANNEL_COLS or col in _NON_TARGET_COLS:
                continue
            if pd.api.types.is_numeric_dtype(df[col]):
                out.append(col)
        # canonical channels first, in canonical order
        canonical = [c for c in DEFAULT_CHANNELS if c in out]
        extra = [c for c in out if c not in DEFAULT_CHANNELS]
        return canonical + extra

    def _compute_meta(self):
        df = self.dataset_df
        if df is None:
            return {}
        meta = {"name": self.dataset_path.name if self.dataset_path else "—"}
        per_file = df.groupby("file").size()
        meta["n_files"] = int(per_file.shape[0])
        meta["n_rows"] = int(len(df))
        meta["seq_min"] = int(per_file.min())
        meta["seq_max"] = int(per_file.max())
        if "treatment" in df.columns:
            meta["treatments"] = sorted(
                df["treatment"].dropna().astype(str).unique().tolist())
        first = df[df["file"] == df["file"].iloc[0]]["time_s"]
        dt = first.diff().median()
        if pd.notna(dt) and dt > 0:
            meta["sampling_rate_hz"] = round(1.0 / float(dt))
        chan = [c for c in self.channel_candidates()]
        meta["n_channel_candidates"] = len(chan)
        meta["missing_in_channels"] = int(
            df[self.channels].isna().sum().sum()) if self.channels else 0
        return meta

    # ── population / class distributions ─────────────────────────────────────
    def file_targets(self):
        """file-level Series of the target column after the inclusion filter."""
        df = self.dataset_df
        if df is None or not self.target_column:
            return None
        s = df.groupby("file")[self.target_column].first().dropna().astype(str)
        if self.include_values is not None:
            s = s[s.isin([str(v) for v in self.include_values])]
        return s

    def binary_class_counts(self):
        """[(class label, count)] for the binary strike target."""
        s = self.file_targets()
        if s is None or s.empty or self.negative_class is None:
            return []
        neg = str(self.negative_class)
        n_neg = int((s == neg).sum())
        n_pos = int((s != neg).sum())
        return [(neg, n_neg), ("blade_strike (all others)", n_pos)]

    def region_class_counts(self):
        """[(collapsed class, count)] for the multiclass region target."""
        df = self.dataset_df
        if (df is None or self.region_column is None
                or self.region_column not in df.columns
                or not self.target_column):
            return []
        scheme = COLLAPSE_SCHEMES[self.collapse_scheme]
        per_file = df.groupby("file").agg(
            {self.target_column: "first", self.region_column: "first"})
        per_file = per_file[per_file[self.target_column].notna()]
        per_file = per_file[per_file[self.target_column].astype(str)
                            != str(self.negative_class)]
        if self.include_values is not None:
            per_file = per_file[per_file[self.target_column].astype(str)
                                .isin([str(v) for v in self.include_values])]
        regions = pd.to_numeric(per_file[self.region_column],
                                errors="coerce").dropna().astype(int)
        counts = {cn: 0 for cn in scheme["class_names"]}
        for r in regions:
            idx = scheme["region_to_class"].get(int(r))
            if idx is not None:
                counts[scheme["class_names"][idx]] += 1
        return list(counts.items())

    def population_size(self):
        s = self.file_targets()
        return 0 if s is None else int(len(s))

    # ── config mutation helpers (all emit config_changed + revalidate) ───────
    def update(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
        if "target_column" in kw:
            self.include_values = None
            self._autodetect_negative()
        self.config_changed.emit()
        self.validate()

    # ── readiness validation (pre-training validation) ───────────────────────
    def validate(self):
        checks = []
        hard_fail = False

        def add(state, label, detail=""):
            nonlocal hard_fail
            if state == "fail":
                hard_fail = True
            checks.append((state, label, detail))

        df = self.dataset_df
        if df is None:
            add("fail", "Training dataset", "Load a training dataset CSV.")
            self.checks = checks
            self.ready = False
            self.validation_changed.emit()
            return

        add("ok", "Training dataset",
            f"{self.dataset_meta.get('n_files')} unique recordings")

        if not self.channels:
            add("fail", "Input channels", "Select at least one channel.")
        else:
            miss = int(df[self.channels].isna().sum().sum())
            if miss:
                add("fail", "No missing values",
                    f"{miss} missing values in the selected channels.")
            else:
                add("ok", "Input channels",
                    f"{len(self.channels)} channels, no missing values")

        seq = self.seq_length if not self.seq_auto \
            else self.dataset_meta.get("seq_max")
        add("ok", "Sequence length",
            f"{seq} samples ({'auto' if self.seq_auto else 'manual'})")

        # ---- stage 1: binary target ----
        counts = self.binary_class_counts()
        if not self.target_column:
            add("fail", "Binary target", "Choose a target column.")
        elif not counts or len([c for _, c in counts if c > 0]) < 2:
            add("fail", "Binary target",
                "The current target definition yields fewer than two classes.")
        else:
            desc = ", ".join(f"{c} {lab}" for lab, c in counts)
            add("ok", "Binary target", f"Strike vs no-contact: {desc}")
            min_class = min(c for _, c in counts)
            if min_class < self.n_folds:
                add("fail", "Binary cross-validation",
                    f"Smallest class has {min_class} recordings - fewer than "
                    f"{self.n_folds} folds.")
            counts_only = [c for _, c in counts if c > 0]
            if max(counts_only) / max(1, min(counts_only)) > 3:
                add("warn", "Class balance",
                    "Binary classes are imbalanced (>3:1). "
                    + ("Balanced class weights are enabled."
                       if self.class_weighting == "balanced"
                       else "Consider enabling balanced class weights."))

        # ---- stage 2: multiclass region target ----
        if self.train_multiclass:
            if self.region_column is None or self.region_column not in df.columns:
                add("fail", "Region model",
                    "The multiclass stage needs a pump-region column "
                    "(e.g. concentric_pump_region).")
            else:
                mc_counts = self.region_class_counts()
                nonzero = [c for _, c in mc_counts if c > 0]
                if len(nonzero) < 2:
                    add("fail", "Region model",
                        "Fewer than two region classes among strike "
                        "recordings.")
                else:
                    desc = ", ".join(f"{c} {lab}" for lab, c in mc_counts)
                    add("ok", "Region model",
                        f"{len(nonzero)}-class ({desc})")
                    if min(nonzero) < self.n_folds:
                        add("fail", "Region cross-validation",
                            f"Smallest region class has {min(nonzero)} "
                            f"recordings - fewer than {self.n_folds} folds.")
        else:
            add("warn", "Region model",
                "Stage 2 disabled - only the binary model will be trained. "
                "Prediction will run in single-class mode.")

        add("ok", "Cross-validation",
            f"{self.n_folds}-fold stratified CV, seed {self.random_seed}"
            + (f", {self.test_size:.0%} hold-out test set"
               if self.split_mode == "holdout_cv" else ""))
        add("ok", "Model",
            f"MiniRocket + RidgeClassifierCV, "
            f"{'balanced' if self.class_weighting == 'balanced' else 'no'} "
            f"class weighting")

        self.checks = checks
        self.ready = not hard_fail and not self.running
        self.validation_changed.emit()

    # ── worker configuration ─────────────────────────────────────────────────
    def build_config(self):
        cfg = {
            "data": str(self.dataset_path),
            "out_dir": str(self.out_dir),
            "target_column": self.target_column,
            "negative_class": self.negative_class,
            "positive_label": "blade_strike",
            "leading_type_column": self.leading_type_column(),
            "other_type_column": self.other_type_column(),
            "include_values": (sorted(self.include_values)
                               if self.include_values is not None else None),
            "channels": list(self.channels),
            "seq_length": None if self.seq_auto else int(self.seq_length),
            "padding": "repeat_last",
            "truncation": "truncate",
            "class_weighting": self.class_weighting,
            "split_mode": self.split_mode,
            "test_size": float(self.test_size),
            "n_folds": int(self.n_folds),
            "shuffle": bool(self.shuffle),
            "random_seed": int(self.random_seed),
            "minirocket": {"random_state": int(self.mr_seed),
                           "n_jobs": int(self.mr_n_jobs)},
            "ridge": {"alpha_min_exp": int(self.alpha_min_exp),
                      "alpha_max_exp": int(self.alpha_max_exp),
                      "n_alphas": int(self.n_alphas)},
            "app_version": self.app_version,
            "train_multiclass": bool(self.train_multiclass),
        }
        if self.train_multiclass:
            scheme = COLLAPSE_SCHEMES[self.collapse_scheme]
            cfg.update({
                "region_column": self.region_column,
                "collapse_scheme": self.collapse_scheme,
                "collapse_desc": scheme["desc"],
                "region_to_class": {str(k): v for k, v
                                    in scheme["region_to_class"].items()},
                "class_names": list(scheme["class_names"]),
                "include_surface_as_region1": bool(self.include_surface),
            })
        return cfg

    # ── run stages ───────────────────────────────────────────────────────────
    def _launch(self, stage):
        cfg_path = self.out_dir / "train_config.json"
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(self.build_config(), f, indent=2)
        cmd = [sys.executable, str(_WORKER),
               "--config", str(cfg_path), "--stage", stage]
        self._thread = _StreamThread(cmd)
        self._thread.line.connect(self._on_line)
        self._thread.done.connect(self._on_done)
        self.running = True
        self.stage = stage
        self._current_model = "binary"
        self.validate()
        self._thread.start()

    def run_cv(self):
        if self.running:
            return
        self.validate()
        if not self.ready:
            self.cv_failed.emit("Configuration is not ready - resolve the "
                                "checks on the Configure tab first.")
            return
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.out_dir = _RUNS_DIR / f"pipeline_{run_id}"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.results = {}
        self.cv_done = False
        self.final_done = False
        self.deployed_path = None
        self.deploy_version = None
        self.cv_started.emit()
        self._launch("cv")

    def run_final(self):
        if self.running or not self.cv_done or self.out_dir is None:
            return
        self.final_started.emit()
        self._launch("final")

    def _on_line(self, ln):
        if ln.startswith("##MODEL "):
            self._current_model = ln.split()[1]
            return
        if ln.startswith("##FOLD "):
            try:
                _, k, n = ln.split()
                self.cv_progress.emit(int(k), int(n), self._current_model)
            except ValueError:
                pass
            return
        if ln.startswith("##STAGE ") or ln.startswith("##DONE"):
            return
        self.cv_line.emit(ln)

    def _on_done(self, rc, tail):
        stage = self.stage
        self.running = False
        self.stage = None
        if rc != 0:
            self.validate()
            if stage == "cv":
                self.cv_failed.emit(tail or "Training worker exited non-zero")
            else:
                self.final_failed.emit(tail or "Worker exited non-zero")
            return
        try:
            if stage == "cv":
                self._load_cv_results()
                self.cv_done = True
                self.validate()
                self.cv_finished.emit()
            else:
                self.final_done = True
                self.validate()
                self.final_finished.emit()
        except Exception as e:
            self.validate()
            (self.cv_failed if stage == "cv" else self.final_failed).emit(
                f"Reading results failed: {e}")

    def _load_cv_results(self):
        self.results = {}
        for kind in MODEL_KINDS:
            d = self.out_dir / kind
            metrics_path = d / "performance_metrics.json"
            if not metrics_path.exists():
                continue
            with open(metrics_path, encoding="utf-8") as f:
                metrics = json.load(f)
            entry = {"metrics": metrics,
                     "cv_predictions": pd.read_csv(d / "cv_predictions.csv"),
                     "curves": None}
            curves = d / "cv_curves.json"
            if curves.exists():
                with open(curves, encoding="utf-8") as f:
                    entry["curves"] = json.load(f)
            self.results[kind] = entry

    # ── deployment ───────────────────────────────────────────────────────────
    def suggest_version(self, models_dir=DEFAULT_MODELS_DIR):
        """Next free <major>_<minor> shared by both pipeline models."""
        best = (1, 0)
        try:
            for prefix in MODEL_KINDS:
                for p in Path(models_dir).glob(f"{prefix}*.joblib"):
                    m = re.match(rf"{prefix}(\d+)_(\d+)$", p.stem)
                    if m:
                        v = (int(m.group(1)), int(m.group(2)))
                        if v >= best:
                            best = (v[0], v[1] + 1)
        except OSError:
            pass
        return f"{best[0]}_{best[1]}"

    def model_card(self):
        """Pipeline provenance card. Built from real values only."""
        na = "Not available"
        bin_m = (self.model_results("binary") or {}).get("metrics", {})
        mc_m = (self.model_results("multiclass") or {}).get("metrics", {})
        tr = bin_m.get("training", {})
        card = {
            "model_id": (f"pipeline {self.deploy_version}"
                         if self.deploy_version else na),
            "pipeline": ("binary + multiclass"
                         if mc_m else "binary only"),
            "binary_model": bin_m.get("model", na),
            "multiclass_model": mc_m.get("model") if mc_m else None,
            "training_dataset": tr.get("dataset", na),
            "trained": tr.get("timestamp", na),
            "application": tr.get("application", na) or na,
            "python_version": tr.get("python_version", na),
            "package_versions": tr.get("package_versions", na),
            "target_column": tr.get("target_column", na),
            "negative_class": tr.get("negative_class", na),
            "include_values": tr.get("include_values") or "all",
            "region_column": self.region_column if mc_m else None,
            "collapse_scheme": mc_m.get("scheme") if mc_m else None,
            "class_names": mc_m.get("class_names") if mc_m else None,
            "input_channels": bin_m.get("channels", na),
            "sequence_length": bin_m.get("max_sequence_length", na),
            "padding": tr.get("padding", na),
            "class_weighting": tr.get("class_weighting", na),
            "cv_method": "Stratified K-Fold",
            "n_folds": bin_m.get("cross_validation", {}).get("n_folds", na),
            "random_seed": tr.get("random_seed", na),
            "split_mode": tr.get("split_mode", na),
            "test_size": tr.get("test_size"),
            "minirocket": tr.get("minirocket", na),
            "ridge": tr.get("ridge", na),
            "threshold_selection": "Youden's J on out-of-fold ROC",
            "binary_performance": bin_m.get("out_of_fold_performance", na),
            "multiclass_performance": (mc_m.get("out_of_fold_performance")
                                       if mc_m else None),
            "binary_holdout": bin_m.get("holdout_performance"),
            "multiclass_holdout": (mc_m.get("holdout_performance")
                                   if mc_m else None),
        }
        return card

    def deploy(self, models_dir, version):
        """Copy the final pipeline models + metrics into the models folder
        (with the binary*/multiclass* naming Model Prediction discovers)
        and build the full deployment package folder.

        Returns (package_dir, [deployed model paths])."""
        if not self.final_done or self.out_dir is None:
            raise RuntimeError("Train the final models first.")
        models_dir = Path(models_dir)
        models_dir.mkdir(parents=True, exist_ok=True)

        kinds = [k for k in MODEL_KINDS
                 if (self.out_dir / k /
                     "final_model_for_deployment.joblib").exists()]
        if "binary" not in kinds:
            raise RuntimeError("No final binary model found in the run "
                               "outputs.")

        # refuse before writing anything so a clash leaves no partial deploy
        for kind in kinds:
            dst = models_dir / f"{kind}{version}.joblib"
            if dst.exists():
                raise FileExistsError(f"{dst.name} already exists - "
                                      "choose another version.")

        self.deploy_version = version
        deployed = []
        for kind in kinds:
            stem = f"{kind}{version}"
            src = self.out_dir / kind
            model_dst = models_dir / f"{stem}.joblib"
            shutil.copy(src / "final_model_for_deployment.joblib", model_dst)
            shutil.copy(src / "performance_metrics.json",
                        models_dir / f"{stem}performance_metrics.json")
            deployed.append(model_dst)

        # full self-describing package
        pkg = models_dir / f"BladeStrikeModel_v{version}"
        pkg.mkdir(parents=True, exist_ok=True)
        for kind in kinds:
            src = self.out_dir / kind
            for name, dst_name in [
                    ("final_model_for_deployment.joblib",
                     f"{kind}_model.joblib"),
                    ("performance_metrics.json",
                     f"{kind}_performance_metrics.json"),
                    ("model_config.json", f"{kind}_model_config.json"),
                    ("cv_predictions.csv", f"{kind}_cv_predictions.csv")]:
                s = src / name
                if s.exists():
                    shutil.copy(s, pkg / dst_name)
        for name in ("channels.json", "max_sequence_length.npy"):
            s = self.out_dir / "binary" / name
            if s.exists():
                shutil.copy(s, pkg / name)
        s = self.out_dir / "train_config.json"
        if s.exists():
            shutil.copy(s, pkg / "train_config.json")
        with open(pkg / "model_card.json", "w", encoding="utf-8") as f:
            json.dump(self.model_card(), f, indent=2, default=str)
        (pkg / "README.md").write_text(self._readme(version, kinds),
                                       encoding="utf-8")

        self.deployed_path = deployed[0]
        self.deployed.emit(str(deployed[0]))
        return pkg, deployed

    def _readme(self, version, kinds):
        bin_m = (self.model_results("binary") or {}).get("metrics", {})
        mc_m = (self.model_results("multiclass") or {}).get("metrics", {})
        tr = bin_m.get("training", {})
        lines = [
            f"# Blade strike model pipeline: v{version}",
            "",
            "Two-stage prediction pipeline: the binary model detects "
            "strike vs no-contact; the multiclass model assigns a pump "
            "region to each predicted strike.",
            "",
            f"- **Trained:** {tr.get('timestamp', '?')} with "
            f"{tr.get('application') or 'StrikeWorks'}",
            f"- **Training dataset:** {tr.get('dataset', '?')}",
            f"- **Channels:** {', '.join(bin_m.get('channels', []))}",
            f"- **Sequence length:** "
            f"{bin_m.get('max_sequence_length', '?')} samples",
        ]
        for kind, m in (("binary", bin_m), ("multiclass", mc_m)):
            if kind not in kinds or not m:
                continue
            perf = m.get("out_of_fold_performance", {})
            lines += ["", f"## {kind.capitalize()} model "
                          f"({m.get('n_samples', '?')} observations)", ""]
            for k, v in perf.items():
                if isinstance(v, float):
                    lines.append(f"- {k}: {v:.4f}")
                elif isinstance(v, int):
                    lines.append(f"- {k}: {v}")
        lines += [
            "",
            "Full provenance: `model_card.json` / `train_config.json`.",
            "The models are also deployed beside this folder as "
            + " and ".join(f"`{k}{version}.joblib`" for k in kinds)
            + " for auto-discovery by Model Prediction.",
        ]
        return "\n".join(lines) + "\n"
