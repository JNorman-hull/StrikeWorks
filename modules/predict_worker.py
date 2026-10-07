# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Subprocess worker: loads models, runs predictions, writes results to CSV.

Two-stage pipeline:
  1. binary model      -> strike vs no-contact (overall strike rate)
  2. multiclass model  -> for each predicted strike, which pump region (class)

Run in a subprocess so sktime/joblib/numba are never imported inside the GUI
process, and a model crash cannot take the application down.

Usage:
    python predict_worker.py \
        --bin-model <path>  --bin-metrics <path> \
        --mc-model  <path>  --mc-metrics  <path> \
        --data <path>       --out <dir> \
        [--threshold <float>] [--hig-peaks]

--mc-model/--mc-metrics are optional; if omitted only the binary stage runs.
--threshold overrides the deployed optimal_threshold (the GUI passes it
only when the override box is ticked). --hig-peaks runs the HIG peak
analysis (hig_peaks.py; Predict's "HIG peak analysis" box, on by default).

Outputs:
    predictions.csv     per-recording predictions
    summary.csv         treatment-level summary with Wilson CIs
    region_summary.csv  tidy treatment x class table (multiclass only)
    severity_summary.csv  treatment x HIG threshold table (when the dataset
                        has the high-g accelerometer channels)
    hig_peaks.csv       with --hig-peaks: every acceleration event found
    acceleration_summary.csv  with --hig-peaks: event counts, collision
                        probability and event acceleration by treatment

Severity is measured, not predicted: each recording's peak high-g
acceleration magnitude over its window (`hig_peak_g`), banded at 95, 200
and 400 g. Only a peak over 400 g is a severe strike - the model flags
contacts of any size, so this says how hard they were.
    run_meta.json       class_names + run/provenance metadata
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

try:
    from . import hig_peaks
except ImportError:          # run as a script from source (worker_launch.py)
    import hig_peaks

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


# HIG severity bands: over 95, 200 and 400 g; only over 400 g is severe
SEVERITY_THRESHOLDS_G = (95, 200, 400)
SEVERE_G = 400
SEVERITY_BANDS = ("<=95 g", "95-200 g", "200-400 g", ">400 g")


def _hig_peaks(df, file_meta):
    """Each recording's peak HIG acceleration magnitude (g) over its window,
    aligned to `file_meta`; (None, None) when the dataset has no HIG."""
    if "higacc_mag_g" in df.columns:
        mag, source = df["higacc_mag_g"].astype(float), "higacc_mag_g"
    elif all(c in df.columns for c in ("higacc_x_g", "higacc_y_g", "higacc_z_g")):
        mag = np.sqrt(df["higacc_x_g"].astype(float) ** 2
                      + df["higacc_y_g"].astype(float) ** 2
                      + df["higacc_z_g"].astype(float) ** 2)
        source = "higacc_x_g/higacc_y_g/higacc_z_g"
    else:
        return None, None
    peaks = mag.groupby(df["file"]).max()
    return file_meta["file"].map(peaks).astype(float).values, source


def _severity_band(peaks):
    """The band label for each peak: <=95 g, 95-200 g, 200-400 g, >400 g."""
    idx = np.digitize(peaks, SEVERITY_THRESHOLDS_G, right=True)
    return np.array(SEVERITY_BANDS, dtype=object)[idx]


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
    from importlib.metadata import PackageNotFoundError, version
    out = {}
    for pkg in ("numpy", "pandas", "scikit-learn", "sktime", "joblib"):
        try:
            out[pkg] = version(pkg)
        except PackageNotFoundError:
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
    ap.add_argument("--hig-peaks",   action="store_true")
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

    # ---- HIG severity (measured, independent of the model) ----
    peaks, hig_source = _hig_peaks(df, file_meta)
    if peaks is not None:
        results["hig_peak_g"] = np.round(peaks, 1)
        results["severity"] = _severity_band(peaks)
        results["severe_strike"] = (peaks > SEVERE_G).astype(int)

    # ---- HIG peak analysis (measured events around the nadir) ----
    acc_summary = None
    if args.hig_peaks:
        events, per_file = hig_peaks.analyse(df, file_meta["file"])
        if events is not None:
            results = results.join(per_file, on="file")
            treatments = (file_meta.set_index("file")["treatment"]
                          if "treatment" in file_meta.columns else None)
            acc_summary = hig_peaks.summary(events, per_file, treatments)
            events.to_csv(out_dir / "hig_peaks.csv", index=False)
            acc_summary.to_csv(out_dir / "acceleration_summary.csv",
                               index=False)

    # ---- per-treatment summary ----
    summary_rows = []
    severity_rows = []
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
        if peaks is not None:
            for g in SEVERITY_THRESHOLDS_G:
                n_over = int((grp["hig_peak_g"] > g).sum())
                row[f"n_over_{g}g"] = n_over
                p_over, lo_over, hi_over = _wilson_ci(n_over, n)
                severity_rows.append(dict(
                    treatment=str(tx), threshold_g=g, n=n, n_over=n_over,
                    rate=round(p_over, 6), ci_lo=round(lo_over, 6),
                    ci_hi=round(hi_over, 6), severe=g == SEVERE_G))
            sev_rate, sev_lo, sev_hi = _wilson_ci(row[f"n_over_{SEVERE_G}g"], n)
            row["severe_rate"] = round(sev_rate, 6)
            row["severe_ci_lo"] = round(sev_lo, 6)
            row["severe_ci_hi"] = round(sev_hi, 6)
            row["n_strike_severe"] = int(strikes["severe_strike"].sum())
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

    if severity_rows:
        pd.DataFrame(severity_rows).to_csv(out_dir / "severity_summary.csv",
                                           index=False)
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
        "severity": None if peaks is None else {
            "thresholds_g": list(SEVERITY_THRESHOLDS_G),
            "severe_g": SEVERE_G,
            "hig_channel": hig_source,
            "n_severe": int(results["severe_strike"].sum()),
            "severe_rate": (round(float(results["severe_strike"].mean()), 6)
                            if n_files else 0.0),
            "n_strike_severe": int(results.loc[results["predicted_strike"] == 1,
                                               "severe_strike"].sum()),
        },
        "hig_peaks": None if acc_summary is None else {
            **hig_peaks.parameters(),
            "n_events": int(results["n_events"].sum()),
            "n_collision": int(results["collision"].sum()),
        },
        "hig_peaks_requested": bool(args.hig_peaks),
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
