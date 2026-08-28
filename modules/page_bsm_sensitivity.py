# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Controller for the Sensitivity analysis page.

Port of the old MVP app's `bsm/pages/sensitivity.py`: every parameter held
at the Calculator's last values, relative fish velocity wf swept
-3.5..+3.5 m/s in 0.1 m/s steps, CEN collision probability re-computed at
each step and fit with a cubic spline. Reacts to `BSMState.calculated`
instead of Calculator calling it directly, so this page updates whether
Calculator ran on this visit or the state was already populated from an
earlier one.
"""
import numpy as np
from scipy.interpolate import CubicSpline

from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout,
    QWidget,
)

from . import bsm_figures, bsm_io
from .bsm_model import compute
from .ml_widgets import MUTED, Section, apply_section_defaults

_NODIALOG = QFileDialog.Option.DontUseNativeDialog
_WF_STEP = 0.1
_WF_SPAN = 3.5


class SensitivityPage(QWidget):
    status = Signal(str, int)

    def __init__(self, frame, window, bsm_state):
        super().__init__()
        self.window = window
        self.bsm_state = bsm_state
        self.base_params = None
        self.wf_sweep = None
        self.fig_wf = Figure(figsize=(5.5, 4.0), dpi=100)
        self.canvas_wf = FigureCanvas(self.fig_wf)
        self.canvas_wf.setSizePolicy(QSizePolicy.Policy.Expanding,
                                     QSizePolicy.Policy.Expanding)
        self._build(frame)
        bsm_figures.draw_sens_wf(self.fig_wf, [], [], [], [], span=_WF_SPAN)
        self.canvas_wf.draw()
        bsm_state.calculated.connect(self.update_from_result)
        if bsm_state.last_result is not None:
            self.update_from_result(bsm_state.last_result)

    def _build(self, frame):
        v = QVBoxLayout(frame)
        v.setContentsMargins(4, 6, 4, 6)
        v.setSpacing(10)
        self.info_lbl = QLabel(
            "Run a calculation on Calculator to populate the sweep.")
        self.info_lbl.setStyleSheet(f"color:{MUTED};")
        self.info_lbl.setWordWrap(True)
        v.addWidget(self.info_lbl)

        g = Section("Collision probability vs relative fish velocity (wf)")
        gv = QVBoxLayout(g)
        gv.addWidget(self.canvas_wf, stretch=1)
        row = QHBoxLayout()
        self.btn_save_wf = QPushButton("Save sweep...")
        self.btn_save_wf.setEnabled(False)
        self.btn_save_wf.clicked.connect(self._save_wf)
        row.addStretch()
        row.addWidget(self.btn_save_wf)
        gv.addLayout(row)
        v.addWidget(g, stretch=1)

        apply_section_defaults(frame)

    # ── sweep ────────────────────────────────────────────────────────────────
    def update_from_result(self, res):
        self.base_params = dict(res["params"])
        try:
            self._run_wf_sweep()
        except Exception as e:
            self.status.emit(f"Sensitivity sweep failed: {e}", 6000)
            return
        self.info_lbl.setText(
            "All parameters fixed at the Calculator values; wf swept "
            f"-{_WF_SPAN:g} to +{_WF_SPAN:g} m/s in {_WF_STEP:g} m/s steps.")

    def _run_wf_sweep(self):
        wf_vals = np.round(np.arange(-_WF_SPAN, _WF_SPAN + 1e-9, _WF_STEP), 10)
        pco = np.empty(len(wf_vals))
        for i, wf in enumerate(wf_vals):
            p = dict(self.base_params)
            p["wf"] = float(wf)
            pco[i] = compute(p)["Pco_tip"] * 100
        self.wf_sweep = (wf_vals, pco)

        fit = CubicSpline(wf_vals, pco, bc_type="natural")
        x_fit = np.linspace(-_WF_SPAN, _WF_SPAN, 801)
        bsm_figures.draw_sens_wf(self.fig_wf, wf_vals, pco, x_fit, fit(x_fit),
                                 span=_WF_SPAN)
        self.canvas_wf.draw()
        self.btn_save_wf.setEnabled(True)

    # ── export ───────────────────────────────────────────────────────────────
    def _save_wf(self):
        if self.wf_sweep is None:
            self.status.emit("Nothing to save - calculate first.", 4000)
            return
        dirpath = QFileDialog.getExistingDirectory(
            self, "Save sweep to folder...", "", _NODIALOG)
        if not dirpath:
            return
        try:
            out = bsm_io.export_sensitivity(
                *self.wf_sweep, self.fig_wf, dirpath,
                stem="sensitivity_wf", x_header="wf_m_per_s")
            self.status.emit(f"Saved sweep to {out}", 5000)
        except Exception as e:
            self.status.emit(f"Save failed: {e}", 6000)
