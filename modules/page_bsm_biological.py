# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Controller for the Biological interpretation page (ROADMAP.md Chunk 5
task 5's final piece).

Three independent tools, each answering one of the roadmap's asks rather
than one mega-table trying to do all of them at once:

  - Per-treatment comparison: each treatment's data-driven (ML model)
    strike rate from `PredictionState.summary`, alongside the single
    mathematical (BSM) collision-probability estimate for the same
    physical setup - shows where the model over/under-predicts a given
    treatment's empirical rate.
  - Mortality / survival estimator: re-runs the BSM mortality integral
    (`bsm_model.recompute_mortality`) at a user-adjustable critical
    mortality threshold and a chosen species (own regression + critical
    velocity), holding the BSM run's hydrodynamic exposure fixed.
  - Manual strike/no-strike proportion: a plain count-based check
    independent of both models, for a quick "what would N=40, 6 strikes
    imply" sanity check.

Longer-term (ROADMAP.md, not this pass): replace the mortality
regression's assumed uniform strike distribution with the concentric
strike locations the blade-strike model itself predicts.
"""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .bsm_model import recompute_mortality
from .ml_widgets import MUTED, TEXT, Section, apply_section_defaults
from .wilson_calc import wilson_interval


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
        v.addWidget(self._manual_group())
        v.addStretch()
        apply_section_defaults(frame)

    def _comparison_group(self):
        g = Section("Per-treatment comparison")
        gv = QVBoxLayout(g)
        note = QLabel(
            "Each treatment's data-driven strike rate (from Model "
            "prediction) alongside the mathematical model's collision "
            "probability for the same setup, calculated on Calculator.")
        note.setStyleSheet(f"color:{MUTED};")
        note.setWordWrap(True)
        gv.addWidget(note)
        self.tbl_compare = QTableWidget(0, 5)
        self.tbl_compare.setHorizontalHeaderLabels(
            ["Treatment", "N", "ML strike rate (95% CI)", "BSM Pco (CEN)",
             "Difference (ML − BSM)"])
        self.tbl_compare.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.tbl_compare.verticalHeader().setVisible(False)
        self.tbl_compare.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_compare.setMinimumHeight(120)
        gv.addWidget(self.tbl_compare)
        return g

    def _mortality_group(self):
        g = Section("Mortality / survival estimator")
        gv = QVBoxLayout(g)
        note = QLabel(
            "Re-runs the mortality integral from the last Calculator run "
            "at a chosen species and critical mortality threshold, "
            "holding the hydrodynamic exposure (blade sweep, strike "
            "velocity) fixed - each species uses its own regression and "
            "critical velocity.")
        note.setStyleSheet(f"color:{MUTED};")
        note.setWordWrap(True)
        gv.addWidget(note)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setColumnStretch(1, 1)
        self.cmb_species = QComboBox()
        self.cmb_species.addItems(["scaly", "eel"])
        self.cmb_species.currentIndexChanged.connect(self._recalculate_mortality)
        form.addWidget(self._muted("Species"), 0, 0)
        form.addWidget(self.cmb_species, 0, 1)

        self.spin_eel_vcrit = QDoubleSpinBox()
        self.spin_eel_vcrit.setRange(0.0, 50.0)
        self.spin_eel_vcrit.setDecimals(2)
        self.spin_eel_vcrit.setValue(2.0)
        self.spin_eel_vcrit.setSuffix(" m/s")
        self.spin_eel_vcrit.valueChanged.connect(self._recalculate_mortality)
        form.addWidget(self._muted("Eel critical velocity"), 1, 0)
        form.addWidget(self.spin_eel_vcrit, 1, 1)

        self.spin_threshold = QDoubleSpinBox()
        self.spin_threshold.setRange(0.0, 100.0)
        self.spin_threshold.setDecimals(1)
        self.spin_threshold.setValue(50.0)
        self.spin_threshold.setSuffix(" %")
        self.spin_threshold.setToolTip(
            "A strike is counted as lethal if its injury fraction (fMR) "
            "meets or exceeds this threshold. Set to 0 to use the "
            "continuous fMR instead (same result as Calculator's Pm).")
        self.spin_threshold.valueChanged.connect(self._recalculate_mortality)
        form.addWidget(self._muted("Critical mortality threshold"), 2, 0)
        form.addWidget(self.spin_threshold, 2, 1)
        gv.addLayout(form)

        self.lbl_mortality = QLabel(
            "Run a calculation on Calculator to populate this estimate.")
        self.lbl_mortality.setStyleSheet(f"color:{TEXT};font-weight:bold;")
        self.lbl_mortality.setWordWrap(True)
        gv.addWidget(self.lbl_mortality)
        return g

    def _manual_group(self):
        g = Section("Manual strike/no-strike proportion")
        gv = QVBoxLayout(g)
        note = QLabel(
            "A quick check independent of both models: enter observed "
            "counts directly to see the implied proportion and its "
            "Wilson 95% CI.")
        note.setStyleSheet(f"color:{MUTED};")
        note.setWordWrap(True)
        gv.addWidget(note)
        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setColumnStretch(1, 1)
        self.spin_manual_total = QSpinBox()
        self.spin_manual_total.setRange(0, 1000000)
        self.spin_manual_total.valueChanged.connect(self._recalculate_manual)
        form.addWidget(self._muted("Sensors deployed"), 0, 0)
        form.addWidget(self.spin_manual_total, 0, 1)
        self.spin_manual_strike = QSpinBox()
        self.spin_manual_strike.setRange(0, 1000000)
        self.spin_manual_strike.valueChanged.connect(self._recalculate_manual)
        form.addWidget(self._muted("Strikes observed"), 1, 0)
        form.addWidget(self.spin_manual_strike, 1, 1)
        gv.addLayout(form)
        self.lbl_manual = QLabel("")
        self.lbl_manual.setStyleSheet(f"color:{TEXT};font-weight:bold;")
        self.lbl_manual.setWordWrap(True)
        gv.addWidget(self.lbl_manual)
        return g

    @staticmethod
    def _muted(text):
        lab = QLabel(text)
        lab.setStyleSheet(f"color:{MUTED};")
        return lab

    # ── reactions ────────────────────────────────────────────────────────────
    def _on_bsm_result(self, res):
        self._recalculate_mortality()
        self._refresh_comparison()

    def _recalculate_mortality(self, *_args):
        res = self.bsm_state.last_result
        if res is None:
            return
        species = self.cmb_species.currentText()
        eel_vcrit = self.spin_eel_vcrit.value()
        threshold = self.spin_threshold.value() / 100.0
        out = recompute_mortality(res, species, eel_vcrit=eel_vcrit,
                                  threshold=threshold if threshold > 0 else None)
        self.lbl_mortality.setText(
            f"{species} at a {self.spin_threshold.value():.1f}% critical "
            f"mortality threshold -> Pm={out['Pm'] * 100:.2f}%, "
            f"S={out['S'] * 100:.2f}% (Pco unchanged from the Calculator "
            f"run, {res['Pco_tip'] * 100:.2f}%).")

    def _recalculate_manual(self, *_args):
        total = self.spin_manual_total.value()
        strike = self.spin_manual_strike.value()
        if total == 0:
            self.lbl_manual.setText("")
            return
        if strike > total:
            self.lbl_manual.setText("Strikes observed cannot exceed sensors deployed.")
            return
        lo, hi, half = wilson_interval(strike / total, total, confidence=95)
        self.lbl_manual.setText(
            f"{strike}/{total} = {strike / total * 100:.1f}% strike rate, "
            f"95% CI [{lo * 100:.1f}%, {hi * 100:.1f}%], "
            f"precision +/-{half * 100:.1f} percentage points.")

    def _refresh_comparison(self):
        res = self.bsm_state.last_result
        pco_cen = res["Pco_tip"] * 100 if res is not None else None
        summary = (self.prediction_state.summary
                  if self.prediction_state is not None else None)
        if summary is None or not len(summary):
            self.tbl_compare.setRowCount(0)
            return
        self.tbl_compare.setRowCount(len(summary))
        for i, (_, r) in enumerate(summary.iterrows()):
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
