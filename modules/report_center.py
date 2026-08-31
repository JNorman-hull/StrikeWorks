# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Central reporting hub - one place every page's report comes from.

Before this module, six pages each built their own report widget in their
own format: BSM (Analysis and reporting), Model training > Evaluate, Model
prediction > Report, Misclassification, Annotate (a Markdown outlier), plus
Study design, Raw data processing and Biological interpretation which had
no report at all. That is one thing to keep consistent per page instead of
one shared implementation, and it left the "Final reporting" page a stub
with nothing to build against.

This module is the shared implementation. Each ``ReportSection`` below
knows how to (a) tell cheaply whether it currently has anything to report,
and (b) build its HTML body - reusing the exact same primitives
(``ml_report._kv_table`` / ``_data_table`` / ``_img_tag`` / ``_DARK``) the
Model prediction and BSM reports already used, so every section looks the
same regardless of source. ``ml_tab_report.py`` (Model Prediction > Report)
is the UI: a checklist of these sections and one "Generate report" action
that calls ``assemble()``.

Every generated report is written under ``OUTPUT_DATA_DIR`` - one place for
every report's output, rather than each page picking its own folder
(a user-chosen dialog, a library-relative path, or nothing at all).
"""
from datetime import datetime
from pathlib import Path

from . import ml_report

OUTPUT_DATA_DIR = Path(__file__).resolve().parent.parent / "output_data"

_HR = "<hr style='margin:32px 0;border:none;border-top:2px solid #cbd5e1;'/>"


class ReportSection:
    """One report source: cheap availability check + HTML body builder.

    ``build(out_dir)`` renders whatever figures it needs into `out_dir` and
    returns ``{"html": str, "tables": {name: DataFrame}}`` (or ``None`` if,
    despite `available`, it turns out there is nothing to write). Figures
    are embedded as base64 directly into the HTML (the same
    `embed_images=True` convention every existing report builder already
    uses), so `assemble()` itself never has to know about images.
    """

    def __init__(self, key, title, available, reason, build):
        self.key = key
        self.title = title
        self.available = available
        self.reason = reason
        self.build = build


def default_output_dir():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return OUTPUT_DATA_DIR / f"Report_{ts}"


def _wrap_document(body_html, title="StrikeWorks Report"):
    """Sized for an A4 page with narrow margins - `ml_report.A4_REPORT_CSS`,
    shared with every other report wrapper so they all print the same."""
    return ("<!DOCTYPE html><html><head><meta charset='utf-8'/>"
            f"<title>{title}</title>"
            f"<style>{ml_report.A4_REPORT_CSS}</style>"
            f"</head><body>{body_html}</body></html>")


def _git_remote_url(root):
    """`origin`'s URL if `root` is a git repository with one, else None."""
    cfg = Path(root) / ".git" / "config"
    if not cfg.exists():
        return None
    try:
        text = cfg.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None
    in_origin = False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            in_origin = line.startswith("[remote") and '"origin"' in line
            continue
        if in_origin and line.startswith("url"):
            return line.split("=", 1)[1].strip()
    return None


