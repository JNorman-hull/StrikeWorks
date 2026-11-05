# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""The card widgets: RingCard (a value or category ring), MetaCard
(label/value rows), ProbBars, and the Spinner shown during long jobs.
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)
from .layout import discard_widget
from .theme import (
    ACCENT, BORDER, CARD_BG, CARD_H, CARD_W, EMPTY, MUTED, PINK, TEXT, style,
)


# ── ring card ────────────────────────────────────────────────────────────────
class RingCard(QFrame):
    """Card with a donut ring; fixed height, expands horizontally.

    Metric mode   (set_value):    single arc fills 0-1, value in the centre.
    Category mode (set_segments): segmented colour ring with legend.
    Both modes start empty (grey ring) until data is supplied.
    """

    RING_D = 64
    RING_T = 11
    PAD    = 10

    def __init__(self, title, w=None, h=None, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(w or CARD_W)
        self.setFixedHeight(h or CARD_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setFrameShape(QFrame.Shape.NoFrame)

        self._title    = title
        self._value    = None
        self._segments = None
        self._centre   = ""
        self._empty    = True

    def set_title(self, title):
        self._title = title
        self.update()

    def set_value(self, v: float, centre_text: str = ""):
        self._value    = max(0.0, min(1.0, v))
        self._segments = None
        self._centre   = centre_text or f"{v:.3f}"
        self._empty    = False
        self.update()

    def set_segments(self, segments, centre_text=""):
        """segments: [(label, count, colour), ...]; `centre_text` (e.g. the
        strike rate) in the ring's centre."""
        self._segments = segments
        self._value    = None
        self._centre   = centre_text
        self._empty    = len(segments) == 0
        self.update()

    def clear(self):
        self._value = self._segments = None
        self._centre = ""
        self._empty = True
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        p.setPen(QPen(QColor(BORDER), 1.5))
        p.setBrush(QColor(CARD_BG))
        p.drawRoundedRect(1, 1, w - 2, h - 2, 8, 8)

        tf = QFont("Segoe UI", 10)
        p.setFont(tf)
        p.setPen(QColor(TEXT))
        # elide rather than clip - metric cards can be narrow
        title_w = w - self.PAD * 2
        title = QFontMetrics(tf).elidedText(
            self._title, Qt.TextElideMode.ElideRight, title_w)
        p.drawText(self.PAD, 0, title_w, 26,
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   title)

        rx = w - self.RING_D - self.PAD
        ry = (h - self.RING_D) // 2 + 4

        p.setPen(QPen(QColor(EMPTY), self.RING_T,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rx, ry, self.RING_D, self.RING_D)

        if self._empty:
            p.end()
            return

        if self._value is not None:
            span = int(self._value * 360 * 16)
            p.setPen(QPen(QColor(ACCENT), self.RING_T,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(rx, ry, self.RING_D, self.RING_D, 90 * 16, -span)

            vf = QFont("Segoe UI", 11)
            p.setFont(vf)
            p.setPen(QColor(TEXT))
            p.drawText(rx, ry, self.RING_D, self.RING_D,
                       Qt.AlignmentFlag.AlignCenter, self._centre)

        elif self._segments:
            total = sum(s[1] for s in self._segments) or 1
            angle = 90 * 16
            for _label, val, colour in self._segments:
                span = int(val / total * 360 * 16)
                p.setPen(QPen(QColor(colour), self.RING_T,
                              Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawArc(rx, ry, self.RING_D, self.RING_D, angle, -span)
                angle -= span
            if self._centre:
                p.setFont(QFont("Segoe UI", 11))
                p.setPen(QColor(TEXT))
                p.drawText(rx, ry, self.RING_D, self.RING_D,
                           Qt.AlignmentFlag.AlignCenter, self._centre)

            lf = QFont("Segoe UI", 9)
            p.setFont(lf)
            text_w = rx - self.PAD * 2
            y = 28
            for label, val, colour in self._segments:
                if y + 28 > h - 4:
                    break
                pct = val / total * 100
                p.setBrush(QColor(colour))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(self.PAD, y + 4, 8, 8)

                p.setPen(QColor(TEXT))
                p.drawText(self.PAD + 13, y, text_w, 15,
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                           label)
                p.setPen(QColor(MUTED))
                p.drawText(self.PAD + 13, y + 15, text_w, 14,
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                           f"n={int(val)}  ({pct:.0f}%)")
                y += 31

        p.end()


# ── spinner ──────────────────────────────────────────────────────────────────
class Spinner(QWidget):
    """Small rotating arc drawn with QPainter. Show/hide around long ops."""

    def __init__(self, parent=None, size=24, colour=PINK):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._colour = colour
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self):
        self.setVisible(True)
        self._timer.start(40)   # ~25 fps

    def stop(self):
        self._timer.stop()
        self.setVisible(False)

    def _tick(self):
        self._angle = (self._angle + 14) % 360
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(BORDER), 3, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        m = 3
        p.drawEllipse(m, m, self.width() - m * 2, self.height() - m * 2)
        p.setPen(QPen(QColor(self._colour), 3, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap))
        p.drawArc(m, m, self.width() - m * 2, self.height() - m * 2,
                  self._angle * 16, 100 * 16)
        p.end()


# ── metadata card ────────────────────────────────────────────────────────────
class MetaCard(QFrame):
    """Key/value metadata card. Unknown values display as an em dash."""

    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.setObjectName("metaCard")

        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(4)

        self._title = QLabel(title)
        style(self._title, role="strong")
        self._title.setVisible(bool(title))
        v.addWidget(self._title)

        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(14)
        self._grid.setVerticalSpacing(3)
        self._grid.setColumnStretch(1, 1)
        v.addLayout(self._grid)
        v.addStretch()

        self._rows = {}

    def set_title(self, title):
        self._title.setText(title)
        self._title.setVisible(bool(title))

    def set_rows(self, rows):
        """rows: [(label, value)] - value None/'' renders as an em dash."""
        # clear existing (detach immediately so stale rows never paint)
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                discard_widget(w)
        self._rows = {}

        for i, (label, value) in enumerate(rows):
            lab = QLabel(label)
            style(lab, role="muted")
            lab.setAlignment(Qt.AlignmentFlag.AlignTop)
            val = QLabel(self._fmt(value))
            style(val)
            val.setWordWrap(True)
            val.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            self._grid.addWidget(lab, i, 0)
            self._grid.addWidget(val, i, 1)
            self._rows[label] = val

    def set_value(self, label, value):
        if label in self._rows:
            self._rows[label].setText(self._fmt(value))

    @staticmethod
    def _fmt(value):
        if value is None or value == "" or value == []:
            return "-"
        if isinstance(value, (list, tuple)):
            return ", ".join(str(v) for v in value)
        return str(value)


# ── validation checklist ─────────────────────────────────────────────────────
# ── horizontal probability bars ──────────────────────────────────────────────
class ProbBars(QWidget):
    """Compact horizontal bar chart for class probabilities.

    set_probs([(label, prob, colour), ...]) - probs in 0-1.
    """

    ROW_H  = 26
    LAB_W  = 130
    VAL_W  = 48

    def __init__(self, parent=None):
        super().__init__(parent)
        self._probs = []
        self.setMinimumHeight(self.ROW_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)

    def set_probs(self, probs):
        self._probs = list(probs)
        self.setFixedHeight(max(1, len(self._probs)) * self.ROW_H)
        self.update()

    def clear(self):
        self.set_probs([])

    def paintEvent(self, _event):
        if not self._probs:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        bar_w = max(30, w - self.LAB_W - self.VAL_W - 16)

        f = QFont("Segoe UI", 9)
        p.setFont(f)
        for i, (label, prob, colour) in enumerate(self._probs):
            y = i * self.ROW_H
            p.setPen(QColor(TEXT))
            p.drawText(0, y, self.LAB_W, self.ROW_H,
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       label)

            # track
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(EMPTY))
            p.drawRoundedRect(self.LAB_W, y + 7, bar_w, self.ROW_H - 14, 4, 4)
            # fill
            fill = int(bar_w * max(0.0, min(1.0, float(prob))))
            if fill > 0:
                p.setBrush(QColor(colour))
                p.drawRoundedRect(self.LAB_W, y + 7, fill, self.ROW_H - 14, 4, 4)

            p.setPen(QColor(MUTED))
            p.drawText(self.LAB_W + bar_w + 8, y, self.VAL_W, self.ROW_H,
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       f"{float(prob):.3f}")
        p.end()
