# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Controller for the Analysis and reporting page (was "Sensitivity
analysis" - ROADMAP.md Chunk 5 task 5 follow-up).

Everything Calculator no longer shows a figure for lives here, and this
page now also owns export - the standalone Reporting page was folded in:

  - One "Figures" box (the same shape as Model training's "Evaluation
    figures" - a grid of canvases, not one box per figure): the Pco/Pm
    bars plus three parameter sweeps in the style of the standalone
    `/Scripts/Mathematical BSM/Project` scripts (`cen_2025_..._CUSTOM.py`'s
    Q_LEVELS fan-out - viridis-coloured lines, the design curve drawn
    heavier, each curve labelled directly on the line): collision
    probability vs relative fish velocity by flow rate, mortality
    probability vs shaft speed by flow rate, and mortality probability vs
    relative fish velocity (single line).
  - The same Results table and "Blade strike output" card Calculator
    shows.
  - One "Generate report..." button - CSV + every figure as PNG + an HTML
    report (equations, tables, figures) in one folder.

Reacts to `BSMState.calculated` rather than Calculator calling this page
directly, so it's populated whether Calculator ran on this visit or the
state already held a result from an earlier one.
"""
import numpy as np

from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import bsm_figures, bsm_io
from .bsm_model import compute
from .bsm_report import build_bsm_report_html
from .bsm_state import output_card_rows
from .ml_report import wrap_html_document
from .ml_widgets import ACCENT, MetaCard, Section, apply_section_defaults

_NODIALOG = QFileDialog.Option.DontUseNativeDialog
_WF_STEP = 0.1
_WF_SPAN = 3.5
_Q_MULTIPLIERS = [0.6, 0.8, 1.0, 1.2, 1.4, 1.6]
_N_MULTIPLIERS_SPAN = (0.6, 1.4)   # shaft-speed sweep bounds, x the design N
_N_POINTS = 41


class SensitivityPage(QWidget):
    status = Signal(str, int)

    def __init__(self, frame, window, bsm_state):
        super().__init__()
        self.window = window
        self.bsm_state = bsm_state
        self.last_result = None
        self.wf_pm_sweep = None      # (wf_vals, Pm%) - single line
        self.wf_q_curves = None      # {label: (wf_vals, Pco%)} - by flow rate
        self.n_q_curves = None       # {label: (N_vals, Pm%)} - by flow rate

        self._build(frame)
        self._draw_blank()
        bsm_state.calculated.connect(self.update_from_result)
        if bsm_state.last_result is not None:
            self.update_from_result(bsm_state.last_result)

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, frame):
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        outer.addWidget(scroll)

        body = QWidget()
        body.setStyleSheet("background:transparent;")
        scroll.setWidget(body)
        v = QVBoxLayout(body)
        v.setContentsMargins(4, 6, 4, 6)
        v.setSpacing(10)

        v.addWidget(self._figures_group())

        row = QHBoxLayout()
        row.addWidget(self._results_group(), stretch=1)
        row.addWidget(self._output_group(), stretch=1)
        v.addLayout(row)

        self.btn_report = QPushButton("Generate report...")
        self.btn_report.setEnabled(False)
        self.btn_report.setStyleSheet(
            f"QPushButton{{background-color:{ACCENT};color:#ffffff;"
            "border-radius:5px;padding:4px 14px;font-weight:bold;}"
            "QPushButton:disabled{background-color:#3a4150;color:#8a95aa;}")
        self.btn_report.clicked.connect(self._generate_report)
        report_row = QHBoxLayout()
        report_row.addStretch()
        report_row.addWidget(self.btn_report)
        v.addLayout(report_row)

        apply_section_defaults(frame)

    def _figures_group(self):
        g = Section("Figures")
        grid = QGridLayout(g)
        grid.setSpacing(8)

        self.fig_pco = Figure(figsize=(4.0, 3.2), dpi=100)
        self.fig_pm = Figure(figsize=(4.0, 3.2), dpi=100)
        self.fig_wf_pm = Figure(figsize=(4.0, 3.2), dpi=100)
        self.fig_wf_q = Figure(figsize=(6.5, 4.0), dpi=100)
        self.fig_n_q = Figure(figsize=(6.5, 4.0), dpi=100)
        self.canvas_pco = self._canvas(self.fig_pco)
        self.canvas_pm = self._canvas(self.fig_pm)
        self.canvas_wf_pm = self._canvas(self.fig_wf_pm)
        self.canvas_wf_q = self._canvas(self.fig_wf_q)
        self.canvas_n_q = self._canvas(self.fig_n_q)

        grid.addWidget(self.canvas_pco, 0, 0)
        grid.addWidget(self.canvas_pm, 0, 1)
        grid.addWidget(self.canvas_wf_pm, 0, 2)
        grid.addWidget(self.canvas_wf_q, 1, 0, 1, 2)
        grid.addWidget(self.canvas_n_q, 1, 2, 1, 1)
        for c in range(3):
            grid.setColumnStretch(c, 1)
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
        bsm_figures.draw_pco(self.fig_pco, {"Pco_tip": 0.0})
        bsm_figures.draw_pm(self.fig_pm, {"Pm": 0.0})
        bsm_figures.draw_sweep_lines(self.fig_wf_q, "wf (m/s)", "Pco (%)", {})
        bsm_figures.draw_sweep_lines(self.fig_n_q, "Shaft speed N (rpm)",
                                     "Pm (%)", {})
        bsm_figures.draw_sens_wf(self.fig_wf_pm, [], [], [], [], span=_WF_SPAN,
                                 y_label="Mortality probability (%)")
        for c in (self.canvas_pco, self.canvas_pm, self.canvas_wf_q,
                  self.canvas_n_q, self.canvas_wf_pm):
            c.draw()

    # ── reactions ────────────────────────────────────────────────────────────
    def update_from_result(self, res):
        self.last_result = res
        bsm_figures.draw_pco(self.fig_pco, res)
        bsm_figures.draw_pm(self.fig_pm, res)
        self.canvas_pco.draw()
        self.canvas_pm.draw()
        self._update_table(res)
        self.card_output.set_rows(output_card_rows(res))
        try:
            self._run_wf_sweeps(res)
            self._run_wf_q_sweep(res)
            self._run_n_q_sweep(res)
        except Exception as e:
            self.status.emit(f"Sensitivity sweep failed: {e}", 6000)
            return
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

    # ── sweeps ───────────────────────────────────────────────────────────────
    def _sweep(self, base_params, overrides_list):
        """compute() once per dict in `overrides_list`, each merged onto
        base_params. Returns (Pco_tip%, Pm%) arrays, same length/order."""
        pco = np.empty(len(overrides_list))
        pm = np.empty(len(overrides_list))
        for i, overrides in enumerate(overrides_list):
            p = dict(base_params)
            p.update(overrides)
            r = compute(p)
            pco[i], pm[i] = r["Pco_tip"] * 100, r["Pm"] * 100
        return pco, pm

    def _run_wf_sweeps(self, res):
        base_params = res["params"]
        wf_vals = np.round(np.arange(-_WF_SPAN, _WF_SPAN + 1e-9, _WF_STEP), 10)
        _pco, pm = self._sweep(base_params, [{"wf": float(w)} for w in wf_vals])
        self.wf_pm_sweep = (wf_vals, pm)
        bsm_figures.draw_sens_wf(
            self.fig_wf_pm, wf_vals, pm, wf_vals, pm, span=_WF_SPAN,
            y_label="Mortality probability (%)")
        self.canvas_wf_pm.draw()

    def _run_wf_q_sweep(self, res):
        base_params = res["params"]
        wf_vals = np.round(np.arange(-_WF_SPAN, _WF_SPAN + 1e-9, _WF_STEP), 10)
        design_q = base_params["Q"]
        curves = {}
        design_label = None
        for mult in _Q_MULTIPLIERS:
            q = design_q * mult
            pco, _pm = self._sweep(base_params,
                                   [{"wf": float(w), "Q": q} for w in wf_vals])
            label = f"Q={q:.3g}" + (" (design)" if abs(mult - 1.0) < 1e-9 else "")
            if abs(mult - 1.0) < 1e-9:
                design_label = label
            curves[label] = (wf_vals, pco)
        self.wf_q_curves = curves
        bsm_figures.draw_sweep_lines(
            self.fig_wf_q, "Relative fish velocity wf (m/s)",
            "Collision probability (%)", curves, design_label=design_label,
            annotation=self._annotation(base_params))
        self.canvas_wf_q.draw()

    def _run_n_q_sweep(self, res):
        base_params = res["params"]
        design_n = base_params["N"]
        lo, hi = _N_MULTIPLIERS_SPAN
        n_vals = np.linspace(design_n * lo, design_n * hi, _N_POINTS)
        design_q = base_params["Q"]
        curves = {}
        design_label = None
        for mult in _Q_MULTIPLIERS:
            q = design_q * mult
            _pco, pm = self._sweep(base_params,
                                   [{"N": float(n), "Q": q} for n in n_vals])
            label = f"Q={q:.3g}" + (" (design)" if abs(mult - 1.0) < 1e-9 else "")
            if abs(mult - 1.0) < 1e-9:
                design_label = label
            curves[label] = (n_vals, pm)
        self.n_q_curves = curves
        bsm_figures.draw_sweep_lines(
            self.fig_n_q, "Shaft speed N (rpm)", "Mortality probability (%)",
            curves, design_label=design_label,
            annotation=self._annotation(base_params))
        self.canvas_n_q.draw()

    @staticmethod
    def _annotation(p):
        return (f"Model = EVS-EN 18110 (2025)\n"
                f"Lf = {p['lf'] * 1000:g} mm  Bf = {p['bf'] * 1000:g} mm\n"
                f"Design Q = {p['Q']:g} m³/s  N = {p['N']:g} rpm")

    # ── report ───────────────────────────────────────────────────────────────
    def _generate_report(self):
        if self.last_result is None:
            self.status.emit("Nothing to report - calculate first.", 4000)
            return
        dirpath = QFileDialog.getExistingDirectory(
            self, "Generate report to folder...", "", _NODIALOG)
        if not dirpath:
            return
        try:
            from pathlib import Path
            out = Path(dirpath)
            bsm_io.export_results(self.last_result, self.fig_pco, self.fig_pm, out)
            image_paths = {"pco": out / "barplot_pco.png",
                           "pm": out / "barplot_pm.png"}
            if self.wf_q_curves:
                bsm_io.export_sweep_lines(
                    self.wf_q_curves, self.fig_wf_q, out,
                    stem="sensitivity_pco_wf_by_q", x_header="wf_m_per_s",
                    line_header="flow", y_header="pco_percent")
                image_paths["wf_q"] = out / "sensitivity_pco_wf_by_q.png"
            if self.n_q_curves:
                bsm_io.export_sweep_lines(
                    self.n_q_curves, self.fig_n_q, out,
                    stem="sensitivity_pm_n_by_q", x_header="N_rpm",
                    line_header="flow", y_header="pm_percent")
                image_paths["n_q"] = out / "sensitivity_pm_n_by_q.png"
            if self.wf_pm_sweep:
                bsm_io.export_sensitivity(
                    *self.wf_pm_sweep, self.fig_wf_pm, out,
                    stem="sensitivity_pm_wf", x_header="wf_m_per_s")
                image_paths["wf_pm"] = out / "sensitivity_pm_wf.png"

            body = build_bsm_report_html(self.last_result,
                                         image_paths=image_paths,
                                         embed_images=True)
            (out / "report.html").write_text(wrap_html_document(body),
                                             encoding="utf-8")
            self.status.emit(f"Report generated in {out}", 5000)
        except Exception as e:
            self.status.emit(f"Report failed: {e}", 6000)
