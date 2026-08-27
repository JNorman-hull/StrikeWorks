# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Behaviour for the Validate & segment page.

Direct port of the MVP's ``bsm/pages/nadir_validation.py``. The channel set,
nadir detection, ROI window maths, saved-window filename, and the columns
written back into ``global_sensor_index.csv`` are unchanged.

Only two things differ, and neither changes behaviour:
  * the widgets come from ``main.ui`` instead of being built in code
  * the library picker is the same QTreeView used on the Raw data processing
    page, rather than the MVP's flat QListWidget

The widgets live in main.ui (edit them in Qt Designer); this module only binds
behaviour to them.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pyqtgraph as pg

from PySide6.QtCore import Qt, QDir, QObject, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFileDialog, QFileSystemModel, QHBoxLayout, QMessageBox, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from . import deployment_index as di
from . import sensor_config, settings
from .page_process import _DirsOnlyProxy
from .plot_style import (
    add_export_button, build_export_data, reserve_top_margin,
    set_right_axis_active,
)

# Global pyqtgraph config - set once, before any PlotWidget is created.
# Dark theme + antialiasing so signal plots match the application styling.
pg.setConfigOptions(antialias=True, background="#21252b",
                    foreground="#c8cdd6")

_INDEX_REL = di.INDEX_REL
_CSV_DIR = Path("processed_sens_data") / "csv"
_WIN_DIR = Path("processed_sens_data") / "nadir_window"

# The ROI window is this page's own decision; the rate the processed CSVs
# are written at belongs to the sensor (Prepare page), so _FS is only the
# fallback used when no configuration can be read.
_FS = 2000        # Hz
_WIN_SEC = 0.2    # seconds - default ROI window width (centered on nadir)

_NADIR_T_COL = "pres_min.time."
_NADIR_V_COL = "pres_min.kPa."
_VALIDATED_COL = "hstrike_processed"

# selectable display channels -> (column name, axis label)
_CHANNELS = {
    "higacc_mag": ("higacc_mag_g", "HIG acc mag (g)"),
    "inacc_mag": ("inacc_mag_ms", "IN acc mag (m/s²)"),
    "pressure": ("pressure_kpa", "Pressure (kPa)"),
    "rot_mag": ("rot_mag_degs", "Rotation mag (°/s)"),
}
_CHANNEL_ORDER = ["higacc_mag", "inacc_mag", "pressure", "rot_mag"]
_MAX_RIGHT_PTS = 8000   # cap for the (manually decimated) right-axis overlay

_EXCL_SUFFIXES = {"_min", "_delineated"}
_EXCL_NAMES = {"global_sensor_index.csv"}

_OK = "#22c55e"
_TEXT = "#dddddd"


def _find_col(df, candidates, keyword=None):
    """First candidate column present in df, else a keyword search."""
    for c in candidates:
        if c in df.columns:
            return c
    if keyword:
        for c in df.columns:
            if keyword in c.lower():
                return c
    return None


def _decimate(x, y, max_pts):
    """Min/max ('peak') decimation: keep each bucket's min and max in time order.

    Used only for the right-axis overlay (pyqtgraph's own downsampling is unsafe
    on an item in a secondary ViewBox).
    """
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


