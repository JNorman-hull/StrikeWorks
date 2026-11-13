"""The Matplotlib canvas every page uses. While a resize is in progress the
last drawing is stretched to fit; the figure is laid out and redrawn once,
when the mouse button is released or the resizing stops. Redrawing on every
resize event made dragging slow on pages with several figures.
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QImage, QPainter, QResizeEvent
from PySide6.QtWidgets import QWidget

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

# how long a resize must have stopped for before the figure is redrawn (and
# how often a held mouse button is checked for)
SETTLE_MS = 80


class FigureCanvas(FigureCanvasQTAgg):
    """`FigureCanvasQTAgg` that redraws once a resize is over. Used like
    it."""

    def __init__(self, figure=None):
        super().__init__(figure)
        # lay the figure out at every draw: a one-off tight_layout() keeps
        # margins for the old size after a resize, clipping axis titles
        fig = self.figure
        fig.tight_layout = lambda **kw: fig.set_layout_engine("tight", **kw)
        self._stale = None          # the last drawing, while resizing
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(SETTLE_MS)
        self._settle.timeout.connect(self._resize_settled)

    def resizeEvent(self, event):
        # nothing drawn yet, or a hidden canvas laid out before it's shown:
        # nothing to stretch, so lay it out now
        if not hasattr(self, "renderer") or not self.isVisible():
            self._stale = None
            super().resizeEvent(event)
            return
        if self._stale is None:
            self._stale = self._snapshot()
        QWidget.resizeEvent(self, event)
        self._settle.start()

    def _resize_settled(self):
        if QGuiApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            self._settle.start()        # still dragging
            return
        self._stale = None
        size = self.size()
        super().resizeEvent(QResizeEvent(size, size))

    def draw(self):
        super().draw()
        # a figure redrawn mid-resize (new data) is stretched as it is now
        if self._stale is not None:
            self._stale = self._snapshot()

    def _snapshot(self):
        buf = self.buffer_rgba()
        image = QImage(buf, buf.shape[1], buf.shape[0],
                       QImage.Format.Format_RGBA8888).copy()
        image.setDevicePixelRatio(self.device_pixel_ratio)
        return image

    def paintEvent(self, event):
        if self._stale is None:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawImage(self.rect(), self._stale)
        finally:
            painter.end()
