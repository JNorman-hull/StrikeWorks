# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Reusable widgets for the Machine Learning Analysis pages.

The RingCard and Spinner are ports of the MVP prediction page's widgets,
recoloured for the StrikeWorks dark theme. MetaCard, CheckList and ProbBars
are new but follow the same card language as page_process.StatCard.
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)

# theme colours (match the PyDracula palette used by the app)
CARD_BG = "#21252b"          # rgb(33,37,43)
BORDER  = "#2c313a"          # rgb(44,49,58)
TEXT    = "#dddddd"
MUTED   = "#8a95aa"
ACCENT  = "#bd93f9"          # purple
PINK    = "#ff79c6"
OK      = "#22c55e"
WARN    = "#f59e0b"
BAD     = "#ef4444"
INFO    = "#568af2"
EMPTY   = "#3a4150"

# category palette for ring segments / stacked bars
PALETTE = [INFO, PINK, WARN, OK, ACCENT, "#00bcd4"]

CARD_W, CARD_H   = 300, 120
CARD_W2, CARD_H2 = 108, 108


# ── ring card (ported from the MVP, dark theme) ──────────────────────────────
class RingCard(QFrame):
    """Fixed-size card with a donut ring.

    Metric mode   (set_value):    single arc fills 0-1, value in the centre.
    Category mode (set_segments): segmented colour ring with legend.
    Both modes start empty (grey ring) until data is supplied.
    """

    RING_D = 64
    RING_T = 11
    PAD    = 10

    def __init__(self, title, w=None, h=None, parent=None):
        super().__init__(parent)
        self.setFixedSize(w or CARD_W, h or CARD_H)
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

    def set_segments(self, segments):
        """segments: [(label, count, colour), ...]"""
        self._segments = segments
        self._value    = None
        self._centre   = ""
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

        tf = QFont("Segoe UI", 9)
        tf.setBold(True)
        p.setFont(tf)
        p.setPen(QColor(TEXT))
        p.drawText(self.PAD, 0, w - self.PAD * 2, 26,
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   self._title)

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

            vf = QFont("Segoe UI", 10)
            vf.setBold(True)
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

            lf = QFont("Segoe UI", 8)
            p.setFont(lf)
            text_w = rx - self.PAD * 2
            y = 28
            for label, val, colour in self._segments:
                if y + 26 > h - 4:
                    break
                pct = val / total * 100
                p.setBrush(QColor(colour))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(self.PAD, y + 3, 8, 8)

                p.setPen(QColor(TEXT))
                p.drawText(self.PAD + 12, y, text_w, 13,
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                           label)
                p.setPen(QColor(MUTED))
                p.drawText(self.PAD + 12, y + 13, text_w, 12,
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                           f"n={int(val)}  ({pct:.0f}%)")
                y += 28

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
        self.setStyleSheet(
            f"#metaCard{{background-color:{CARD_BG};border-radius:6px;"
            f"border:1px solid {BORDER};}}")

        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(4)

        self._title = QLabel(title)
        self._title.setStyleSheet(
            f"color:{TEXT};font-weight:bold;font-size:11px;border:none;")
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

    def set_rows(self, rows):
        """rows: [(label, value)] - value None/'' renders as an em dash."""
        # clear existing (detach immediately so stale rows never paint)
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._rows = {}

        for i, (label, value) in enumerate(rows):
            lab = QLabel(label)
            lab.setStyleSheet(f"color:{MUTED};font-size:10px;border:none;")
            lab.setAlignment(Qt.AlignmentFlag.AlignTop)
            val = QLabel(self._fmt(value))
            val.setStyleSheet(f"color:{TEXT};font-size:10px;border:none;")
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
            return "—"
        if isinstance(value, (list, tuple)):
            return ", ".join(str(v) for v in value)
        return str(value)


# ── validation checklist ─────────────────────────────────────────────────────
class CheckList(QFrame):
    """Renders (state, label, detail) validation rows plus a verdict banner."""

    _ICON = {"ok": ("✓", OK), "warn": ("⚠", WARN),
             "fail": ("✗", BAD), "off": ("–", MUTED)}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("checkList")
        self.setStyleSheet(
            f"#checkList{{background-color:{CARD_BG};border-radius:6px;"
            f"border:1px solid {BORDER};}}")
        self._v = QVBoxLayout(self)
        self._v.setContentsMargins(12, 10, 12, 10)
        self._v.setSpacing(4)

        self._verdict = QLabel("")
        vf = QFont("Segoe UI", 10)
        vf.setBold(True)
        self._verdict.setFont(vf)
        self._verdict.setStyleSheet("border:none;")
        self._items = []

    def set_checks(self, checks, ready, ready_text="READY TO PREDICT",
                   blocked_text="PREDICTION UNAVAILABLE"):
        for w in self._items:
            w.setParent(None)
            w.deleteLater()
        self._items = []
        self._v.removeWidget(self._verdict)

        for state, label, detail in checks:
            icon, colour = self._ICON.get(state, self._ICON["off"])
            row = QLabel(f"<span style='color:{colour};'>{icon}</span>&nbsp; "
                         f"<span style='color:{TEXT};'>{label}</span>"
                         + (f"<br/><span style='color:{MUTED};font-size:9px;'>"
                            f"&nbsp;&nbsp;&nbsp;{detail}</span>" if detail else ""))
            row.setStyleSheet("border:none;font-size:10px;")
            row.setWordWrap(True)
            self._v.addWidget(row)
            self._items.append(row)

        if ready:
            self._verdict.setText(ready_text)
            self._verdict.setStyleSheet(f"color:{OK};border:none;")
        else:
            self._verdict.setText(blocked_text)
            self._verdict.setStyleSheet(f"color:{BAD};border:none;")
        self._v.addWidget(self._verdict)

    def set_running(self):
        self._verdict.setText("PREDICTION RUNNING…")
        self._verdict.setStyleSheet(f"color:{ACCENT};border:none;")


# ── horizontal probability bars ──────────────────────────────────────────────
class ProbBars(QWidget):
    """Compact horizontal bar chart for class probabilities.

    set_probs([(label, prob, colour), ...]) - probs in 0-1.
    """

    ROW_H  = 24
    LAB_W  = 110
    VAL_W  = 44

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

        f = QFont("Segoe UI", 8)
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
