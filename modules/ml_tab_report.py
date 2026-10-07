# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Export and report - the one place every StrikeWorks report is built.

A dialog opened from the "Export and report" button at the bottom of the
sidebar (`page_ml_prediction.open_report()`).

Hosts the central reporting hub (`report_center.py`): a checklist of every
report a page in the app can produce - BSM maths, Study design, Raw data
processing, Annotation, Model training, Misclassification, Model
deployment summary, Model prediction, Model comparison - all in the same
HTML format; a section with nothing to report yet is greyed out. Three
actions:

  Preview     - assembles the checked sections and opens the result in the
                user's default web browser.
  Export      - the same, written to disk under the session library's
                output folder (or the Settings default), its folder opened.
  Export all  - every *available* section (not just checked), as Export -
                the quickest way to get everything there is.

(Simple mode's Download writes the prediction's self-contained package,
`ml_report.export_analysis`.)

Figure output settings (file formats, DPI) sit underneath and thread
through to every section that renders its own figure (the `formats=`/
`dpi=` arguments of the report_center sections).
"""
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QSpinBox, QVBoxLayout,
)

from . import report_center, win_utils
from .layout import apply_section_defaults, Section
from .theme import muted_label, style

# (key, title) in the order report_center.all_sections() builds them
_SECTION_TITLES = [
    ("bsm",              "Blade strike modelling (mathematical)"),
    ("study_design",     "Study design"),
    ("process",          "Raw data processing"),
    ("annotation",       "Annotation"),
    ("training",         "Model training / evaluation"),
    ("misclassification","Misclassification analysis"),
    ("deployment",       "Model deployment summary"),
    ("prediction",       "Model prediction"),
    ("biological",       "Model comparison"),
]

# these two sections report on "a model" rather than "the app's current
# state" - own picker here, independent of Evaluate/Misclassification.
_MODEL_PICKER_KEYS = ("training", "misclassification")


class ReportDialog(QDialog):
    """Builds the Export and report UI and binds it to `state`."""

    def __init__(self, state, window):
        super().__init__(window)
        self.setWindowTitle("Export and report")
        self.resize(760, 680)
        self.state = state
        self.window = window
        self._checks = {}
        self._model_combos = {}
        self._sections = []

        self._build()
        self._connect_state()
        self._refresh_checklist()

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_checklist()

    def refresh(self):
        """Public entry point for callers opening this dialog (`page_ml_
        prediction.py.open_report()`) - `showEvent` already refreshes on
        every open, so this only matters if a caller wants the checklist
        current before `exec()` is even called."""
        self._refresh_checklist()

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(10)

        grp_sections = Section("Report sections")
        sv = QVBoxLayout(grp_sections)
        sv.setSpacing(4)

        for key, title in _SECTION_TITLES:
            row = QHBoxLayout()
            cb = QCheckBox(title)
            cb.setChecked(key == "prediction")
            self._checks[key] = cb
            row.addWidget(cb, stretch=1)
            if key in _MODEL_PICKER_KEYS:
                combo = QComboBox()
                combo.setEnabled(False)
                combo.setMinimumWidth(160)
                self._model_combos[key] = combo
                row.addWidget(combo)
                if key == "training":
                    combo.setToolTip(
                        "The picked model's evaluation - its binary and "
                        "multiclass (region) stages both, when it has both.")
                    self.chk_all_models = QCheckBox("All models")
                    self.chk_all_models.setToolTip(
                        "Include every available model's evaluation report "
                        "(with figures), not just the one picked above.")
                    row.addWidget(self.chk_all_models)
            sv.addLayout(row)

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

        # Preview: the ticked sections in the browser; Export: the ticked
        # sections to a report folder; Export all: every available section
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.btn_preview = QPushButton("Preview")
        self.btn_preview.setToolTip("Open the ticked sections as a report in "
                                    "the browser.")
        self.btn_preview.clicked.connect(self._preview_report)
        self.btn_export_full = QPushButton("Export")
        style(self.btn_export_full, role="primary")
        self.btn_export_full.setToolTip(
            "Write the ticked sections as one report, with their tables and "
            "figures, and open its folder.")
        self.btn_export_full.clicked.connect(self._export_full_report)
        self.btn_export_all = QPushButton("Export all")
        self.btn_export_all.setToolTip(
            "Tick every section with something to report, then export.")
        self.btn_export_all.clicked.connect(self._export_all)
        for b in (self.btn_preview, self.btn_export_full, self.btn_export_all):
            bar.addWidget(b)
        bar.addStretch()
        v.addLayout(bar)

        v.addWidget(self._figure_output_group())

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        style(self.lbl_status, role="muted")
        v.addWidget(self.lbl_status)
        v.addStretch()

        close_row = QHBoxLayout()
        close_row.addStretch()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        close_row.addWidget(btn_close)
        v.addLayout(close_row)

        apply_section_defaults(self)

    def _figure_output_group(self):
        grp = Section("Figure output")
        gv = QVBoxLayout(grp)
        gv.setSpacing(6)

        row = QHBoxLayout()
        row.addWidget(muted_label("File format"))
        self.chk_png = QCheckBox(".png")
        self.chk_png.setChecked(True)
        self.chk_svg = QCheckBox(".svg")
        self.chk_svg.setChecked(True)
        row.addWidget(self.chk_png)
        row.addWidget(self.chk_svg)
        row.addSpacing(16)
        row.addWidget(muted_label("DPI"))
        self.spin_dpi = QSpinBox()
        self.spin_dpi.setRange(50, 1200)
        self.spin_dpi.setValue(300)
        self.spin_dpi.setSingleStep(50)
        row.addWidget(self.spin_dpi)
        row.addSpacing(16)
        row.addWidget(muted_label("Output size"))
        self.cmb_fig_size = QComboBox()
        self.cmb_fig_size.addItem("Default")
        self.cmb_fig_size.setEnabled(False)
        self.cmb_fig_size.setToolTip(
            "Planned: per-figure output sizing (e.g. print/poster "
            "presets). Default uses each figure's own layout.")
        row.addWidget(self.cmb_fig_size)
        row.addStretch()
        gv.addLayout(row)
        return grp

    def _connect_state(self):
        s = self.state
        s.run_finished.connect(self._refresh_checklist)
        s.models_changed.connect(self._refresh_checklist)
        s.dataset_changed.connect(self._refresh_checklist)

    # ── figure output settings ──────────────────────────────────────────────
    def _selected_formats(self):
        fmts = []
        if self.chk_png.isChecked():
            fmts.append("png")
        if self.chk_svg.isChecked():
            fmts.append("svg")
        return tuple(fmts) or ("png",)

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
        if hasattr(self, "chk_all_models"):
            self.chk_all_models.setEnabled(len(entries) > 1)

    def _refresh_checklist(self):
        self._refresh_model_combos()
        self._sections = report_center.all_sections(
            self.window,
            training_entry_getter=lambda: self._model_combos["training"].currentData(),
            misclass_entry_getter=lambda: self._model_combos["misclassification"].currentData(),
            all_models=lambda: self.chk_all_models.isChecked(),
            formats=self._selected_formats(), dpi=self.spin_dpi.value())
        for sec in self._sections:
            cb = self._checks.get(sec.key)
            if cb is None:
                continue
            cb.setEnabled(sec.available)
            if not sec.available:
                cb.setChecked(False)
            # why a section can't be ticked yet - on hover, not alongside
            cb.setToolTip("" if sec.available else sec.reason)

    def _select_all_available(self):
        for sec in self._sections:
            cb = self._checks.get(sec.key)
            if cb is not None and sec.available:
                cb.setChecked(True)

    def _select_none(self):
        for cb in self._checks.values():
            cb.setChecked(False)

    def _checked_keys(self):
        return {k for k, cb in self._checks.items() if cb.isChecked()}

    # ── report assembly ─────────────────────────────────────────────────────
    def _assemble(self, checked):
        # state may have changed since the checklist was drawn (a run
        # finished, a model deployed); refreshing unchecks anything that's
        # no longer available
        self._refresh_checklist()
        checked = self._checked_keys()
        if not checked:
            return None, None
        out_dir = report_center.default_output_dir(self.window)
        try:
            doc_path, warnings = report_center.assemble(
                self._sections, out_dir, checked)
        except Exception as e:
            QMessageBox.critical(self.window, "Report failed", str(e))
            return None, None
        return doc_path, warnings

    def _preview_report(self):
        checked = self._checked_keys()
        if not checked:
            QMessageBox.information(
                self.window, "Nothing checked",
                "Check at least one report section first.")
            return
        doc_path, warnings = self._assemble(checked)
        if doc_path is None:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(doc_path)))
        self.lbl_status.setText(f"Opened in browser: {doc_path}")
        self.state.status.emit(f"Report opened in browser: {doc_path}", 6000)

    def _export_full_report(self):
        checked = self._checked_keys()
        if not checked:
            QMessageBox.information(
                self.window, "Nothing checked",
                "Check at least one report section first.")
            return
        doc_path, warnings = self._assemble(checked)
        if doc_path is None:
            QMessageBox.information(
                self.window, "Nothing available",
                "None of the checked sections have data to report - see "
                "the notes next to each section.")
            return
        self._report_done(doc_path, warnings)

    def _export_all(self):
        self._refresh_checklist()
        self._select_all_available()
        checked = self._checked_keys()
        if not checked:
            QMessageBox.information(
                self.window, "Nothing available",
                "No report section has data to export yet.")
            return
        doc_path, warnings = self._assemble(checked)
        if doc_path is None:
            return
        self._report_done(doc_path, warnings)

    def _report_done(self, doc_path, warnings):
        win_utils.open_folder(doc_path)
        self.lbl_status.setText(f"Report written to {doc_path}")
        self.state.status.emit(f"Report generated: {doc_path}", 7000)
        if warnings:
            QMessageBox.warning(
                self.window, "Report generated with warnings",
                f"Report written to:\n{doc_path}\n\n" + "\n".join(warnings))
        else:
            QMessageBox.information(
                self.window, "Report generated",
                f"Report written to:\n{doc_path}")
