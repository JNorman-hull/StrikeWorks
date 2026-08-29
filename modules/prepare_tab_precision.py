# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Study design tab - sampling precision, for a pragmatic choice of effort.

Deliberately one simple tool for now rather than a full study-planning
suite: given a hypothesised strike rate and a planned sample size, show the
Wilson score interval (`wilson_calc.py`) that size would achieve, plus how
it changes at a spread of other sizes - enough to answer "is N=50 enough,
or should I plan for 100?" without asking the user to understand the
statistics. The deployment/treatment planning that used to live on this
tab (site, machine, per-treatment conditions) moved to Setup and deploy >
Create and edit deployment, which now owns writing the plan into the
library.

"Load from Blade Strike Modelling" (ROADMAP.md Chunk 5 task 5) reads
`bsm_state.LATEST_RESULT_PATH` - the small JSON Calculator writes after
every run - and fills the expected strike rate from the CEN estimate.
Deliberately reads the file rather than taking a live BSMState reference:
Setup and deploy stays decoupled from whether the BSM pages have even been
visited this session, and "expected" strike rate for planning purposes is
the a-priori CEN estimate, not an observed rate that does not exist yet.
"""
import json

import numpy as np

from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from PySide6.QtCore import Qt

from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from .bsm_state import LATEST_RESULT_PATH
from .ml_figures import fg_colour, style_axes, style_legend, _grid
from .ml_widgets import MUTED, TEXT, Section, apply_section_defaults
from .wilson_calc import wilson_interval

_N_MULTIPLIERS = (0.5, 1, 2, 4)
_N_CURVE_POINTS = 60


class PrecisionCalcTab:
    """Builds the sampling-precision calculator into `frame`."""

    def __init__(self, frame, window, status=None):
        self.window = window
        self._status = status
        self._build(frame)
        self._recalculate()

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

        grp = Section("Study size")
        gv = QVBoxLayout(grp)
        gv.setSpacing(8)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)

        form.addWidget(self._muted("Expected strike rate (%)"), 0, 0)
        rate_row = QHBoxLayout()
        self.spin_rate = QDoubleSpinBox()
        self.spin_rate.setRange(0.0, 100.0)
        self.spin_rate.setDecimals(1)
        self.spin_rate.setValue(10.0)
        self.spin_rate.valueChanged.connect(self._recalculate)
        rate_row.addWidget(self.spin_rate)
        self.btn_load_bsm = QPushButton("Load from Blade Strike Modelling")
        self.btn_load_bsm.clicked.connect(self._load_from_bsm)
        rate_row.addWidget(self.btn_load_bsm)
        form.addLayout(rate_row, 0, 1)

        form.addWidget(self._muted("Planned sample size (N)"), 1, 0)
        self.spin_n = QSpinBox()
        self.spin_n.setRange(1, 100000)
        self.spin_n.setValue(50)
        self.spin_n.valueChanged.connect(self._recalculate)
        form.addWidget(self.spin_n, 1, 1)

        form.addWidget(self._muted("Confidence level"), 2, 0)
        self.cmb_confidence = QComboBox()
        for pct in (90, 95, 99):
            self.cmb_confidence.addItem(f"{pct}%", pct)
        self.cmb_confidence.setCurrentIndex(1)
        self.cmb_confidence.currentIndexChanged.connect(self._recalculate)
        form.addWidget(self.cmb_confidence, 2, 1)
        form.setColumnStretch(1, 1)
        gv.addLayout(form)

        self.lbl_result = QLabel("")
        self.lbl_result.setStyleSheet(f"color:{TEXT};font-weight:bold;")
        self.lbl_result.setWordWrap(True)
        gv.addWidget(self.lbl_result)

        self.tbl_sweep = QTableWidget(0, 4)
        self.tbl_sweep.setHorizontalHeaderLabels(
            ["N", "Interval", "Precision (±)", ""])
        self.tbl_sweep.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_sweep.setMinimumHeight(160)

        self.fig_precision = Figure(figsize=(5.0, 3.2), dpi=100)
        self.canvas_precision = FigureCanvas(self.fig_precision)
        self.canvas_precision.setMinimumSize(220, 190)
        self.canvas_precision.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        row = QSplitter(Qt.Orientation.Horizontal)
        row.setChildrenCollapsible(False)
        row.addWidget(self.tbl_sweep)
        row.addWidget(self.canvas_precision)
        row.setSizes([1, 1])
        gv.addWidget(row, stretch=1)

        v.addWidget(grp)
        v.addStretch()
        apply_section_defaults(frame)

    @staticmethod
    def _muted(text):
        lab = QLabel(text)
        lab.setStyleSheet(f"color:{MUTED};")
        return lab

    # ── Blade Strike Modelling handoff ──────────────────────────────────────
    def _load_from_bsm(self):
        if not LATEST_RESULT_PATH.exists():
            if self._status is not None:
                self._status("No Blade Strike Modelling result found - run "
                             "a calculation on Calculator first.", 5000)
            return
        try:
            with open(LATEST_RESULT_PATH, encoding="utf-8") as f:
                payload = json.load(f)
            self.spin_rate.setValue(payload["pco_cen_percent"])
        except Exception as e:
            if self._status is not None:
                self._status(f"Could not read Blade Strike Modelling "
                             f"result: {e}", 6000)
            return
        if self._status is not None:
            self._status(
                f"Loaded {payload['pco_cen_percent']:.1f}% expected strike "
                f"rate from Blade Strike Modelling ({payload['species']}, "
                f"{payload['timestamp']}).", 5000)

    # ── calculation ──────────────────────────────────────────────────────────
    def _recalculate(self, *_args):
        p = self.spin_rate.value() / 100.0
        n = self.spin_n.value()
        confidence = self.cmb_confidence.currentData()

        result = wilson_interval(p, n, confidence)
        lo, hi, half = result
        self.lbl_result.setText(
            f"N={n} at an assumed {p * 100:.1f}% strike rate → "
            f"{confidence}% CI [{lo * 100:.1f}%, {hi * 100:.1f}%], "
            f"precision ±{half * 100:.1f} percentage points.")

        rows = []
        for mult in _N_MULTIPLIERS:
            n_i = max(1, round(n * mult))
            lo_i, hi_i, half_i = wilson_interval(p, n_i, confidence)
            label = "planned N" if mult == 1 else f"{mult}x"
            rows.append((n_i, f"[{lo_i * 100:.1f}%, {hi_i * 100:.1f}%]",
                        f"±{half_i * 100:.1f} pp", label))

        self.tbl_sweep.setRowCount(len(rows))
        for r, (n_i, interval, precision, label) in enumerate(rows):
            self.tbl_sweep.setItem(r, 0, QTableWidgetItem(str(n_i)))
            self.tbl_sweep.setItem(r, 1, QTableWidgetItem(interval))
            self.tbl_sweep.setItem(r, 2, QTableWidgetItem(precision))
            self.tbl_sweep.setItem(r, 3, QTableWidgetItem(label))
        self.tbl_sweep.resizeColumnsToContents()

        self._draw_precision_curve(p, n, confidence, half)

    def _draw_precision_curve(self, p, n, confidence, planned_half):
        n_max = max(n * 4, 20)
        n_vals = np.unique(np.round(np.linspace(2, n_max, _N_CURVE_POINTS))
                           .astype(int))
        half_vals = np.array([wilson_interval(p, int(ni), confidence)[2] * 100
                              for ni in n_vals])

        fig = self.fig_precision
        fig.clear()
        ax = fig.add_subplot(111)
        dark = True
        fg = fg_colour(dark)
        _grid(ax, dark)
        ax.plot(n_vals, half_vals, color="#568af2", linewidth=1.5, zorder=2)
        ax.scatter([n], [planned_half * 100], s=50, color="#f59e0b",
                  edgecolor=fg, linewidth=0.8, zorder=4,
                  label=f"Planned N={n}")
        style_legend(ax.legend(loc="upper right", fontsize=8), dark)
        ax.set_xlabel("Sample size N", fontsize=9)
        ax.set_ylabel("Precision ± (percentage points)", fontsize=9)
        ax.tick_params(labelsize=8)
        style_axes(fig, ax, dark)
        fig.tight_layout()
        self.canvas_precision.draw()
