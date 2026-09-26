# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Study design (Setup and deploy): sampling precision. Given a
hypothesised strike rate and a planned sample size, shows the Wilson score
interval (`wilson_calc.py`) that size would give, and how it changes over a
range of sizes - "is N=50 enough, or plan for 100?".

"Load from Blade Strike Modelling" fills the expected strike rate from the
CEN estimate in `bsm_state.LATEST_RESULT_PATH`, the JSON Calculator writes
after every run - so it works whether or not the BSM pages were opened
this session.
"""
import json

import numpy as np

from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from PySide6.QtCore import Qt

from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from .bsm_state import LATEST_RESULT_PATH
from .ml_figures import fg_colour, style_axes, style_legend, _grid
from .layout import apply_section_defaults, scroll_page, Section
from .theme import TEXT, muted_label
from .wilson_calc import required_n, wilson_interval

_N_MULTIPLIERS = (0.5, 1, 2, 4)
_N_CURVE_POINTS = 60

# the Study design report figure (cm)
STUDY_DESIGN_SIZE_CM = (14.0, 10.0)


class PrecisionCalcTab:
    """Builds the sampling-precision calculator into `frame`."""

    def __init__(self, frame, window, status=None):
        self.window = window
        self._status = status
        self._curve = None      # (p, n, confidence, planned_half) last drawn
        self._build(frame)
        self._recalculate()

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, frame):
        v = scroll_page(frame)

        grp = Section("Study size")
        gv = QVBoxLayout(grp)
        gv.setSpacing(8)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)

        form.addWidget(muted_label("Expected strike rate (%)"), 0, 0)
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

        form.addWidget(muted_label("Planned sample size (N)"), 1, 0)
        self.spin_n = QSpinBox()
        self.spin_n.setRange(1, 100000)
        self.spin_n.setValue(50)
        self.spin_n.valueChanged.connect(self._recalculate)
        form.addWidget(self.spin_n, 1, 1)

        form.addWidget(muted_label("Confidence level"), 2, 0)
        self.cmb_confidence = QComboBox()
        for pct in (90, 95, 99):
            self.cmb_confidence.addItem(f"{pct}%", pct)
        self.cmb_confidence.setCurrentIndex(1)
        self.cmb_confidence.currentIndexChanged.connect(self._recalculate)
        form.addWidget(self.cmb_confidence, 2, 1)

        # the inverse question: how many sensors for a wanted precision
        form.addWidget(muted_label("Target precision (± pp)"), 3, 0)
        target_row = QHBoxLayout()
        self.spin_target = QDoubleSpinBox()
        self.spin_target.setRange(0.1, 50.0)
        self.spin_target.setDecimals(1)
        self.spin_target.setSingleStep(0.5)
        self.spin_target.setValue(5.0)
        self.spin_target.setToolTip(
            "How close (± percentage points) the observed strike rate should "
            "be expected to land - the sample size needed for it is shown "
            "alongside.")
        self.spin_target.valueChanged.connect(self._recalculate)
        target_row.addWidget(self.spin_target)
        self.lbl_required = QLabel("")
        self.lbl_required.setStyleSheet(f"color:{TEXT};")
        target_row.addWidget(self.lbl_required, stretch=1)
        self.btn_use_required = QPushButton("Use as planned N")
        self.btn_use_required.clicked.connect(self._use_required_n)
        target_row.addWidget(self.btn_use_required)
        form.addLayout(target_row, 3, 1)
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

        # the same figsize as ml_figures.render_figures, so the exported
        # figure matches the other report figures (on screen the canvas
        # sets the size)
        self.fig_precision = Figure(figsize=(6.0, 4.2), dpi=100)
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

        target = self.spin_target.value()
        self._required_n = required_n(p, target / 100.0, confidence)
        self.lbl_required.setText(
            f"→ N = {self._required_n} sensor(s) needed"
            if self._required_n else "→ not reachable")
        self.btn_use_required.setEnabled(bool(self._required_n)
                                         and self._required_n != n)

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

    def _use_required_n(self):
        if getattr(self, "_required_n", None):
            self.spin_n.setValue(self._required_n)

    def _draw_precision_curve(self, p, n, confidence, planned_half):
        self._curve = (p, n, confidence, planned_half)
        self.draw_curve(self.fig_precision, dark=True)
        self.canvas_precision.draw()

    def draw_curve(self, fig, dark=True):
        """Precision (±, percentage points) against sample size N, the
        planned N marked - onto any figure: the page's own dark canvas,
        or the Study design report's light 14 x 10 cm one."""
        if self._curve is None:
            return
        p, n, confidence, planned_half = self._curve
        n_max = max(n * 4, 20)
        n_vals = np.unique(np.round(np.linspace(2, n_max, _N_CURVE_POINTS))
                           .astype(int))
        half_vals = np.array([wilson_interval(p, int(ni), confidence)[2] * 100
                              for ni in n_vals])

        fig.clear()
        ax = fig.add_subplot(111)
        fg = fg_colour(dark)
        _grid(ax, dark)
        ax.plot(n_vals, half_vals, color="#568af2", linewidth=1.5, zorder=2)
        ax.scatter([n], [planned_half * 100], s=50, color="#f59e0b",
                  edgecolor=fg, linewidth=0.8, zorder=4,
                  label=f"Planned N={n}")
        style_legend(ax.legend(loc="upper right", fontsize=8), dark)
        ax.set_xlabel("Sample size N", fontsize=9)
        ax.set_ylabel("Precision ± (percentage points)", fontsize=9)
        ax.set_title(f"Precision at {p * 100:.1f}% expected strike rate "
                     f"({confidence}% CI)", fontsize=10, fontweight="bold")
        ax.tick_params(labelsize=8)
        style_axes(fig, ax, dark)
        fig.tight_layout()
