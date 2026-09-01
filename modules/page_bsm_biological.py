# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Controller for the Model comparison page (renamed from Biological
interpretation - ROADMAP.md Chunk 5 task 5's final piece; the mortality
box that used to live here moved to Model prediction > Predict, see
ml_tab_predict.py).

Comparison: each treatment's data-driven (ML model) strike rate against
the mathematical (BSM) collision-probability estimate, as a table and a
bar figure, plus a manual strike/total count that folds into the same
figure as its own "Manual" bar (Wilson 95% CI).
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QGridLayout, QLabel, QScrollArea,
    QSizePolicy, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from . import bsm_figures
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
        bsm_state.calculated.connect(self._refresh_comparison)
        if prediction_state is not None:
            prediction_state.run_finished.connect(self._refresh_comparison)
        self._refresh_comparison()

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
        v.addWidget(self._comparison_group())
        v.addStretch()
        apply_section_defaults(frame)

    def _comparison_group(self):
        g = Section("Comparison")
        gv = QVBoxLayout(g)

        gv.addWidget(self._muted("Treatments (deselect to leave out of the "
                                 "table and figure)"))
        self._treatment_checks = {}
        self.treatment_check_row = QGridLayout()
        gv.addLayout(self.treatment_check_row)

        self.tbl_compare = QTableWidget(0, 6)
        self.tbl_compare.setHorizontalHeaderLabels(
            ["Treatment", "N", "Video ground truth", "Model 1.1 OOF",
             "Previous model prediction", "Cen"])
        self.tbl_compare.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_compare.setMinimumHeight(120)

        self.fig_compare = Figure(figsize=(5.0, 3.2), dpi=100)
        self.canvas_compare = FigureCanvas(self.fig_compare)
        self.canvas_compare.setMinimumSize(220, 190)
        self.canvas_compare.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        row = QSplitter(Qt.Orientation.Horizontal)
        row.setChildrenCollapsible(False)
        row.addWidget(self.tbl_compare)
        row.addWidget(self.canvas_compare)
        row.setSizes([1, 1])
        gv.addWidget(row, stretch=1)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        self.spin_manual_total = QSpinBox()
        self.spin_manual_total.setRange(0, 1000000)
        self.spin_manual_total.valueChanged.connect(self._recalculate_manual)
        form.addWidget(self._muted("Video ground truth: sensors deployed"), 0, 0)
        form.addWidget(self.spin_manual_total, 0, 1)
        self.spin_manual_strike = QSpinBox()
        self.spin_manual_strike.setRange(0, 1000000)
        self.spin_manual_strike.valueChanged.connect(self._recalculate_manual)
        form.addWidget(self._muted("Strikes observed"), 0, 2)
        form.addWidget(self.spin_manual_strike, 0, 3)
        self.spin_prev_model = QDoubleSpinBox()
        self.spin_prev_model.setRange(0.0, 100.0)
        self.spin_prev_model.setDecimals(1)
        self.spin_prev_model.setSuffix(" %")
        self.spin_prev_model.setSpecialValueText("Not entered")
        self.spin_prev_model.valueChanged.connect(self._refresh_comparison)
        form.addWidget(self._muted("Previous model prediction"), 0, 4)
        form.addWidget(self.spin_prev_model, 0, 5)
        gv.addLayout(form)
        self.lbl_manual = QLabel("")
        self.lbl_manual.setStyleSheet(f"color:{TEXT};")
        self.lbl_manual.setWordWrap(True)
        gv.addWidget(self.lbl_manual)
        return g

    @staticmethod
    def _muted(text):
        lab = QLabel(text)
        lab.setStyleSheet(f"color:{MUTED};")
        return lab

    # ── treatments checklist ─────────────────────────────────────────────────
    def _rebuild_treatment_checks(self, names):
        """Rebuilds the checklist from whatever treatments are actually in
        the current prediction summary, keeping each box's checked state
        (matched by name) across refreshes rather than resetting every
        treatment back to selected whenever a new run comes in."""
        current_names = list(self._treatment_checks.keys())
        if current_names == list(names):
            return
        keep = {n: cb.isChecked() for n, cb in self._treatment_checks.items()}
        while self.treatment_check_row.count():
            item = self.treatment_check_row.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._treatment_checks = {}
        for i, name in enumerate(names):
            cb = QCheckBox(str(name))
            cb.setChecked(keep.get(name, True))
            cb.toggled.connect(self._refresh_comparison)
            self.treatment_check_row.addWidget(cb, i // 4, i % 4)
            self._treatment_checks[name] = cb

    def _selected_treatments(self):
        return {n for n, cb in self._treatment_checks.items() if cb.isChecked()}

    # ── reactions ────────────────────────────────────────────────────────────
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

    def _video_ground_truth_bar(self):
        """(label, value_pct, ci_lo, ci_hi) for the video ground truth
        entry, or None if it's empty/invalid - an extra bar in the
        comparison figure, same across every selected treatment (a single
        deployment-wide count, not per treatment)."""
        total = self.spin_manual_total.value()
        strike = self.spin_manual_strike.value()
        if total == 0 or strike > total:
            return None
        lo, hi, _half = wilson_interval(strike / total, total, confidence=95)
        return ("Video ground truth", strike / total * 100, lo * 100, hi * 100)

    def _previous_model_bar(self):
        """(label, value_pct, None, None) for the previous-model-prediction
        entry, or None if it hasn't been entered (spinbox at its
        special-value "Not entered" floor of 0)."""
        value = self.spin_prev_model.value()
        if value <= 0:
            return None
        return ("Previous model prediction", value, None, None)

    def _refresh_comparison(self, *_args):
        res = self.bsm_state.last_result
        pco_cen = res["Pco_tip"] * 100 if res is not None else None
        summary = (self.prediction_state.summary
                  if self.prediction_state is not None else None)

        all_rows = summary if summary is not None and len(summary) else None
        self._rebuild_treatment_checks(
            list(all_rows["treatment"]) if all_rows is not None else [])
        selected = self._selected_treatments()
        rows = (all_rows[all_rows["treatment"].isin(selected)]
                if all_rows is not None else None)

        self.tbl_compare.setRowCount(len(rows) if rows is not None else 0)
        comparisons = []
        if rows is not None:
            for i, (_, r) in enumerate(rows.iterrows()):
                ml_rate = r["strike_rate"] * 100
                self.tbl_compare.setItem(i, 0, QTableWidgetItem(str(r["treatment"])))
                self.tbl_compare.setItem(i, 1, QTableWidgetItem(str(int(r["n"]))))
                video = self._video_ground_truth_bar()
                self.tbl_compare.setItem(i, 2, QTableWidgetItem(
                    f"{video[1]:.1f}%" if video else ""))
                self.tbl_compare.setItem(i, 3, QTableWidgetItem(
                    f"{ml_rate:.1f}% [{r['ci_lo'] * 100:.1f}%, {r['ci_hi'] * 100:.1f}%]"))
                prev = self._previous_model_bar()
                self.tbl_compare.setItem(i, 4, QTableWidgetItem(
                    f"{prev[1]:.1f}%" if prev else ""))
                self.tbl_compare.setItem(i, 5, QTableWidgetItem(
                    f"{pco_cen:.1f}%" if pco_cen is not None else "Not calculated"))
                comparisons.append((f"{r['treatment']} (Model 1.1 OOF)", ml_rate,
                                   r["ci_lo"] * 100, r["ci_hi"] * 100))

        video = self._video_ground_truth_bar()
        if video is not None:
            comparisons.append(video)
        prev = self._previous_model_bar()
        if prev is not None:
            comparisons.append(prev)

        bsm_figures.draw_comparison_bars(self.fig_compare, pco_cen, comparisons)
        self.canvas_compare.draw()
