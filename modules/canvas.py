# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""The figure canvas every page uses: Matplotlib's Qt canvas, redrawn once
a resize is over rather than at every step of one.

Matplotlib lays a figure out and draws it again on every resize event, and
a drag (a splitter handle, the window's edge) or the sidebar sliding open
sends dozens a second - with a few figures on a page that is what made
dragging slow. Here the last drawing is stretched to fit while the size
changes, and the figure is laid out and drawn once at its new size: as soon
as the mouse button is released, or, for a resize without the mouse
(maximising, the sidebar), once it stops.
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QImage, QPainter, QResizeEvent
from PySide6.QtWidgets import QWidget

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

# how long a resize must have stopped for before the figure is redrawn (and
# how often a held mouse button is checked for)
SETTLE_MS = 80


class FigureCanvas(FigureCanvasQTAgg):
    """`FigureCanvasQTAgg` that redraws when a resize is over (see the
    module docstring). Used exactly like it."""

    def __init__(self, figure=None):
        super().__init__(figure)
        # the figure laid out for the size it's drawn at, every time:
        # Matplotlib's tight_layout() lays it out once, for the size it has
        # then, and a canvas the page later resizes keeps those margins -
        # cutting off axis titles and putting legends over them. The drawing
        # code's call is kept as the figure's layout engine instead
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
