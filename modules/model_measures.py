# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""The measures a trained model is described by, under one set of names
everywhere - Model training's cards, Evaluate, the figures, the model and
prediction reports, Predict's Model card. The multiclass model's are the
binary model's counterparts, averaged over its classes (each class
against the rest); it has no decision threshold - the class with the
highest score is its prediction.

Also the two tables Evaluate and the model report share: the summary
(out-of-fold, cross-validation, hold-out) and the per-class one.
"""
import numpy as np

# (name, the binary model's key, the multiclass model's) in a metrics
# file's out_of_fold_performance, grouped as the summary table heads them
GROUPS = (
    ("Discrimination", (("ROC AUC", "roc_auc", "macro_roc_auc"),
                        ("PR AUC", "pr_auc", "macro_pr_auc"))),
    ("Classification", (("Accuracy", "overall_accuracy", "overall_accuracy"),
                        ("Sensitivity", "sensitivity", "macro_recall"),
                        ("Specificity", "specificity", "macro_specificity"),
                        ("Precision", "precision", "macro_precision"),
                        ("F1 score", "f1_score", "macro_f1"),
                        ("MCC", "mcc", "mcc"))),
)
MEASURES = tuple(m for _group, measures in GROUPS for m in measures)
THRESHOLD = "Decision threshold"
AVERAGED_NOTE = ("For a multiclass model, sensitivity, specificity, "
                 "precision, F1 score and the AUCs are averaged over its "
                 "classes, each class against the rest.")

# the per-fold (cross_validation's mean_/std_) and hold-out names, where
# they differ from the out-of-fold ones
_CV_KEYS = {"roc_auc": "auc", "overall_accuracy": "accuracy", "f1_score": "f1"}
_HOLDOUT_KEYS = {"overall_accuracy": "accuracy"}

BINARY_CLASSES = ("No strike", "Strike")


def is_binary(metrics):
    return "roc_auc" in (metrics or {}).get("out_of_fold_performance", {})


def _key(metrics, name):
    for label, bin_key, mc_key in MEASURES:
        if label == name:
            return bin_key if is_binary(metrics) else mc_key
    return None


def value(metrics, name):
    """A model's out-of-fold value of measure `name` (None if not saved);
    a multiclass model trained before 29 October 2026 has its specificity
    worked out from its confusion matrix."""
    perf = (metrics or {}).get("out_of_fold_performance", {})
    if name == THRESHOLD:
        return perf.get("optimal_threshold")
    key = _key(metrics, name)
    if key == "macro_specificity" and perf.get(key) is None:
        from .train_worker import macro_specificity
        return macro_specificity(perf.get("confusion_matrix") or [])
    return perf.get(key) if key else None


def fmt(v, digits=3):
    return "-" if v is None else f"{float(v):.{digits}f}"


def summary_table(metrics):
    """(columns [(group, name)], rows [(label, [cell, ...])]): out-of-fold,
    cross-validation (mean ± SD) and hold-out (when the run had one), each
    measure once."""
    m = metrics or {}
    binary = is_binary(m)
    names = [label for label, _b, _m in MEASURES]
    keys = [_key(m, n) for n in names]
    columns = [(group, label) for group, measures in GROUPS
               for label, _b, _m in measures]
    if binary:
        columns.append(("", THRESHOLD))
    columns.append(("", "n"))
    extra = ["-"] if binary else []

    rows = [("Out-of-fold",
             [fmt(value(m, n)) for n in names]
             + ([fmt(value(m, THRESHOLD))] if binary else [])
             + [str(m.get("n_samples", "-"))])]
    cv = m.get("cross_validation") or {}
    if cv:
        cells = []
        for key in keys:
            k = _CV_KEYS.get(key, key)
            mean, sd = cv.get(f"mean_{k}"), cv.get(f"std_{k}")
            cells.append("-" if mean is None or sd is None
                         else f"{mean:.2f} ± {sd:.2f}")
        rows.append((f"Cross-validation, {cv.get('n_folds', '?')} folds "
                     "(mean ± SD)", cells + extra + ["-"]))
    ho = m.get("holdout_performance") or {}
    if ho:
        rows.append(("Hold-out test",
                     [fmt(ho.get(_HOLDOUT_KEYS.get(k, k))) for k in keys]
                     + extra + [str(ho.get("n_test", "-"))]))
    return columns, rows


CLASS_HEADERS = ["Class", "n", "Sensitivity", "Specificity", "Precision",
                 "F1 score"]


def class_table(metrics):
    """Each of the model's classes against the rest, from its confusion
    matrix (a binary model's: No strike, Strike): rows of
    [class, n, sensitivity, specificity, precision, F1 score]."""
    m = metrics or {}
    cm = m.get("out_of_fold_performance", {}).get("confusion_matrix")
    if isinstance(cm, dict):
        mat = [[cm["tn"], cm["fp"]], [cm["fn"], cm["tp"]]]
        names = list(BINARY_CLASSES)
    elif isinstance(cm, list) and m.get("class_names"):
        mat, names = cm, list(m["class_names"])
    else:
        return []
    mat = np.asarray(mat, dtype=float)
    total = mat.sum()
    rows = []
    for i, name in enumerate(names):
        tp, n, predicted = mat[i, i], mat[i].sum(), mat[:, i].sum()
        fp = predicted - tp
        tn = total - n - fp
        sens = tp / n if n else None
        spec = tn / (tn + fp) if tn + fp else None
        prec = tp / predicted if predicted else None
        f1 = (2 * prec * sens / (prec + sens)
              if prec is not None and sens is not None and prec + sens
              else None)
        rows.append([name, str(int(n)), fmt(sens), fmt(spec), fmt(prec),
                     fmt(f1)])
    return rows
