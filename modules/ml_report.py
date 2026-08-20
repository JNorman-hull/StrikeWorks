# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Blade Strike Analysis report: HTML builder, provenance and export.

The report is a structured HTML document (printable / saveable to PDF from
any browser) built from the shared PredictionState, so it uses exactly the
same prediction results and metadata as the Predict and Inspect tabs.

`export_analysis` produces the self-contained analysis package:

    BladeStrike_Analysis_<run_id>/
        report.html
        prediction_summary.csv
        predictions_per_file.csv
        region_summary.csv            (multiclass runs only)
        predicted_strike_rate.png/.svg
        predicted_strike_region.png/.svg  (multiclass runs only)
        provenance.json
"""
import base64
import json
import math
from datetime import datetime
from pathlib import Path

from . import ml_figures

_DARK  = "#1e3a5f"
_MUTED = "#64748b"
_BORD  = "#cbd5e1"


def _wilson_ci(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0, 0.0
    p      = k / n
    denom  = 1 + z ** 2 / n
    centre = (p + z ** 2 / (2 * n)) / denom
    half   = z * math.sqrt(p * (1 - p) / n + z ** 2 / (4 * n ** 2)) / denom
    return p, max(0.0, centre - half), min(1.0, centre + half)


def _esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _kv_table(rows):
    """Two-column key/value table."""
    body = "".join(
        f"<tr><td style='color:{_MUTED};padding:2px 14px 2px 0;"
        f"white-space:nowrap;'>{_esc(k)}</td>"
        f"<td style='padding:2px 0;'>{_esc(v)}</td></tr>"
        for k, v in rows)
    return f"<table cellspacing='0' cellpadding='0'>{body}</table>"


def _data_table(headers, rows):
    head = "".join(
        f"<th style='border-bottom:2px solid {_BORD};padding:4px 10px;"
        f"text-align:left;color:{_DARK};'>{_esc(h)}</th>" for h in headers)
    body = ""
    for r in rows:
        cells = "".join(
            f"<td style='border-bottom:1px solid {_BORD};"
            f"padding:3px 10px;'>{_esc(c)}</td>" for c in r)
        body += f"<tr>{cells}</tr>"
    return (f"<table cellspacing='0' cellpadding='0' "
            f"style='margin:6px 0;'>"
            f"<tr>{head}</tr>{body}</table>")


def _img_tag(path, embed):
    path = Path(path)
    if not path.exists():
        return ""
    if embed:
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        src = f"data:image/png;base64,{data}"
    else:
        src = path.as_uri()
    return (f"<img src='{src}' width='560' "
            f"style='margin:8px 16px 8px 0;'/>")


# ═════════════════════════════════════════════════════════════════════════════
def build_report_html(state, image_paths=None, embed_images=False):
    """Assemble the full report. `image_paths` maps figure name -> file."""
    s = state
    prov = s.provenance()
    meta = s.run_meta or {}
    image_paths = image_paths or {}
    na = "Not available"

    h = []
    h.append(
        "<div style='font-family:Segoe UI, Arial, sans-serif;"
        "color:#1e293b;font-size:13px;'>")
    h.append(f"<h1 style='color:{_DARK};'>Blade Strike Analysis Report</h1>")
    if s.summary is None:
        h.append(f"<p style='color:{_MUTED};'>No prediction has been run yet. "
                 "Run a prediction on the Predict tab, then refresh this "
                 "report.</p></div>")
        return "".join(h)

    n = int(meta.get("n_files", s.summary["n"].sum()))
    k = int(meta.get("n_strike", s.summary["n_strike"].sum()))
    rate, lo, hi = _wilson_ci(k, n)
    mode = meta.get("mode", s.mode)
    mc_run = mode == "multiclass"

    # ── analysis overview ────────────────────────────────────────────────────
    h.append(f"<h2 style='color:{_DARK};'>Analysis overview</h2>")
    tx = s.dataset_meta.get("treatments")
    h.append(_kv_table([
        ("Dataset",        s.dataset_meta.get("name", na)),
        ("Dataset source", s.dataset_source or na),
        ("Date / time",    meta.get("timestamp", na)),
        ("Recordings",     n),
        ("Treatments",     ", ".join(tx) if tx else na),
        ("Model",          prov["model"]["binary_model"]),
        ("Model version",  _model_version_text(s)),
        ("Prediction mode", "Binary + multiclass (two-stage)" if mc_run
                            else "Binary (strike / no strike)"),
    ]))

    # ── model ────────────────────────────────────────────────────────────────
    h.append(f"<h2 style='color:{_DARK};'>Model</h2>")
    bm = s.bin_metrics or {}
    perf = bm.get("out_of_fold_performance", {})
    rows = [
        ("Binary model",  prov["model"]["binary_model"]),
        ("Model type",    bm.get("model", na)),
        ("Configuration", "Two-stage: binary strike detection followed by "
                          "pump-region classification of predicted strikes"
                          if mc_run else
                          "Single stage: binary strike detection"),
        ("Input channels", ", ".join(bm.get("channels", [])) or na),
        ("Sequence length", f"{bm.get('max_sequence_length', na)} samples"),
        ("Decision threshold", _threshold_text(s)),
    ]
    for key, label in (("overall_accuracy", "Accuracy"),
                       ("sensitivity", "Sensitivity"),
                       ("specificity", "Specificity"),
                       ("roc_auc", "ROC AUC")):
        if key in perf:
            rows.append((f"Binary {label.lower()} (out-of-fold)",
                         f"{perf[key]:.3f}"))
    if mc_run and s.mc_metrics:
        mperf = s.mc_metrics.get("out_of_fold_performance", {})
        rows.append(("Multiclass model", prov["model"]["multiclass_model"]))
        rows.append(("Classes", ", ".join(s.class_names)))
        if "overall_accuracy" in mperf:
            rows.append(("Multiclass accuracy (out-of-fold)",
                         f"{mperf['overall_accuracy']:.3f}"))
    h.append(_kv_table(rows))

    # ── prediction results ───────────────────────────────────────────────────
    h.append(f"<h2 style='color:{_DARK};'>Prediction results</h2>")
    mean_conf = (f"{float(s.predictions['confidence'].mean()):.3f}"
                 if s.predictions is not None else na)
    h.append(_kv_table([
        ("Total recordings",        n),
        ("Total predicted strikes", k),
        ("Overall strike rate",     f"{rate * 100:.1f}%"),
        ("95% CI (Wilson)",         f"{lo * 100:.1f}% – {hi * 100:.1f}%"),
        ("Mean confidence",         mean_conf),
        ("Elapsed time",            f"{meta.get('elapsed_s', na)} s"),
    ]))

    # ── results by treatment ─────────────────────────────────────────────────
    h.append(f"<h2 style='color:{_DARK};'>Results by treatment</h2>")
    headers = ["Treatment", "N", "Strikes", "No strike", "Strike rate",
               "95% CI", "Mean conf"]
    rows = []
    for _, r in s.summary.iterrows():
        rows.append([
            r["treatment"], int(r["n"]), int(r["n_strike"]),
            int(r["n_no_strike"]),
            f"{r['strike_rate'] * 100:.1f}%",
            f"{r['ci_lo'] * 100:.1f}% – {r['ci_hi'] * 100:.1f}%",
            f"{r['mean_conf']:.3f}",
        ])
    h.append(_data_table(headers, rows))

    # ── strike classification (multiclass) ───────────────────────────────────
    if mc_run and s.region_summary is not None and len(s.region_summary):
        h.append(f"<h2 style='color:{_DARK};'>Strike classification</h2>")
        totals = (s.region_summary.groupby("region")["n"].sum()
                  .reindex(s.class_names))
        tot_strikes = int(totals.sum())
        rows = [[cn, int(totals[cn]),
                 f"{(totals[cn] / tot_strikes * 100):.1f}%"
                 if tot_strikes else "0.0%"]
                for cn in s.class_names]
        h.append("<p style='margin:4px 0;color:#1e293b;'>"
                 "Predicted class distribution among strikes:</p>")
        h.append(_data_table(["Class / region", "N", "Proportion"], rows))

        h.append("<p style='margin:4px 0;color:#1e293b;'>"
                 "Treatment × class summary:</p>")
        rows = [[r["treatment"], r["region"], int(r["n"]),
                 f"{r['proportion'] * 100:.1f}%"]
                for _, r in s.region_summary.iterrows()]
        h.append(_data_table(["Treatment", "Class", "N", "Share of strikes"],
                             rows))

    # ── figures ──────────────────────────────────────────────────────────────
    figs = [p for p in (image_paths.get("predicted_strike_rate"),
                        image_paths.get("predicted_strike_region")) if p]
    if figs:
        h.append(f"<h2 style='color:{_DARK};'>Figures</h2>")
        for p in figs:
            h.append(_img_tag(p, embed_images))

    # ── data quality / validation ────────────────────────────────────────────
    h.append(f"<h2 style='color:{_DARK};'>Data quality &amp; validation</h2>")
    icon = {"ok": "✓", "warn": "⚠", "fail": "✗", "off": "–"}
    rows = [(icon.get(state_, "–") + " " + label, detail or "")
            for state_, label, detail in s.checks]
    h.append(_kv_table(rows) if rows else
             f"<p style='color:{_MUTED};'>{na}</p>")
    if s.dataset_meta.get("annotated"):
        h.append("<p>The dataset carries ground-truth annotation labels; "
                 "prediction accuracy can be reviewed per recording on the "
                 "Inspect tab.</p>")

    # ── notes / warnings ─────────────────────────────────────────────────────
    warnings = [f"{label}: {detail}" for st, label, detail in s.checks
                if st == "warn"]
    if meta.get("threshold_overridden"):
        warnings.append(
            f"The deployed decision threshold "
            f"({meta.get('deployed_threshold', na)}) was overridden by the "
            f"user to {meta.get('threshold', na)}.")
    h.append(f"<h2 style='color:{_DARK};'>Notes &amp; warnings</h2>")
    if warnings:
        h.append("<ul>" + "".join(f"<li>{_esc(w)}</li>" for w in warnings)
                 + "</ul>")
    else:
        h.append("<p>No warnings were generated during this analysis.</p>")

    # ── provenance ───────────────────────────────────────────────────────────
    h.append(f"<h2 style='color:{_DARK};'>Provenance</h2>")
    for section, title in (("dataset", "Dataset"), ("model", "Model"),
                           ("analysis", "Analysis"), ("outputs", "Outputs")):
        h.append(f"<h3 style='color:{_DARK};margin-bottom:2px;'>{title}</h3>")
        rows = []
        for kk, vv in prov[section].items():
            if isinstance(vv, dict):
                vv = ", ".join(f"{a} {b}" for a, b in vv.items())
            elif isinstance(vv, list):
                vv = ", ".join(str(x) for x in vv)
            rows.append((kk.replace("_", " "), vv))
        h.append(_kv_table(rows))

    h.append(f"<p style='color:{_MUTED};font-size:11px;margin-top:16px;'>"
             f"Generated by {prov['analysis']['application']} on "
             f"{datetime.now().strftime('%Y-%m-%d %H:%M')}.</p>")
    h.append("</div>")
    return "".join(h)


def _model_version_text(state):
    from .ml_tab_predict import _model_version
    v = _model_version(state.bin_model_path)
    return v if v else "Not available"


def _threshold_text(state):
    meta = state.run_meta or {}
    thr = meta.get("threshold", state.effective_threshold)
    if thr is None:
        return "Not available"
    if meta.get("threshold_overridden"):
        return (f"{thr:.4f} (user override; deployed "
                f"{meta.get('deployed_threshold', '?')})")
    return f"{thr:.4f} (deployed optimal threshold)"


def wrap_html_document(body_html):
    """Standalone HTML file around the report body (print/PDF friendly)."""
    return ("<!DOCTYPE html><html><head><meta charset='utf-8'/>"
            "<title>Blade Strike Analysis Report</title>"
            "<style>body{max-width:900px;margin:24px auto;padding:0 16px;"
            "background:#ffffff;} @media print {body{margin:0;}}</style>"
            f"</head><body>{body_html}</body></html>")


# ═════════════════════════════════════════════════════════════════════════════
def export_analysis(state, parent_dir):
    """Create the self-contained analysis package. Returns its Path."""
    if state.summary is None or state.run_id is None:
        raise RuntimeError("No prediction run to export.")

    out = Path(parent_dir) / f"BladeStrike_Analysis_{state.run_id}"
    out.mkdir(parents=True, exist_ok=True)

    # tables (reuse the worker's outputs rather than recomputing)
    state.summary.to_csv(out / "prediction_summary.csv", index=False)
    if state.predictions is not None:
        state.predictions.to_csv(out / "predictions_per_file.csv", index=False)
    if state.region_summary is not None:
        state.region_summary.to_csv(out / "region_summary.csv", index=False)

    # figures (PNG for the report + SVG vector versions)
    figs = ml_figures.render_figures(state, out, formats=("png", "svg"))
    image_paths = {name: paths[0] for name, paths in figs.items()}

    # report with embedded figures - fully self-contained
    body = build_report_html(state, image_paths=image_paths,
                             embed_images=True)
    (out / "report.html").write_text(wrap_html_document(body),
                                     encoding="utf-8")

    # provenance
    prov = state.provenance()
    prov["outputs"]["package"] = out.name
    prov["outputs"]["package_files"] = sorted(p.name for p in out.glob("*"))
    with open(out / "provenance.json", "w", encoding="utf-8") as f:
        json.dump(prov, f, indent=2, default=str)

    return out


def export_tables(state, target_dir):
    """Export the prediction tables to a chosen folder. Returns file names."""
    target = Path(target_dir)
    written = []
    if state.summary is not None:
        state.summary.to_csv(target / "prediction_summary.csv", index=False)
        written.append("prediction_summary.csv")
    if state.predictions is not None:
        state.predictions.to_csv(target / "predictions_per_file.csv",
                                 index=False)
        written.append("predictions_per_file.csv")
    if state.region_summary is not None:
        state.region_summary.to_csv(target / "region_summary.csv", index=False)
        written.append("region_summary.csv")
    return written


def export_figures(state, target_dir, formats=("png", "svg")):
    """Export the prediction figures. Returns file names."""
    figs = ml_figures.render_figures(state, Path(target_dir), formats=formats)
    return [p.name for paths in figs.values() for p in paths]
