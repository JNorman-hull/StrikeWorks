# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Which annotation (label) columns a deployed model was trained on, read
from its metrics JSON exactly as training recorded them - so prediction
compares against the same columns and values. Nothing is renamed or
recoded: a dataset whose columns or values differ from the model's simply
can't be compared (`ml_state.PredictionState.ground_truth_column`).

Plain Python (no Qt): the prediction worker imports it too.

  binary model  metrics["training"]: "target_column", "negative_class"
                (the "no strike" value), "breakdown_columns"
                (train_worker.provenance_section)
  region model  metrics["region_column"] and ["region_to_class"], keyed by
                `level_key` of each level, as train_worker groups them
"""


def level_key(value):
    """Stable key for a level: numbers in their integer form ("2.0" ->
    "2"), anything else as trimmed text - train_worker's own rule."""
    try:
        f = float(value)
        if f.is_integer():
            return str(int(f))
        return repr(f)
    except (TypeError, ValueError):
        return str(value).strip()


def _training(bin_metrics):
    return (bin_metrics or {}).get("training") or {}


def target_column(bin_metrics):
    """The binary model's target (annotation) column, if recorded."""
    return _training(bin_metrics).get("target_column")


def negative_class(bin_metrics):
    """The target value the binary model was trained to call "no strike",
    if recorded."""
    value = _training(bin_metrics).get("negative_class")
    return None if value is None else str(value)


def breakdown_columns(bin_metrics):
    """The columns the binary model's performance was broken down by."""
    return list(_training(bin_metrics).get("breakdown_columns") or [])


def region_column(mc_metrics):
    """The region model's class column: recorded as "region_column", or in
    "<column> (collapsed)" by models trained before that was."""
    if not mc_metrics:
        return None
    if mc_metrics.get("region_column"):
        return mc_metrics["region_column"]
    target = str(mc_metrics.get("target", ""))
    suffix = " (collapsed)"
    return target[:-len(suffix)] if target.endswith(suffix) else None


def label_columns(bin_metrics, mc_metrics=None):
    """The columns the models were trained on and broken down by -
    carried into predictions.csv for the comparison."""
    cols = [target_column(bin_metrics), region_column(mc_metrics)]
    cols += breakdown_columns(bin_metrics)
    out = []
    for c in cols:
        if c and c not in out:
            out.append(c)
    return out


def region_class(level, mc_metrics, class_names):
    """The region model's class name for an annotated `level`, or None
    when the level isn't in its grouping (or there is no region model)."""
    mapping = {level_key(k): v for k, v in
               ((mc_metrics or {}).get("region_to_class") or {}).items()}
    idx = mapping.get(level_key(level))
    if idx is None:
        return None
    idx = int(idx)
    return class_names[idx] if 0 <= idx < len(class_names) else None