class _Spinner(QWidget):
    """Small rotating arc drawn with QPainter. Show/hide around long ops."""

    def __init__(self, parent=None, size=20, colour="#ff79c6"):
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
        p.setPen(QPen(QColor("#2c313a"), 3, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        m = 3
        p.drawEllipse(m, m, self.width() - m * 2, self.height() - m * 2)
        p.setPen(QPen(QColor(self._colour), 3, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap))
        p.drawArc(m, m, self.width() - m * 2, self.height() - m * 2,
                  self._angle * 16, 100 * 16)
        p.end()


class _CsvLoadThread(QThread):
    """Reads one sensor CSV off the GUI thread so the UI stays responsive."""
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


class _NavViewBox(pg.ViewBox):
    """ViewBox where the wheel *pans* instead of zooming.

    - Plain wheel        -> scroll the X (time) axis left/right
    - Shift + wheel      -> scroll the Y axis up/down
    - Wheel over an axis -> native per-axis zoom (axis is not None)
    Zoom proper is done with a box-select (RectMode), set on the widget.
    """
    _STEP = 0.10   # fraction of the current range to move per wheel notch

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


# ═════════════════════════════════════════════════════════════════════════════
class ValidatePage(QObject):
    """Binds nadir-validation behaviour to the widgets defined in main.ui."""

    status = Signal(str, int)

    def __init__(self, ui, window):
        super().__init__(window)
        self.ui = ui
        self.window = window

        self._lib_dir = None
        self._lib_root = None
        self._index_df = None
        self._csv_files = []
        self._df = None
        self._time = None
        self._pres = None
        self._cur_file = None
        self._cur_stem = ""
        self._nadir_idx = None
        self._curve = None
        self._right_curve = None
        self._left_key = "pressure"
        self._right_key = None
        self._win_sec = _WIN_SEC
        self._updating_right = False
        self._loaders = []
        self._pending_path = None
        self._loading = False

        self._fs_model = QFileSystemModel()
        self._fs_model.setFilter(QDir.Filter.Dirs | QDir.Filter.NoDotAndDotDot)
        self._proxy = _DirsOnlyProxy()
        self._proxy.setSourceModel(self._fs_model)

        self._build_plot()
        self._configure_widgets()
        self._connect()
        self._init_tree()

    # ── setup ────────────────────────────────────────────────────────────────
    def _build_plot(self):
        u = self.ui

        holder = QVBoxLayout(u.frame_val_plot)
        holder.setContentsMargins(0, 0, 0, 0)

        toolbar = QHBoxLayout()
        toolbar.addStretch()
        add_export_button(toolbar, self._export_data, self.window,
                          file_stub="segmentation")
        holder.addLayout(toolbar)

        self._pw = pg.PlotWidget(viewBox=_NavViewBox())
        pi = self._pw.plotItem
        pi.getViewBox().setMouseMode(pg.ViewBox.RectMode)
        pi.setLabel("left", _CHANNELS[self._left_key][1])
        pi.setLabel("bottom", "Time (s)")
        reserve_top_margin(pi)
        holder.addWidget(self._pw)

        # secondary ViewBox for the optional right-axis channel
        self._vb2 = pg.ViewBox()
        pi.scene().addItem(self._vb2)
        pi.getAxis("right").linkToView(self._vb2)
        self._vb2.setXLink(pi)
        set_right_axis_active(pi, False)
        pi.vb.sigResized.connect(self._sync_vb2)
        pi.vb.sigXRangeChanged.connect(self._on_xrange_changed)

        # nadir InfiniteLine - yellow, draggable
        self._nadir_line = pg.InfiniteLine(
            angle=90, movable=True,
            pen=pg.mkPen(color=(255, 220, 0), width=3),
            label="Nadir",
            labelOpts={"position": 0.92, "color": (180, 150, 0)},
        )
        self._nadir_line.sigPositionChanged.connect(self._on_nadir_moved)

        # window region - translucent blue, not resizable by user
        self._region = pg.LinearRegionItem(
            movable=False,
            brush=pg.mkBrush(0, 100, 255, 40),
            pen=pg.mkPen(0, 100, 255, 80),
        )
        pi.addItem(self._region)
        pi.addItem(self._nadir_line)

        # spinner lives inside the placeholder frame from the .ui
        sp = QVBoxLayout(u.frame_val_spinner)
        sp.setContentsMargins(0, 0, 0, 0)
        self._spinner = _Spinner(size=20)
        self._spinner.setVisible(False)
        sp.addWidget(self._spinner)

    def _configure_widgets(self):
        u = self.ui

        u.tree_val_library.setModel(self._proxy)
        u.tree_val_library.setHeaderHidden(True)
        for col in range(1, 4):
            u.tree_val_library.hideColumn(col)

        u.cmb_val_left.clear()
        for k in _CHANNEL_ORDER:
            u.cmb_val_left.addItem(_CHANNELS[k][1], k)
        u.cmb_val_left.setCurrentIndex(_CHANNEL_ORDER.index(self._left_key))

        u.cmb_val_right.clear()
        u.cmb_val_right.addItem("None", None)
        for k in _CHANNEL_ORDER:
            u.cmb_val_right.addItem(_CHANNELS[k][1], k)
        u.cmb_val_right.setCurrentIndex(0)

        self._fill_window_combo()

        for b in (u.btn_val_save_next, u.btn_val_reset, u.btn_val_jump):
            b.setEnabled(False)

    def _connect(self):
        u = self.ui
        u.tree_val_library.selectionModel().selectionChanged.connect(
            self._on_library_selected)
        u.btn_val_change_libraries.clicked.connect(self._change_libraries)
        u.tree_val_files.itemClicked.connect(self._on_file_clicked)
        u.cmb_val_left.currentIndexChanged.connect(self._on_axis_changed)
        u.cmb_val_right.currentIndexChanged.connect(self._on_axis_changed)
        u.cmb_val_window.currentIndexChanged.connect(self._on_win_size_changed)
        u.btn_val_save_next.clicked.connect(self._save_and_next)
        u.btn_val_reset.clicked.connect(self._reset_current)
        u.btn_val_jump.clicked.connect(self._jump_next_unvalidated)
        sensor_config.notifier.changed.connect(self._on_sensor_changed)

    def _init_tree(self):
        self._lib_dir = settings.get_libraries_dir()
        self.ui.btn_val_change_libraries.setToolTip(str(self._lib_dir))
        fs_root = self._fs_model.setRootPath(str(self._lib_dir))
        self.ui.tree_val_library.setRootIndex(self._proxy.mapFromSource(fs_root))

    def reload_libraries(self):
        self._init_tree()

    def _change_libraries(self):
        chosen = QFileDialog.getExistingDirectory(
            self.window, "Select libraries folder", str(self._lib_dir))
        if not chosen:
            return
        settings.set_libraries_dir(chosen)
        self._lib_root = None
        self._index_df = None
        self._csv_files = []
        self.ui.tree_val_files.clear()
        self._init_tree()
        self._update_progress()

    # ── library selection ────────────────────────────────────────────────────
    def _on_library_selected(self, selected, _deselected):
        idxs = selected.indexes()
        if not idxs:
            return
        folder = Path(self._fs_model.filePath(self._proxy.mapToSource(idxs[0])))
        try:
            rel = folder.relative_to(self._lib_dir)
            lib_root = self._lib_dir / rel.parts[0]
        except (ValueError, IndexError):
            lib_root = folder

        if lib_root == self._lib_root:
            return
        self._lib_root = lib_root
        self._load_index()
        self._populate_file_tree()
        self._update_progress()
        self.status.emit(f"Library: {lib_root.name}", 4000)

    # ── index ────────────────────────────────────────────────────────────────
    def _load_index(self):
        idx_path = self._lib_root / _INDEX_REL
        if not idx_path.exists():
            self._index_df = None
            return
        try:
            self._index_df = pd.read_csv(idx_path, low_memory=False)
        except Exception as e:
            self.status.emit(f"Index load failed: {e}", 6000)
            self._index_df = None
            return

        if _VALIDATED_COL not in self._index_df.columns:
            self._index_df[_VALIDATED_COL] = "N"
            self._index_df.to_csv(idx_path, index=False)

    def _save_index(self):
        if self._index_df is None or self._lib_root is None:
            return
        self._index_df.to_csv(self._lib_root / _INDEX_REL, index=False)

    def _is_validated(self, stem: str) -> bool:
        if self._index_df is None or "file" not in self._index_df.columns:
            return False
        row = self._index_df[self._index_df["file"] == stem]
        if row.empty or _VALIDATED_COL not in self._index_df.columns:
            return False
        return str(row[_VALIDATED_COL].iloc[0]).strip().upper() == "Y"

    def _update_progress(self):
        if self._index_df is None:
            self.ui.lbl_val_progress.setText("No index")
            return
        # the deployment plan's treatment rows share this file but are not
        # sensors, so they are not something to validate
        sensors = di.sensor_rows(self._index_df)
        total = len(sensors)
        done = (int((sensors[_VALIDATED_COL]
                     .astype(str).str.upper() == "Y").sum())
                if _VALIDATED_COL in sensors.columns else 0)
        self.ui.lbl_val_progress.setText(f"Validated: {done} / {total}")

    # ── file tree ────────────────────────────────────────────────────────────
    def _populate_file_tree(self):
        tree = self.ui.tree_val_files
        tree.clear()
        self._csv_files = []
        if self._lib_root is None:
            return
        csv_dir = self._lib_root / _CSV_DIR
        if not csv_dir.exists():
            return

        valid = [p for p in sorted(csv_dir.rglob("*.csv"))
                 if p.name not in _EXCL_NAMES
                 and not any(p.stem.endswith(s) for s in _EXCL_SUFFIXES)]
        self._csv_files = valid

        folder_items = {}
        for p in valid:
            rel = p.relative_to(csv_dir)
            colour = QColor(_OK) if self._is_validated(p.stem) else QColor(_TEXT)

            if len(rel.parts) == 1:
                parent = tree.invisibleRootItem()
            else:
                key = str(rel.parent)
                if key not in folder_items:
                    fi = QTreeWidgetItem(tree, [rel.parent.name])
                    fi.setExpanded(True)
                    folder_items[key] = fi
                parent = folder_items[key]

            it = QTreeWidgetItem(parent, [p.name])
            it.setData(0, Qt.ItemDataRole.UserRole, p)
            it.setForeground(0, colour)

    def _on_file_clicked(self, item, _col):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path is not None:
            self._load_sensor(path)

    # ── sensor loading ───────────────────────────────────────────────────────
    def _load_sensor(self, path: Path):
        if not path.exists():
            QMessageBox.warning(self.window, "File missing", f"Cannot find:\n{path}")
            return

        self._pending_path = path
        self._loading = True
        self._spinner.start()
        self.ui.lbl_val_loading.setText(f"Loading {path.name} …")
        self.status.emit(f"Loading {path.name} …", 0)
        for b in (self.ui.btn_val_save_next, self.ui.btn_val_reset,
                  self.ui.btn_val_jump):
            b.setEnabled(False)

        loader = _CsvLoadThread(path)
        loader.loaded.connect(self._on_csv_loaded)
        loader.failed.connect(self._on_csv_failed)
        loader.finished.connect(lambda lt=loader: self._drop_loader(lt))
        self._loaders.append(loader)
        loader.start()

    def _drop_loader(self, loader):
        if loader in self._loaders:
            self._loaders.remove(loader)

    def _on_csv_failed(self, path: Path, msg: str):
        if path != self._pending_path:
            return
        self._loading = False
        self._spinner.stop()
        self.ui.lbl_val_loading.setText("")
        self.status.emit(f"Load failed: {path.name}", 5000)
        QMessageBox.warning(self.window, "Load error",
                            f"Cannot load {path.name}:\n{msg}")

    def _on_csv_loaded(self, path: Path, df):
        if path != self._pending_path:
            return
        self._loading = False
        self._spinner.stop()
        self.ui.lbl_val_loading.setText("")
        if len(df) == 0:
            self.status.emit(f"{path.name} is empty - skipping.", 5000)
            return
        self._apply_loaded_df(path, df)

    def _apply_loaded_df(self, path: Path, df):
        time_col = _find_col(df, ["time_s", "time"], keyword="time")
        pres_col = _find_col(df, ["pressure_kpa", _NADIR_V_COL], keyword="pressure")

        time = (df[time_col].to_numpy(dtype=float) if time_col
                else np.arange(len(df), dtype=float) / self._fs())

        if pres_col is None:
            QMessageBox.warning(self.window, "No pressure column",
                                f"No pressure column found in {path.name}.\n"
                                "Nadir detection may be inaccurate.")

        self._df = df
        self._time = time
        self._pres = df[pres_col].to_numpy(dtype=float) if pres_col else None
        self._cur_file = path
        self._cur_stem = path.stem

        nadir_t = self._index_nadir_time()
        if nadir_t is not None:
            self._nadir_idx = int(np.argmin(np.abs(time - float(nadir_t))))
        elif self._pres is not None:
            self._nadir_idx = int(np.argmin(self._pres))
        else:
            self._nadir_idx = len(df) // 2

        self._draw_plot()
        for b in (self.ui.btn_val_save_next, self.ui.btn_val_reset,
                  self.ui.btn_val_jump):
            b.setEnabled(True)
        self.status.emit(f"Loaded: {path.name}", 3000)

    def _index_nadir_time(self):
        if (self._index_df is None
                or "file" not in self._index_df.columns
                or _NADIR_T_COL not in self._index_df.columns):
            return None
        row = self._index_df[self._index_df["file"] == self._cur_stem]
        if row.empty:
            return None
        val = row[_NADIR_T_COL].iloc[0]
        return None if pd.isna(val) else val

    # ── plot ─────────────────────────────────────────────────────────────────
    def _channel(self, key):
        if key is None or self._df is None:
            return None
        col = _CHANNELS.get(key, (None,))[0]
        if col and col in self._df.columns:
            return self._df[col].to_numpy(dtype=float)
        return None

    def _draw_plot(self):
        pi = self._pw.plotItem
        self._refresh_curves()

        nadir_t = float(self._time[self._nadir_idx])
        self._nadir_line.blockSignals(True)
        self._nadir_line.setValue(nadir_t)
        self._nadir_line.blockSignals(False)
        self._update_region(nadir_t)

        self._apply_view_limits()
        pi.enableAutoRange("y", True)
        pi.setXRange(nadir_t - 0.5, nadir_t + 0.5, padding=0)

    def _on_axis_changed(self):
        self._left_key = self.ui.cmb_val_left.currentData()
        self._right_key = self.ui.cmb_val_right.currentData()
        if self._df is None:
            return
        self._refresh_curves()
        self._apply_view_limits()

    def _refresh_curves(self):
        pi = self._pw.plotItem

        if self._curve is not None:
            pi.removeItem(self._curve)
            self._curve = None
        y = self._channel(self._left_key)
        if y is not None:
            self._curve = self._pw.plot(self._time, y,
                                        pen=pg.mkPen("#dddddd", width=1))
            self._curve.setDownsampling(auto=True, method="peak")
            self._curve.setClipToView(True)
        pi.setLabel("left", _CHANNELS[self._left_key][1])

        self._refresh_right_curve()

    def _refresh_right_curve(self):
        pi = self._pw.plotItem
        if self._right_curve is not None:
            self._vb2.removeItem(self._right_curve)
            self._right_curve = None

        if self._right_key is None or self._channel(self._right_key) is None:
            set_right_axis_active(pi, False)
            return

        set_right_axis_active(pi, True)
        pi.setLabel("right", _CHANNELS[self._right_key][1])
        self._right_curve = pg.PlotCurveItem(
            pen=pg.mkPen("#ff5555", width=1))
        self._vb2.addItem(self._right_curve)
        self._update_right_data()
        self._sync_vb2()

    def _update_right_data(self):
        if self._right_curve is None or self._time is None:
            return
        y = self._channel(self._right_key)
        if y is None:
            return
        (x0, x1), _ = self._pw.plotItem.vb.viewRange()
        t = self._time
        lo = max(0, int(np.searchsorted(t, x0, "left")) - 1)
        hi = min(len(t), int(np.searchsorted(t, x1, "right")) + 1)
        if hi - lo < 2:
            return
        xd, yd = _decimate(t[lo:hi], y[lo:hi], _MAX_RIGHT_PTS)
        self._right_curve.setData(xd, yd)
        self._vb2.enableAutoRange("y", True)

    def _on_xrange_changed(self):
        if self._right_curve is None or self._updating_right:
            return
        self._updating_right = True
        try:
            self._update_right_data()
        finally:
            self._updating_right = False

    def _sync_vb2(self):
        pi = self._pw.plotItem
        self._vb2.setGeometry(pi.vb.sceneBoundingRect())
        self._vb2.linkedViewChanged(pi.vb, self._vb2.XAxis)

    def _export_data(self):
        (x0, x1), _ = self._pw.plotItem.vb.viewRange()
        left_label = _CHANNELS[self._left_key][1] if self._left_key else ""
        right_label = _CHANNELS[self._right_key][1] if self._right_key else ""
        return build_export_data(
            self._time, left_label, self._channel(self._left_key),
            right_label, self._channel(self._right_key), (x0, x1))

    def _apply_view_limits(self):
        vb = self._pw.plotItem.getViewBox()
        if self._time is None or len(self._time) == 0:
            vb.setLimits(xMin=None, xMax=None, yMin=None, yMax=None)
            return
        x0, x1 = float(self._time[0]), float(self._time[-1])
        xpad = (x1 - x0) * 0.02 or 1.0
        kw = dict(xMin=x0 - xpad, xMax=x1 + xpad)
        y = self._channel(self._left_key)
        if y is not None and len(y):
            y0, y1 = float(np.min(y)), float(np.max(y))
            ypad = (y1 - y0) * 0.05 or 1.0
            kw.update(yMin=y0 - ypad, yMax=y1 + ypad)
        vb.setLimits(**kw)

    def _update_region(self, t: float):
        self._region.setRegion([t - self._win_sec / 2, t + self._win_sec / 2])

    def _fill_window_combo(self):
        """Offer 100-1000 ms, defaulting to this page's own width."""
        cmb = self.ui.cmb_val_window
        want = int(round(self._win_sec * 1000))
        options = sorted(set(range(100, 1001, 100)) | {want})
        cmb.blockSignals(True)
        cmb.clear()
        for ms in options:
            cmb.addItem(f"{ms} ms", ms)
        cmb.setCurrentIndex(max(0, cmb.findData(want)))
        cmb.blockSignals(False)

    def _on_sensor_changed(self, _key):
        """A new sensor means a new rate, so the window spans new samples."""
        if self._time is not None and self._nadir_idx is not None:
            self._update_region(float(self._time[self._nadir_idx]))

    def _on_win_size_changed(self):
        ms = self.ui.cmb_val_window.currentData()
        if ms is None:
            return
        self._win_sec = ms / 1000.0
        if self._time is not None and self._nadir_idx is not None:
            self._update_region(float(self._time[self._nadir_idx]))

    def _on_nadir_moved(self):
        if self._time is None:
            return
        raw_t = self._nadir_line.value()
        idx = int(np.argmin(np.abs(self._time - raw_t)))
        self._nadir_idx = idx
        t_snap = float(self._time[idx])
        self._nadir_line.blockSignals(True)
        self._nadir_line.setValue(t_snap)
        self._nadir_line.blockSignals(False)
        self._update_region(t_snap)

    # ── save / advance ───────────────────────────────────────────────────────
    def _save_and_next(self):
        if self._df is None:
            return
        try:
            self._do_save_window()
            self._do_update_index()
            self._mark_validated_in_tree(self._cur_file)
            self._update_progress()
        except Exception as e:
            QMessageBox.critical(self.window, "Save error", str(e))
            return
        self._jump_next_unvalidated()

    @staticmethod
    def _fs():
        """Sample rate of the processed CSVs for the active sensor."""
        return sensor_config.active().output_rate_hz or _FS

    def _window_bounds(self):
        n = len(self._df)
        half_n = int(round(self._win_sec / 2 * self._fs()))
        start = max(0, self._nadir_idx - half_n)
        end = min(n - 1, self._nadir_idx + half_n)
        return start, end

    def _do_save_window(self):
        start, end = self._window_bounds()
        ms = int(round(self._win_sec * 1000))
        out_dir = self._lib_root / _WIN_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        self._df.iloc[start:end + 1].to_csv(
            out_dir / f"{self._cur_stem}_{ms}ms.csv", index=False)

    def _do_update_index(self):
        if self._index_df is None:
            return
        start, end = self._window_bounds()
        nadir_t = float(self._time[self._nadir_idx])
        nadir_v = (float(self._pres[self._nadir_idx])
                   if self._pres is not None else float("nan"))

        mask = self._index_df["file"] == self._cur_stem
        if not mask.any():
            new_row = pd.DataFrame([{"file": self._cur_stem}])
            self._index_df = pd.concat([self._index_df, new_row], ignore_index=True)
            mask = self._index_df["file"] == self._cur_stem

        self._index_df.loc[mask, _NADIR_T_COL] = nadir_t
        self._index_df.loc[mask, _NADIR_V_COL] = nadir_v
        self._index_df.loc[mask, "nadir_window_start"] = self._time[start]
        self._index_df.loc[mask, "nadir_window_end"] = self._time[end]
        self._index_df.loc[mask, _VALIDATED_COL] = "Y"
        self._save_index()

    def _reset_current(self):
        if self._cur_file:
            self._load_sensor(self._cur_file)

    def _jump_next_unvalidated(self):
        if (self._index_df is None
                or "file" not in self._index_df.columns
                or _VALIDATED_COL not in self._index_df.columns):
            return
        unval = self._index_df[
            self._index_df[_VALIDATED_COL].astype(str).str.upper() != "Y"
        ]["file"].tolist()
        if not unval:
            self.status.emit("All sensors validated!", 5000)
            return
        match = next((p for p in self._csv_files if p.stem == unval[0]), None)
        if match:
            self._select_tree_item(match)
            self._load_sensor(match)
        else:
            self.status.emit(
                f"Next unvalidated '{unval[0]}' has no CSV - skipping.", 5000)

    # ── tree helpers ─────────────────────────────────────────────────────────
    def _mark_validated_in_tree(self, path: Path):
        self._walk_tree(
            lambda item: item.setForeground(0, QColor(_OK))
            if item.data(0, Qt.ItemDataRole.UserRole) == path else None)

    def _select_tree_item(self, path: Path):
        def _try(item):
            if item.data(0, Qt.ItemDataRole.UserRole) == path:
                self.ui.tree_val_files.setCurrentItem(item)
                self.ui.tree_val_files.scrollToItem(item)
        self._walk_tree(_try)

    def _walk_tree(self, fn):
        def _recurse(parent):
            for i in range(parent.childCount()):
                child = parent.child(i)
                fn(child)
                _recurse(child)
        _recurse(self.ui.tree_val_files.invisibleRootItem())
