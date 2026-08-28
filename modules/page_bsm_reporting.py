# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Controller for the Reporting page (Mathematical Blade Strike Modelling).

Two jobs:
  - Export a self-contained CSV+PNG+HTML package on demand (`bsm_io`,
    `bsm_report`), matching the shape of every other export in the app.
  - On every new result, write `bsm_state.LATEST_RESULT_PATH` - a small
    JSON with the CEN collision-probability estimate - so Setup and
    deploy > Study design can pull a hypothesised strike rate from the
    model instead of a typed guess (ROADMAP.md Chunk 5 task 5's "Load
    from Blade Strike Modelling" hook).
"""
import json
from datetime import datetime, timezone

from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout,
    QWidget,
)

from . import bsm_figures, bsm_io
from .bsm_report import build_bsm_report_html
from .bsm_state import LATEST_RESULT_PATH
from .ml_report import wrap_html_document
from .ml_widgets import MUTED, Section, apply_section_defaults

_NODIALOG = QFileDialog.Option.DontUseNativeDialog


class ReportingPage(QWidget):
    status = Signal(str, int)

    def __init__(self, frame, window, bsm_state):
        super().__init__()
        self.window = window
        self.bsm_state = bsm_state
        self.last_result = None
        self.fig_pco = Figure(figsize=(4.2, 3.4), dpi=100)
        self.fig_pm = Figure(figsize=(4.2, 3.4), dpi=100)
        self.canvas_pco = FigureCanvas(self.fig_pco)
        self.canvas_pm = FigureCanvas(self.fig_pm)
        for canvas in (self.canvas_pco, self.canvas_pm):
            canvas.setSizePolicy(QSizePolicy.Policy.Expanding,
                                 QSizePolicy.Policy.Expanding)
        self._build(frame)
        bsm_figures.draw_pco(self.fig_pco, {"Pco_tip": 0.0})
        bsm_figures.draw_pm(self.fig_pm, {"Pm": 0.0})
        self.canvas_pco.draw()
        self.canvas_pm.draw()
        bsm_state.calculated.connect(self._on_result)
        if bsm_state.last_result is not None:
            self._on_result(bsm_state.last_result)

    def _build(self, frame):
        v = QVBoxLayout(frame)
        v.setContentsMargins(4, 6, 4, 6)
        v.setSpacing(10)

        self.info_lbl = QLabel(
            "Run a calculation on Calculator to populate the report.")
        self.info_lbl.setStyleSheet(f"color:{MUTED};")
        self.info_lbl.setWordWrap(True)
        v.addWidget(self.info_lbl)

        g = Section("Report preview")
        gv = QVBoxLayout(g)
        plots_row = QHBoxLayout()
        plots_row.addWidget(self.canvas_pco)
        plots_row.addWidget(self.canvas_pm)
        gv.addLayout(plots_row, stretch=1)
        v.addWidget(g, stretch=1)

        g2 = Section("Export")
        gv2 = QVBoxLayout(g2)
        note = QLabel(
            "Writes a CSV of the headline results, PNGs of both figures "
            "and a self-contained HTML report to a chosen folder.")
        note.setStyleSheet(f"color:{MUTED};")
        note.setWordWrap(True)
        gv2.addWidget(note)
        row = QHBoxLayout()
        self.btn_export = QPushButton("Export report package...")
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self._export)
        row.addStretch()
        row.addWidget(self.btn_export)
        gv2.addLayout(row)
        self.lbl_publish = QLabel(
            "Every new calculation is also published automatically for "
            "Setup and deploy > Study design's 'Load from Blade Strike "
            "Modelling' hypothesised strike rate.")
        self.lbl_publish.setStyleSheet(f"color:{MUTED};")
        self.lbl_publish.setWordWrap(True)
        gv2.addWidget(self.lbl_publish)
        v.addWidget(g2)

        apply_section_defaults(frame)

    # ── reactions ────────────────────────────────────────────────────────────
    def _on_result(self, res):
        self.last_result = res
        bsm_figures.draw_pco(self.fig_pco, res)
        bsm_figures.draw_pm(self.fig_pm, res)
        self.canvas_pco.draw()
        self.canvas_pm.draw()
        self.btn_export.setEnabled(True)
        obs = " Observed data included." if "Pco_obs" in res else ""
        self.info_lbl.setText(
            f"CEN estimate: Pco {res['Pco_tip'] * 100:.2f}%, "
            f"Pm {res['Pm'] * 100:.2f}%.{obs}")
        self._publish_latest(res)

    def _publish_latest(self, res):
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "species": res["params"]["species"],
            "pco_cen_percent": res["Pco_tip"] * 100,
            "pm_cen_percent": res["Pm"] * 100,
            "s_cen_percent": res["S"] * 100,
        }
        if "Pco_obs" in res:
            payload.update({
                "pco_observed_percent": res["Pco_obs"] * 100,
                "pm_observed_percent": res["Pm_obs"] * 100,
                "wilson_lo_percent": res["wilson_lo"] * 100,
                "wilson_hi_percent": res["wilson_hi"] * 100,
            })
        LATEST_RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LATEST_RESULT_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    # ── export ───────────────────────────────────────────────────────────────
    def _export(self):
        if self.last_result is None:
            self.status.emit("Nothing to export - calculate first.", 4000)
            return
        dirpath = QFileDialog.getExistingDirectory(
            self, "Export report package to folder...", "", _NODIALOG)
        if not dirpath:
            return
        try:
            bsm_io.export_results(self.last_result, self.fig_pco, self.fig_pm,
                                  dirpath)
            from pathlib import Path
            out = Path(dirpath)
            body = build_bsm_report_html(
                self.last_result,
                image_paths={"pco": out / "barplot_pco.png",
                            "pm": out / "barplot_pm.png"},
                embed_images=True)
            (out / "report.html").write_text(wrap_html_document(body),
                                             encoding="utf-8")
            self.status.emit(f"Exported report package to {out}", 5000)
        except Exception as e:
            self.status.emit(f"Export failed: {e}", 6000)
