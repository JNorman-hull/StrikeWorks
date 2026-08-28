# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Controller for the Calculator page (Mathematical Blade Strike Modelling).

Faithful port of the old MVP app's `bsm/pages/calculator.py`: same inputs
(fish, pump, blade profile, optional observed strike data), same
`bsm_model.compute()` call, same results table/plots - restyled into
StrikeWorks' `Section`-based layout instead of raw `QGroupBox`, and the two
bar-chart Figures now use the shared in-app dark theme
(`bsm_figures.draw_pco`/`draw_pm`) rather than the old app's white-on-navy
styling. Deliberately still starts blank (species unselected, no seeded
numbers) - a faithful port, not a redesign.

Publishes every result through `BSMState.set_result()`, which is what lets
Sensitivity analysis re-sweep and Reporting export without this page
needing to know either exists.
"""
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSizePolicy, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from . import bsm_figures
from .bsm_model import compute
from .ml_widgets import ACCENT, MUTED, Section, apply_section_defaults

_NUMERIC = ("lf", "bf", "wf", "alpha", "eel_vcrit", "n", "N", "Q", "r", "bh")


class CalculatorPage(QWidget):
    calculated = Signal(dict)
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
            canvas.setMinimumSize(260, 220)
            canvas.setSizePolicy(QSizePolicy.Policy.Expanding,
                                 QSizePolicy.Policy.Expanding)

        self._build(frame)
        self._wire_validation()
        bsm_figures.draw_pco(self.fig_pco, {"Pco_tip": 0.0})
        bsm_figures.draw_pm(self.fig_pm, {"Pm": 0.0})
        self.canvas_pco.draw()
        self.canvas_pm.draw()

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, frame):
        outer = QHBoxLayout(frame)
        outer.setContentsMargins(4, 6, 4, 6)
        outer.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        left = QWidget()
        left.setStyleSheet("background:transparent;")
        lv = QVBoxLayout(left)
        lv.setSpacing(10)
        lv.addWidget(self._fish_group())
        lv.addWidget(self._pump_group())
        lv.addWidget(self._blade_group())
        lv.addWidget(self._observed_group())
        lv.addLayout(self._button_row())
        lv.addStretch()
        scroll.setWidget(left)
        scroll.setMinimumWidth(380)
        scroll.setMaximumWidth(440)
        outer.addWidget(scroll)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setSpacing(10)
        rv.addWidget(self._results_group())
        plots_row = QHBoxLayout()
        plots_row.addWidget(self.canvas_pco)
        plots_row.addWidget(self.canvas_pm)
        rv.addLayout(plots_row, stretch=1)
        outer.addWidget(right, stretch=1)

        apply_section_defaults(frame)

    def _fish_group(self):
        g = Section("Fish")
        grid = QGridLayout(g)
        grid.setColumnStretch(1, 1)
        self.in_lf = QLineEdit()
        self.in_bf = QLineEdit()
        self.in_species = QComboBox()
        self.in_species.addItems(["scaly", "eel"])
        self.in_species.setCurrentIndex(-1)
        self.in_wf = QLineEdit()
        self.in_alpha = QLineEdit()
        self.in_eel_vcrit = QLineEdit()
        rows = [
            ("Body length Lf (m)", self.in_lf),
            ("Body height Bf (m)", self.in_bf),
            ("Species", self.in_species),
            ("Rel. velocity wf (m/s)", self.in_wf),
            ("Pre-rotation α (rad)", self.in_alpha),
            ("Eel vcrit (m/s)", self.in_eel_vcrit),
        ]
        for i, (lbl, w) in enumerate(rows):
            grid.addWidget(self._muted(lbl), i, 0)
            grid.addWidget(w, i, 1)
        return g

    def _pump_group(self):
        g = Section("Pump")
        grid = QGridLayout(g)
        grid.setColumnStretch(1, 1)
        self.in_n = QLineEdit()
        self.in_N = QLineEdit()
        self.in_Q = QLineEdit()
        self.in_r = QLineEdit()
        self.in_bh = QLineEdit()
        rows = [
            ("Number of blades n", self.in_n),
            ("Shaft speed N (rpm)", self.in_N),
            ("Flow rate Q (m³/s)", self.in_Q),
            ("Tip radius r (m)", self.in_r),
            ("Hub radius bh (m)", self.in_bh),
        ]
        for i, (lbl, w) in enumerate(rows):
            grid.addWidget(self._muted(lbl), i, 0)
            grid.addWidget(w, i, 1)
        return g

    def _blade_group(self):
        g = Section("Blade profile")
        v = QVBoxLayout(g)
        self.blade_tbl = QTableWidget(0, 4)
        self.blade_tbl.setHorizontalHeaderLabels(
            ["r/Tr", "d (mm)", "β (°)", "δ (°)"])
        self.blade_tbl.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.blade_tbl.verticalHeader().setVisible(False)
        self._set_blade_rows(6)
        v.addWidget(self.blade_tbl)
        row = QHBoxLayout()
        self.btn_row_add = QPushButton("+ Row")
        self.btn_row_del = QPushButton("− Row")
        self.btn_row_add.clicked.connect(
            lambda: (self._set_blade_rows(self.blade_tbl.rowCount() + 1),
                     self._validate()))
        self.btn_row_del.clicked.connect(
            lambda: (self._set_blade_rows(self.blade_tbl.rowCount() - 1),
                     self._validate()))
        row.addStretch()
        row.addWidget(self.btn_row_add)
        row.addWidget(self.btn_row_del)
        v.addLayout(row)
        return g

    def _set_blade_rows(self, count):
        count = max(2, count)   # spline interpolation needs at least two points
        self.blade_tbl.setRowCount(count)
        for i in range(count):
            for j in range(4):
                if self.blade_tbl.item(i, j) is None:
                    self.blade_tbl.setItem(i, j, QTableWidgetItem(""))
        self.blade_tbl.setMaximumHeight(36 + 30 * count)

    def _observed_group(self):
        g = Section("Observed strike data")
        v = QVBoxLayout(g)
        self.chk_use_observed = None  # set below; kept off Section's own checkbox
        from PySide6.QtWidgets import QCheckBox
        self.chk_use_observed = QCheckBox("Include observed strike data")
        self.chk_use_observed.setChecked(True)
        self.chk_use_observed.toggled.connect(self.calculate)
        v.addWidget(self.chk_use_observed)
        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        self.in_total = QLineEdit()
        self.in_strike = QLineEdit()
        grid.addWidget(self._muted("Sensors deployed"), 0, 0)
        grid.addWidget(self.in_total, 0, 1)
        grid.addWidget(self._muted("Strikes observed"), 1, 0)
        grid.addWidget(self.in_strike, 1, 1)
        v.addLayout(grid)
        return g

    def _button_row(self):
        row = QHBoxLayout()
        self.btn_calc = QPushButton("Calculate")
        self.btn_calc.setMinimumHeight(30)
        self.btn_calc.setStyleSheet(
            f"QPushButton{{background-color:{ACCENT};color:#ffffff;"
            "border-radius:5px;padding:4px 14px;font-weight:bold;}"
            "QPushButton:disabled{background-color:#3a4150;color:#8a95aa;}")
        self.btn_calc.clicked.connect(self.calculate)
        row.addStretch()
        row.addWidget(self.btn_calc)
        return row

    def _results_group(self):
        g = Section("Results")
        v = QVBoxLayout(g)
        self.results_tbl = QTableWidget(2, 5)
        self.results_tbl.setHorizontalHeaderLabels(
            ["Method", "Pco (%)", "fMR (%)", "Pm (%)", "S (%)"])
        self.results_tbl.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.results_tbl.verticalHeader().setVisible(False)
        self.results_tbl.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self.results_tbl.setMaximumHeight(95)
        v.addWidget(self.results_tbl)
        self.wilson_lbl = QLabel("")
        self.wilson_lbl.setStyleSheet(f"color:{ACCENT};")
        self.wilson_lbl.setWordWrap(True)
        v.addWidget(self.wilson_lbl)
        return g

    @staticmethod
    def _muted(text):
        lab = QLabel(text)
        lab.setStyleSheet(f"color:{MUTED};")
        return lab

    # ── validation ───────────────────────────────────────────────────────────
    def _numeric_widgets(self):
        return [getattr(self, f"in_{k}") for k in _NUMERIC]

    def _validate(self, *_args):
        try:
            for w in self._numeric_widgets():
                if not w.text().strip():
                    self.btn_calc.setEnabled(False)
                    return
                float(w.text())
            if self.in_species.currentIndex() < 0:
                self.btn_calc.setEnabled(False)
                return
            for i in range(self.blade_tbl.rowCount()):
                for j in range(4):
                    item = self.blade_tbl.item(i, j)
                    if item is None or not item.text().strip():
                        self.btn_calc.setEnabled(False)
                        return
                    float(item.text())
            if self.chk_use_observed.isChecked():
                for w in (self.in_total, self.in_strike):
                    if not w.text().strip():
                        self.btn_calc.setEnabled(False)
                        return
                    float(w.text())
            self.btn_calc.setEnabled(True)
        except ValueError:
            self.btn_calc.setEnabled(False)

    def _wire_validation(self):
        for w in self._numeric_widgets() + [self.in_total, self.in_strike]:
            w.textChanged.connect(self._validate)
        self.in_species.currentIndexChanged.connect(self._validate)
        self.blade_tbl.itemChanged.connect(self._validate)
        self.chk_use_observed.toggled.connect(self._validate)
        self._validate()

    # ── state in/out ─────────────────────────────────────────────────────────
    def read_inputs(self):
        rttr, d, b, dlt = [], [], [], []
        for i in range(self.blade_tbl.rowCount()):
            rttr.append(float(self.blade_tbl.item(i, 0).text()))
            d.append(float(self.blade_tbl.item(i, 1).text()))
            b.append(float(self.blade_tbl.item(i, 2).text()))
            dlt.append(float(self.blade_tbl.item(i, 3).text()))
        return {
            "lf": float(self.in_lf.text()), "bf": float(self.in_bf.text()),
            "species": self.in_species.currentText(),
            "wf": float(self.in_wf.text()), "alpha": float(self.in_alpha.text()),
            "eel_vcrit": float(self.in_eel_vcrit.text()),
            "n": int(float(self.in_n.text())), "N": float(self.in_N.text()),
            "Q": float(self.in_Q.text()), "r": float(self.in_r.text()),
            "bh": float(self.in_bh.text()),
            "rttr": rttr, "d_vals": d, "beta_vals": b, "delta_vals": dlt,
            "total": int(float(self.in_total.text())) if self.in_total.text().strip() else 0,
            "strike": int(float(self.in_strike.text())) if self.in_strike.text().strip() else 0,
            "use_observed": self.chk_use_observed.isChecked(),
        }

    # ── run ──────────────────────────────────────────────────────────────────
    def calculate(self):
        try:
            res = compute(self.read_inputs())
        except Exception as e:
            self.status.emit(f"Error: {e}", 6000)
            return
        self.last_result = res
        self._update_table(res)
        bsm_figures.draw_pco(self.fig_pco, res)
        bsm_figures.draw_pm(self.fig_pm, res)
        self.canvas_pco.draw()
        self.canvas_pm.draw()
        self.calculated.emit(res)
        self.bsm_state.set_result(res)
        self.status.emit("Calculated.", 3000)

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
            self.wilson_lbl.setText(
                f"Wilson 95% CI on observed Pco: "
                f"[{res['wilson_lo'] * 100:.4f}%, {res['wilson_hi'] * 100:.4f}%]")
        else:
            self.wilson_lbl.setText("")
