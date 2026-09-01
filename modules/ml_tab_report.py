# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Report tab - the one place every StrikeWorks report is built.

Used to render only the Blade Strike Analysis report from the shared
PredictionState. Now also hosts the central reporting hub
(``report_center.py``): a checklist of every report a page in the app can
produce - BSM maths, Study design, Raw data processing, Annotation, Model
training, Misclassification, Model deployment summary, Model prediction,
Biological interpretation - all in the same HTML format, assembled into one
document under ``output_data/``. This is also what "Final reporting"
(previously an empty stub page) now points at.

The Model prediction report keeps its own quick-export actions (Export
analysis / tables / figures) below the checklist: they package more than
report.html alone (SVGs, provenance.json, raw CSVs) for this one dataset,
so they stay distinct utility rather than a duplicate of the unified
report.
"""
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QTextBrowser, QVBoxLayout, QWidget,
)

from . import ml_figures, ml_report, report_center
from .ml_widgets import ACCENT, MUTED, Section, apply_section_defaults

# (key, title) in the order report_center.all_sections() builds them
_SECTION_TITLES = [
    ("bsm",              "Blade strike modelling (mathematical)"),
    ("study_design",     "Study design"),
    ("process",          "Raw data processing"),
    ("annotation",       "Annotation"),
    ("training",         "Model training"),
    ("misclassification","Misclassification analysis"),
    ("deployment",       "Model deployment summary"),
    ("prediction",       "Model prediction"),
    ("biological",       "Biological interpretation"),
]

# these two sections report on "a model" rather than "the app's current
# state" - previously they silently used whatever was last selected on
# Model training > Evaluate / Misclassification analysis, which drifted
# out of sync with what the checkbox actually said it would report. Own
# picker here instead, independent of either page.
_MODEL_PICKER_KEYS = ("training", "misclassification")


class ReportTab:
    """Builds the Report tab UI into `frame` and binds it to `state`."""

    def __init__(self, frame, state, window):
        self.state = state
        self.window = window
        self._image_paths = {}
        self._checks = {}
        self._status_labels = {}
        self._model_combos = {}
        self._sections = []

        self._build(frame)
        self._connect_state()
        self._refresh_checklist()
        self._refresh()

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, frame):
        v = QVBoxLayout(frame)
        v.setContentsMargins(4, 6, 4, 6)
        v.setSpacing(8)

        grp_sections = Section("Report sections")
        sv = QVBoxLayout(grp_sections)
        sv.setSpacing(4)

        hint = QLabel("Every StrikeWorks report shares one format. Check "
                      "the sections to include, then Generate report. "
                      "Sections with nothing to report yet are disabled.")
        hint.setStyleSheet(f"color:{MUTED};")
        hint.setWordWrap(True)
        sv.addWidget(hint)

        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(2)
        for i, (key, title) in enumerate(_SECTION_TITLES):
            row, col = divmod(i, 2)
            cell = QVBoxLayout()
            cell.setSpacing(0)
            cb = QCheckBox(title)
            cb.setChecked(key == "prediction")
            self._checks[key] = cb
            cell.addWidget(cb)
            if key in _MODEL_PICKER_KEYS:
                combo = QComboBox()
                combo.setEnabled(False)
                self._model_combos[key] = combo
                cell.addWidget(combo)
            lab = QLabel("")
            lab.setStyleSheet(f"color:{MUTED};font-size:11px;")
            lab.setWordWrap(True)
            self._status_labels[key] = lab
            cell.addWidget(lab)
            wrap = QWidget()
            wrap.setLayout(cell)
            grid.addWidget(wrap, row, col)
        sv.addLayout(grid)

        sel_row = QHBoxLayout()
        btn_all = QPushButton("Select all available")
        btn_all.clicked.connect(self._select_all_available)
        btn_none = QPushButton("Clear")
        btn_none.clicked.connect(self._select_none)
        sel_row.addWidget(btn_all)
        sel_row.addWidget(btn_none)
        sel_row.addStretch()
        sv.addLayout(sel_row)
        v.addWidget(grp_sections)

        bar = QHBoxLayout()
        bar.setSpacing(6)

        self.btn_generate = QPushButton("Generate report")
        self.btn_generate.setMinimumHeight(32)
        self.btn_generate.setStyleSheet(
            f"QPushButton{{background-color:{ACCENT};color:#ffffff;"
            "border-radius:5px;padding:4px 14px;font-weight:bold;}"
            "QPushButton:disabled{background-color:#3a4150;color:#8a95aa;}")
        self.btn_generate.clicked.connect(self._generate_report)

        self.btn_export_all = QPushButton("Export analysis (prediction only)")
        self.btn_export_all.clicked.connect(self._export_analysis)
        self.btn_export_tables = QPushButton("Export tables (CSV)")
        self.btn_export_tables.clicked.connect(self._export_tables)
        self.btn_export_figs = QPushButton("Export figures (PNG/SVG)")
        self.btn_export_figs.clicked.connect(self._export_figures)
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self._on_refresh_clicked)

        bar.addWidget(self.btn_generate)
        bar.addWidget(self.btn_export_all)
        bar.addWidget(self.btn_export_tables)
        bar.addWidget(self.btn_export_figs)
        bar.addStretch()
        bar.addWidget(self.btn_refresh)
        v.addLayout(bar)

        grp = Section("Report preview")
        gv = QVBoxLayout(grp)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        self.browser.setStyleSheet(
            "QTextBrowser{background-color:#ffffff;color:#1e293b;"
            "border:1px solid #2c313a;border-radius:5px;padding:12px;}")
        gv.addWidget(self.browser)
        v.addWidget(grp, stretch=1)

        apply_section_defaults(frame)

    def _connect_state(self):
        s = self.state
        s.run_finished.connect(self._on_run_finished)
        s.models_changed.connect(self._refresh)
        s.dataset_changed.connect(self._refresh)

    # ── section checklist ────────────────────────────────────────────────────
    def _refresh_model_combos(self):
        """Repopulates the Model training / Misclassification pickers with
        every available model, keeping the previous selection (matched by
        label, since `available_model_entries` builds fresh `ModelEntry`
        objects each call) if it's still in the list."""
        entries = report_center.available_model_entries(self.window)
        for combo in self._model_combos.values():
            keep_label = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            for e in entries:
                combo.addItem(e.label, e)
            combo.setEnabled(bool(entries))
            idx = combo.findText(keep_label) if keep_label else -1
            combo.setCurrentIndex(idx if idx >= 0 else (0 if entries else -1))
            combo.blockSignals(False)

    def _refresh_checklist(self):
        self._refresh_model_combos()
        self._sections = report_center.all_sections(
            self.window,
            training_entry_getter=lambda: self._model_combos["training"].currentData(),
            misclass_entry_getter=lambda: self._model_combos["misclassification"].currentData())
        for sec in self._sections:
            cb = self._checks.get(sec.key)
            lab = self._status_labels.get(sec.key)
            if cb is None:
                continue
            cb.setEnabled(sec.available)
            if not sec.available:
                cb.setChecked(False)
            if lab is not None:
                lab.setText("" if sec.available else sec.reason)

    def _select_all_available(self):
        for sec in self._sections:
            cb = self._checks.get(sec.key)
            if cb is not None and sec.available:
                cb.setChecked(True)

    def _select_none(self):
        for cb in self._checks.values():
            cb.setChecked(False)

    def _on_refresh_clicked(self):
        self._refresh_checklist()
        self._refresh()

    def _generate_report(self):
        checked = {k for k, cb in self._checks.items() if cb.isChecked()}
        if not checked:
            QMessageBox.information(
                self.window, "Nothing checked",
                "Check at least one report section first.")
            return
        self._refresh_checklist()
        checked &= {k for k, cb in self._checks.items() if cb.isChecked()}
        if not checked:
            QMessageBox.information(
                self.window, "Nothing available",
                "None of the checked sections have data to report any "
                "more - see the notes under each section.")
            return

        out_dir = report_center.default_output_dir(self.window)
        try:
            doc_path, warnings = report_center.assemble(
                self._sections, out_dir, checked)
        except Exception as e:
            QMessageBox.critical(self.window, "Report failed", str(e))
            return

        self.browser.setHtml(doc_path.read_text(encoding="utf-8"))
        self.state.status.emit(f"Report generated: {doc_path}", 7000)
        if warnings:
            QMessageBox.warning(
                self.window, "Report generated with warnings",
                f"Report written to:\n{doc_path}\n\n" + "\n".join(warnings))
        else:
            QMessageBox.information(
                self.window, "Report generated",
                f"Report written to:\n{doc_path}")

    # ── refresh (Model prediction quick preview) ────────────────────────────
    def _on_run_finished(self):
        # render preview figures into the run's output directory so the
        # report always shows the current run's figures
        self._image_paths = {}
        try:
            figs = ml_figures.render_figures(
                self.state, self.state.out_dir, formats=("png",))
            self._image_paths = {name: paths[0]
                                 for name, paths in figs.items()}
        except Exception:
            pass
        self._refresh_checklist()
        self._refresh()

    def _refresh(self):
        has_run = self.state.summary is not None
        for b in (self.btn_export_all, self.btn_export_tables,
                  self.btn_export_figs):
            b.setEnabled(has_run)
        html = ml_report.build_report_html(
            self.state, image_paths=self._image_paths, embed_images=False)
        self.browser.setHtml(html)

    # ── exports (Model prediction only - see module docstring) ─────────────
    def _pick_dir(self, caption):
        return QFileDialog.getExistingDirectory(self.window, caption, "")

    def _export_analysis(self):
        dirpath = self._pick_dir("Create analysis package in folder")
        if not dirpath:
            return
        try:
            out = ml_report.export_analysis(self.state, dirpath)
        except Exception as e:
            QMessageBox.critical(self.window, "Export failed", str(e))
            return
        self.state.status.emit(f"Analysis exported to {out}", 6000)
        QMessageBox.information(
            self.window, "Export analysis",
            ""
            f"{out}\n\n" + "\n".join(
                f"  • {p.name}" for p in sorted(out.glob('*'))))

    def _export_tables(self):
        dirpath = self._pick_dir("Export tables to folder")
        if not dirpath:
            return
        try:
            written = ml_report.export_tables(self.state, dirpath)
        except Exception as e:
            QMessageBox.critical(self.window, "Export failed", str(e))
            return
        self.state.status.emit(
            f"Exported {len(written)} table(s) to {dirpath}", 5000)

    def _export_figures(self):
        dirpath = self._pick_dir("Export figures to folder")
        if not dirpath:
            return
        try:
            written = ml_report.export_figures(self.state, dirpath)
        except Exception as e:
            QMessageBox.critical(self.window, "Export failed", str(e))
            return
        self.state.status.emit(
            f"Exported {len(written)} figure file(s) to {dirpath}", 5000)
