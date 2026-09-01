# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Discovery and evaluation of deployed models.

Any model in the models folder can be evaluated, not just one trained in
the current session: a deployed model is a ``<kind><version>.joblib`` with
its ``<kind><version>performance_metrics.json`` beside it (the naming
Model Prediction discovers). Where the model was deployed by the Model
Training page, the ``BladeStrikeModel_v<version>/`` package alongside it
also carries the cross-validation predictions, which unlock the error
analysis and the per-recording figures.

Shared by Model Training → Evaluate and (later) the Model Performance
page. The model report reuses the HTML helpers from ``ml_report`` rather
than duplicating them.
"""
import json
import re
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from . import ml_report, ml_train_figures

_STEM_RE = re.compile(r"^(binary|multiclass)(\d+(?:_\d+)*)$")


class ModelEntry:
    """One evaluatable model: either a session result or a deployed file."""

    def __init__(self, label, kind, metrics, cv_predictions=None,
                 curves=None, model_path=None, metrics_path=None,
                 source="session"):
        self.label = label
        self.kind = kind                    # "binary" | "multiclass"
        self.metrics = metrics
        self.cv_predictions = cv_predictions
        self.curves = curves
        self.model_path = model_path
        self.metrics_path = metrics_path
        self.source = source                # "session" | "deployed"

    @property
    def version(self):
        if self.model_path:
            m = _STEM_RE.match(Path(self.model_path).stem)
            if m:
                return m.group(2).replace("_", ".")
        return None


def roc_pr_from_scores(y_true, scores):
    """ROC and precision-recall curves from raw scores, in numpy only.

    Lets a deployed model that shipped its cross-validation predictions but
    not its curve JSON still draw ROC/PR, without importing the model stack
    into the GUI process.
    """
    y = np.asarray(y_true).astype(int)
    s = np.asarray(scores, dtype=float)
    if len(y) == 0 or len(np.unique(y)) < 2:
        return None

    order = np.argsort(-s, kind="mergesort")
    y, s = y[order], s[order]
    # one point per distinct score
    distinct = np.where(np.diff(s))[0]
    idx = np.r_[distinct, len(y) - 1]

    tp = np.cumsum(y)[idx]
    fp = np.cumsum(1 - y)[idx]
    n_pos, n_neg = tp[-1], fp[-1]
    if n_pos == 0 or n_neg == 0:
        return None

    tpr = np.r_[0.0, tp / n_pos]
    fpr = np.r_[0.0, fp / n_neg]
    thresholds = np.r_[s[idx[0]] + 1.0, s[idx]]

    precision = tp / np.maximum(tp + fp, 1)
    recall = tp / n_pos
    # sklearn orders PR from high recall to low and closes at (0, 1)
    precision = np.r_[precision[::-1], 1.0]
    recall = np.r_[recall[::-1], 0.0]

    return {
        "fpr": fpr.tolist(),
        "tpr": tpr.tolist(),
        "roc_optimal_idx": int(np.argmax(tpr - fpr)),
        "thresholds": thresholds.tolist(),
        "precision": precision.tolist(),
        "recall": recall.tolist(),
        "baseline_rate": float(y.mean()),
    }


def derive_curves(cv_predictions):
    """Curves for a binary model from its per-recording CV predictions."""
    if cv_predictions is None:
        return None
    cols = cv_predictions.columns
    if "y_true" not in cols or "probability" not in cols:
        return None
    return roc_pr_from_scores(cv_predictions["y_true"],
                              cv_predictions["probability"])


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _package_dir_for(model_path):
    """The BladeStrikeModel_v<version>/ package beside a deployed model."""
    m = _STEM_RE.match(Path(model_path).stem)
    if not m:
        return None
    pkg = Path(model_path).parent / f"BladeStrikeModel_v{m.group(2)}"
    return pkg if pkg.is_dir() else None


def discover_models(models_dir):
    """Every deployed model in `models_dir`, newest version first."""
    models_dir = Path(models_dir)
    entries = []
    if not models_dir.is_dir():
        return entries

    for path in sorted(models_dir.glob("*.joblib")):
        m = _STEM_RE.match(path.stem)
        if not m:
            continue
        kind, version = m.group(1), m.group(2)
        metrics_path = path.parent / f"{path.stem}performance_metrics.json"
        if not metrics_path.exists():
            continue
        metrics = _read_json(metrics_path)
        if metrics is None:
            continue

        # cross-validation predictions and curves, when the deployment
        # package carries them
        cv_predictions = None
        curves = None
        pkg = _package_dir_for(path)
        if pkg is not None:
            cv_path = pkg / f"{kind}_cv_predictions.csv"
            if cv_path.exists():
                try:
                    cv_predictions = pd.read_csv(cv_path)
                except Exception:
                    cv_predictions = None
            curves = _read_json(pkg / f"{kind}_cv_curves.json")
        if curves is None and kind == "binary":
            curves = derive_curves(cv_predictions)

        entries.append(ModelEntry(
            label=f"{path.stem}  (deployed {kind}, v{version.replace('_', '.')})",
            kind=kind, metrics=metrics, cv_predictions=cv_predictions,
            curves=curves, model_path=path, metrics_path=metrics_path,
            source="deployed"))

    entries.sort(key=lambda e: (e.kind, e.model_path.stem), reverse=True)
    return entries


def session_entries(state):
    """Evaluatable entries for the models trained in this session."""
    out = []
    for kind in ("binary", "multiclass"):
        res = state.model_results(kind)
        if not res:
            continue
        out.append(ModelEntry(
            label=f"This session - {kind} model",
            kind=kind, metrics=res["metrics"],
            cv_predictions=res["cv_predictions"], curves=res["curves"],
            source="session"))
    return out


# ── model report ─────────────────────────────────────────────────────────────
def build_model_report_html(entry, image_paths=None, embed_images=False,
                            app_version=""):
    """Model evaluation report for one model, in the report style used by
    Model Prediction (helpers reused from ml_report)."""
    from datetime import datetime

    esc, kv, table = ml_report._esc, ml_report._kv_table, ml_report._data_table
    dark = ml_report._DARK
    m = entry.metrics or {}
    perf = m.get("out_of_fold_performance", {})
    tr = m.get("training", {})
    na = "Not available"
    image_paths = image_paths or {}

    h = ["<div style='font-family:Segoe UI, Arial, sans-serif;"
         "color:#1e293b;font-size:13px;'>"]
    h.append(f"<h1 style='color:{dark};'>Model Evaluation Report</h1>")
    h.append(f"<h2 style='color:{dark};'>Model</h2>")
    rows = [
        ("Model", m.get("model", na)),
        ("Stage", "Binary (strike / no contact)" if entry.kind == "binary"
                  else "Multiclass (strike region)"),
        ("Source", "Trained in this session" if entry.source == "session"
                   else f"Deployed model: {Path(entry.model_path).name}"),
        ("Version", entry.version or na),
        ("Training observations", m.get("n_samples", na)),
        ("Input channels", ", ".join(m.get("channels", [])) or na),
        ("Sequence length", f"{m.get('max_sequence_length', na)} samples"),
    ]
    if m.get("class_names"):
        rows.append(("Classes", ", ".join(m["class_names"])))
    if tr:
        rows += [
            ("Training dataset", tr.get("dataset_name", na)),
            ("Trained", tr.get("timestamp", na)),
            ("Class weighting", tr.get("class_weighting", na)),
            ("Random seed", tr.get("random_seed", na)),
        ]
    h.append(kv(rows))

    # ── performance ──────────────────────────────────────────────────────────
    h.append(f"<h2 style='color:{dark};'>Out-of-fold performance</h2>")
    labels = {"roc_auc": "ROC-AUC", "pr_auc": "PR-AUC",
              "overall_accuracy": "Accuracy", "sensitivity": "Sensitivity",
              "specificity": "Specificity", "precision": "Precision",
              "f1_score": "F1-score", "mcc": "MCC", "FNR": "FNR",
              "FPR": "FPR", "optimal_threshold": "Optimal threshold",
              "macro_precision": "Macro precision",
              "macro_recall": "Macro recall", "macro_f1": "Macro F1"}
    rows = [(labels[k], f"{perf[k]:.4f}") for k in labels if k in perf]
    h.append(kv(rows) if rows else f"<p style='color:#64748b;'>{na}</p>")

    ho = m.get("holdout_performance")
    if ho:
        h.append(f"<h3 style='color:{dark};'>Hold-out test set</h3>")
        h.append(kv([(k.replace("_", " "),
                      f"{v:.4f}" if isinstance(v, float) else v)
                     for k, v in ho.items()]))

    # ── cross-validation ─────────────────────────────────────────────────────
    cv = m.get("cross_validation", {})
    if cv:
        h.append(f"<h2 style='color:{dark};'>Cross-validation</h2>")
        keys = sorted(k[5:] for k in cv if k.startswith("mean_"))
        rows = [[k, f"{cv[f'mean_{k}']:.4f}", f"{cv.get(f'std_{k}', 0):.4f}"]
                for k in keys]
        h.append(f"<p>{cv.get('n_folds', '?')}-fold stratified "
                 "cross-validation.</p>")
        h.append(table(["Metric", "Mean", "SD"], rows))

    # ── per-class / confusion ────────────────────────────────────────────────
    per_class = perf.get("per_class_metrics")
    if per_class:
        h.append(f"<h2 style='color:{dark};'>Per-class performance</h2>")
        rows = [[cn, f"{d['precision']:.3f}", f"{d['recall']:.3f}",
                 f"{d['f1_score']:.3f}", d["support"]]
                for cn, d in per_class.items()]
        h.append(table(["Class", "Precision", "Recall", "F1", "Support"],
                       rows))

    cm = perf.get("confusion_matrix")
    if isinstance(cm, dict):
        h.append(f"<h2 style='color:{dark};'>Confusion matrix</h2>")
        h.append(table(["", "Predicted no strike", "Predicted strike"],
                       [["True no strike", cm["tn"], cm["fp"]],
                        ["True strike", cm["fn"], cm["tp"]]]))
    elif isinstance(cm, list) and m.get("class_names"):
        names = m["class_names"]
        h.append(f"<h2 style='color:{dark};'>Confusion matrix</h2>")
        h.append(table([""] + [f"Pred {n}" for n in names],
                       [[f"True {names[i]}"] + list(row)
                        for i, row in enumerate(cm)]))

    by_type = m.get("performance_by_strike_type")
    if by_type:
        h.append(f"<h2 style='color:{dark};'>Performance by strike type</h2>")
        h.append(table(["Strike type", "N", "Accuracy"],
                       [[st, d["n_files"], f"{d['accuracy']:.3f}"]
                        for st, d in by_type.items()]))

    # ── error analysis ───────────────────────────────────────────────────────
    mis = m.get("misclassified", {})
    if mis:
        h.append(f"<h2 style='color:{dark};'>Error analysis</h2>")
        h.append(kv([(k.replace("_", " "), v) for k, v in mis.items()
                     if not isinstance(v, dict)]))
        if isinstance(mis.get("by_true_class"), dict):
            h.append(table(["True class", "Misclassified"],
                           list(mis["by_true_class"].items())))

    # ── figures ──────────────────────────────────────────────────────────────
    if image_paths:
        h.append(f"<h2 style='color:{dark};'>Figures</h2>")
        for path in image_paths.values():
            h.append(ml_report._img_tag(path, embed_images))

    # ── provenance ───────────────────────────────────────────────────────────
    h.append(f"<h2 style='color:{dark};'>Provenance</h2>")
    rows = []
    for k, v in (tr or {}).items():
        if isinstance(v, dict):
            v = ", ".join(f"{a} {b}" for a, b in v.items())
        elif isinstance(v, list):
            v = ", ".join(str(x) for x in v)
        rows.append((k.replace("_", " "), v if v not in (None, "") else na))
    if entry.metrics_path:
        rows.append(("metrics file", str(entry.metrics_path)))
    h.append(kv(rows) if rows else f"<p style='color:#64748b;'>{na}</p>")

    h.append(f"<p style='color:#64748b;font-size:11px;margin-top:16px;'>"
             f"Generated by StrikeWorks {esc(app_version)} on "
             f"{datetime.now().strftime('%Y-%m-%d %H:%M')}.</p>")
    h.append("</div>")
    return "".join(h)


def export_model_report(entry, target_dir, app_version=""):
    """Write report.html + figures + metrics for one model. Returns the dir."""
    target_dir = Path(target_dir)
    name = (Path(entry.model_path).stem if entry.model_path
            else f"session_{entry.kind}")
    out = target_dir / f"ModelReport_{name}"
    out.mkdir(parents=True, exist_ok=True)

    figs = ml_train_figures.render_model_figures(
        out, entry.metrics, entry.cv_predictions, entry.curves,
        formats=("png",))
    if entry.metrics is not None:
        with open(out / "performance_metrics.json", "w",
                  encoding="utf-8") as f:
            json.dump(entry.metrics, f, indent=2)
    if entry.curves is not None:
        with open(out / "cv_curves.json", "w", encoding="utf-8") as f:
            json.dump(entry.curves, f)

    df = entry.cv_predictions
    if df is not None:
        df.to_csv(out / "cv_predictions.csv", index=False)

        # the misclassifications are the actionable part of the report
        if "error_type" in df.columns:
            mis = df[df["error_type"] != "correct"]
        elif "correct" in df.columns:
            mis = df[~df["correct"].astype(bool)]
        else:
            mis = None
        if mis is not None:
            mis.to_csv(out / "misclassified_files_for_review.csv",
                       index=False)

        # per-treatment summary, for reporting alongside the figures
        if "treatment" in df.columns and "correct" in df.columns:
            agg = {"n": ("correct", "size"), "accuracy": ("correct", "mean")}
            if "y_true" in df.columns and "y_pred" in df.columns:
                agg["true_strike_rate"] = ("y_true", "mean")
                agg["predicted_strike_rate"] = ("y_pred", "mean")
            (df.groupby("treatment").agg(**agg).round(4)
               .to_csv(out / "performance_by_treatment.csv"))

    # anything else the deployment package carries for this model
    if entry.model_path is not None:
        pkg = _package_dir_for(entry.model_path)
        if pkg is not None:
            for extra in ("model_card.json", "train_config.json",
                          f"{entry.kind}_model_config.json"):
                src = pkg / extra
                if src.exists():
                    shutil.copy(src, out / extra)

    body = build_model_report_html(entry, image_paths=figs,
                                   embed_images=True,
                                   app_version=app_version)
    (out / "report.html").write_text(ml_report.wrap_html_document(body),
                                     encoding="utf-8")
    return out
