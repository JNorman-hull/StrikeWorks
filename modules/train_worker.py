# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Subprocess worker: trains the two-stage blade-strike model pipeline.

Port of the ML pipeline scripts ``01_binary_model.py`` (binary strike model)
and ``05_multiclass_collapsed.py`` (collapsed pump-region model), driven by a
JSON configuration written by the GUI. Run in a subprocess so that the
sktime/numba model stack is never imported into the GUI process; stdout is
streamed line-by-line into the training console.

One run trains the pipeline the prediction page deploys:

    Stage 1  binary      strike vs no-contact (always trained)
    Stage 2  multiclass  pump region for each ground-truth strike
                         (trained when ``train_multiclass`` is set)

Outputs land in ``<out_dir>/binary/`` and ``<out_dir>/multiclass/``.

Usage:
    python train_worker.py --config <train_config.json> --stage cv
    python train_worker.py --config <train_config.json> --stage final

Stage ``cv``   : cross-validation (optionally after a stratified hold-out
                 split) -> performance_metrics.json, cv_predictions.csv,
                 misclassified_files_for_review.csv, cv_curves.json,
                 blade_strike_predictions.csv (binary model only).
Stage ``final``: retrains on ALL training data and saves the deployment
                 model(s) (final_model_for_deployment.joblib,
                 max_sequence_length.npy, model_config.json, channels.json).

The two stages are deliberately separate: the GUI requires the user to
review the cross-validated performance before committing final models.

