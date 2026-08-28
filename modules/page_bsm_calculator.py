# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Controller for the Calculator page (Mathematical Blade Strike Modelling).

Inputs (fish, pump, blade profile - loaded from a saved `bsm_config` file
by picking it, no separate Load step) and a Calculate button. The result
goes into one "Blade strike output" card holding every equation result
(geometry, Pco, fMR, Pm, S, Wilson CI) - the figures and sweeps live on
Analysis and reporting instead.

"Observed strike data" is temporarily out of the visible UI (its widgets
are still built - `read_inputs()`/`_validate()` reference them unchanged -
just not attached to the layout) pending a decision on how to bring it
back; `bsm_model.compute()` itself is untouched and still accepts it.

Publishes every result through `BSMState.set_result()` (Analysis and
reporting re-sweeps from it) and writes `LATEST_RESULT_PATH` directly -
Calculator owns the one BSM run, so it owns publishing it.
"""
import json
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSizePolicy, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from . import bsm_config
from .bsm_model import compute
from .bsm_state import LATEST_RESULT_PATH, build_latest_payload, output_card_rows
from .ml_widgets import ACCENT, MUTED, MetaCard, Section, apply_section_defaults

_NUMERIC = ("lf", "bf", "wf", "alpha", "eel_vcrit", "n", "N", "Q", "r", "bh")


class CalculatorPage(QWidget):
    calculated = Signal(dict)
    status = Signal(str, int)

    def __init__(self, frame, window, bsm_state):
        super().__init__()
        self.window = window
        self.bsm_state = bsm_state
        self.last_result = None

        self._build(frame)
        self._wire_validation()
        self._load_selected_config()

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
        lv.addWidget(self._config_group())
        lv.addWidget(self._fish_group())
        lv.addWidget(self._pump_group())
        lv.addWidget(self._blade_group())
        # "Observed strike data" is temporarily off the visible page (see
        # module docstring) - built so read_inputs()/_validate() stay
        # unchanged, just never attached to a layout here. Kept as an
        # attribute (not just a local) so Qt doesn't garbage-collect the
        # unparented Section and its children out from under us.
        self._observed_section = self._observed_group()
        lv.addLayout(self._button_row())
        lv.addStretch()
        scroll.setWidget(left)
        scroll.setMinimumWidth(380)
        scroll.setMaximumWidth(440)
        outer.addWidget(scroll)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setSpacing(10)
        rv.addWidget(self._output_group())
        rv.addStretch()
        outer.addWidget(right, stretch=1)

        apply_section_defaults(frame)

    def _config_group(self):
        g = Section("Configuration")
        v = QVBoxLayout(g)
        self.cmb_config = QComboBox()
        self.cmb_config.setMinimumWidth(140)
        self.cmb_config.currentIndexChanged.connect(self._load_selected_config)
        v.addWidget(self.cmb_config)
        self._populate_configs()
        return g

    def _populate_configs(self):
        # signals blocked: the Fish/Pump/Blade widgets _load_selected_config
        # needs don't exist yet this early in _build() - __init__ triggers
        # the initial load explicitly once they do
        self.cmb_config.blockSignals(True)
        self.cmb_config.clear()
        configs = bsm_config.list_configs()
        for p in configs:
            self.cmb_config.addItem(p.stem, str(p))
        self.cmb_config.blockSignals(False)

    def _load_selected_config(self, *_args):
        path = self.cmb_config.currentData()
        if not path:
            return
        try:
            p = bsm_config.load_config(path)
        except Exception as e:
            self.status.emit(f"Could not load configuration: {e}", 6000)
            return

        self.in_lf.setText(f"{p['lf']:g}")
        self.in_bf.setText(f"{p['bf']:g}")
        idx = self.in_species.findText(p["species"])
        self.in_species.setCurrentIndex(idx if idx >= 0 else -1)
        self.in_wf.setText(f"{p['wf']:g}")
        self.in_alpha.setText(f"{p['alpha']:g}")
        self.in_eel_vcrit.setText(f"{p['eel_vcrit']:g}")
        self.in_n.setText(f"{p['n']:g}")
        self.in_N.setText(f"{p['N']:g}")
        self.in_Q.setText(f"{p['Q']:g}")
        self.in_r.setText(f"{p['r']:g}")
        self.in_bh.setText(f"{p['bh']:g}")

        rows = list(zip(p["rttr"], p["d_vals"], p["beta_vals"], p["delta_vals"]))
        self._set_blade_rows(len(rows))
        for i, (rt, d, b, dl) in enumerate(rows):
            self.blade_tbl.setItem(i, 0, QTableWidgetItem(f"{rt:g}"))
            self.blade_tbl.setItem(i, 1, QTableWidgetItem(f"{d:g}"))
            self.blade_tbl.setItem(i, 2, QTableWidgetItem(f"{b:g}"))
            self.blade_tbl.setItem(i, 3, QTableWidgetItem(f"{dl:g}"))

        self.status.emit(f"Loaded configuration: {Path(path).stem}", 4000)
        self._validate()

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
        self.chk_use_observed = QCheckBox("Include observed strike data")
        self.chk_use_observed.setChecked(False)
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

    def _output_group(self):
        g = Section("Blade strike output")
        v = QVBoxLayout(g)
        self.card_output = MetaCard("Blade strike output")
        v.addWidget(self.card_output)
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
        self._update_output_card(res)
        self.calculated.emit(res)
        self.bsm_state.set_result(res)
        self._publish_latest(res)
        self.status.emit("Calculated.", 3000)

    def _update_output_card(self, res):
        self.card_output.set_rows(output_card_rows(res))
        has_obs = "Pco_obs" in res
        self.wilson_lbl.setText(
            f"Wilson 95% CI on observed Pco: [{res['wilson_lo'] * 100:.4f}%, "
            f"{res['wilson_hi'] * 100:.4f}%]" if has_obs else "")

    def _publish_latest(self, res):
        payload = build_latest_payload(res)
        LATEST_RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LATEST_RESULT_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
