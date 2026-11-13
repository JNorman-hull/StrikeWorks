"""A slider with two handles - a low and a high value on one track (Qt
has no such slider of its own). Drawn in the stylesheet's slider colours
(themes/app.qss, QSlider): the track, the span between the handles in the
accent, the handles in the accent text colour.
"""
from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from .theme import P

_TRACK_H = 6        # the track's height
_HANDLE_D = 14      # a handle's diameter


class RangeSlider(QWidget):
    """`low` to `high`, between `minimum` and `maximum`, in steps of
    `step`; the handles stay at least a step apart. Drag either handle
    (a press on the track takes the nearer one there); the arrow keys
    move the last one used."""

    valuesChanged = Signal(float, float)

    def __init__(self, minimum, maximum, step, low, high, parent=None):
        super().__init__(parent)
        self._min, self._step = minimum, step
        self._n = round((maximum - minimum) / step)
        self._pos = [self._index(low), self._index(high)]
        self._drag = None
        self._last = 1
        self.setMinimumHeight(_HANDLE_D + 6)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def sizeHint(self):
        return QSize(160, _HANDLE_D + 6)

    # values
    def _index(self, value):
        return max(0, min(self._n, round((value - self._min) / self._step)))

    def _value(self, index):
        return round(self._min + index * self._step, 6)

    def values(self):
        return self._value(self._pos[0]), self._value(self._pos[1])

    def setValues(self, low, high):
        self._move_to(0, self._index(low), emit=False)
        self._move_to(1, self._index(high), emit=False)
        self.update()

    def _move_to(self, handle, index, emit=True):
        if handle == 0:
            index = max(0, min(index, self._pos[1] - 1))
        else:
            index = min(self._n, max(index, self._pos[0] + 1))
        if index == self._pos[handle]:
            return
        self._pos[handle] = index
        self.update()
        if emit:
            self.valuesChanged.emit(*self.values())

    # geometry
    def _x(self, index):
        r = _HANDLE_D / 2
        return r + (self.width() - 2 * r) * index / max(self._n, 1)

    def _index_at(self, x):
        r = _HANDLE_D / 2
        return round((x - r) / max(self.width() - 2 * r, 1) * self._n)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        cy = self.height() / 2
        r = _HANDLE_D / 2
        p.setBrush(QColor(P["track"]))
        p.drawRoundedRect(QRectF(r, cy - _TRACK_H / 2, self.width() - 2 * r,
                                 _TRACK_H), _TRACK_H / 2, _TRACK_H / 2)
        x_lo, x_hi = self._x(self._pos[0]), self._x(self._pos[1])
        p.setBrush(QColor(P["accent"]))
        p.drawRect(QRectF(x_lo, cy - _TRACK_H / 2, x_hi - x_lo, _TRACK_H))
        for handle, x in enumerate((x_lo, x_hi)):
            colour = (P["highlight"] if handle == self._drag
                      else P["accent_text"])
            p.setBrush(QColor(colour))
            p.drawEllipse(QRectF(x - r, cy - r, _HANDLE_D, _HANDLE_D))
        p.end()

    # mouse and keys
    def mousePressEvent(self, event):
        x = event.position().x()
        d_lo, d_hi = (abs(x - self._x(i)) for i in self._pos)
        # handles together: the one on the side pressed
        if d_lo == d_hi:
            self._drag = 0 if x < self._x(self._pos[0]) else 1
        else:
            self._drag = 0 if d_lo < d_hi else 1
        self._last = self._drag
        self._move_to(self._drag, self._index_at(x))
        self.update()

    def mouseMoveEvent(self, event):
        if self._drag is not None:
            self._move_to(self._drag, self._index_at(event.position().x()))

    def mouseReleaseEvent(self, _event):
        self._drag = None
        self.update()

    def keyPressEvent(self, event):
        step = {Qt.Key.Key_Left: -1, Qt.Key.Key_Down: -1,
                Qt.Key.Key_Right: 1, Qt.Key.Key_Up: 1}.get(event.key())
        if step is None:
            super().keyPressEvent(event)
            return
        self._move_to(self._last, self._pos[self._last] + step)
