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

Future hook (not built yet): when the Mathematical Blade Strike Modelling
pages exist (ROADMAP.md Chunk 5 task 5), the expected strike rate here
should be able to pull from a treatment's BSM output instead of a typed
guess - the input is deliberately a plain field now so that wiring is a
later, additive change.
"""
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QGridLayout, QHBoxLayout, QLabel, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .ml_widgets import MUTED, TEXT, Section, apply_section_defaults
from .wilson_calc import wilson_interval

_N_MULTIPLIERS = (0.5, 1, 2, 4)


class PrecisionCalcTab:
    """Builds the sampling-precision calculator into `frame`."""

    def __init__(self, frame, window, status=None):
        self.window = window
        self._status = status
        self._build(frame)
        self._recalculate()

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, frame):
        v = QVBoxLayout(frame)
        v.setContentsMargins(4, 6, 4, 6)
        v.setSpacing(10)

        grp = Section("Sampling precision (Wilson score interval)")
        gv = QVBoxLayout(grp)
        gv.setSpacing(8)

        lab_note = QLabel(
            "Estimate the precision a planned sample size would achieve for "
            "a hypothesised strike rate - a quick way to judge whether the "
            "sampling effort planned in Create and edit deployment is "
            "enough, before any data comes back.")
        lab_note.setStyleSheet(f"color:{MUTED};")
        lab_note.setWordWrap(True)
        gv.addWidget(lab_note)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)

        form.addWidget(self._muted("Expected strike rate (%)"), 0, 0)
        self.spin_rate = QDoubleSpinBox()
        self.spin_rate.setRange(0.0, 100.0)
        self.spin_rate.setDecimals(1)
        self.spin_rate.setValue(10.0)
        self.spin_rate.valueChanged.connect(self._recalculate)
        form.addWidget(self.spin_rate, 0, 1)

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
        v.addWidget(grp)

        grp_table = Section("Precision at other sample sizes")
        tv = QVBoxLayout(grp_table)
        lab_table = QLabel(
            "Same strike rate and confidence level, at half, double and "
            "quadruple the planned N.")
        lab_table.setStyleSheet(f"color:{MUTED};")
        lab_table.setWordWrap(True)
        tv.addWidget(lab_table)
        self.tbl_sweep = QTableWidget(0, 4)
        self.tbl_sweep.setHorizontalHeaderLabels(
            ["N", "Interval", "Precision (±)", ""])
        self.tbl_sweep.verticalHeader().setVisible(False)
        self.tbl_sweep.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_sweep.setMinimumHeight(160)
        tv.addWidget(self.tbl_sweep)
        v.addWidget(grp_table)

        v.addStretch()
        apply_section_defaults(frame)

    @staticmethod
    def _muted(text):
        lab = QLabel(text)
        lab.setStyleSheet(f"color:{MUTED};")
        return lab

    # ── calculation ──────────────────────────────────────────────────────────
    def _recalculate(self, *_args):
        p = self.spin_rate.value() / 100.0
        n = self.spin_n.value()
        confidence = self.cmb_confidence.currentData()

        result = wilson_interval(p, n, confidence)
        lo, hi, half = result
        self.lbl_result.setText(
            f"N={n} at an assumed {p * 100:.1f}% strike rate -> "
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