def assemble(sections, out_dir, checked_keys):
    """Build one combined report from the checked, available `sections`.

    Returns (report_html_path, warnings) - `warnings` lists sections that
    were checked but failed to build (e.g. figures could not be rendered),
    so a partial report is still produced rather than the whole action
    failing over one section.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    body_parts = []
    warnings = []
    for sec in sections:
        if sec.key not in checked_keys or not sec.available:
            continue
        try:
            content = sec.build(out_dir)
        except Exception as e:
            warnings.append(f"{sec.title}: failed to build ({e})")
            continue
        if not content or not content.get("html"):
            warnings.append(f"{sec.title}: nothing to report")
            continue
        body_parts.append(content["html"])
        for name, table in (content.get("tables") or {}).items():
            try:
                table.to_csv(out_dir / f"{sec.key}_{name}.csv", index=False)
            except Exception:
                pass

    if not body_parts:
        raise RuntimeError("None of the checked sections had data to report.")

    body = "<div>" + _HR.join(body_parts) + "</div>"
    doc_path = out_dir / "report.html"
    doc_path.write_text(_wrap_document(body), encoding="utf-8")
    return doc_path, warnings


# ═════════════════════════════════════════════════════════════════════════════
# Section factories. Each takes the MainWindow (so it can reach whichever
# page/state it needs via getattr(..., None) - safe even before every page
# has finished constructing, since only the *cheap* availability check runs
# eagerly; `build()` itself is only ever called once the app is fully up).
# ═════════════════════════════════════════════════════════════════════════════
def bsm_section(window):
    sens = getattr(window, "bsm_sensitivity_page", None)
    bsm_state = getattr(window, "bsm_state", None)
    res = bsm_state.last_result if bsm_state is not None else None
    available = res is not None and sens is not None
    reason = "" if available else "Run a calculation on Calculator first."

    def build(out_dir):
        from . import bsm_io
        from .bsm_report import build_bsm_report_html
        res_ = bsm_state.last_result
        if res_ is None:
            return None
        fig_dir = out_dir / "bsm_figures"
        fig_dir.mkdir(parents=True, exist_ok=True)
        image_paths = {}
        try:
            bsm_io.export_results(res_, sens.fig_pco, sens.fig_pm, fig_dir)
            image_paths["pco"] = fig_dir / "barplot_pco.png"
            image_paths["pm"] = fig_dir / "barplot_pm.png"
            if getattr(sens, "wf_q_curves", None):
                bsm_io.export_sweep_lines(
                    sens.wf_q_curves, sens.fig_wf_q, fig_dir,
                    stem="sensitivity_pco_wf_by_q", x_header="wf_m_per_s",
                    line_header="flow", y_header="pco_percent")
                image_paths["wf_q"] = fig_dir / "sensitivity_pco_wf_by_q.png"
            if getattr(sens, "n_q_curves", None):
                bsm_io.export_sweep_lines(
                    sens.n_q_curves, sens.fig_n_q, fig_dir,
                    stem="sensitivity_pm_n_by_q", x_header="N_rpm",
                    line_header="flow", y_header="pm_percent")
                image_paths["n_q"] = fig_dir / "sensitivity_pm_n_by_q.png"
            if getattr(sens, "wf_pm_sweep", None):
                bsm_io.export_sensitivity(
                    *sens.wf_pm_sweep, sens.fig_wf_pm, fig_dir,
                    stem="sensitivity_pm_wf", x_header="wf_m_per_s")
                image_paths["wf_pm"] = fig_dir / "sensitivity_pm_wf.png"
        except Exception:
            pass
        html = build_bsm_report_html(res_, image_paths=image_paths,
                                     embed_images=True)
        return {"html": html}

    return ReportSection("bsm", "Blade strike modelling (mathematical)",
                         available, reason, build)


def study_design_section(window):
    # The precision calculator (Study design) always has a value - it
    # opens with sensible defaults rather than requiring input - so this
    # section is always available; the deployment plan half is folded in
    # underneath it only once a library is selected.
    prep = getattr(window, "prepare_page", None)
    precision = getattr(prep, "tab_precision", None) if prep is not None else None
    dep = getattr(window, "initiate_deployment_page", None)
    available = precision is not None
    reason = "" if available else "Study design tab not built yet."

    def build(out_dir):
        if precision is None:
            return None
        from . import deployment_index as di
        kv, table, esc, dark = (ml_report._kv_table, ml_report._data_table,
                                ml_report._esc, ml_report._DARK)

        h = ["<div style='font-family:Segoe UI, Arial, sans-serif;"
             "color:#1e293b;font-size:13px;'>"]
        h.append(f"<h1 style='color:{dark};'>Study Design Report</h1>")

        h.append(f"<h2 style='color:{dark};'>Sampling precision</h2>")
        if precision.lbl_result.text():
            h.append(f"<p>{esc(precision.lbl_result.text())}</p>")
        t = precision.tbl_sweep
        rows = [[t.item(r, c).text() if t.item(r, c) else ""
                 for c in range(t.columnCount())]
                for r in range(t.rowCount())]
        headers = [t.horizontalHeaderItem(c).text()
                  for c in range(t.columnCount())]
        if rows:
            h.append(table(headers, rows))
        fig_dir = out_dir / "study_design_figures"
        fig_dir.mkdir(parents=True, exist_ok=True)
        try:
            png = fig_dir / "precision_ci_vs_n.png"
            precision.fig_precision.savefig(png, dpi=200, bbox_inches="tight")
            h.append(ml_report._img_tag(png, True))
        except Exception:
            pass

        root = getattr(dep, "_lib_root", None) if dep is not None else None
        if root is None:
            h.append("</div>")
            return {"html": "".join(h)}

        h.append(f"<h2 style='color:{dark};'>Library</h2>")
        h.append(kv([
            ("Library name", root.name),
            ("Storage location", str(root)),
            ("GitHub remote", _git_remote_url(root) or
                              "Not a git repository / no remote configured"),
        ]))

        h.append(f"<h2 style='color:{dark};'>Folder structure</h2>")
        h.append(kv([
            ("Raw sensor data", f"{root.name}/raw_sens_data/<deployment id>/"
                                "<treatment>/"),
            ("Raw video",       f"{root.name}/raw_sens_data/<deployment id>/"
                                "VIDEO/"),
            ("Sensor index",    f"{root.name}/processed_sens_data/index/"
                                "global_sensor_index.csv"),
            ("Processed CSV",   f"{root.name}/processed_sens_data/csv/"),
            ("Nadir windows",   f"{root.name}/processed_sens_data/"
                                "nadir_window/"),
            ("Model dataset",   f"{root.name}/processed_sens_data/"
                                "model_features.csv"),
        ]))

        deployments = di.deployments(root)
        h.append(f"<h2 style='color:{dark};'>Deployments</h2>")
        if deployments:
            headers = [label for _, label in di.DEPLOYMENT_FIELDS]
            rows = [[d.get(c, "") for c, _ in di.DEPLOYMENT_FIELDS]
                    for d in deployments]
            h.append(table(headers, rows))
        else:
            h.append("<p style='color:#64748b;'>No deployment plan recorded "
                     "yet.</p>")

        headers = [label for _, label in di.TREATMENT_FIELDS] + ["Runs"]
        for dep_entry in deployments:
            ident = dep_entry.get("deployment_id", "")
            tx = di.treatments(root, ident)
            if not tx:
                continue
            h.append(f"<h3 style='color:{dark};'>Treatments &mdash; "
                     f"{di.describe_deployment(dep_entry)}</h3>")
            rows = [[t.get(c, "") for c, _ in di.TREATMENT_FIELDS] +
                    [t.get("runs", "")] for t in tx]
            h.append(table(headers, rows))
        if not deployments:
            tx = di.treatments(root)
            if tx:
                h.append(f"<h3 style='color:{dark};'>Treatments</h3>")
                rows = [[t.get(c, "") for c, _ in di.TREATMENT_FIELDS] +
                        [t.get("runs", "")] for t in tx]
                h.append(table(headers, rows))

        h.append("</div>")
        return {"html": "".join(h)}

    return ReportSection("study_design", "Study design", available, reason,
                         build)


def _files_dataframe(files):
    import pandas as pd
    return pd.DataFrame([{
        "file": f["stem"], "sensor": f["sensor"], "date": f["date"],
        "time": f["time"], "complete": f["complete"],
        "processed": f["processed"],
    } for f in files])


def process_section(window):
    proc = getattr(window, "process_page", None)
    files = getattr(proc, "_files", None) if proc is not None else None
    available = bool(files)
    reason = "" if available else "Scan a folder on Raw data processing first."

    def build(out_dir):
        files_ = getattr(proc, "_files", None)
        if not files_:
            return None
        kv, table, dark = ml_report._kv_table, ml_report._data_table, ml_report._DARK
        n = len(files_)
        n_complete = sum(1 for f in files_ if f["complete"])
        n_proc = sum(1 for f in files_ if f["processed"])
        sensors = {}
        for f in files_:
            sensors[f["sensor"]] = sensors.get(f["sensor"], 0) + 1

        h = ["<div style='font-family:Segoe UI, Arial, sans-serif;"
             "color:#1e293b;font-size:13px;'>"]
        h.append(f"<h1 style='color:{dark};'>Raw Data Processing Report</h1>")
        h.append(kv([
            ("Scanned folder", str(getattr(proc, "_scan_dir", "") or "")),
            ("Library", str(getattr(proc, "_root", "") or "Not set")),
            ("Sensor files found", n),
            ("Complete recordings", f"{n_complete}/{n}"),
            ("Already processed", f"{n_proc}/{n}"),
            ("Distinct sensors", len(sensors)),
        ]))
        h.append(f"<h2 style='color:{dark};'>Files by sensor</h2>")
        rows = sorted(sensors.items(), key=lambda kv_: -kv_[1])
        h.append(table(["Sensor", "Files"], rows))
        h.append("</div>")
        return {"html": "".join(h),
                "tables": {"inventory": _files_dataframe(files_)}}

    return ReportSection("process", "Raw data processing", available, reason,
                         build)


def annotation_section(window):
    ann = getattr(window, "annotation_page", None)
    lib_root = getattr(ann, "_lib_root", None) if ann is not None else None
    available = lib_root is not None
    reason = "" if available else "Select a library on Validate and annotate first."

    def build(out_dir):
        root = getattr(ann, "_lib_root", None)
        if root is None:
            return None
        df = ann._library_sensor_rows()
        if df is None:
            return None
        from .deployment_index import BAD_SENS_COL
        kv, table, dark = ml_report._kv_table, ml_report._data_table, ml_report._DARK

        total = len(df)
        in_dataset = len(ann._dataset_stems)
        bad = 0
        if BAD_SENS_COL in df.columns:
            bad = int((df[BAD_SENS_COL].astype(str).str.strip().str.upper()
                      == "Y").sum())

        h = ["<div style='font-family:Segoe UI, Arial, sans-serif;"
             "color:#1e293b;font-size:13px;'>"]
        h.append(f"<h1 style='color:{dark};'>Annotation Report</h1>")
        h.append(kv([
            ("Library", root.name),
            ("Sensors in index", total),
            ("In dataset (annotated + saved)", in_dataset),
            ("Not yet in dataset", total - in_dataset),
            ("Flagged bad", bad),
        ]))

        by_var = {}
        for label, value, count in ann._variable_value_counts(df):
            by_var.setdefault(label, []).append((value, count))
        if by_var:
            for label, values in by_var.items():
                h.append(f"<h3 style='color:{dark};'>{label}</h3>")
                h.append(table(["Value", "Count"], values))
        else:
            h.append("<p style='color:#64748b;'>No annotation values "
                     "recorded yet.</p>")
        h.append("</div>")
        return {"html": "".join(h)}

    return ReportSection("annotation", "Annotation", available, reason, build)


def available_model_entries(window):
    """Every model that can be reported on: this session's freshly
    trained binary/multiclass (if any) plus every model deployed to the
    models folder - the same list Evaluate and Misclassification analysis
    already offer in their own combos. Shared so the Report page's own
    per-section model picker (`training_section`/`misclassification_
    section`) doesn't depend on whichever model happens to be selected on
    either of those other pages right now."""
    tp = getattr(window, "ml_training_page", None)
    training_state = getattr(tp, "state", None) if tp is not None else None
    mp = getattr(window, "ml_prediction_page", None)
    pred_state = getattr(mp, "state", None) if mp is not None else None
    models_dir = getattr(pred_state, "models_dir", None) if pred_state else None

    from . import ml_model_library
    entries = []
    if training_state is not None:
        entries += ml_model_library.session_entries(training_state)
    if models_dir is not None:
        entries += ml_model_library.discover_models(models_dir)
    return entries


def training_section(window, get_entry):
    """`get_entry()` - a no-arg callable, typically the Report page's own
    model-picker combo's `currentData` - returns the `ModelEntry` to
    report on, called at build time so it always reflects whichever
    model is currently selected there, not whatever was last opened on
    Model training > Evaluate."""
    available = bool(available_model_entries(window))
    reason = "" if available else "No trained or deployed models found."

    def build(out_dir):
        entry_ = get_entry()
        if entry_ is None:
            return None
        from . import ml_model_library, ml_train_figures
        fig_dir = out_dir / "training_figures"
        fig_dir.mkdir(parents=True, exist_ok=True)
        image_paths = {}
        try:
            figs = ml_train_figures.render_model_figures(
                fig_dir, entry_.metrics, entry_.cv_predictions,
                entry_.curves, formats=("png",))
            image_paths = {name: paths[0] for name, paths in figs.items()}
        except Exception:
            pass
        mp = getattr(window, "ml_prediction_page", None)
        pred_state = getattr(mp, "state", None) if mp is not None else None
        app_version = getattr(pred_state, "app_version", "") if pred_state else ""
        html = ml_model_library.build_model_report_html(
            entry_, image_paths=image_paths, embed_images=True,
            app_version=app_version)
        return {"html": html}

    return ReportSection("training", "Model training", available, reason,
                         build)


def misclassification_section(window, get_entry):
    """Same per-section model picker as `training_section` - `get_entry()`
    chooses which model's misclassifications to report, independent of
    whatever's currently selected on the Misclassification analysis page
    itself. Reuses that page's own `_misclassified_rows`/`_video_index` so
    the content matches exactly what it would show for the same model."""
    mis = getattr(window, "misclassification_page", None)
    available = mis is not None and bool(available_model_entries(window))
    reason = "" if available else "No trained or deployed models found."

    def build(out_dir):
        entry_ = get_entry()
        if entry_ is None or mis is None:
            return None
        from .page_misclassification import _misclassified_rows
        rows = _misclassified_rows(entry_)
        if not rows:
            return None
        video_index = mis._video_index()
        for r in rows:
            r["video_matches"] = video_index.get(str(r["file"]), [])

        kv, table, esc, dark = (ml_report._kv_table, ml_report._data_table,
                                ml_report._esc, ml_report._DARK)
        h = ["<div style='font-family:Segoe UI, Arial, sans-serif;"
             "color:#1e293b;font-size:13px;'>"]
        h.append(f"<h1 style='color:{dark};'>Misclassification Report</h1>")
        h.append(f"<h2 style='color:{dark};'>{esc(entry_.label)}</h2>")
        h.append(f"<p>{len(rows)} misclassified recording(s).</p>")
        rows_ = [[r["file"], f"{r['true']} → {r['pred']}",
                  f"{r['confidence']:.3f}", r["treatment"],
                  "; ".join(dict.fromkeys(
                      p.name for p in r.get("video_matches", [])))
                  or "—"] for r in rows]
        h.append(table(["File", "True → Predicted", "Confidence",
                        "Treatment", "Video"], rows_))

        # session corrections are page-local editing state, not part of
        # any deployed/session model's own data - only meaningful when
        # the picked entry is the one actively being corrected right now
        if getattr(mis, "_entry", None) is entry_ and getattr(mis, "_corrections", None):
            h.append(f"<h2 style='color:{dark};'>Changes made this "
                     "session</h2>")
            rows_ = [[c["file"], c["variable"], c["old"], c["new"], c["when"]]
                     for c in mis._corrections]
            h.append(table(["File", "Variable", "Old value", "New value",
                            "When"], rows_))
        h.append("</div>")
        return {"html": "".join(h)}

    return ReportSection("misclassification", "Misclassification analysis",
                         available, reason, build)


def deployment_summary_section(window):
    mp = getattr(window, "ml_prediction_page", None)
    state = getattr(mp, "state", None) if mp is not None else None
    models_dir = getattr(state, "models_dir", None) if state is not None else None
    entries = []
    if models_dir is not None:
        from .ml_model_library import discover_models
        entries = discover_models(models_dir)
    available = bool(entries)
    reason = "" if available else "No deployed models found."

    def build(out_dir):
        if not entries:
            return None
        kv, table, dark = ml_report._kv_table, ml_report._data_table, ml_report._DARK
        h = ["<div style='font-family:Segoe UI, Arial, sans-serif;"
             "color:#1e293b;font-size:13px;'>"]
        h.append(f"<h1 style='color:{dark};'>Model Deployment Summary</h1>")
        h.append(kv([("Models folder", str(models_dir)),
                     ("Deployed models", len(entries))]))
        rows = []
        for e in entries:
            perf = (e.metrics or {}).get("out_of_fold_performance", {})
            rows.append([
                Path(e.model_path).name if e.model_path else e.label,
                e.kind, e.version or "",
                (f"{perf['overall_accuracy']:.3f}"
                 if "overall_accuracy" in perf else "—"),
                f"{perf['roc_auc']:.3f}" if "roc_auc" in perf else "—",
            ])
        h.append(table(["Model file", "Stage", "Version", "Accuracy",
                        "ROC AUC"], rows))
        h.append("</div>")
        return {"html": "".join(h)}

    return ReportSection("deployment", "Model deployment summary", available,
                         reason, build)


def prediction_section(window):
    mp = getattr(window, "ml_prediction_page", None)
    state = getattr(mp, "state", None) if mp is not None else None
    available = state is not None and state.summary is not None
    reason = "" if available else "Run a prediction on the Predict tab first."

    def build(out_dir):
        if state is None or state.summary is None:
            return None
        from . import ml_figures
        fig_dir = out_dir / "prediction_figures"
        fig_dir.mkdir(parents=True, exist_ok=True)
        try:
            figs = ml_figures.render_figures(state, fig_dir, formats=("png",))
            image_paths = {name: paths[0] for name, paths in figs.items()}
        except Exception:
            image_paths = {}
        html = ml_report.build_report_html(state, image_paths=image_paths,
                                           embed_images=True)
        tables = {"prediction_summary": state.summary}
        if state.predictions is not None:
            tables["predictions_per_file"] = state.predictions
        if state.region_summary is not None:
            tables["region_summary"] = state.region_summary
        return {"html": html, "tables": tables}

    return ReportSection("prediction", "Model prediction", available, reason,
                         build)


def biological_section(window):
    bio = getattr(window, "biological_page", None)
    bsm_state = getattr(bio, "bsm_state", None) if bio is not None else None
    available = bsm_state is not None and bsm_state.last_result is not None
    reason = "" if available else "Run a Blade Strike Modelling calculation first."

    def build(out_dir):
        if bio is None:
            return None
        esc, table, dark = ml_report._esc, ml_report._data_table, ml_report._DARK
        fig_dir = out_dir / "biological_figures"
        fig_dir.mkdir(parents=True, exist_ok=True)

        h = ["<div style='font-family:Segoe UI, Arial, sans-serif;"
             "color:#1e293b;font-size:13px;'>"]
        h.append(f"<h1 style='color:{dark};'>Biological Interpretation "
                 "Report</h1>")
        h.append(f"<h2 style='color:{dark};'>Comparison: ML vs Blade Strike "
                 "Modelling</h2>")
        t = bio.tbl_compare
        rows = [[t.item(r, c).text() if t.item(r, c) else ""
                 for c in range(t.columnCount())]
                for r in range(t.rowCount())]
        headers = [t.horizontalHeaderItem(c).text()
                  for c in range(t.columnCount())]
        h.append(table(headers, rows) if rows else
                "<p style='color:#64748b;'>No comparison data available.</p>")
        if bio.lbl_manual.text():
            h.append(f"<p>{esc(bio.lbl_manual.text())}</p>")
        try:
            cmp_png = fig_dir / "comparison_bars.png"
            bio.fig_compare.savefig(cmp_png, dpi=200, bbox_inches="tight")
            h.append(ml_report._img_tag(cmp_png, True))
        except Exception:
            pass

        h.append(f"<h2 style='color:{dark};'>Mortality</h2>")
        if bio.lbl_mortality.text():
            h.append(f"<p>{esc(bio.lbl_mortality.text())}</p>")
        try:
            vcrit_png = fig_dir / "vcrit_sweep.png"
            bio.fig_vcrit.savefig(vcrit_png, dpi=200, bbox_inches="tight")
            h.append(ml_report._img_tag(vcrit_png, True))
        except Exception:
            pass
        h.append("</div>")
        return {"html": "".join(h)}

    return ReportSection("biological", "Biological interpretation",
                         available, reason, build)


def all_sections(window, training_entry_getter=None, misclass_entry_getter=None):
    """Every report section, in the order the report is assembled.

    `training_entry_getter`/`misclass_entry_getter`: no-arg callables
    returning the `ModelEntry` those two sections should report on -
    typically the Report page's own per-section model-picker combos
    (`ml_tab_report.py`). Default to whichever model is first in
    `available_model_entries` when not supplied, so this still works
    standalone without a combo box behind it.
    """
    if training_entry_getter is None or misclass_entry_getter is None:
        entries = available_model_entries(window)
        default_getter = (lambda: entries[0]) if entries else (lambda: None)
        training_entry_getter = training_entry_getter or default_getter
        misclass_entry_getter = misclass_entry_getter or default_getter
    return [
        bsm_section(window),
        study_design_section(window),
        process_section(window),
        annotation_section(window),
        training_section(window, training_entry_getter),
        misclassification_section(window, misclass_entry_getter),
        deployment_summary_section(window),
        prediction_section(window),
        biological_section(window),
    ]
