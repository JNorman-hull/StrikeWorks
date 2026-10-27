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

from PySide6.QtCore import Qt

from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QGridLayout, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QSizePolicy, QSpinBox, QSplitter,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .bsm_state import LATEST_RESULT_PATH
from .canvas import FigureCanvas
from .ml_figures import fg_colour, style_axes, style_legend, _grid
from .layout import scroll_page, Section
from .theme import INFO, WARN, muted_label, style
from .wilson_calc import required_n, wilson_interval

_N_MULTIPLIERS = (0.5, 1, 2, 4)
_N_CURVE_POINTS = 60
_INPUT_WIDTH = 80

# the Study design report figure (cm)
STUDY_DESIGN_SIZE_CM = (14.0, 10.0)


class PrecisionCalcTab(QWidget):
    """Builds the sampling-precision calculator."""

    def __init__(self, main_window, status=None):
        super().__init__()
        self.main_window = main_window
        self._status = status
        self._curve = None      # (p, n, confidence, planned_half) last drawn
        self._build(self)
        self._recalculate()

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, frame):
        v = scroll_page(frame)

        grp = Section("Study size")
        gv = QVBoxLayout(grp)
        gv.setSpacing(8)

        # the inputs at their natural size, the Notes box taking the rest
        top = QHBoxLayout()
        top.setSpacing(16)
        top.addLayout(self._inputs())
        top.addWidget(self._notes(), stretch=1)
        gv.addLayout(top)

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
        row.setSizes([1, 3])
        gv.addWidget(row, stretch=1)

        v.addWidget(grp)
        v.addStretch()

    def _inputs(self):
        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)
        left = Qt.AlignmentFlag.AlignLeft

        form.addWidget(muted_label("Expected strike rate (%)"), 0, 0)
        self.spin_rate = QDoubleSpinBox()
        self.spin_rate.setRange(0.0, 100.0)
        self.spin_rate.setDecimals(1)
        self.spin_rate.setValue(10.0)
        self.spin_rate.valueChanged.connect(self._recalculate)
        form.addWidget(self.spin_rate, 0, 1)
        self.btn_load_bsm = QPushButton("Load from Blade Strike Modelling")
        self.btn_load_bsm.clicked.connect(self._load_from_bsm)
        form.addWidget(self.btn_load_bsm, 0, 2, left)

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
        self.spin_target = QDoubleSpinBox()
        self.spin_target.setRange(0.1, 50.0)
        self.spin_target.setDecimals(1)
        self.spin_target.setSingleStep(0.5)
        self.spin_target.setValue(5.0)
        self.spin_target.setToolTip(
            "How close (± percentage points) the observed strike rate should "
            "be expected to land; the sample size needed for it is shown "
            "below.")
        self.spin_target.valueChanged.connect(self._recalculate)
        form.addWidget(self.spin_target, 3, 1)
        self.btn_use_required = QPushButton("Use as planned N")
        self.btn_use_required.clicked.connect(self._use_required_n)
        form.addWidget(self.btn_use_required, 3, 2, left)
        self.lbl_required = QLabel("")
        style(self.lbl_required)
        form.addWidget(self.lbl_required, 4, 1, 1, 2)

        for w in (self.spin_rate, self.spin_n, self.cmb_confidence,
                  self.spin_target):
            w.setFixedWidth(_INPUT_WIDTH)
        return form

    def _notes(self):
        """The result as text that can be selected and copied."""
        grp = Section("Notes")
        nv = QVBoxLayout(grp)
        self.txt_result = QPlainTextEdit()
        self.txt_result.setReadOnly(True)
        style(self.txt_result, role="strong")
        self.txt_result.setToolTip("Select and copy (Ctrl+C) to paste it "
                                   "elsewhere.")
        self.txt_result.setMinimumWidth(240)
        self.txt_result.setMaximumHeight(110)
        nv.addWidget(self.txt_result)
        return grp

    def result_text(self):
        """The Notes text: planned N, its interval and precision."""
        return self.txt_result.toPlainText()

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

        lo, hi, half = wilson_interval(p, n, confidence)
        self.txt_result.setPlainText(
            f"N={n} at an assumed {p * 100:.1f}% strike rate\n"
            f"{confidence}% CI [{lo * 100:.1f}%, {hi * 100:.1f}%],\n"
            f"precision ±{half * 100:.1f} percentage points.")

        target = self.spin_target.value()
        self._required_n = required_n(p, target / 100.0, confidence)
        self.lbl_required.setText(
            f"N = {self._required_n} sensor(s) needed"
            if self._required_n else "Not reachable at this strike rate")
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
        self.draw_curve(self.fig_precision, dark=True, title=False)
        self.canvas_precision.draw()

    def draw_curve(self, fig, dark=True, title=True):
        """Precision (±, percentage points) against sample size N, the
        planned N marked - onto any figure: the page's own dark canvas
        (no title; the Notes box gives it), or the Study design report's
        light 14 x 10 cm one."""
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
        ax.plot(n_vals, half_vals, color=INFO, linewidth=1.5, zorder=2)
        ax.scatter([n], [planned_half * 100], s=50, color=WARN,
                  edgecolor=fg, linewidth=0.8, zorder=4,
                  label=f"Planned N={n}")
        style_legend(ax.legend(loc="upper right", fontsize=8), dark)
        ax.set_xlabel("Sample size N", fontsize=9)
        ax.set_ylabel("Precision ± (percentage points)", fontsize=9)
        if title:
            ax.set_title(f"Precision at {p * 100:.1f}% expected strike rate "
                         f"({confidence}% CI)", fontsize=10)
        ax.tick_params(labelsize=8)
        style_axes(fig, ax, dark)
        fig.tight_layout()
