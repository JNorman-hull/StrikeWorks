# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Report tab - summarise, document and export the prediction analysis.

Renders the Blade Strike Analysis report from the shared PredictionState
(the exact results and metadata used by Predict/Inspect) and provides the
export actions, including the one-click self-contained "Export analysis"
package.
"""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QTextBrowser, QVBoxLayout,
)

from . import ml_figures, ml_report
from .ml_widgets import ACCENT, MUTED


class ReportTab:
    """Builds the Report tab UI into `frame` and binds it to `state`."""

    def __init__(self, frame, state, window):
        self.state = state
        self.window = window
        self._image_paths = {}

        self._build(frame)
        self._connect_state()
        self._refresh()

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, frame):
        v = QVBoxLayout(frame)
        v.setContentsMargins(4, 6, 4, 6)
        v.setSpacing(8)

        bar = QHBoxLayout()
        bar.setSpacing(6)

        self.btn_export_all = QPushButton("Export analysis…")
        self.btn_export_all.setMinimumHeight(32)
        self.btn_export_all.setStyleSheet(
            f"QPushButton{{background-color:{ACCENT};color:#ffffff;"
            "border-radius:5px;padding:4px 14px;font-weight:bold;}"
            "QPushButton:disabled{background-color:#3a4150;color:#8a95aa;}")
        self.btn_export_all.clicked.connect(self._export_analysis)

        self.btn_save_report = QPushButton("Save report (HTML)…")
        self.btn_save_report.clicked.connect(self._save_report)
        self.btn_export_tables = QPushButton("Export tables (CSV)…")
        self.btn_export_tables.clicked.connect(self._export_tables)
        self.btn_export_figs = QPushButton("Export figures (PNG/SVG)…")
        self.btn_export_figs.clicked.connect(self._export_figures)
        self.btn_refresh = QPushButton("Refresh report")
        self.btn_refresh.clicked.connect(self._refresh)

        bar.addWidget(self.btn_export_all)
        bar.addWidget(self.btn_save_report)
        bar.addWidget(self.btn_export_tables)
        bar.addWidget(self.btn_export_figs)
        bar.addStretch()
        bar.addWidget(self.btn_refresh)
        v.addLayout(bar)

        self.lbl_note = QLabel(
            "The report uses exactly the prediction results and metadata "
            "shown on the Predict and Inspect tabs. The exported report.html "
            "is self-contained and prints/saves to PDF from any browser.")
        self.lbl_note.setStyleSheet(f"color:{MUTED};")
        self.lbl_note.setWordWrap(True)
        v.addWidget(self.lbl_note)

        grp = QGroupBox("Report preview")
        gv = QVBoxLayout(grp)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        self.browser.setStyleSheet(
            "QTextBrowser{background-color:#ffffff;color:#1e293b;"
            "border:1px solid #2c313a;border-radius:5px;padding:12px;}")
        gv.addWidget(self.browser)
        v.addWidget(grp, stretch=1)

    def _connect_state(self):
        s = self.state
        s.run_finished.connect(self._on_run_finished)
        s.models_changed.connect(self._refresh)
        s.dataset_changed.connect(self._refresh)

    # ── refresh ──────────────────────────────────────────────────────────────
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
        self._refresh()

    def _refresh(self):
        has_run = self.state.summary is not None
        for b in (self.btn_export_all, self.btn_save_report,
                  self.btn_export_tables, self.btn_export_figs):
            b.setEnabled(has_run)
        html = ml_report.build_report_html(
            self.state, image_paths=self._image_paths, embed_images=False)
        self.browser.setHtml(html)

    # ── exports ──────────────────────────────────────────────────────────────
    def _pick_dir(self, caption):
        return QFileDialog.getExistingDirectory(self.window, caption, "")

    def _export_analysis(self):
        dirpath = self._pick_dir("Create analysis package in folder…")
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
            "Self-contained analysis package created:\n\n"
            f"{out}\n\n" + "\n".join(
                f"  • {p.name}" for p in sorted(out.glob('*'))))

    def _save_report(self):
        path, _ = QFileDialog.getSaveFileName(
            self.window, "Save report",
            str(Path.cwd() / f"BladeStrike_Report_{self.state.run_id}.html"),
            "HTML files (*.html)")
        if not path:
            return
        try:
            figs = ml_figures.render_figures(
                self.state, self.state.out_dir, formats=("png",))
            image_paths = {name: paths[0] for name, paths in figs.items()}
            body = ml_report.build_report_html(
                self.state, image_paths=image_paths, embed_images=True)
            Path(path).write_text(ml_report.wrap_html_document(body),
                                  encoding="utf-8")
        except Exception as e:
            QMessageBox.critical(self.window, "Save failed", str(e))
            return
        self.state.status.emit(f"Report saved: {Path(path).name}", 5000)

    def _export_tables(self):
        dirpath = self._pick_dir("Export tables to folder…")
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
        dirpath = self._pick_dir("Export figures to folder…")
        if not dirpath:
            return
        try:
            written = ml_report.export_figures(self.state, dirpath)
        except Exception as e:
            QMessageBox.critical(self.window, "Export failed", str(e))
            return
        self.state.status.emit(
            f"Exported {len(written)} figure file(s) to {dirpath}", 5000)
