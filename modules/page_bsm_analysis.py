# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Analysis and reporting (Mathematical blade strike modelling).

  - Figures: the headline results as one 4-panel figure ((a) scaly
    collision, (b) scaly mortality, (c) eel collision, (d) eel mortality)
    and the sensitivity sweeps as another ((a)/(b) collision probability
    vs shaft speed / relative fish velocity, (c)/(d) mortality vs the
    same), one line per flow rate Q.
  - The Results table and "Blade strike output" card Calculator shows.
  - "Generate report...": CSV, every figure as PNG and an HTML report
    (equations, tables, figures) in one folder.

Follows `BSMState.calculated`, so it shows the latest result however it
was produced.
"""
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QPushButton, QSizePolicy, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import bsm_figures, bsm_io
from .bsm_model import sensitivity_sweeps
from .bsm_state import output_card_rows
from .cards import MetaCard
from .layout import apply_section_defaults, centred, scroll_page, Section
from .theme import ACCENT_BUTTON

_NODIALOG = QFileDialog.Option.DontUseNativeDialog


class BSMAnalysisPage(QWidget):
    status = Signal(str, int)

    def __init__(self, frame, window, bsm_state):
        super().__init__()
        self.window = window
        self.bsm_state = bsm_state
        self.last_result = None
        self.sweeps = None           # bsm_model.sensitivity_sweeps() of last_result

        self._build(frame)
        self._draw_blank()
        bsm_state.calculated.connect(self.update_from_result)
        bsm_state.calculated_all.connect(self._draw_results)
        if bsm_state.results:
            self._draw_results(bsm_state.results)
        if bsm_state.last_result is not None:
            self.update_from_result(bsm_state.last_result)

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, frame):
        v = scroll_page(frame)

        v.addWidget(self._figures_group())

        row = QHBoxLayout()
        row.addWidget(self._results_group(), stretch=1)
        row.addWidget(self._output_group(), stretch=1)
        v.addLayout(row)

        self.btn_report = QPushButton("Generate report...")
        self.btn_report.setEnabled(False)
        self.btn_report.setStyleSheet(ACCENT_BUTTON)
        self.btn_report.clicked.connect(self._generate_report)
        report_row = QHBoxLayout()
        report_row.addStretch()
        report_row.addWidget(self.btn_report)
        v.addLayout(report_row)

        apply_section_defaults(frame)

    def _figures_group(self):
        g = Section("Figures")
        gv = QVBoxLayout(g)

        # the report's own two figures, at their report proportions
        # (12 x 12 cm and 20 x 16 cm) - the canvases still scale with the page
        w, h = bsm_figures.RESULTS_PANELS_CM
        self.fig_results = Figure(figsize=(w / 2.54, h / 2.54), dpi=100)
        w, h = bsm_figures.SWEEP_PANELS_CM
        self.fig_sweeps = Figure(figsize=(w / 2.54, h / 2.54), dpi=100)
        self.canvas_results = self._canvas(self.fig_results)
        self.canvas_sweeps = self._canvas(self.fig_sweeps)

        # one row each, centred at roughly the report figures' proportions
        # (square, and 20:16) rather than stretched across the page
        self.canvas_results.setMinimumHeight(460)
        self.canvas_results.setMaximumWidth(620)
        self.canvas_sweeps.setMinimumHeight(560)
        self.canvas_sweeps.setMaximumWidth(900)
        gv.addWidget(centred(self.canvas_results))
        gv.addWidget(centred(self.canvas_sweeps))
        return g

    @staticmethod
    def _canvas(fig):
        c = FigureCanvas(fig)
        c.setMinimumSize(220, 190)
        c.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        return c

    def _results_group(self):
        g = Section("Results")
        v = QVBoxLayout(g)
        self.results_tbl = QTableWidget(2, 5)
        self.results_tbl.setHorizontalHeaderLabels(
            ["Method", "Pco (%)", "fMR (%)", "Pm (%)", "S (%)"])
        self.results_tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_tbl.setMaximumHeight(95)
        v.addWidget(self.results_tbl)
        return g

    def _output_group(self):
        g = Section("Blade strike output")
        v = QVBoxLayout(g)
        self.card_output = MetaCard("Blade strike output")
        v.addWidget(self.card_output)
        return g

    def _draw_blank(self):
        bsm_figures.draw_results_panels(self.fig_results, {}, dark=True)
        bsm_figures.draw_sweep_panels(self.fig_sweeps, None, dark=True)
        self.canvas_results.draw()
        self.canvas_sweeps.draw()

    # ── reactions ────────────────────────────────────────────────────────────
    def _draw_results(self, results):
        """Both species' headline results (Calculator runs scaly and eel
        every time - BSMState.calculated_all)."""
        bsm_figures.draw_results_panels(self.fig_results, results, dark=True)
        self.canvas_results.draw()

    def update_from_result(self, res):
        self.last_result = res
        self._update_table(res)
        self.card_output.set_rows(output_card_rows(res))
        try:
            self.sweeps = sensitivity_sweeps(res["params"])
        except Exception as e:
            self.sweeps = None
            self.status.emit(f"Sensitivity sweep failed: {e}", 6000)
            return
        bsm_figures.draw_sweep_panels(
            self.fig_sweeps, self.sweeps, dark=True,
            title=bsm_figures.sweep_panels_title(res["params"]["species"],
                                                 res["params"]))
        self.canvas_sweeps.draw()
        self.btn_report.setEnabled(True)

    def _update_table(self, res):
        has_obs = "Pco_obs" in res
        self.results_tbl.setItem(0, 0, QTableWidgetItem("CEN"))
        for j, v in enumerate([res["Pco_tip"], res["fMR_tip"], res["Pm"], res["S"]],
                              start=1):
            self.results_tbl.setItem(0, j, QTableWidgetItem(f"{v * 100:.4f}"))
        self.results_tbl.setRowHidden(1, not has_obs)
        if has_obs:
            self.results_tbl.setItem(1, 0, QTableWidgetItem("Observed"))
            for j, v in enumerate(
                    [res["Pco_obs"], res["fMR_tip"], res["Pm_obs"], res["S_obs"]],
                    start=1):
                self.results_tbl.setItem(1, j, QTableWidgetItem(f"{v * 100:.4f}"))

    # ── report ───────────────────────────────────────────────────────────────
    def _generate_report(self):
        if self.last_result is None:
            self.status.emit("Nothing to report - calculate first.", 4000)
            return
        dirpath = QFileDialog.getExistingDirectory(
            self, "Generate report to folder...", "", _NODIALOG)
        if not dirpath:
            return
        # the central report's Blade strike modelling section on its own,
        # plus the results table as CSV
        from pathlib import Path
        from . import report_center
        out = Path(dirpath)
        try:
            results = self.bsm_state.results or {
                self.last_result["params"]["species"]: self.last_result}
            bsm_io.export_results(results, out)
            _doc, warnings = report_center.assemble(
                [report_center.bsm_section(self.window)], out, {"bsm"})
        except Exception as e:
            self.status.emit(f"Report failed: {e}", 6000)
            return
        self.status.emit(f"Report generated in {out}"
                         + (f" ({'; '.join(warnings)})" if warnings else ""),
                         5000)
