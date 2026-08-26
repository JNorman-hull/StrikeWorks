# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Controller for the Annotate page (Annotation & Video Analysis).

One place to review a sensor recording against its signal - and, where a
matching clip exists, its video - and record what happened: a quick nadir
window (the same window Sensor Processing's Validate & segment page saves,
so Dataset creation's segmented mode picks it up unchanged either way), the
manual `bad_sens` flag, and free-form annotation values.

Built the same way Chunk 3's Prepare tabs were: widgets constructed in code
into ``ui.content_annotate`` rather than laid out in main.ui. The signal
plot reuses ``page_validate.py``'s already-standalone loader/viewbox
classes (the same reuse ``ml_tab_inspect.py`` already makes) rather than
duplicating them; ``page_validate.py`` itself is untouched and stays under
Sensor Processing, since it is the page slated to grow into the Delineation
tool later.

Annotation values and the manual flag are written straight onto the
sensor's own row in ``global_sensor_index.csv`` via
``deployment_index.set_row_values`` - no separate annotation CSV. The four
annotation variables default to the columns the old ``model_labels.csv``
workflow already used (``modules/annotation_schema.py``), so a dataset
built the old way still reads the same.
"""
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pyqtgraph as pg

from PySide6.QtCore import Qt, QDir, QObject, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFileSystemModel, QGridLayout,
    QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QSizePolicy, QSplitter, QTreeView,
    QVBoxLayout, QWidget,
)

from . import annotation_schema as asch
from . import deployment_index as di
from . import sensor_config, settings
from .annotation_widgets import AnnotationValueEditor, VariableListDialog
from .ml_widgets import (
    ACCENT, BAD, BORDER, CARD_BG, MUTED, OK, WARN, Section,
    apply_section_defaults,
)
from .page_process import _DirsOnlyProxy
from .page_validate import (
    _CHANNEL_ORDER, _CHANNELS, _CsvLoadThread, _EXCL_NAMES, _EXCL_SUFFIXES,
    _NavViewBox, _Spinner, _find_col,
)

pg.setConfigOptions(antialias=True, background="#21252b",
                    foreground="#c8cdd6")

_CSV_DIR = Path("processed_sens_data") / "csv"
_WIN_DIR = Path("processed_sens_data") / "nadir_window"
_VIDEO_DIR = Path("video")

_NADIR_T_COL = "pres_min.time."
_NADIR_V_COL = "pres_min.kPa."
_VALIDATED_COL = "hstrike_processed"
_BAD_SENS_COL = "bad_sens"

_FS = 2000
_WIN_SEC = 0.2

LOSSLESSCUT_EXE = Path(__file__).parent.parent / "exteneral_software" / "LosslessCut.exe"


class AnnotationPage(QObject):
    """Binds the Annotate page widgets to ``ui.content_annotate``."""

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
        self._channel_key = "pressure"
        self._win_sec = _WIN_SEC
        self._loaders = []
        self._pending_path = None
        self._editors = {}
        self._video_matches = []

        self._fs_model = QFileSystemModel()
        self._fs_model.setFilter(QDir.Filter.Dirs | QDir.Filter.NoDotAndDotDot)
        self._proxy = _DirsOnlyProxy()
        self._proxy.setSourceModel(self._fs_model)

        self._build(ui.content_annotate)
        self._connect()
        self._init_tree()
        self._rebuild_annotation_panel()
        self._set_loaded_enabled(False)

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, frame):
        v = QVBoxLayout(frame)
        v.setContentsMargins(4, 6, 4, 6)
        v.setSpacing(8)

        # ── browsing row: library tree + file list ──────────────────────────
        grp_browse = Section("Library")
        bv = QHBoxLayout(grp_browse)
        bv.setSpacing(8)

        left_col = QVBoxLayout()
        lib_row = QHBoxLayout()
        self.btn_change_libs = QPushButton("Change libraries folder…")
        self.btn_change_libs.clicked.connect(self._change_libraries)
        lib_row.addWidget(self.btn_change_libs)
        left_col.addLayout(lib_row)
        self.tree_library = QTreeView()
        self.tree_library.setModel(self._proxy)
        self.tree_library.setHeaderHidden(True)
        for col in range(1, 4):
            self.tree_library.hideColumn(col)
        self.tree_library.setMaximumHeight(120)
        self.tree_library.setStyleSheet(
            f"QTreeView{{background-color:{CARD_BG};"
            f"border:1px solid {BORDER};border-radius:5px;}}")
        left_col.addWidget(self.tree_library)
        bv.addLayout(left_col, stretch=1)

        right_col = QVBoxLayout()
        filt_row = QHBoxLayout()
        self.chk_show_flags = QCheckBox("Show flags")
        self.chk_show_flags.setChecked(True)
        filt_row.addWidget(self.chk_show_flags)
        filt_row.addStretch()
        right_col.addLayout(filt_row)
        self.list_files = QListWidget()
        self.list_files.setMaximumHeight(120)
        self.list_files.setStyleSheet(
            f"QListWidget{{background-color:{CARD_BG};"
            f"border:1px solid {BORDER};border-radius:5px;}}")
        right_col.addWidget(self.list_files)
        bv.addLayout(right_col, stretch=2)
        v.addWidget(grp_browse)

        self.lbl_loading = QLabel("")
        self.lbl_loading.setStyleSheet(f"color:{MUTED};")
        v.addWidget(self.lbl_loading)

        # ── main content: plot | annotations, half and half ─────────────────
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        v.addWidget(split, stretch=1)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(8)
        self._build_plot_side(lv)
        split.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        self._build_annotation_side(rv)
        split.addWidget(right)
        split.setSizes([1, 1])   # half / half

        apply_section_defaults(frame)

    def _build_plot_side(self, v):
        grp_sig = Section("Signal")
        sv = QVBoxLayout(grp_sig)
        sv.setSpacing(6)

        top = QHBoxLayout()
        top.addWidget(self._muted("Channel"))
        self.cmb_channel = QComboBox()
        for key in _CHANNEL_ORDER:
            self.cmb_channel.addItem(_CHANNELS[key][1], key)
        self.cmb_channel.setCurrentIndex(_CHANNEL_ORDER.index(self._channel_key))
        top.addWidget(self.cmb_channel, stretch=1)
        top.addWidget(self._muted("Window"))
        self.cmb_window = QComboBox()
        top.addWidget(self.cmb_window)
        self._spinner = _Spinner(size=18)
        self._spinner.setVisible(False)
        top.addWidget(self._spinner)
        sv.addLayout(top)

        plot_holder = QWidget()
        plot_holder.setSizePolicy(QSizePolicy.Policy.Expanding,
                                  QSizePolicy.Policy.Expanding)
        ph = QVBoxLayout(plot_holder)
        ph.setContentsMargins(0, 0, 0, 0)
        self._pw = pg.PlotWidget(viewBox=_NavViewBox())
        pi = self._pw.plotItem
        pi.getViewBox().setMouseMode(pg.ViewBox.RectMode)
        pi.setLabel("bottom", "Time (s)")
        ph.addWidget(self._pw)
        sv.addWidget(plot_holder, stretch=1)

        self._nadir_line = pg.InfiniteLine(
            angle=90, movable=True,
            pen=pg.mkPen(color=(255, 220, 0), width=3),
            label="Nadir",
            labelOpts={"position": 0.92, "color": (180, 150, 0)})
        self._nadir_line.sigPositionChanged.connect(self._on_nadir_moved)
        self._region = pg.LinearRegionItem(
            movable=False, brush=pg.mkBrush(0, 100, 255, 40),
            pen=pg.mkPen(0, 100, 255, 80))
        pi.addItem(self._region)
        pi.addItem(self._nadir_line)

        act = QHBoxLayout()
        self.btn_save_window = QPushButton("Save window")
        self.btn_save_window.setStyleSheet(
            f"QPushButton{{background-color:{ACCENT};color:#ffffff;"
            "border-radius:5px;padding:4px 14px;font-weight:bold;}"
            "QPushButton:disabled{background-color:#3a4150;color:#8a95aa;}")
        self.btn_save_window.clicked.connect(self._save_window)
        act.addWidget(self.btn_save_window)
        act.addStretch()
        sv.addLayout(act)
        v.addWidget(grp_sig)

        grp_flag = Section("Flag and video")
        fv = QGridLayout(grp_flag)
        fv.setVerticalSpacing(6)
        self.chk_bad = QCheckBox("Bad")
        self.chk_bad.setChecked(False)
        fv.addWidget(self.chk_bad, 0, 0)
        self.btn_set_flag = QPushButton("Set flag")
        self.btn_set_flag.clicked.connect(self._set_flag)
        fv.addWidget(self.btn_set_flag, 0, 1)
        self.btn_video = QPushButton("Open video")
        self.btn_video.setToolTip(
            f"Looks for <library>/{_VIDEO_DIR}/<sensor>_vid_*.mp4")
        self.btn_video.clicked.connect(self._open_video)
        fv.addWidget(self.btn_video, 0, 2)
        v.addWidget(grp_flag)

    def _build_annotation_side(self, v):
        grp = Section("Annotations")
        gv = QVBoxLayout(grp)
        gv.setSpacing(6)

        self.annotation_grid = QGridLayout()
        self.annotation_grid.setVerticalSpacing(6)
        self.annotation_grid.setColumnStretch(1, 1)
        gv.addLayout(self.annotation_grid)

        act = QHBoxLayout()
        self.btn_save_annotations = QPushButton("Save annotations")
        self.btn_save_annotations.setStyleSheet(
            f"QPushButton{{background-color:{ACCENT};color:#ffffff;"
            "border-radius:5px;padding:4px 14px;font-weight:bold;}"
            "QPushButton:disabled{background-color:#3a4150;color:#8a95aa;}")
        self.btn_save_annotations.clicked.connect(self._save_annotations)
        act.addWidget(self.btn_save_annotations)
        self.btn_manage_vars = QPushButton("Manage variables…")
        self.btn_manage_vars.clicked.connect(self._manage_variables)
        act.addWidget(self.btn_manage_vars)
        act.addStretch()
        gv.addLayout(act)

        self.lbl_annotation_status = QLabel("")
        self.lbl_annotation_status.setStyleSheet(f"color:{MUTED};")
        self.lbl_annotation_status.setWordWrap(True)
        gv.addWidget(self.lbl_annotation_status)
        gv.addStretch()
        v.addWidget(grp)

    @staticmethod
    def _muted(text):
        lab = QLabel(text)
        lab.setStyleSheet(f"color:{MUTED};")
        return lab

    def _connect(self):
        self.tree_library.selectionModel().selectionChanged.connect(
            self._on_library_selected)
        self.list_files.itemClicked.connect(self._on_file_clicked)
        self.chk_show_flags.toggled.connect(self._populate_file_list)
        self.cmb_channel.currentIndexChanged.connect(self._on_channel_changed)
        self.cmb_window.currentIndexChanged.connect(self._on_win_size_changed)
        sensor_config.notifier.changed.connect(self._on_sensor_changed)
        asch.notifier.changed.connect(self._rebuild_annotation_panel)
        self._fill_window_combo()

    def _set_loaded_enabled(self, enabled):
        for b in (self.btn_save_window, self.btn_set_flag,
                  self.btn_save_annotations):
            b.setEnabled(enabled)
        self.chk_bad.setEnabled(enabled)
        self._refresh_video_button()

    # ── libraries ────────────────────────────────────────────────────────────
    def _init_tree(self):
        self._lib_dir = settings.get_libraries_dir()
        self.btn_change_libs.setToolTip(str(self._lib_dir))
        fs_root = self._fs_model.setRootPath(str(self._lib_dir))
        self.tree_library.setRootIndex(self._proxy.mapFromSource(fs_root))

    def _change_libraries(self):
        chosen = QFileDialog.getExistingDirectory(
            self.window, "Select libraries folder", str(self._lib_dir))
        if not chosen:
            return
        self._lib_dir = settings.set_libraries_dir(chosen)
        self._lib_root = None
        self._index_df = None
        self._csv_files = []
        self.list_files.clear()
        self._init_tree()

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
        self._populate_file_list()
        self.status.emit(f"Library: {lib_root.name}", 4000)

    # ── index ────────────────────────────────────────────────────────────────
    def _load_index(self):
        if self._lib_root is None:
            self._index_df = None
            return
        self._index_df = di.read_index(self._lib_root)

    def _is_bad(self, stem: str) -> bool:
        if self._index_df is None or "file" not in self._index_df.columns:
            return False
        row = self._index_df[self._index_df["file"] == stem]
        if row.empty or _BAD_SENS_COL not in self._index_df.columns:
            return False
        return str(row[_BAD_SENS_COL].iloc[0]).strip().upper() == "Y"

    # ── file list ────────────────────────────────────────────────────────────
    def _populate_file_list(self):
        self.list_files.clear()
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

        show_flags = self.chk_show_flags.isChecked()
        for p in valid:
            item = QListWidgetItem(p.stem)
            item.setData(Qt.ItemDataRole.UserRole, p)
            if show_flags and self._is_bad(p.stem):
                item.setForeground(QColor(BAD))
            self.list_files.addItem(item)

    def _on_file_clicked(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path is not None:
            self._load_sensor(path)

    # ── sensor loading ───────────────────────────────────────────────────────
    def _load_sensor(self, path: Path):
        if not path.exists():
            QMessageBox.warning(self.window, "File missing", f"Cannot find:\n{path}")
            return
        self._pending_path = path
        self._spinner.start()
        self.lbl_loading.setText(f"Loading {path.name} …")
        self.status.emit(f"Loading {path.name} …", 0)
        self._set_loaded_enabled(False)

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
        self._spinner.stop()
        self.lbl_loading.setText("")
        self.status.emit(f"Load failed: {path.name}", 5000)
        QMessageBox.warning(self.window, "Load error",
                            f"Cannot load {path.name}:\n{msg}")

    def _on_csv_loaded(self, path: Path, df):
        if path != self._pending_path:
            return
        self._spinner.stop()
        self.lbl_loading.setText("")
        if len(df) == 0:
            self.status.emit(f"{path.name} is empty - skipping.", 5000)
            return
        self._apply_loaded_df(path, df)

    def _apply_loaded_df(self, path: Path, df):
        time_col = _find_col(df, ["time_s", "time"], keyword="time")
        pres_col = _find_col(df, ["pressure_kpa", _NADIR_V_COL], keyword="pressure")

        time = (df[time_col].to_numpy(dtype=float) if time_col
                else np.arange(len(df), dtype=float) / self._fs())

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
        self._load_flag_state()
        self._load_annotations_for_current()
        self._set_loaded_enabled(True)
        self.status.emit(f"Loaded: {path.name}", 3000)

    def _index_nadir_time(self):
        if (self._index_df is None or "file" not in self._index_df.columns
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
        self._refresh_curve()
        nadir_t = float(self._time[self._nadir_idx])
        self._nadir_line.blockSignals(True)
        self._nadir_line.setValue(nadir_t)
        self._nadir_line.blockSignals(False)
        self._update_region(nadir_t)
        self._apply_view_limits()
        pi.enableAutoRange("y", True)
        pi.setXRange(nadir_t - 0.5, nadir_t + 0.5, padding=0)

    def _on_channel_changed(self):
        self._channel_key = self.cmb_channel.currentData()
        if self._df is not None:
            self._refresh_curve()
            self._apply_view_limits()

    def _refresh_curve(self):
        pi = self._pw.plotItem
        if self._curve is not None:
            pi.removeItem(self._curve)
            self._curve = None
        y = self._channel(self._channel_key)
        if y is not None:
            self._curve = self._pw.plot(
                self._time, y, pen=pg.mkPen("#dddddd", width=1))
            self._curve.setDownsampling(auto=True, method="peak")
            self._curve.setClipToView(True)
        pi.setLabel("left", _CHANNELS[self._channel_key][1])

    def _apply_view_limits(self):
        vb = self._pw.plotItem.getViewBox()
        if self._time is None or len(self._time) == 0:
            vb.setLimits(xMin=None, xMax=None, yMin=None, yMax=None)
            return
        x0, x1 = float(self._time[0]), float(self._time[-1])
        xpad = (x1 - x0) * 0.02 or 1.0
        kw = dict(xMin=x0 - xpad, xMax=x1 + xpad)
        y = self._channel(self._channel_key)
        if y is not None and len(y):
            y0, y1 = float(np.min(y)), float(np.max(y))
            ypad = (y1 - y0) * 0.05 or 1.0
            kw.update(yMin=y0 - ypad, yMax=y1 + ypad)
        vb.setLimits(**kw)

    def _update_region(self, t: float):
        self._region.setRegion([t - self._win_sec / 2, t + self._win_sec / 2])

    def _fill_window_combo(self):
        want = int(round(self._win_sec * 1000))
        options = sorted(set(range(100, 1001, 100)) | {want})
        self.cmb_window.blockSignals(True)
        self.cmb_window.clear()
        for ms in options:
            self.cmb_window.addItem(f"{ms} ms", ms)
        self.cmb_window.setCurrentIndex(max(0, self.cmb_window.findData(want)))
        self.cmb_window.blockSignals(False)

    def _on_sensor_changed(self, _key):
        if self._time is not None and self._nadir_idx is not None:
            self._update_region(float(self._time[self._nadir_idx]))

    def _on_win_size_changed(self):
        ms = self.cmb_window.currentData()
        if ms is None:
            return
        self._win_sec = ms / 1000.0
        if self._time is not None and self._nadir_idx is not None:
            self._update_region(float(self._time[self._nadir_idx]))

    def _on_nadir_moved(self):
        if self._time is None:
            return
        idx = int(np.argmin(np.abs(self._time - self._nadir_line.value())))
        self._nadir_idx = idx
        t_snap = float(self._time[idx])
        self._nadir_line.blockSignals(True)
        self._nadir_line.setValue(t_snap)
        self._nadir_line.blockSignals(False)
        self._update_region(t_snap)

    # ── save window (same locations page_validate.py already uses) ──────────
    @staticmethod
    def _fs():
        return sensor_config.active().output_rate_hz or _FS

    def _window_bounds(self):
        n = len(self._df)
        half_n = int(round(self._win_sec / 2 * self._fs()))
        start = max(0, self._nadir_idx - half_n)
        end = min(n - 1, self._nadir_idx + half_n)
        return start, end

    def _save_window(self):
        if self._df is None or self._lib_root is None:
            return
        try:
            start, end = self._window_bounds()
            ms = int(round(self._win_sec * 1000))
            out_dir = self._lib_root / _WIN_DIR
            out_dir.mkdir(parents=True, exist_ok=True)
            self._df.iloc[start:end + 1].to_csv(
                out_dir / f"{self._cur_stem}_{ms}ms.csv", index=False)

            nadir_t = float(self._time[self._nadir_idx])
            nadir_v = (float(self._pres[self._nadir_idx])
                      if self._pres is not None else float("nan"))
            n = di.set_row_values(self._lib_root, self._cur_stem, {
                _NADIR_T_COL: nadir_t,
                _NADIR_V_COL: nadir_v,
                "nadir_window_start": self._time[start],
                "nadir_window_end": self._time[end],
                _VALIDATED_COL: "Y",
            })
        except Exception as e:
            QMessageBox.critical(self.window, "Save error", str(e))
            return
        self._load_index()
        if not n:
            self.status.emit(
                f"Window saved, but {self._cur_stem} has no index row yet - "
                "process it first for the flag/nadir columns to be kept.",
                6000)
        else:
            self.status.emit(f"Window saved: {self._cur_stem}", 4000)

    # ── manual bad_sens flag ─────────────────────────────────────────────────
    def _load_flag_state(self):
        self.chk_bad.blockSignals(True)
        self.chk_bad.setChecked(self._is_bad(self._cur_stem))
        self.chk_bad.blockSignals(False)

    def _set_flag(self):
        if self._lib_root is None or not self._cur_stem:
            return
        value = "Y" if self.chk_bad.isChecked() else "N"
        n = di.set_row_values(self._lib_root, self._cur_stem,
                              {_BAD_SENS_COL: value})
        if not n:
            self.status.emit(
                f"{self._cur_stem} has no index row yet - process it first.",
                5000)
            return
        self._load_index()
        self._populate_file_list()
        self.status.emit(
            f"{self._cur_stem} flagged {'Bad' if value == 'Y' else 'Good'}.",
            4000)

    # ── video ────────────────────────────────────────────────────────────────
    def _refresh_video_button(self):
        self._video_matches = []
        if self._lib_root and self._cur_stem:
            video_dir = self._lib_root / _VIDEO_DIR
            if video_dir.exists():
                self._video_matches = sorted(
                    video_dir.glob(f"{self._cur_stem}_vid_*.mp4"))
        self.btn_video.setEnabled(bool(self._video_matches)
                                  and LOSSLESSCUT_EXE.exists())
        if not self._video_matches:
            self.btn_video.setToolTip(
                f"No matching video in {self._lib_root / _VIDEO_DIR}"
                if self._lib_root else "Load a sensor first.")
        elif not LOSSLESSCUT_EXE.exists():
            self.btn_video.setToolTip(f"Missing: {LOSSLESSCUT_EXE}")
        else:
            self.btn_video.setToolTip(
                "; ".join(p.name for p in self._video_matches))

    def _open_video(self):
        if not self._video_matches:
            return
        video_path = self._video_matches[0]
        if len(self._video_matches) > 1:
            names = [p.name for p in self._video_matches]
            choice, ok = QInputDialog.getItem(
                self.window, "Choose video",
                f"{len(names)} videos match {self._cur_stem}:",
                names, 0, False)
            if not ok:
                return
            video_path = self._video_matches[names.index(choice)]
        try:
            subprocess.Popen([str(LOSSLESSCUT_EXE), str(video_path)])
        except Exception as e:
            QMessageBox.critical(self.window, "Could not open video", str(e))
            return
        self.status.emit(f"Opened {video_path.name} in LosslessCut", 4000)

    # ── annotations ──────────────────────────────────────────────────────────
    def _rebuild_annotation_panel(self):
        while self.annotation_grid.count():
            item = self.annotation_grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._editors = {}

        for row, var in enumerate(asch.all_variables()):
            lab = self._muted(var.label)
            editor = AnnotationValueEditor(var.name)
            self.annotation_grid.addWidget(lab, row, 0)
            self.annotation_grid.addWidget(editor, row, 1)
            self._editors[var.name] = editor

        if self._cur_stem:
            self._load_annotations_for_current()

    def _load_annotations_for_current(self):
        row = None
        if (self._index_df is not None
                and "file" in self._index_df.columns):
            match = self._index_df[self._index_df["file"] == self._cur_stem]
            if not match.empty:
                row = match.iloc[0]
        for name, editor in self._editors.items():
            value = row.get(name, "") if row is not None else ""
            value = "" if pd.isna(value) else value
            editor.set_current(value)

    def _save_annotations(self):
        if self._lib_root is None or not self._cur_stem:
            return
        values = {name: editor.current()
                 for name, editor in self._editors.items()}
        filled = {k: v for k, v in values.items() if v}
        if not filled:
            self.lbl_annotation_status.setText("Nothing entered.")
            self.lbl_annotation_status.setStyleSheet(f"color:{WARN};")
            return
        n = di.set_row_values(self._lib_root, self._cur_stem, filled)
        self._load_index()
        if not n:
            self.lbl_annotation_status.setText(
                f"{self._cur_stem} has no index row yet - process it first.")
            self.lbl_annotation_status.setStyleSheet(f"color:{WARN};")
            return
        self.lbl_annotation_status.setText(
            f"Saved {len(filled)} value(s) for {self._cur_stem}.")
        self.lbl_annotation_status.setStyleSheet(f"color:{OK};")
        self.status.emit(f"Annotations saved: {self._cur_stem}", 4000)

    def _manage_variables(self):
        dlg = VariableListDialog(self.window)
        dlg.exec()
        # asch.notifier.changed already triggers _rebuild_annotation_panel