Lines beginning with ``##`` are machine-readable progress markers for the
GUI (##MODEL binary|multiclass, ##FOLD k n, ##STAGE name, ##DONE);
everything else is human console output, kept close to the original
scripts' prints.
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


# the GUI reads this stream as UTF-8; make that explicit so symbols like
# "±" survive regardless of the Windows locale codepage
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass


def log(msg=""):
    print(msg, flush=True)


# ── data preparation (shared by both stages) ─────────────────────────────────

def pad_time_series(ts, target_length):
    if len(ts) >= target_length:
        return ts[:target_length]
    n_pad = target_length - len(ts)
    return np.vstack([ts, np.tile(ts[-1], (n_pad, 1))])


def derive_strike_type(row, cfg):
    """Strike type for downstream analysis (generalised from 01_binary_model:
    works with both passage_type/leading_type and the curated dataset's
    overall_passage_type/leading_edge_type column names)."""
    target = str(row[cfg["target_column"]])
    if target == str(cfg["negative_class"]):
        return "no_contact"
    lead_col = cfg.get("leading_type_column")
    other_col = cfg.get("other_type_column")
    if "leading" in target.lower():
        lead = row.get(lead_col) if lead_col else None
        if pd.notna(lead) and str(lead).strip():
            return f"leading_{str(lead).lower().strip().replace(' ', '_')}"
        return "leading_unknown"
    other = row.get(other_col) if other_col else None
    if pd.notna(other) and str(other).strip():
        return f"other_{str(other).lower().strip().replace(' ', '_')}"
    return str(target).lower().strip().replace(" ", "_")


def prepare_data(cfg, kind):
    """Load, filter, label and tensorise the training dataset for one
    pipeline stage (`kind` is "binary" or "multiclass").

    Returns dict with X, y, file_metadata, channels, max_length, class_names
    and bookkeeping counts. Identical for the cv and final stages so the
    final model is trained on exactly the population that was validated.
    """
    df = pd.read_csv(cfg["data"], low_memory=False)
    log(f"Rows: {len(df)}")
    log(f"Unique files: {df['file'].nunique()}")

    tcol = cfg["target_column"]
    if tcol not in df.columns:
        raise ValueError(f"Target column '{tcol}' not in dataset.")

    # drop records with missing target metadata (always excluded, reported)
    n_missing_target = int(df.loc[df[tcol].isna(), "file"].nunique())
    df = df[df[tcol].notna()].copy()
    if n_missing_target:
        log(f"Excluded {n_missing_target} file(s) with missing '{tcol}'.")

    # explicit inclusion filter (dataset filtering step in the GUI)
    include = cfg.get("include_values")
    if include:
        before = df["file"].nunique()
        df = df[df[tcol].astype(str).isin([str(v) for v in include])].copy()
        log(f"Inclusion filter on '{tcol}': {df['file'].nunique()} of "
            f"{before} file(s) kept ({', '.join(map(str, include))}).")

    channels = list(cfg["channels"])
    missing = [c for c in channels if c not in df.columns]
    if missing:
        raise ValueError(f"Missing channels in dataset: {missing}")
    n_nan = int(df[channels].isna().sum().sum())
    if n_nan:
        raise ValueError(
            f"{n_nan} missing values in the selected channels - MiniRocket "
            "requires complete sequences. Clean the dataset first.")

    n_surface = 0
    if kind == "binary":
        df["blade_strike"] = (
            df[tcol].astype(str) != str(cfg["negative_class"])).astype(int)
        df["strike_type"] = df.apply(
            lambda r: derive_strike_type(r, cfg), axis=1)

        agg = {"blade_strike": "first", "strike_type": "first"}
        for col in ("treatment", tcol, cfg.get("leading_type_column"),
                    cfg.get("other_type_column")):
            if col and col in df.columns:
                agg[col] = "first"
        file_metadata = df.groupby("file").agg(agg).reset_index()
        y = file_metadata["blade_strike"].values
        class_names = [str(cfg["negative_class"]), str(cfg["positive_label"])]
        log("\nStrike distribution:")
        for line in str(file_metadata["strike_type"].value_counts()).splitlines():
            log(f"  {line}")

    else:  # multiclass: collapsed pump-region pipeline (05_multiclass_collapsed)
        rcol = cfg["region_column"]
        if rcol not in df.columns:
            raise ValueError(f"Region column '{rcol}' not in dataset.")

        df = df[df[tcol].astype(str) != str(cfg["negative_class"])].copy()
        log(f"Strike files after removing '{cfg['negative_class']}': "
            f"{df['file'].nunique()}")

        # unlabeled impeller-surface strikes
        other_col = cfg.get("other_type_column")
        if other_col and other_col in df.columns:
            surface_mask = (df[other_col].astype(str).str.lower()
                            .str.contains("surface", na=False)
                            & df[rcol].isna())
        else:
            surface_mask = pd.Series(False, index=df.index)
        n_surface = int(df.loc[surface_mask, "file"].nunique())
        if cfg.get("include_surface_as_region1"):
            df.loc[surface_mask, rcol] = 1
            log(f"Relabelled {n_surface} unlabeled surface file(s) as region 1.")
        elif n_surface:
            log(f"Dropping {n_surface} unlabeled surface file(s).")

        df = df[df[rcol].notna()].copy()
        df["region"] = df[rcol].astype(float).astype(int)

        agg = {"region": "first"}
        for col in ("treatment", tcol, cfg.get("leading_type_column"),
                    cfg.get("other_type_column")):
            if col and col in df.columns:
                agg[col] = "first"
        file_metadata = df.groupby("file").agg(agg).reset_index()

        region_to_class = {int(k): int(v)
                           for k, v in cfg["region_to_class"].items()}
        known = file_metadata["region"].isin(region_to_class)
        n_unknown = int((~known).sum())
        if n_unknown:
            log(f"Dropping {n_unknown} file(s) with regions outside the "
                "collapse scheme.")
            keep_files = set(file_metadata.loc[known, "file"])
            file_metadata = file_metadata[known].reset_index(drop=True)
            df = df[df["file"].isin(keep_files)].copy()

        y = np.array([region_to_class[r] for r in file_metadata["region"]])
        class_names = list(cfg["class_names"])
        log(f"Strike files: {len(file_metadata)}")
        log("\nClass distribution:")
        for i, cn in enumerate(class_names):
            c = int((y == i).sum())
            pct = c / len(y) * 100 if len(y) else 0
            log(f"  {cn:14s}: {c:4d}  ({pct:.1f}%)")

    # ---- time-series extraction ----
    lengths = [len(df[df["file"] == f]) for f in file_metadata["file"]]
    auto_max = max(lengths)
    max_length = int(cfg["seq_length"]) if cfg.get("seq_length") else auto_max
    log(f"\nSequence lengths: min={min(lengths)}, max={auto_max}, "
        f"mean={np.mean(lengths):.1f}")
    if max_length != auto_max:
        log(f"Using configured sequence length: {max_length} samples "
            "(shorter padded, longer truncated).")

    X_list = []
    for file_id in file_metadata["file"]:
        fd = df[df["file"] == file_id].sort_values("time_s")
        X_list.append(pad_time_series(fd[channels].values, max_length).T)
    X = np.stack(X_list)

    log(f"\nX shape: {X.shape}")
    log(f"y distribution: {np.bincount(y, minlength=len(class_names))}")

    return dict(X=X, y=y, file_metadata=file_metadata, channels=channels,
                max_length=max_length, class_names=class_names,
                n_surface=n_surface, n_missing_target=n_missing_target,
                lengths=lengths)


def sample_weights(cfg, y, class_names, kind):
    """Per-sample weights. Binary keeps 01_binary_model's ratio weighting;
    multiclass keeps 05's sklearn 'balanced' weights."""
    if cfg.get("class_weighting", "balanced") == "none":
        return np.ones(len(y)), {cn: 1.0 for cn in class_names}

    if kind == "binary":
        n_pos = int((y == 1).sum())
        n_neg = int((y == 0).sum())
        w_pos = n_neg / n_pos if n_pos else 1.0
        log(f"\nClass imbalance: {n_neg} no-strikes, {n_pos} strikes")
        log(f"Strike class weight: {w_pos:.2f}")
        return (np.where(y == 1, w_pos, 1.0),
                {class_names[0]: 1.0, class_names[1]: float(w_pos)})

    from sklearn.utils.class_weight import compute_class_weight
    cw_arr = compute_class_weight("balanced", classes=np.unique(y), y=y)
    cw = dict(zip(np.unique(y), cw_arr))
    log("\nBalanced class weights:")
    for i, cn in enumerate(class_names):
        log(f"  {cn:14s}: {cw.get(i, 0.0):.3f}")
    return (np.array([cw[v] for v in y]),
            {class_names[i]: float(cw.get(i, 0.0))
             for i in range(len(class_names))})


def build_pipeline(cfg):
    from sklearn.linear_model import RidgeClassifierCV
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sktime.transformations.panel.rocket import MiniRocket

    ridge = cfg.get("ridge", {})
    alphas = np.logspace(ridge.get("alpha_min_exp", -3),
                         ridge.get("alpha_max_exp", 3),
                         int(ridge.get("n_alphas", 100)))
    mr = cfg.get("minirocket", {})
    return make_pipeline(
        MiniRocket(random_state=int(mr.get("random_state", 42)),
                   n_jobs=int(mr.get("n_jobs", -1))),
        StandardScaler(with_mean=False),
        RidgeClassifierCV(alphas=alphas),
    )


def _sigmoid(scores):
    return 1 / (1 + np.exp(-np.clip(scores, -500, 500)))


def _softmax(scores):
    if scores.ndim == 1:
        scores = np.column_stack([-scores, scores])
    e = np.exp(scores - scores.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


def wilson_ci(k, n):
    if n == 0:
        return 0.0, 0.0, 0.0
    z = 1.959964
    p_hat = k / n
    denom = 1 + z ** 2 / n
    centre = (p_hat + z ** 2 / (2 * n)) / denom
    margin = (z * np.sqrt(p_hat * (1 - p_hat) / n + z ** 2 / (4 * n ** 2))) / denom
    return p_hat, max(0, centre - margin), min(1, centre + margin)


def _package_versions():
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


def provenance_section(cfg, data, t0, kind):
    return {
        "timestamp":        datetime.now().isoformat(timespec="seconds"),
        "elapsed_s":        round(time.monotonic() - t0, 2),
        "dataset":          str(cfg["data"]),
        "dataset_name":     Path(cfg["data"]).name,
        "pipeline":         ("binary + multiclass"
                             if cfg.get("train_multiclass") else "binary"),
        "target_kind":      kind,
        "target_column":    cfg["target_column"],
        "negative_class":   cfg.get("negative_class"),
        "include_values":   cfg.get("include_values"),
        "n_missing_target_excluded": data["n_missing_target"],
        "class_weighting":  cfg.get("class_weighting", "balanced"),
        "split_mode":       cfg.get("split_mode", "cv_only"),
        "test_size":        cfg.get("test_size"),
        "n_folds":          cfg["n_folds"],
        "shuffle":          cfg.get("shuffle", True),
        "random_seed":      cfg.get("random_seed", 42),
        "sequence_length":  data["max_length"],
        "padding":          cfg.get("padding", "repeat_last"),
        "truncation":       cfg.get("truncation", "truncate"),
        "minirocket":       cfg.get("minirocket", {}),
        "ridge":            cfg.get("ridge", {}),
        "application":      cfg.get("app_version", ""),
        "python_version":   sys.version.split()[0],
        "package_versions": _package_versions(),
    }


# ── binary CV (port of 01_binary_model.py) ───────────────────────────────────

def binary_metrics_from_preds(y_true, preds):
    from sklearn.metrics import confusion_matrix
    tn, fp_n, fn, tp = confusion_matrix(y_true, preds, labels=[0, 1]).ravel()
    sens = tp / (tp + fn) if (tp + fn) else 0.0
    spec = tn / (tn + fp_n) if (tn + fp_n) else 0.0
    prec = tp / (tp + fp_n) if (tp + fp_n) else 0.0
    acc = (tp + tn) / (tp + tn + fp_n + fn)
    f1 = 2 * prec * sens / (prec + sens) if (prec + sens) else 0.0
    mcc_num = (tp * tn) - (fp_n * fn)
    mcc_den = np.sqrt(float((tp + fp_n) * (tp + fn) * (tn + fp_n) * (tn + fn)))
    mcc = float(mcc_num / mcc_den) if mcc_den > 0 else 0.0
    return dict(tn=int(tn), fp=int(fp_n), fn=int(fn), tp=int(tp),
                sensitivity=sens, specificity=spec, precision=prec,
                accuracy=acc, f1=f1, mcc=mcc)


def run_cv_binary(cfg, data, out_dir, cv_idx, t0):
    from sklearn.metrics import (auc, precision_recall_curve, roc_auc_score,
                                 roc_curve)

    X, y = data["X"], data["y"]
    fm = data["file_metadata"]
    weights, weight_map = sample_weights(cfg, y, data["class_names"],
                                         "binary")

    n_folds = int(cfg["n_folds"])
    log(f"\n{n_folds}-Fold Stratified Cross-Validation")
    log(f"##STAGE cv {n_folds}")

    oof_probs = np.zeros(len(y))
    fold_assignment = np.zeros(len(y), dtype=int)
    cv_metrics = {"auc": [], "accuracy": [], "sensitivity": [],
                  "specificity": [], "precision": [], "f1": []}

    for fold, (tr, te) in enumerate(cv_idx):
        log(f"##FOLD {fold + 1} {n_folds}")
        log(f"\nFold {fold + 1}/{n_folds}: train={len(tr)}, test={len(te)}")

        pipe = build_pipeline(cfg)
        pipe.fit(X[tr], y[tr], ridgeclassifiercv__sample_weight=weights[tr])
        probs = _sigmoid(pipe.decision_function(X[te]))

        fpr_f, tpr_f, thr_f = roc_curve(y[te], probs)
        opt_thr = thr_f[np.argmax(tpr_f - fpr_f)]
        preds = (probs >= opt_thr).astype(int)

        oof_probs[te] = probs
        fold_assignment[te] = fold

        m = binary_metrics_from_preds(y[te], preds)
        auc_f = roc_auc_score(y[te], probs)
        for k, v in (("auc", auc_f), ("accuracy", m["accuracy"]),
                     ("sensitivity", m["sensitivity"]),
                     ("specificity", m["specificity"]),
                     ("precision", m["precision"]), ("f1", m["f1"])):
            cv_metrics[k].append(float(v))
        log(f"  AUC={auc_f:.3f}, Accuracy={m['accuracy']:.3f}, "
            f"Threshold={opt_thr:.3f}")

    # ---- overall out-of-fold performance ----
    log("\nOverall out-of-fold performance")
    final_auc = roc_auc_score(y, oof_probs)
    fpr, tpr, thresholds = roc_curve(y, oof_probs)
    prec_curve, rec_curve, _ = precision_recall_curve(y, oof_probs)
    pr_auc = auc(rec_curve, prec_curve)
    optimal_idx = int(np.argmax(tpr - fpr))
    optimal_threshold = float(thresholds[optimal_idx])
    final_preds = (oof_probs >= optimal_threshold).astype(int)
    m = binary_metrics_from_preds(y, final_preds)

    log(f"\n  AUC:               {final_auc:.3f}")
    log(f"  PR-AUC:            {pr_auc:.3f}")
    log(f"  Accuracy:          {m['accuracy']:.3f}")
    log(f"  Sensitivity:       {m['sensitivity']:.3f}")
    log(f"  Specificity:       {m['specificity']:.3f}")
    log(f"  Precision:         {m['precision']:.3f}")
    log(f"  F1-Score:          {m['f1']:.3f}")
    log(f"  MCC:               {m['mcc']:.3f}")
    log(f"  Optimal threshold: {optimal_threshold:.3f}")

    log(f"\nCV summary (mean ± std, {n_folds} folds):")
    for k in cv_metrics:
        log(f"  {k:12s}: {np.mean(cv_metrics[k]):.3f} ± "
            f"{np.std(cv_metrics[k]):.3f}")

    log("\nConfusion Matrix:")
    log("              Pred No Strike  Pred Strike")
    log(f"True No Strike     {m['tn']:3d}           {m['fp']:3d}")
    log(f"True Strike        {m['fn']:3d}           {m['tp']:3d}")

    # ---- per-file results / misclassification ----
    res = fm.copy()
    res["probability"] = oof_probs
    res["y_pred"] = final_preds
    res["y_true"] = y
    res["cv_fold"] = fold_assignment
    res["correct"] = res["y_pred"] == res["y_true"]
    res["error_type"] = "correct"
    res.loc[(res.y_true == 0) & (res.y_pred == 1), "error_type"] = "false_positive"
    res.loc[(res.y_true == 1) & (res.y_pred == 0), "error_type"] = "false_negative"
    mis = res[res.error_type != "correct"].copy()
    n_fp = int((mis.error_type == "false_positive").sum())
    n_fn = int((mis.error_type == "false_negative").sum())
    log(f"\nTotal misclassified: {len(mis)}  "
        f"(false positives: {n_fp}, false negatives: {n_fn})")

    # ---- treatment-level Wilson CI table ----
    rows = []
    if "treatment" in res.columns:
        for tx, grp in res.groupby("treatment"):
            n = len(grp)
            k = int(grp["y_pred"].sum())
            p_hat, lo, hi = wilson_ci(k, n)
            rows.append({
                "treatment": tx, "n_fish": n,
                "n_predicted_strike": k,
                "n_true_strike": int(grp["y_true"].sum()),
                "predicted_strike_rate": round(p_hat, 4),
                "wilson_ci_lower": round(lo, 4),
                "wilson_ci_upper": round(hi, 4),
                "accuracy": round(float(grp["correct"].mean()), 4),
            })
    pd.DataFrame(rows).to_csv(out_dir / "blade_strike_predictions.csv",
                              index=False)

    res.to_csv(out_dir / "cv_predictions.csv", index=False)
    mis.to_csv(out_dir / "misclassified_files_for_review.csv", index=False)

    # curves for the Evaluate figures (drawn in the GUI without sklearn)
    with open(out_dir / "cv_curves.json", "w") as f:
        json.dump({
            "fpr": fpr.tolist(), "tpr": tpr.tolist(),
            "roc_optimal_idx": optimal_idx,
            "precision": prec_curve.tolist(), "recall": rec_curve.tolist(),
            "baseline_rate": float(np.mean(y)),
        }, f)

    metrics = {
        "model": "MiniRocket + RidgeClassifierCV (Binary)",
        "n_samples": int(len(y)),
        "n_strikes": int(y.sum()),
        "n_no_strikes": int((y == 0).sum()),
        "strike_rate": float(y.mean()),
        "class_weight": float(weight_map[data["class_names"][1]]),
        "n_channels": len(data["channels"]),
        "max_sequence_length": int(data["max_length"]),
        "channels": data["channels"],
        "cross_validation": {
            "n_folds": n_folds,
            **{f"mean_{k}": float(np.mean(v)) for k, v in cv_metrics.items()},
            **{f"std_{k}": float(np.std(v)) for k, v in cv_metrics.items()},
        },
        "out_of_fold_performance": {
            "roc_auc": float(final_auc),
            "pr_auc": float(pr_auc),
            "overall_accuracy": float(m["accuracy"]),
            "sensitivity": float(m["sensitivity"]),
            "specificity": float(m["specificity"]),
            "precision": float(m["precision"]),
            "f1_score": float(m["f1"]),
            "mcc": m["mcc"],
            "FNR": float(m["fn"] / (m["fn"] + m["tp"])) if (m["fn"] + m["tp"]) else 0.0,
            "FPR": float(m["fp"] / (m["fp"] + m["tn"])) if (m["fp"] + m["tn"]) else 0.0,
            "optimal_threshold": optimal_threshold,
            "confusion_matrix": {"tn": m["tn"], "fp": m["fp"],
                                 "fn": m["fn"], "tp": m["tp"]},
        },
        "performance_by_strike_type": {
            st: {"n_files": int(grp["file"].count()),
                 "accuracy": float(grp["correct"].mean())}
            for st, grp in res.groupby("strike_type")
        } if "strike_type" in res.columns else {},
        "misclassified": {"total": int(len(mis)),
                          "false_positives": n_fp,
                          "false_negatives": n_fn},
    }
    return metrics, res


# ── multiclass CV (port of 05_multiclass_collapsed.py) ───────────────────────

def run_cv_multiclass(cfg, data, out_dir, cv_idx, t0):
    from sklearn.metrics import (accuracy_score, confusion_matrix,
                                 precision_recall_fscore_support)

    X, y = data["X"], data["y"]
    fm = data["file_metadata"]
    class_names = data["class_names"]
    n_classes = len(class_names)
    weights, weight_map = sample_weights(cfg, y, class_names, "multiclass")

    n_folds = int(cfg["n_folds"])
    log(f"\n{n_folds}-Fold Stratified Cross-Validation")
    log(f"##STAGE cv {n_folds}")

    oof_preds = np.zeros(len(y), dtype=int)
    oof_probs = np.zeros((len(y), n_classes))
    fold_assignment = np.zeros(len(y), dtype=int)
    cv_metrics = {"accuracy": [], "macro_precision": [],
                  "macro_recall": [], "macro_f1": []}

    for fold, (tr, te) in enumerate(cv_idx):
        log(f"##FOLD {fold + 1} {n_folds}")
        pipe = build_pipeline(cfg)
        pipe.fit(X[tr], y[tr], ridgeclassifiercv__sample_weight=weights[tr])
        scores = pipe.decision_function(X[te])
        probs = _softmax(np.atleast_1d(scores))
        preds = probs.argmax(axis=1)

        oof_preds[te] = preds
        oof_probs[te] = probs
        fold_assignment[te] = fold

        acc = accuracy_score(y[te], preds)
        p, r, f1, _ = precision_recall_fscore_support(
            y[te], preds, average="macro", zero_division=0)
        for k, v in (("accuracy", acc), ("macro_precision", p),
                     ("macro_recall", r), ("macro_f1", f1)):
            cv_metrics[k].append(float(v))
        log(f"Fold {fold + 1}/{n_folds}: train={len(tr)}, test={len(te)} | "
            f"Accuracy={acc:.3f}, Macro-F1={f1:.3f}")

    overall_acc = accuracy_score(y, oof_preds)
    prec_all, rec_all, f1_all, support_all = precision_recall_fscore_support(
        y, oof_preds, labels=range(n_classes), average=None, zero_division=0)
    prec_ma, rec_ma, f1_ma, _ = precision_recall_fscore_support(
        y, oof_preds, average="macro", zero_division=0)
    cm = confusion_matrix(y, oof_preds, labels=range(n_classes))

    log(f"\nOverall Accuracy: {overall_acc:.3f} | Macro-F1: {f1_ma:.3f}")
    log(f"{'Class':14s} {'Precision':>10} {'Recall':>10} {'F1':>10} {'Support':>9}")
    for i, cn in enumerate(class_names):
        log(f"{cn:14s} {prec_all[i]:>10.3f} {rec_all[i]:>10.3f} "
            f"{f1_all[i]:>10.3f} {support_all[i]:>9d}")

    log("\nConfusion Matrix (rows=true, cols=pred):")
    log(" " * 14 + "".join(f"{cn:>12s}" for cn in class_names))
    for i, cn in enumerate(class_names):
        log(f"{cn:14s}" + "".join(f"{cm[i, j]:>12d}"
                                  for j in range(n_classes)))

    res = fm.copy()
    res["y_true"] = y
    res["y_pred"] = oof_preds
    res["true_class"] = [class_names[t] for t in y]
    res["pred_class"] = [class_names[p] for p in oof_preds]
    res["cv_fold"] = fold_assignment
    res["correct"] = res["y_pred"] == res["y_true"]
    res["confidence"] = oof_probs.max(axis=1)
    for i, cn in enumerate(class_names):
        res[f"prob_{cn}"] = oof_probs[:, i]
    mis = res[~res["correct"]].copy()
    log(f"\nMisclassified: {len(mis)}/{len(res)}")

    res.to_csv(out_dir / "cv_predictions.csv", index=False)
    mis.to_csv(out_dir / "misclassified_files_for_review.csv", index=False)

    # class-by-treatment table (predicted vs ground truth)
    rows = []
    if "treatment" in res.columns:
        for tx, grp in res.groupby("treatment"):
            n = len(grp)
            row = {"treatment": tx, "n_strikes": n}
            for i, cn in enumerate(class_names):
                row[f"n_pred_{cn}"] = int((grp["y_pred"] == i).sum())
                row[f"prop_pred_{cn}"] = round(
                    row[f"n_pred_{cn}"] / n, 4) if n else 0.0
                row[f"n_true_{cn}"] = int((grp["y_true"] == i).sum())
                row[f"prop_true_{cn}"] = round(
                    row[f"n_true_{cn}"] / n, 4) if n else 0.0
            rows.append(row)
    pd.DataFrame(rows).to_csv(out_dir / "class_by_treatment.csv", index=False)

    with open(out_dir / "cv_curves.json", "w") as f:
        json.dump({"confusion_matrix": cm.tolist()}, f)

    metrics = {
        "model": ("MiniRocket + RidgeClassifierCV "
                  f"(collapsed: {cfg.get('collapse_desc', '')})"),
        "scheme": cfg.get("collapse_scheme", ""),
        "target": f"{cfg['region_column']} (collapsed)",
        "region_to_class": {str(k): int(v)
                            for k, v in cfg["region_to_class"].items()},
        "include_surface_as_region1":
            "Y" if cfg.get("include_surface_as_region1") else "N",
        "n_surface_files": data["n_surface"],
        "n_samples": int(len(y)),
        "n_classes": n_classes,
        "class_names": class_names,
        "class_distribution": {class_names[i]: int((y == i).sum())
                               for i in range(n_classes)},
        "class_weights": weight_map,
        "n_channels": len(data["channels"]),
        "channels": data["channels"],
        "max_sequence_length": int(data["max_length"]),
        "cross_validation": {
            "n_folds": n_folds,
            **{f"mean_{k}": float(np.mean(v)) for k, v in cv_metrics.items()},
            **{f"std_{k}": float(np.std(v)) for k, v in cv_metrics.items()},
        },
        "out_of_fold_performance": {
            "overall_accuracy": float(overall_acc),
            "macro_precision": float(prec_ma),
            "macro_recall": float(rec_ma),
            "macro_f1": float(f1_ma),
            "confusion_matrix": cm.tolist(),
            "per_class_metrics": {
                class_names[i]: {
                    "precision": float(prec_all[i]),
                    "recall": float(rec_all[i]),
                    "f1_score": float(f1_all[i]),
                    "support": int(support_all[i]),
                } for i in range(n_classes)
            },
        },
        "misclassified": {
            "total": int(len(mis)),
            "by_true_class": {
                class_names[i]: int((mis["y_true"] == i).sum())
                for i in range(n_classes)
            },
        },
    }
    return metrics, res


# ── stages ───────────────────────────────────────────────────────────────────

def _cv_one_model(cfg, kind, out_dir):
    """Cross-validation (plus optional hold-out) for one pipeline stage."""
    from sklearn.model_selection import StratifiedKFold, train_test_split

    t0 = time.monotonic()
    out_dir.mkdir(parents=True, exist_ok=True)
    data = prepare_data(cfg, kind)
    X, y = data["X"], data["y"]

    # optional hold-out test split - the test set is only touched once,
    # after cross-validation, by a model fit on the whole training portion
    holdout = None
    train_idx = np.arange(len(y))
    if cfg.get("split_mode") == "holdout_cv":
        train_idx, test_idx = train_test_split(
            np.arange(len(y)), test_size=float(cfg.get("test_size", 0.2)),
            stratify=y, shuffle=True,
            random_state=int(cfg.get("random_seed", 42)))
        holdout = test_idx
        log(f"\nHold-out split: train={len(train_idx)}, "
            f"test={len(test_idx)} (stratified, "
            f"seed={cfg.get('random_seed', 42)})")

    data_cv = dict(data)
    data_cv["X"] = X[train_idx]
    data_cv["y"] = y[train_idx]
    data_cv["file_metadata"] = (
        data["file_metadata"].iloc[train_idx].reset_index(drop=True))

    skf = StratifiedKFold(n_splits=int(cfg["n_folds"]),
                          shuffle=bool(cfg.get("shuffle", True)),
                          random_state=int(cfg.get("random_seed", 42))
                          if cfg.get("shuffle", True) else None)
    cv_idx = list(skf.split(data_cv["X"], data_cv["y"]))

    if kind == "binary":
        metrics, res = run_cv_binary(cfg, data_cv, out_dir, cv_idx, t0)
    else:
        metrics, res = run_cv_multiclass(cfg, data_cv, out_dir, cv_idx, t0)

    # ---- hold-out evaluation (final, single use of the test set) ----
    if holdout is not None:
        log("\nHold-out test evaluation (model fit on the full training "
            "portion):")
        log("##STAGE holdout 1")
        weights, _ = sample_weights(cfg, data_cv["y"], data["class_names"],
                                    kind)
        pipe = build_pipeline(cfg)
        pipe.fit(data_cv["X"], data_cv["y"],
                 ridgeclassifiercv__sample_weight=weights)
        scores = pipe.decision_function(X[holdout])
        if kind == "binary":
            from sklearn.metrics import roc_auc_score
            probs = _sigmoid(scores)
            thr = metrics["out_of_fold_performance"]["optimal_threshold"]
            preds = (probs >= thr).astype(int)
            hm = binary_metrics_from_preds(y[holdout], preds)
            ho = {"n_test": int(len(holdout)),
                  "roc_auc": float(roc_auc_score(y[holdout], probs)),
                  "accuracy": float(hm["accuracy"]),
                  "sensitivity": float(hm["sensitivity"]),
                  "specificity": float(hm["specificity"]),
                  "threshold": float(thr)}
            log(f"  n={ho['n_test']}  AUC={ho['roc_auc']:.3f}  "
                f"Accuracy={ho['accuracy']:.3f}")
        else:
            from sklearn.metrics import accuracy_score, precision_recall_fscore_support
            probs = _softmax(np.atleast_1d(scores))
            preds = probs.argmax(axis=1)
            _, _, f1_ma, _ = precision_recall_fscore_support(
                y[holdout], preds, average="macro", zero_division=0)
            ho = {"n_test": int(len(holdout)),
                  "accuracy": float(accuracy_score(y[holdout], preds)),
                  "macro_f1": float(f1_ma)}
            log(f"  n={ho['n_test']}  Accuracy={ho['accuracy']:.3f}  "
                f"Macro-F1={ho['macro_f1']:.3f}")
        metrics["holdout_performance"] = ho

    metrics["training"] = provenance_section(cfg, data, t0, kind)
    with open(out_dir / "performance_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    log(f"\n{kind.capitalize()} cross-validation complete in "
        f"{time.monotonic() - t0:.1f} s. Outputs: {out_dir}")


def stage_cv(cfg, out_dir):
    np.random.seed(int(cfg.get("random_seed", 42)))

    log("=" * 60)
    log("STAGE 1 - Binary strike model (strike vs no-contact)")
    log("=" * 60)
    log("##MODEL binary")
    _cv_one_model(cfg, "binary", out_dir / "binary")

    if cfg.get("train_multiclass"):
        log("")
        log("=" * 60)
        log("STAGE 2 - Multiclass region model (ground-truth strikes)")
        log("=" * 60)
        log("##MODEL multiclass")
        _cv_one_model(cfg, "multiclass", out_dir / "multiclass")

    log("##DONE cv")


def _final_one_model(cfg, kind, out_dir):
    t0 = time.monotonic()
    out_dir.mkdir(parents=True, exist_ok=True)
    log(f"Training final {kind} deployment model on ALL training data")
    log("##STAGE final 1")
    data = prepare_data(cfg, kind)
    weights, _ = sample_weights(cfg, data["y"], data["class_names"], kind)

    pipe = build_pipeline(cfg)
    pipe.fit(data["X"], data["y"],
             ridgeclassifiercv__sample_weight=weights)
    joblib.dump(pipe, out_dir / "final_model_for_deployment.joblib")
    np.save(out_dir / "max_sequence_length.npy", data["max_length"])
    with open(out_dir / "channels.json", "w") as f:
        json.dump(data["channels"], f, indent=2)

    model_config = {
        "target_kind": kind,
        "channels": data["channels"],
        "n_channels": len(data["channels"]),
        "max_sequence_length": int(data["max_length"]),
        "padding": cfg.get("padding", "repeat_last"),
        "truncation": cfg.get("truncation", "truncate"),
        "n_training_observations": int(len(data["y"])),
        "class_names": data["class_names"],
        "trained": datetime.now().isoformat(timespec="seconds"),
        "training_config": {k: v for k, v in cfg.items()
                            if k not in ("app_version",)},
    }
    with open(out_dir / "model_config.json", "w") as f:
        json.dump(model_config, f, indent=2, default=str)

    log(f"\n✓ Final {kind} model trained on {len(data['y'])} observations "
        f"({time.monotonic() - t0:.1f} s)")
    log(f"  Channels: {len(data['channels'])}")
    log(f"  Sequence length: {data['max_length']}")
    log("  Saved final_model_for_deployment.joblib")


def stage_final(cfg, out_dir):
    np.random.seed(int(cfg.get("random_seed", 42)))
    log("##MODEL binary")
    _final_one_model(cfg, "binary", out_dir / "binary")
    if cfg.get("train_multiclass"):
        log("")
        log("##MODEL multiclass")
        _final_one_model(cfg, "multiclass", out_dir / "multiclass")
    log("##DONE final")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--stage", required=True, choices=["cv", "final"])
    args = ap.parse_args()

    with open(args.config, encoding="utf-8-sig") as f:
        cfg = json.load(f)
    out_dir = Path(cfg["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    # echo the configuration next to the outputs for provenance
    with open(out_dir / "train_config.json", "w") as f:
        json.dump(cfg, f, indent=2)

    if args.stage == "cv":
        stage_cv(cfg, out_dir)
    else:
        stage_final(cfg, out_dir)


if __name__ == "__main__":
    import traceback
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
