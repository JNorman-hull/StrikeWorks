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
    QCheckBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QScrollArea,
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
        bsm_state.calculated_all.connect(self._refresh_comparison)
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

        gv.addWidget(self._muted(
            "Treatments (deselect to leave out of the table and figure) - "
            "no deployment filter yet: the curated prediction dataset "
            "doesn't carry which deployment a treatment came from, only "
            "its name, so same-named treatments across deployments can't "
            "be told apart here."))
        self._treatment_checks = {}
        self.treatment_check_col = QVBoxLayout()
        gv.addLayout(self.treatment_check_col)

        self.tbl_compare = QTableWidget(0, 7)
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

        gv.addWidget(self._video_observed_group())
        gv.addWidget(self._model1_group())
        gv.addWidget(self._bsm_group())
        return g

    def _video_observed_group(self):
        g = Section("Video observed")
        gv = QVBoxLayout(g)
        head = QHBoxLayout()
        self.ed_video_label = QLineEdit("Video observed")
        self.ed_video_label.setToolTip("Label shown on the table/figure.")
        self.ed_video_label.textChanged.connect(self._refresh_comparison)
        head.addWidget(self.ed_video_label, stretch=1)
        self.chk_video_plot = QCheckBox("Plot")
        self.chk_video_plot.setChecked(True)
        self.chk_video_plot.toggled.connect(self._refresh_comparison)
        head.addWidget(self.chk_video_plot)
        gv.addLayout(head)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        self.spin_manual_total = QSpinBox()
        self.spin_manual_total.setRange(0, 1000000)
        self.spin_manual_total.valueChanged.connect(self._refresh_comparison)
        form.addWidget(self._muted("Sensors deployed"), 0, 0)
        form.addWidget(self.spin_manual_total, 0, 1)
        self.spin_manual_strike = QSpinBox()
        self.spin_manual_strike.setRange(0, 1000000)
        self.spin_manual_strike.valueChanged.connect(self._refresh_comparison)
        form.addWidget(self._muted("Strikes observed"), 0, 2)
        form.addWidget(self.spin_manual_strike, 0, 3)
        gv.addLayout(form)
        self.lbl_manual = QLabel("")
        self.lbl_manual.setStyleSheet(f"color:{TEXT};")
        self.lbl_manual.setWordWrap(True)
        gv.addWidget(self.lbl_manual)
        return g

    def _model1_group(self):
        g = Section("Model 1")
        gv = QVBoxLayout(g)
        head = QHBoxLayout()
        self.ed_model1_label = QLineEdit("Model 1")
        self.ed_model1_label.setToolTip("Label shown on the table/figure.")
        self.ed_model1_label.textChanged.connect(self._refresh_comparison)
        head.addWidget(self.ed_model1_label, stretch=1)
        self.chk_model1_plot = QCheckBox("Plot")
        self.chk_model1_plot.setChecked(True)
        self.chk_model1_plot.toggled.connect(self._refresh_comparison)
        head.addWidget(self.chk_model1_plot)
        gv.addLayout(head)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        self.spin_model1_total = QSpinBox()
        self.spin_model1_total.setRange(0, 1000000)
        self.spin_model1_total.valueChanged.connect(self._refresh_comparison)
        form.addWidget(self._muted("Sensors deployed"), 0, 0)
        form.addWidget(self.spin_model1_total, 0, 1)
        self.spin_model1_strike = QSpinBox()
        self.spin_model1_strike.setRange(0, 1000000)
        self.spin_model1_strike.valueChanged.connect(self._refresh_comparison)
        form.addWidget(self._muted("Predicted strike"), 0, 2)
        form.addWidget(self.spin_model1_strike, 0, 3)
        gv.addLayout(form)
        self.lbl_model1 = QLabel("")
        self.lbl_model1.setStyleSheet(f"color:{TEXT};")
        self.lbl_model1.setWordWrap(True)
        gv.addWidget(self.lbl_model1)
        return g

    def _bsm_group(self):
        g = Section("Blade strike model")
        gv = QVBoxLayout(g)
        head = QHBoxLayout()
        self.ed_bsm_label = QLineEdit("Blade strike model")
        self.ed_bsm_label.setToolTip("Label shown on the table/figure.")
        self.ed_bsm_label.textChanged.connect(self._refresh_comparison)
        head.addWidget(self.ed_bsm_label, stretch=1)
        gv.addLayout(head)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        self.lbl_scaly_value = QLabel("Not calculated")
        self.lbl_scaly_value.setStyleSheet(f"color:{TEXT};")
        self.chk_scaly_show = QCheckBox("Show")
        self.chk_scaly_show.setChecked(True)
        self.chk_scaly_show.toggled.connect(self._refresh_comparison)
        form.addWidget(self._muted("Scaly"), 0, 0)
        form.addWidget(self.lbl_scaly_value, 0, 1)
        form.addWidget(self.chk_scaly_show, 0, 2)
        self.lbl_eel_value = QLabel("Not calculated")
        self.lbl_eel_value.setStyleSheet(f"color:{TEXT};")
        self.chk_eel_show = QCheckBox("Show")
        self.chk_eel_show.setChecked(True)
        self.chk_eel_show.toggled.connect(self._refresh_comparison)
        form.addWidget(self._muted("Eel"), 1, 0)
        form.addWidget(self.lbl_eel_value, 1, 1)
        form.addWidget(self.chk_eel_show, 1, 2)
        gv.addLayout(form)
        return g

    @staticmethod
    def _muted(text):
        lab = QLabel(text)
        lab.setStyleSheet(f"color:{MUTED};")
        lab.setWordWrap(True)
        return lab

    # ── treatments checklist ─────────────────────────────────────────────────
    def _rebuild_treatment_checks(self, names):
        """Rebuilds the checklist (vertically stacked) from whatever
        treatments are actually in the current prediction summary,
        keeping each box's checked state (matched by name) across
        refreshes rather than resetting every treatment back to selected
        whenever a new run comes in."""
        current_names = list(self._treatment_checks.keys())
        if current_names == list(names):
            return
        keep = {n: cb.isChecked() for n, cb in self._treatment_checks.items()}
        while self.treatment_check_col.count():
            item = self.treatment_check_col.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._treatment_checks = {}
        for name in names:
            cb = QCheckBox(str(name))
            cb.setChecked(keep.get(name, True))
            cb.toggled.connect(self._refresh_comparison)
            self.treatment_check_col.addWidget(cb)
            self._treatment_checks[name] = cb

    def _selected_treatments(self):
        return {n for n, cb in self._treatment_checks.items() if cb.isChecked()}

    # ── reactions ────────────────────────────────────────────────────────────
    def _video_observed_bar(self):
        """(label, value_pct, ci_lo, ci_hi) for the video-observed entry,
        or None if it's empty/invalid/hidden - an extra bar in the
        comparison figure, same across every selected treatment (a single
        deployment-wide count, not per treatment)."""
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
        if total == 0 or strike > total or not self.chk_video_plot.isChecked():
            return None
        lo, hi, _half = wilson_interval(strike / total, total, confidence=95)
        label = self.ed_video_label.text().strip() or "Video observed"
        return (label, strike / total * 100, lo * 100, hi * 100)

    def _model1_bar(self):
        """(label, value_pct, ci_lo, ci_hi) for Model 1, or None if it's
        empty/invalid/hidden."""
        total = self.spin_model1_total.value()
        strike = self.spin_model1_strike.value()
        if total == 0:
            self.lbl_model1.setText("")
        elif strike > total:
            self.lbl_model1.setText(
                "Predicted strike cannot exceed sensors deployed.")
        else:
            lo, hi, half = wilson_interval(strike / total, total, confidence=95)
            self.lbl_model1.setText(
                f"{strike}/{total} = {strike / total * 100:.1f}% strike rate, "
                f"95% CI [{lo * 100:.1f}%, {hi * 100:.1f}%], "
                f"precision +/-{half * 100:.1f} percentage points.")
        if total == 0 or strike > total or not self.chk_model1_plot.isChecked():
            return None
        lo, hi, _half = wilson_interval(strike / total, total, confidence=95)
        label = self.ed_model1_label.text().strip() or "Model 1"
        return (label, strike / total * 100, lo * 100, hi * 100)

    def _refresh_comparison(self, *_args):
        # dual-species default: Calculator computes both scaly and eel per
        # run (BSMState.set_results()) - each species' Cen is that
        # species' own Pco_tip, an independent full BSM run, not one
        # result relabelled twice
        results = self.bsm_state.results or {}
        cen_raw = {
            sp: (results[sp]["Pco_tip"] * 100 if results.get(sp) else None)
            for sp in ("scaly", "eel")
        }
        self.lbl_scaly_value.setText(
            f"{cen_raw['scaly']:.1f}%" if cen_raw["scaly"] is not None
            else "Not calculated")
        self.lbl_eel_value.setText(
            f"{cen_raw['eel']:.1f}%" if cen_raw["eel"] is not None
            else "Not calculated")
        bsm_label = self.ed_bsm_label.text().strip() or "Blade strike model"
        cen_values = {
            f"{bsm_label} - scaly": cen_raw["scaly"] if self.chk_scaly_show.isChecked() else None,
            f"{bsm_label} - eel": cen_raw["eel"] if self.chk_eel_show.isChecked() else None,
        }

        summary = (self.prediction_state.summary
                  if self.prediction_state is not None else None)
        all_rows = summary if summary is not None and len(summary) else None
        self._rebuild_treatment_checks(
            list(all_rows["treatment"]) if all_rows is not None else [])
        selected = self._selected_treatments()
        rows = (all_rows[all_rows["treatment"].isin(selected)]
                if all_rows is not None else None)

        video_label = self.ed_video_label.text().strip() or "Video observed"
        model1_label = self.ed_model1_label.text().strip() or "Model 1"
        self.tbl_compare.setHorizontalHeaderLabels(
            ["Treatment", "N", video_label, "Model 1.1 OOF", model1_label,
             f"{bsm_label} - scaly", f"{bsm_label} - eel"])

        # each also refreshes its own status label as a side effect - one
        # call each, reused below, rather than once per table row
        video = self._video_observed_bar()
        model1 = self._model1_bar()

        self.tbl_compare.setRowCount(len(rows) if rows is not None else 0)
        comparisons = []
        if rows is not None:
            for i, (_, r) in enumerate(rows.iterrows()):
                ml_rate = r["strike_rate"] * 100
                self.tbl_compare.setItem(i, 0, QTableWidgetItem(str(r["treatment"])))
                self.tbl_compare.setItem(i, 1, QTableWidgetItem(str(int(r["n"]))))
                self.tbl_compare.setItem(i, 2, QTableWidgetItem(
                    f"{video[1]:.1f}%" if video else ""))
                self.tbl_compare.setItem(i, 3, QTableWidgetItem(
                    f"{ml_rate:.1f}% [{r['ci_lo'] * 100:.1f}%, {r['ci_hi'] * 100:.1f}%]"))
                self.tbl_compare.setItem(i, 4, QTableWidgetItem(
                    f"{model1[1]:.1f}%" if model1 else ""))
                self.tbl_compare.setItem(i, 5, QTableWidgetItem(
                    f"{cen_raw['scaly']:.1f}%" if cen_raw["scaly"] is not None
                    else "Not calculated"))
                self.tbl_compare.setItem(i, 6, QTableWidgetItem(
                    f"{cen_raw['eel']:.1f}%" if cen_raw["eel"] is not None
                    else "Not calculated"))
                comparisons.append((f"{r['treatment']} (Model 1.1 OOF)", ml_rate,
                                   r["ci_lo"] * 100, r["ci_hi"] * 100))

        if video is not None:
            comparisons.append(video)
        if model1 is not None:
            comparisons.append(model1)

        bsm_figures.draw_comparison_bars(self.fig_compare, cen_values, comparisons)
        self.canvas_compare.draw()
