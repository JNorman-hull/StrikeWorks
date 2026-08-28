# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Controller for the Biological interpretation page (ROADMAP.md Chunk 5
task 5's final piece).

Two boxes:

  - Comparison: each treatment's data-driven (ML model) strike rate
    against the mathematical (BSM) collision-probability estimate, as a
    table and a bar figure, plus a manual strike/total count that folds
    into the same figure as its own "Manual" bar (Wilson 95% CI).
  - Mortality: what the chosen species' own regression predicts from this
    BSM run (no adjustable threshold - each species' fMR regression
    already defines what counts as lethal), and a critical-velocity
    sensitivity sweep (2-10 m/s, bypassing the regression's own vcrit
    formula) marking the point the regression would derive by itself
    (`bsm_model.default_vcrit` - 4.8 m/s for scaly's floor case).

Longer-term (ROADMAP.md, not this pass): replace the mortality
regression's assumed uniform strike distribution with the concentric
strike locations the blade-strike model itself predicts.
"""
import numpy as np

from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QGridLayout, QHBoxLayout, QLabel,
    QSizePolicy, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from . import bsm_figures
from .bsm_model import default_vcrit, recompute_mortality, recompute_mortality_at_vcrit
from .ml_widgets import MUTED, TEXT, Section, apply_section_defaults
from .wilson_calc import wilson_interval

_VCRIT_MIN, _VCRIT_MAX, _VCRIT_STEP = 2.0, 10.0, 0.25


class BiologicalPage(QWidget):
    status = Signal(str, int)

    def __init__(self, frame, window, bsm_state, prediction_state=None):
        super().__init__()
        self.window = window
        self.bsm_state = bsm_state
        self.prediction_state = prediction_state
        self._build(frame)
        bsm_state.calculated.connect(self._on_bsm_result)
        if prediction_state is not None:
            prediction_state.run_finished.connect(self._refresh_comparison)
        if bsm_state.last_result is not None:
            self._on_bsm_result(bsm_state.last_result)
        else:
            self._refresh_comparison()

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, frame):
        v = QVBoxLayout(frame)
        v.setContentsMargins(4, 6, 4, 6)
        v.setSpacing(10)
        v.addWidget(self._comparison_group())
        v.addWidget(self._mortality_group())
        v.addStretch()
        apply_section_defaults(frame)

    def _comparison_group(self):
        g = Section("Comparison")
        gv = QVBoxLayout(g)

        row = QHBoxLayout()
        self.tbl_compare = QTableWidget(0, 5)
        self.tbl_compare.setHorizontalHeaderLabels(
            ["Treatment", "N", "ML strike rate (95% CI)", "BSM Pco (CEN)",
             "Difference (ML − BSM)"])
        self.tbl_compare.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_compare.setMinimumHeight(120)
        row.addWidget(self.tbl_compare, stretch=1)

        self.fig_compare = Figure(figsize=(5.0, 3.2), dpi=100)
        self.canvas_compare = FigureCanvas(self.fig_compare)
        self.canvas_compare.setMinimumSize(220, 190)
        self.canvas_compare.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        row.addWidget(self.canvas_compare, stretch=1)
        gv.addLayout(row, stretch=1)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        self.spin_manual_total = QSpinBox()
        self.spin_manual_total.setRange(0, 1000000)
        self.spin_manual_total.valueChanged.connect(self._recalculate_manual)
        form.addWidget(self._muted("Manual: sensors deployed"), 0, 0)
        form.addWidget(self.spin_manual_total, 0, 1)
        self.spin_manual_strike = QSpinBox()
        self.spin_manual_strike.setRange(0, 1000000)
        self.spin_manual_strike.valueChanged.connect(self._recalculate_manual)
        form.addWidget(self._muted("Strikes observed"), 0, 2)
        form.addWidget(self.spin_manual_strike, 0, 3)
        gv.addLayout(form)
        self.lbl_manual = QLabel("")
        self.lbl_manual.setStyleSheet(f"color:{TEXT};")
        self.lbl_manual.setWordWrap(True)
        gv.addWidget(self.lbl_manual)
        return g

    def _mortality_group(self):
        g = Section("Mortality")
        gv = QVBoxLayout(g)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        self.cmb_species = QComboBox()
        self.cmb_species.addItems(["scaly", "eel"])
        self.cmb_species.currentIndexChanged.connect(self._on_species_changed)
        form.addWidget(self._muted("Species"), 0, 0)
        form.addWidget(self.cmb_species, 0, 1)

        self.spin_eel_vcrit = QDoubleSpinBox()
        self.spin_eel_vcrit.setRange(0.0, 50.0)
        self.spin_eel_vcrit.setDecimals(2)
        self.spin_eel_vcrit.setValue(2.0)
        self.spin_eel_vcrit.setSuffix(" m/s")
        self.spin_eel_vcrit.valueChanged.connect(self._on_species_changed)
        form.addWidget(self._muted("Eel critical velocity"), 0, 2)
        form.addWidget(self.spin_eel_vcrit, 0, 3)
        gv.addLayout(form)

        self.lbl_mortality = QLabel("")
        self.lbl_mortality.setStyleSheet(f"color:{TEXT};font-weight:bold;")
        self.lbl_mortality.setWordWrap(True)
        gv.addWidget(self.lbl_mortality)

        self.fig_vcrit = Figure(figsize=(6.0, 3.2), dpi=100)
        self.canvas_vcrit = FigureCanvas(self.fig_vcrit)
        self.canvas_vcrit.setMinimumSize(220, 190)
        self.canvas_vcrit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        gv.addWidget(self.canvas_vcrit, stretch=1)
        return g

    @staticmethod
    def _muted(text):
        lab = QLabel(text)
        lab.setStyleSheet(f"color:{MUTED};")
        return lab

    # ── reactions ────────────────────────────────────────────────────────────
    def _on_bsm_result(self, res):
        self._recalculate_mortality()
        self._run_vcrit_sweep()
        self._refresh_comparison()

    def _on_species_changed(self, *_args):
        self._recalculate_mortality()
        self._run_vcrit_sweep()

    def _recalculate_mortality(self):
        res = self.bsm_state.last_result
        if res is None:
            return
        species = self.cmb_species.currentText()
        eel_vcrit = self.spin_eel_vcrit.value()
        out = recompute_mortality(res, species, eel_vcrit=eel_vcrit,
                                  threshold=None)
        self.lbl_mortality.setText(
            f"{species}: Pm={out['Pm'] * 100:.2f}%, S={out['S'] * 100:.2f}% "
            f"(Pco unchanged from the Calculator run, "
            f"{res['Pco_tip'] * 100:.2f}%).")

    def _run_vcrit_sweep(self):
        res = self.bsm_state.last_result
        if res is None:
            return
        species = self.cmb_species.currentText()
        eel_vcrit = self.spin_eel_vcrit.value()
        vcrit_vals = np.arange(_VCRIT_MIN, _VCRIT_MAX + 1e-9, _VCRIT_STEP)
        pm_vals = np.array([
            recompute_mortality_at_vcrit(res, species, float(v))["Pm"] * 100
            for v in vcrit_vals])
        default_v = default_vcrit(res, species, eel_vcrit=eel_vcrit)
        default_pm = recompute_mortality_at_vcrit(
            res, species, default_v)["Pm"] * 100
        bsm_figures.draw_vcrit_sweep(
            self.fig_vcrit, vcrit_vals, pm_vals, default_v, default_pm)
        self.canvas_vcrit.draw()

    def _recalculate_manual(self, *_args):
        total = self.spin_manual_total.value()
        strike = self.spin_manual_strike.value()
        if total == 0:
            self.lbl_manual.setText("")
        elif strike > total:
            self.lbl_manual.setText(
                "Strikes observed cannot exceed sensors deployed.")
        else:
            lo, hi, half = wilson_interval(strike / total, total, confidence=95)
            self.lbl_manual.setText(
                f"{strike}/{total} = {strike / total * 100:.1f}% strike rate, "
                f"95% CI [{lo * 100:.1f}%, {hi * 100:.1f}%], "
                f"precision +/-{half * 100:.1f} percentage points.")
        self._refresh_comparison()

    def _manual_comparison_bar(self):
        """(label, value_pct, ci_lo, ci_hi) for the manual entry, or None
        if it's empty/invalid - the extra bar in the comparison figure."""
        total = self.spin_manual_total.value()
        strike = self.spin_manual_strike.value()
        if total == 0 or strike > total:
            return None
        lo, hi, _half = wilson_interval(strike / total, total, confidence=95)
        return ("Manual", strike / total * 100, lo * 100, hi * 100)

    def _refresh_comparison(self):
        res = self.bsm_state.last_result
        pco_cen = res["Pco_tip"] * 100 if res is not None else None
        summary = (self.prediction_state.summary
                  if self.prediction_state is not None else None)

        rows = summary if summary is not None and len(summary) else None
        self.tbl_compare.setRowCount(len(rows) if rows is not None else 0)
        comparisons = []
        if rows is not None:
            for i, (_, r) in enumerate(rows.iterrows()):
                ml_rate = r["strike_rate"] * 100
                self.tbl_compare.setItem(i, 0, QTableWidgetItem(str(r["treatment"])))
                self.tbl_compare.setItem(i, 1, QTableWidgetItem(str(int(r["n"]))))
                self.tbl_compare.setItem(i, 2, QTableWidgetItem(
                    f"{ml_rate:.1f}% [{r['ci_lo'] * 100:.1f}%, {r['ci_hi'] * 100:.1f}%]"))
                if pco_cen is None:
                    self.tbl_compare.setItem(i, 3, QTableWidgetItem("Not calculated"))
                    self.tbl_compare.setItem(i, 4, QTableWidgetItem(""))
                else:
                    self.tbl_compare.setItem(i, 3, QTableWidgetItem(f"{pco_cen:.1f}%"))
                    self.tbl_compare.setItem(
                        i, 4, QTableWidgetItem(f"{ml_rate - pco_cen:+.1f} pp"))
                comparisons.append((str(r["treatment"]), ml_rate,
                                   r["ci_lo"] * 100, r["ci_hi"] * 100))

        manual = self._manual_comparison_bar()
        if manual is not None:
            comparisons.append(manual)

        if pco_cen is None:
            self.fig_compare.clear()
            self.canvas_compare.draw()
            return
        bsm_figures.draw_comparison_bars(self.fig_compare, pco_cen, comparisons)
        self.canvas_compare.draw()
