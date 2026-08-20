# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Subprocess worker: loads models, runs predictions, writes results to CSV.

Port of the MVP's ``bsm/predict_worker.py``. Two-stage pipeline:
  1. binary model      -> strike vs no-contact (overall strike rate)
  2. multiclass model  -> for each predicted strike, which pump region (class)

Run in a subprocess so sktime/joblib/numba are never imported inside the GUI
process, and a model crash cannot take the application down.

Usage:
    python predict_worker.py \
        --bin-model <path>  --bin-metrics <path> \
        --mc-model  <path>  --mc-metrics  <path> \
        --data <path>       --out <dir> \
        [--threshold <float>]

--mc-model/--mc-metrics are optional; if omitted only the binary stage runs.
--threshold overrides the deployed optimal_threshold (explicit user choice
only - the GUI passes it exclusively when the user ticks the override box).

Outputs (unchanged from the MVP, plus a richer run_meta.json):
    predictions.csv     per-recording predictions
    summary.csv         treatment-level summary with Wilson CIs
    region_summary.csv  tidy treatment x class table (multiclass only)
    run_meta.json       class_names (as before) + run/provenance metadata
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

# Shim: models saved with numpy >= 2.0 pickle references to numpy._core.*,
# which does not exist on numpy 1.x. Register every numpy.core submodule
# under the numpy._core name so pickle can find them. Only applied on
# numpy 1.x - on numpy >= 2 the real numpy._core exists (and pre-seeding
# placeholders would shadow its lazily-imported submodules).
if int(np.__version__.split(".")[0]) < 2:
    import numpy.core as _ncore
    import types

    _shim = types.ModuleType("numpy._core")
    _shim.__path__ = []
    sys.modules.setdefault("numpy._core", _shim)

    for _attr in [
        "numeric", "multiarray", "umath", "fromnumeric", "function_base",
        "numerictypes", "arrayprint", "defchararray", "records", "memmap",
        "machar", "getlimits", "shape_base", "einsumfunc", "overrides",
        "_multiarray_umath", "_dtype", "_dtype_ctypes", "_ufunc_config",
    ]:
        _full = f"numpy._core.{_attr}"
        sys.modules.setdefault(_full, getattr(_ncore, _attr, None) or
                               sys.modules.get(f"numpy.core.{_attr}") or
                               types.ModuleType(_full))


_DEFAULT_CHANNELS = [
    "higacc_x_g", "higacc_y_g", "higacc_z_g",
    "inacc_x_ms", "inacc_y_ms", "inacc_z_ms",
    "rot_x_degs", "rot_y_degs", "rot_z_degs",
    "pressure_kpa",
]

# per-recording metadata carried into predictions.csv when present.
# The second group are the annotation/ground-truth columns a curated
# StrikeWorks dataset may contain - carrying them through lets the GUI
# compare predictions against ground truth without re-reading the dataset.
_META_COLS = [
    "treatment", "n_contact", "c_1_type",
    "clear_passage", "centre_hub_contact", "blade_contact",
    "deployment_id", "run",
    "overall_passage_type", "leading_edge_type", "other_type",
    "concentric_pump_region",
]


def _pad(ts, target):
    if len(ts) >= target:
        return ts[:target]
    return np.vstack([ts, np.tile(ts[-1], (target - len(ts), 1))])


def _file_metadata(df):
    meta_cols = ["file"]
    for col in _META_COLS:
        if col in df.columns:
            meta_cols.append(col)
    return df.groupby("file")[meta_cols[1:]].first().reset_index()


def _build_X(df, file_meta, channels, max_length):
    """Build padded (n_files, n_channels, max_len) array aligned to file_meta."""
    missing = [c for c in channels if c not in df.columns]
    if missing:
        raise ValueError(f"Missing channels: {missing}")
    X_list = []
    for fid in file_meta["file"]:
        ts = df[df["file"] == fid].sort_values("time_s")[channels].values
        X_list.append(_pad(ts, max_length).T)
    return np.stack(X_list)


