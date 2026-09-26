# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Pieces shared by every page with a live signal plot (Annotate, Export
animations, Misclassification analysis, Model prediction > Inspect).
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pyqtgraph as pg

from PySide6.QtCore import Qt, QThread, Signal

from .theme import CARD_BG

# display channels -> (column name, axis label)
CHANNELS = {
    "higacc_mag": ("higacc_mag_g", "HIG acc mag (g)"),
    "inacc_mag": ("inacc_mag_ms", "IN acc mag (m/s²)"),
    "pressure": ("pressure_kpa", "Pressure (kPa)"),
    "rot_mag": ("rot_mag_degs", "Rotation mag (°/s)"),
}
CHANNEL_ORDER = ["higacc_mag", "inacc_mag", "pressure", "rot_mag"]
MAX_RIGHT_PTS = 8000   # points kept for a right-axis overlay (see decimate)


def configure_pyqtgraph():
    """The dark theme and antialiasing every plot uses - once, before the
    first plot widget is built."""
    pg.setConfigOptions(antialias=True, background=CARD_BG,
                        foreground="#c8cdd6")


def find_col(df, candidates, keyword=None):
    """First of `candidates` that's a column of `df`, else the first column
    whose name contains `keyword`."""
    for c in candidates:
        if c in df.columns:
            return c
    if keyword:
        for c in df.columns:
            if keyword in c.lower():
                return c
    return None


def decimate(x, y, max_pts):
    """Min/max decimation: each bucket's min and max, in time order. For a
    right-axis overlay, where pyqtgraph's own downsampling can't be used
    (the curve lives in a second ViewBox)."""
    n = len(x)
    if n <= max_pts:
        return x, y
    n_buckets = max(1, max_pts // 2)
    stride = n // n_buckets
    usable = n_buckets * stride
    yb = y[:usable].reshape(n_buckets, stride)
    base = np.arange(n_buckets) * stride
    i_min = yb.argmin(axis=1) + base
    i_max = yb.argmax(axis=1) + base
    first_min = i_min <= i_max
    out = np.empty(n_buckets * 2, dtype=np.intp)
    out[0::2] = np.where(first_min, i_min, i_max)
    out[1::2] = np.where(first_min, i_max, i_min)
    if usable < n:
        out = np.concatenate([out, np.arange(usable, n, dtype=np.intp)])
    return x[out], y[out]


class CsvLoadThread(QThread):
    """Reads one sensor CSV off the GUI thread."""
    loaded = Signal(object, object)   # (Path, DataFrame)
    failed = Signal(object, str)      # (Path, message)

    def __init__(self, path: Path):
        super().__init__()
        self._path = path

    def run(self):
        try:
            df = pd.read_csv(self._path, low_memory=False)
            self.loaded.emit(self._path, df)
        except Exception as e:
            self.failed.emit(self._path, str(e))


class NavViewBox(pg.ViewBox):
    """A ViewBox whose mouse wheel pans instead of zooming: plain wheel
    scrolls time, Shift + wheel scrolls the Y axis, and the wheel over an
    axis zooms that axis. Zooming proper is box-select (RectMode)."""
    _STEP = 0.10   # fraction of the visible range per wheel notch

    def wheelEvent(self, ev, axis=None):
        if axis is not None:
            super().wheelEvent(ev, axis=axis)
            return
        try:
            delta = ev.delta()
        except AttributeError:
            delta = ev.angleDelta().y()
        if not delta:
            ev.accept()
            return
        frac = self._STEP if delta > 0 else -self._STEP
        (x0, x1), (y0, y1) = self.viewRange()
        if ev.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.translateBy(y=(y1 - y0) * frac)
        else:
            self.translateBy(x=(x1 - x0) * frac)
        ev.accept()