def _softmax(scores):
    if scores.ndim == 1:                       # binary decision fn -> 2 columns
        scores = np.column_stack([-scores, scores])
    e = np.exp(scores - scores.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


def _wilson_ci(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0, 0.0
    p      = k / n
    denom  = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half   = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return p, max(0.0, centre - half), min(1.0, centre + half)


def _package_versions():
    """Versions of the model stack, for provenance. Best effort only."""
    out = {}
    try:
        from importlib.metadata import version
        for pkg in ("numpy", "pandas", "scikit-learn", "sktime", "joblib"):
            try:
                out[pkg] = version(pkg)
            except Exception:
                pass
    except Exception:
        pass
    return out


def main():
    t0 = time.monotonic()

    ap = argparse.ArgumentParser()
    ap.add_argument("--bin-model",   required=True)
    ap.add_argument("--bin-metrics", required=True)
    ap.add_argument("--mc-model",    default=None)
    ap.add_argument("--mc-metrics",  default=None)
    ap.add_argument("--data",        required=True)
    ap.add_argument("--out",         required=True)
    ap.add_argument("--threshold",   type=float, default=None)
    # legacy single-model flags (binary only)
    ap.add_argument("--model",       default=None)
    ap.add_argument("--metrics",     default=None)
    args = ap.parse_args()

    bin_model_path   = args.bin_model   or args.model
    bin_metrics_path = args.bin_metrics or args.metrics

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- binary stage ----
    with open(bin_metrics_path) as f:
        bin_metrics = json.load(f)
    bin_channels = bin_metrics.get("channels", _DEFAULT_CHANNELS)
    deployed_threshold = bin_metrics["out_of_fold_performance"]["optimal_threshold"]
    threshold   = args.threshold if args.threshold is not None else deployed_threshold
    bin_max_len = bin_metrics["max_sequence_length"]

    df        = pd.read_csv(args.data, low_memory=False)
    file_meta = _file_metadata(df)

    bin_model = joblib.load(bin_model_path)
    X_bin     = _build_X(df, file_meta, bin_channels, bin_max_len)

    scores = np.clip(bin_model.decision_function(X_bin), -500, 500)
    probs  = 1 / (1 + np.exp(-scores))
    preds  = (probs >= threshold).astype(int)

    results = file_meta.copy()
    results["probability_strike"] = np.round(probs, 4)
    results["predicted_strike"]   = preds
    results["confidence"]         = np.where(preds == 1, probs, 1 - probs).round(4)

    # ---- multiclass (region) stage ----
    class_names = []
    mc_channels = None
    mc_max_len  = None
    if args.mc_model and args.mc_metrics:
        with open(args.mc_metrics) as f:
            mc_metrics = json.load(f)
        class_names  = mc_metrics.get("class_names", [])
        mc_channels  = mc_metrics.get("channels", _DEFAULT_CHANNELS)
        mc_max_len   = mc_metrics["max_sequence_length"]

        mc_model = joblib.load(args.mc_model)
        X_mc     = _build_X(df, file_meta, mc_channels, mc_max_len)

        mc_scores = mc_model.decision_function(X_mc)
        mc_probs  = _softmax(mc_scores)
        mc_idx    = mc_probs.argmax(axis=1)

        is_strike = results["predicted_strike"].values == 1
        labels    = np.array([class_names[i] for i in mc_idx], dtype=object)
        results["predicted_region"]  = np.where(is_strike, labels, "")
        results["region_confidence"] = np.where(is_strike, mc_probs.max(axis=1).round(4), np.nan)
        for i, cn in enumerate(class_names):
            results[f"prob_{cn}"] = mc_probs[:, i].round(4)

    # ---- per-treatment summary ----
    summary_rows = []
    groups = results.groupby("treatment") if "treatment" in results.columns \
        else [("All data", results)]
    for tx, grp in groups:
        n = len(grp)
        k = int(grp["predicted_strike"].sum())
        rate, lo, hi = _wilson_ci(k, n)
        row = dict(
            treatment    = str(tx),
            n            = n,
            n_strike     = k,
            n_no_strike  = n - k,
            strike_rate  = round(rate, 6),
            ci_lo        = round(lo,   6),
            ci_hi        = round(hi,   6),
            mean_prob    = round(float(grp["probability_strike"].mean()), 4),
            mean_conf    = round(float(grp["confidence"].mean()),         4),
        )
        # region counts among predicted strikes in this treatment
        strikes = grp[grp["predicted_strike"] == 1]
        for cn in class_names:
            row[f"n_{cn}"] = int((strikes["predicted_region"] == cn).sum())
        summary_rows.append(row)

    summary = pd.DataFrame(summary_rows)

    # tidy region summary (per treatment x class) - convenient for saving
    if class_names:
        region_rows = []
        for _, r in summary.iterrows():
            ns = r["n_strike"]
            for cn in class_names:
                nc = int(r[f"n_{cn}"])
                region_rows.append(dict(
                    treatment  = r["treatment"],
                    region     = cn,
                    n          = nc,
                    proportion = round(nc / ns, 4) if ns else 0.0,
                ))
        pd.DataFrame(region_rows).to_csv(out_dir / "region_summary.csv", index=False)

    results.to_csv(out_dir / "predictions.csv", index=False)
    summary.to_csv(out_dir / "summary.csv",     index=False)

    # run metadata. "class_names" is kept at the top level for backwards
    # compatibility; everything else is additive.
    n_files  = int(len(results))
    n_strike = int(results["predicted_strike"].sum())
    run_meta = {
        "class_names":        class_names,
        "timestamp":          datetime.now().isoformat(timespec="seconds"),
        "elapsed_s":          round(time.monotonic() - t0, 2),
        "n_files":            n_files,
        "n_strike":           n_strike,
        "strike_rate":        round(n_strike / n_files, 6) if n_files else 0.0,
        "n_rows":             int(len(df)),
        "threshold":          float(threshold),
        "deployed_threshold": float(deployed_threshold),
        "threshold_overridden": args.threshold is not None,
        "mode":               "multiclass" if class_names else "binary",
        "bin_model":          str(bin_model_path),
        "bin_metrics":        str(bin_metrics_path),
        "mc_model":           str(args.mc_model) if args.mc_model else None,
        "mc_metrics":         str(args.mc_metrics) if args.mc_metrics else None,
        "data":               str(args.data),
        "bin_channels":       list(bin_channels),
        "mc_channels":        list(mc_channels) if mc_channels else None,
        "bin_max_sequence_length": int(bin_max_len),
        "mc_max_sequence_length":  int(mc_max_len) if mc_max_len else None,
        "python_version":     sys.version.split()[0],
        "package_versions":   _package_versions(),
    }
    with open(out_dir / "run_meta.json", "w") as f:
        json.dump(run_meta, f, indent=2)
    print("OK", flush=True)


if __name__ == "__main__":
    import traceback
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
