# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""The sensor validation screen of Validate and annotate (page_annotate.py)
- the Development toolkit's page and StrikeWorks's Validate step.

  left   the sensor list - Sort by, coloured by validation state (the
         colours' key on hover) - Mark bad / Show bad, the counts, Save +
         Next, Reset current sensor and Auto process all. A host can put
         its own controls above the list (the library filters).
  right  Left / Right channels, the loading spinner and Export over the
         signal plot (drag the nadir line; the ROI window is shaded), then
         ROI window, the status line, Open video, any buttons of the
         host's own (Annotations and notes) and Save and export.

What's flagged, saving a window, Auto process all and the dataset export
are validation_core.py's. The host gives the library, its sensors and how
to find a sensor's video (`set_source`), and can hook into Save + Next
(`save_values`: more columns for the index - the annotations) and the
counts line (`counts_suffix`).
"""
import subprocess

import numpy as np
import pandas as pd
import pyqtgraph as pg

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QInputDialog, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QSizePolicy, QVBoxLayout,
    QWidget,
)

from . import deployment_index as di
from . import sensor_sort, settings
from . import validation_core as vc
from .cards import Spinner
from .plot_style import (
    add_export_button, build_export_data, reserve_top_margin,
    set_right_axis_active,
)
from .plot_widgets import (
    CHANNEL_ORDER, CHANNELS, MAX_RIGHT_PTS, CsvLoadThread, NavViewBox,
    decimate,
)
from .theme import (
    ACCENT, BAD, NADIR, OK, REGION_EDGE, REGION_FILL, TEXT, TRACE, TRACE2,
    WARN, muted_label, style,
)

# video review opens clips in LosslessCut (not shipped - 900 MB): in
# external_software/ at the repo root from source, beside StrikeWorks.exe
# once packaged (the build puts a readme there saying what to copy in)
LOSSLESSCUT_EXE = settings.app_root() / "external_software" / "LosslessCut.exe"
LOSSLESSCUT_MISSING = (
    "Video review opens clips in LosslessCut, which isn't installed.\n\n"
    f"Copy LosslessCut.exe and all the files that come with it into\n"
    f"{LOSSLESSCUT_EXE.parent}\n\n"
    "(readme.txt in that folder has the download link).")

LIST_W = 300                     # the left column's width


def open_video(parent, stem, matches):
    """Open one of a sensor's video clips (`matches`, paths) in LosslessCut
    - asking which, when there are several. Returns a status message, or
    None when nothing was opened."""
    if not matches:
        return f"No matching video for {stem}."
    if not LOSSLESSCUT_EXE.exists():
        QMessageBox.warning(parent, "LosslessCut missing", LOSSLESSCUT_MISSING)
        return None
    video_path = matches[0]
    if len(matches) > 1:
        names = [p.name for p in matches]
        choice, ok = QInputDialog.getItem(
            parent, "Choose video", f"{len(names)} videos match {stem}:",
            names, 0, False)
        if not ok:
            return None
        video_path = matches[names.index(choice)]
    try:
        subprocess.Popen([str(LOSSLESSCUT_EXE), str(video_path)])
    except Exception as e:
        QMessageBox.critical(parent, "Could not open video", str(e))
        return None
    return f"Opened {video_path.name} in LosslessCut"


class ValidationView(QWidget):
    """The validation screen (see the module docstring). `top`: a widget of
    the host's above the list; `extra_buttons`: buttons of the host's under
    the plot, before Save and export."""

    sensor_loaded = Signal(str)                  # the stem now shown
    index_changed = Signal()                     # this view wrote the index
    export_done = Signal(object, object, str)    # DatasetExporter.finished
    status = Signal(str, int)

    def __init__(self, parent_window, top=None, extra_buttons=()):
        super().__init__()
        self.parent_window = parent_window       # the dialogs' parent
        self.save_values = None     # (stem) -> {column: value}, with Save + Next
        self.counts_suffix = None   # (stems) -> str, under the counts
        self.export_name = None     # () -> the exported dataset's name
        self._lib_root = None
        self._files = []            # [{"stem", "path"}]
        self._export_all = True
        self._video_lookup = None   # stem -> [Path]
        self._status = vc.validation_status(None)
        self._df = None
        self._time = None
        self._stem = None
        self._path = None
        self._nadir_idx = None
        self._loaded_nadir_idx = None
        self._pending_path = None
        self._loaders = []
        self._curve = None
        self._right_curve = None
        self._updating_right = False
        self._left_key = "pressure"
        self._right_key = "higacc_mag"
        self._win_sec = vc.WIN_SEC
        self._auto_thread = None
        self.exporter = vc.DatasetExporter(self)
        self.exporter.finished.connect(self._on_export_done)

        self._build(top, extra_buttons)
        vc.install_save_next_shortcut(self, self.sensor_list, self.save_and_next)
        self._set_loaded_enabled(False)

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, top, extra_buttons):
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        left = QWidget()
        left.setFixedWidth(LIST_W)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        if top is not None:
            lv.addWidget(top)
        # the one Sort by every sensor list shares (sensor_sort.py)
        self.sort_control = sensor_sort.SortControl()
        self.sort_control.changed.connect(lambda _how: self.refresh_list())
        lv.addWidget(self.sort_control)
        self.sensor_list = QListWidget()
        # the highlighted sensor is the loaded one - by mouse or arrow keys
        self.sensor_list.currentItemChanged.connect(self._on_current_changed)
        # what the colours mean, on hover
        vc.legend_tooltip(self.sensor_list, OK, WARN, BAD, ACCENT, TEXT)
        lv.addWidget(self.sensor_list, stretch=1)

        mark_row = QHBoxLayout()
        self.btn_mark = QPushButton("Mark bad")
        self.btn_mark.setToolTip("Mark this sensor bad (or good again) - bad "
                                 "sensors stay out of the exported dataset.")
        self.btn_mark.clicked.connect(self.toggle_bad)
        mark_row.addWidget(self.btn_mark)
        self.chk_show_bad = QCheckBox("Show bad")
        self.chk_show_bad.toggled.connect(lambda _on: self.refresh_list())
        mark_row.addWidget(self.chk_show_bad)
        lv.addLayout(mark_row)

        self.lbl_counts = QLabel("")
        lv.addWidget(self.lbl_counts)

        self.btn_save_next = QPushButton(f"Save + Next  ({vc.SAVE_NEXT_KEYS})")
        self.btn_save_next.setToolTip(
            "Save this sensor's window as reviewed (clears its flag) and go "
            f"to the next sensor in the list - {vc.SAVE_NEXT_KEYS}. The "
            "arrow keys move through the list.")
        self.btn_save_next.clicked.connect(self.save_and_next)
        lv.addWidget(self.btn_save_next)

        # Reset and Auto process all side by side
        auto_row = QHBoxLayout()
        self.btn_reset = QPushButton("Reset sensor")
        self.btn_reset.setToolTip("Reload this sensor's file without saving.")
        self.btn_reset.clicked.connect(self.reset_current)
        auto_row.addWidget(self.btn_reset, stretch=1)
        self.btn_auto_process = QPushButton("Auto process all")
        style(self.btn_auto_process, tone="ok")
        self.btn_auto_process.setToolTip(
            "Press Auto process all first, then check the sensors it "
            "flagged for review.")
        self.btn_auto_process.clicked.connect(self.auto_process_all)
        auto_row.addWidget(self.btn_auto_process, stretch=1)
        self._auto_spinner = Spinner(size=20)
        self._auto_spinner.setVisible(False)
        auto_row.addWidget(self._auto_spinner)
        lv.addLayout(auto_row)
        row.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        toolbar = QHBoxLayout()
        self.cmb_left = QComboBox()
        self.cmb_right = QComboBox()
        self.cmb_right.addItem("None", None)
        for key in CHANNEL_ORDER:
            self.cmb_left.addItem(CHANNELS[key][1], key)
            self.cmb_right.addItem(CHANNELS[key][1], key)
        self.cmb_left.setCurrentIndex(self.cmb_left.findData(self._left_key))
        self.cmb_right.setCurrentIndex(self.cmb_right.findData(self._right_key))
        self.cmb_left.currentIndexChanged.connect(self._on_axis_changed)
        self.cmb_right.currentIndexChanged.connect(self._on_axis_changed)
        toolbar.addWidget(muted_label("Left"))
        toolbar.addWidget(self.cmb_left)
        toolbar.addWidget(muted_label("Right"))
        toolbar.addWidget(self.cmb_right)
        # while a sensor's file loads (in the background)
        self._spinner = Spinner(size=18)
        self._spinner.setVisible(False)
        toolbar.addWidget(self._spinner)
        toolbar.addStretch()
        add_export_button(toolbar, self._export_data, self.parent_window,
                          file_stub="validate_signal")
        rv.addLayout(toolbar)

        self._pw = pg.PlotWidget(viewBox=NavViewBox())
        self._pw.setSizePolicy(QSizePolicy.Policy.Expanding,
                               QSizePolicy.Policy.Expanding)
        pi = self._pw.plotItem
        pi.getViewBox().setMouseMode(pg.ViewBox.RectMode)
        reserve_top_margin(pi)
        pi.setLabel("bottom", "Time (s)")
        self._vb2 = pg.ViewBox()
        pi.scene().addItem(self._vb2)
        pi.getAxis("right").linkToView(self._vb2)
        self._vb2.setXLink(pi)
        set_right_axis_active(pi, False)
        pi.vb.sigResized.connect(self._sync_vb2)
        pi.vb.sigXRangeChanged.connect(self._on_xrange_changed)
        self._region = pg.LinearRegionItem(
            movable=False, brush=pg.mkBrush(*REGION_FILL),
            pen=pg.mkPen(*REGION_EDGE))
        pi.addItem(self._region)
        self._nadir_line = pg.InfiniteLine(
            angle=90, movable=True, pen=pg.mkPen(color=NADIR, width=2),
            label="Nadir", labelOpts={"position": 0.92, "color": (180, 150, 0)})
        self._nadir_line.sigPositionChanged.connect(self._on_nadir_moved)
        pi.addItem(self._nadir_line)
        rv.addWidget(self._pw, stretch=1)

        bottom = QHBoxLayout()
        bottom.addWidget(muted_label("ROI window:"))
        self.cmb_window = QComboBox()
        self._fill_window_combo()
        self.cmb_window.currentIndexChanged.connect(self._on_win_size_changed)
        bottom.addWidget(self.cmb_window)
        self.lbl_status = QLabel("")
        style(self.lbl_status, role="muted")
        bottom.addWidget(self.lbl_status, stretch=1)
        self.btn_video = QPushButton("Open video")
        self.btn_video.setToolTip("This sensor's video, in LosslessCut.")
        self.btn_video.clicked.connect(self._open_video)
        bottom.addWidget(self.btn_video)
        for btn in extra_buttons:
            bottom.addWidget(btn)
        self.btn_save_export = QPushButton("Save and export")
        style(self.btn_save_export, tone="bad")
        self.btn_save_export.setToolTip(
            "Bind every listed sensor's saved window, with its annotations, "
            "into one dataset - written to the input data folder and the "
            "library's running dataset, and passed to Model prediction.")
        self.btn_save_export.clicked.connect(self.save_and_export)
        bottom.addWidget(self.btn_save_export)
        rv.addLayout(bottom)
        row.addWidget(right, stretch=1)

    def _set_loaded_enabled(self, enabled):
        for b in (self.btn_save_next, self.btn_reset, self.btn_mark):
            b.setEnabled(enabled)
        self._refresh_video_button()

    # ── source ───────────────────────────────────────────────────────────────
    @property
    def lib_root(self):
        return self._lib_root

    @property
    def files(self):
        """The sensors listed ([{"stem", "path"}]), bad ones included."""
        return self._files

    @property
    def current_stem(self):
        return self._stem

    @property
    def loading(self):
        """True while a sensor's file is still loading."""
        return self._pending_path is not None

    def set_source(self, lib_root, files, video_lookup=None, export_all=True):
        """The library and its sensors to list (`files`: [{"stem", "path"}]);
        `video_lookup(stem)` -> the sensor's video clips; `export_all`:
        Save and export takes every sensor with a saved window, not just
        those listed."""
        self._lib_root = lib_root
        self._files = list(files)
        self._video_lookup = video_lookup
        self._export_all = export_all
        if self._stem is not None and self._stem not in {f["stem"] for f in self._files}:
            self.clear_sensor()
        self.refresh_list()

    def set_video_lookup(self, video_lookup):
        self._video_lookup = video_lookup
        self._refresh_video_button()

    def read_index(self):
        return di.read_index(self._lib_root) if self._lib_root else None

    def validation_status(self):
        """(auto_validated, user_validated, flagged, bad) stem sets, read
        from the index now."""
        return vc.validation_status(self.read_index())

    def _write_index(self, index_df):
        vc.write_index(self._lib_root, index_df)
        self.index_changed.emit()

    # ── the list ─────────────────────────────────────────────────────────────
    def refresh_list(self):
        """Re-list from the index - in Sort by's order, coloured by state,
        bad sensors only with Show bad - keeping the loaded one selected
        (not reloaded, which would drop an unsaved nadir move)."""
        self._status = self.validation_status()
        status = self._status
        ordered = sensor_sort.sort_rows(
            self._files, needs_review=lambda stem: vc.needs_review(stem, status))
        show_bad = self.chk_show_bad.isChecked()
        self.sensor_list.blockSignals(True)
        self.sensor_list.clear()
        for f in ordered:
            stem = f["stem"]
            if stem in status[3] and not show_bad:
                continue
            # plain stem - colour alone marks the state (lookups by text)
            item = QListWidgetItem(stem)
            colour = vc.status_colour(stem, status, OK, WARN, BAD, ACCENT)
            if colour:
                item.setForeground(QColor(colour))
            self.sensor_list.addItem(item)
            if stem == self._stem:
                self.sensor_list.setCurrentItem(item)
        self.sensor_list.blockSignals(False)
        stems = [f["stem"] for f in self._files]
        text = vc.counts_text(stems, status)
        if self.counts_suffix is not None:
            text += "\n" + self.counts_suffix(stems)
        self.lbl_counts.setText(text)
        if vc.all_validated(stems, status) and stems:
            self.lbl_status.setText("All sensors validated")
        self._refresh_mark_button()

    def order(self):
        """The listed stems, top to bottom."""
        return [self.sensor_list.item(i).text()
                for i in range(self.sensor_list.count())]

    def _on_current_changed(self, current, _previous):
        if current is not None and current.text() != self._stem:
            self.load_sensor(current.text())

    def select(self, stem):
        """Highlight `stem` in the list (loading it if it isn't loaded)."""
        items = self.sensor_list.findItems(stem, Qt.MatchFlag.MatchExactly)
        if items:
            self.sensor_list.setCurrentItem(items[0])
        elif stem != self._stem:
            self.load_sensor(stem)

    # ── loading a sensor (in the background) ─────────────────────────────────
    def load_sensor(self, stem):
        match = next((f for f in self._files if f["stem"] == stem), None)
        if match is None:
            return
        path = match["path"]
        if not path.exists():
            QMessageBox.warning(self.parent_window, "File missing",
                                f"Cannot find:\n{path}")
            return
        self._pending_path = path
        self._spinner.start()
        self.status.emit(f"Loading {path.name} …", 0)
        self._set_loaded_enabled(False)
        loader = CsvLoadThread(path)
        loader.loaded.connect(self._on_loaded)
        loader.failed.connect(self._on_load_failed)
        loader.finished.connect(lambda lt=loader: self._loaders.remove(lt)
                                if lt in self._loaders else None)
        self._loaders.append(loader)
        loader.start()

    def _on_load_failed(self, path, msg):
        if path != self._pending_path:
            return
        self._pending_path = None
        self._spinner.stop()
        self.status.emit(f"Load failed: {path.name}", 5000)
        QMessageBox.warning(self.parent_window, "Load error",
                            f"Cannot load {path.name}:\n{msg}")

    def _on_loaded(self, path, df):
        if path != self._pending_path:
            return                  # superseded by a newer selection
        self._pending_path = None
        self._spinner.stop()
        if not len(df):
            self.status.emit(f"{path.name} is empty - skipping.", 5000)
            return
        self._df = df
        self._path = path
        self._stem = path.stem
        self._time, pres, _hig = vc.signals(df)
        self._nadir_idx = vc.detect_nadir_idx(self._stem, df, self._time, pres,
                                              self.read_index())
        # the nadir as loaded: Save + Next records whether it was moved
        self._loaded_nadir_idx = self._nadir_idx
        self._draw_plot()
        self._set_loaded_enabled(True)
        self._refresh_mark_button()
        self.select(self._stem)
        self.status.emit(f"Loaded: {path.name}", 3000)
        self.sensor_loaded.emit(self._stem)

    def clear_sensor(self):
        """Nothing loaded (the sensor left the list)."""
        self._df = self._time = self._stem = self._path = None
        self._nadir_idx = self._loaded_nadir_idx = None
        pi = self._pw.plotItem
        if self._curve is not None:
            pi.removeItem(self._curve)
            self._curve = None
        if self._right_curve is not None:
            self._vb2.removeItem(self._right_curve)
            self._right_curve = None
        set_right_axis_active(pi, False)
        self._set_loaded_enabled(False)

    def reset_current(self):
        if self._stem:
            self.load_sensor(self._stem)

    # ── the plot ─────────────────────────────────────────────────────────────
    def _channel(self, key):
        if key is None or self._df is None:
            return None
        col = CHANNELS.get(key, (None,))[0]
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
        self._left_key = self.cmb_left.currentData()
        self._right_key = self.cmb_right.currentData()
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
                                        pen=pg.mkPen(TRACE, width=1))
            self._curve.setDownsampling(auto=True, method="peak")
            self._curve.setClipToView(True)
        pi.setLabel("left", CHANNELS[self._left_key][1])
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
        pi.setLabel("right", CHANNELS[self._right_key][1])
        self._right_curve = pg.PlotCurveItem(pen=pg.mkPen(TRACE2, width=1))
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
        xd, yd = decimate(t[lo:hi], y[lo:hi], MAX_RIGHT_PTS)
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

    def _apply_view_limits(self):
        vb = self._pw.plotItem.getViewBox()
        if self._time is None or not len(self._time):
            vb.setLimits(xMin=None, xMax=None, yMin=None, yMax=None)
            return
        x0, x1 = float(self._time[0]), float(self._time[-1])
        xpad = (x1 - x0) * 0.02 or 1.0
        kw = dict(xMin=x0 - xpad, xMax=x1 + xpad)
        y = self._channel(self._left_key)
        if y is not None and len(y):
            y0, y1 = float(np.nanmin(y)), float(np.nanmax(y))
            ypad = (y1 - y0) * 0.05 or 1.0
            kw.update(yMin=y0 - ypad, yMax=y1 + ypad)
        vb.setLimits(**kw)

    def _export_data(self):
        """Feeds Export (plot_style.add_export_button) - None while nothing
        is loaded."""
        if self._time is None or not len(self._time):
            return None
        left_label = CHANNELS[self._left_key][1] if self._left_key else ""
        right_label = CHANNELS[self._right_key][1] if self._right_key else ""
        return build_export_data(
            self._time, left_label, self._channel(self._left_key),
            right_label, self._channel(self._right_key), self._pw, self._vb2)

    # ── the nadir and the ROI window ─────────────────────────────────────────
    def _update_region(self, t):
        self._region.setRegion((t - self._win_sec / 2, t + self._win_sec / 2))

    def _fill_window_combo(self):
        """100-1000 ms, starting at validation_core's width."""
        want = int(round(self._win_sec * 1000))
        self.cmb_window.blockSignals(True)
        self.cmb_window.clear()
        for ms in sorted(set(range(100, 1001, 100)) | {want}):
            self.cmb_window.addItem(f"{ms} ms", ms)
        self.cmb_window.setCurrentIndex(max(0, self.cmb_window.findData(want)))
        self.cmb_window.blockSignals(False)

    def _on_win_size_changed(self):
        ms = self.cmb_window.currentData()
        if ms is None:
            return
        self._win_sec = ms / 1000.0
        if self._time is not None and self._nadir_idx is not None:
            self._update_region(float(self._time[self._nadir_idx]))

    def _on_nadir_moved(self):
        """Dragging the nadir snaps it to the nearest sample and moves the
        ROI window with it; nothing is written until Save + Next."""
        if self._time is None:
            return
        idx = int(np.argmin(np.abs(self._time - self._nadir_line.value())))
        self._nadir_idx = idx
        t_snap = float(self._time[idx])
        self._nadir_line.blockSignals(True)
        self._nadir_line.setValue(t_snap)
        self._nadir_line.blockSignals(False)
        self._update_region(t_snap)

    def window_df(self):
        """The current sensor's ROI window, as Save + Next saves it."""
        start, end = vc.window_bounds(self._nadir_idx, len(self._df),
                                      self._win_sec, vc.sample_rate())
        return self._df.iloc[start:end + 1].copy()

    @property
    def win_sec(self):
        return self._win_sec

    # ── marking bad ──────────────────────────────────────────────────────────
    def _is_bad(self, stem):
        return stem in self._status[3]

    def _refresh_mark_button(self):
        self.btn_mark.setText("Mark good" if self._stem and self._is_bad(self._stem)
                              else "Mark bad")
        style(self.btn_mark, tone="ok" if self._stem and self._is_bad(self._stem)
              else "bad")

    def toggle_bad(self):
        """Mark the current sensor bad - or good again. A bad sensor stays
        validated; Save and export leaves it out."""
        if not self._stem or self._lib_root is None:
            return
        index_df = self.read_index()
        if index_df is None or "file" not in index_df.columns:
            index_df = pd.DataFrame({"file": []})
        bad = not self._is_bad(self._stem)
        mask = index_df["file"].astype(str) == self._stem
        if not mask.any():
            index_df = pd.concat([index_df, pd.DataFrame([{"file": self._stem}])],
                                 ignore_index=True)
            mask = index_df["file"].astype(str) == self._stem
        if di.BAD_SENS_COL not in index_df.columns:
            index_df[di.BAD_SENS_COL] = ""
        index_df[di.BAD_SENS_COL] = index_df[di.BAD_SENS_COL].astype(object)
        index_df.loc[mask, di.BAD_SENS_COL] = "Y" if bad else "N"
        self._write_index(index_df)
        self.refresh_list()
        self.lbl_status.setText(f"{self._stem} marked {'bad' if bad else 'good'}.")

    # ── Save + Next ──────────────────────────────────────────────────────────
    def save_and_next(self):
        """Save + Next (Ctrl+V): saves the window as reviewed by a person -
        which clears the sensor's flag - with the host's own columns
        (`save_values`), and loads the next sensor
        (validation_core.next_after_save)."""
        if (not self._stem or self._lib_root is None or self._df is None
                or not self.btn_save_next.isEnabled()):
            return                   # nothing loaded, or still loading
        stem = self._stem
        order = self.order()
        index_df = vc.save_window(
            self._lib_root, self.read_index(), stem, self._df,
            self._nadir_idx, self._win_sec, user_validated=True,
            nadir_changed=(self._loaded_nadir_idx is not None
                           and self._nadir_idx != self._loaded_nadir_idx))
        extra = self.save_values(stem) if self.save_values is not None else {}
        if extra:
            mask = index_df["file"].astype(str) == stem
            for col, value in extra.items():
                if col not in index_df.columns:
                    index_df[col] = ""
                index_df[col] = index_df[col].astype(object)
                index_df.loc[mask, col] = value
        self._write_index(index_df)
        message = f"Saved {stem}."
        self.refresh_list()
        self.lbl_status.setText(message)
        self.status.emit(message, 4000)
        target = vc.next_after_save(order, stem, self._status)
        if target is not None:
            self.select(target)
        else:
            self.lbl_status.setText(f"{stem} saved - end of the list.")
        # keep the arrow keys / Ctrl+V on the list after a button click
        self.sensor_list.setFocus()

    # ── Auto process all ─────────────────────────────────────────────────────
    def auto_process_all(self):
        """Starts Auto process all over the listed sensors in the background
        and returns the thread - or None with nothing to do."""
        if self._lib_root is None or not self._files:
            return None
        if self._auto_thread is not None and self._auto_thread.isRunning():
            return self._auto_thread
        self.btn_auto_process.setEnabled(False)
        self.btn_save_export.setEnabled(False)
        self._auto_spinner.start()
        self.lbl_status.setText("Auto-processing…")
        self._auto_thread = vc.AutoProcessThread(
            self._lib_root, self._win_sec,
            [{"stem": f["stem"], "path": f["path"]} for f in self._files],
            self.read_index())
        self._auto_thread.progress.connect(
            lambda d, t: self.lbl_status.setText(f"Auto-processing… {d}/{t}"))
        self._auto_thread.done.connect(self._on_auto_done)
        self._auto_thread.start()
        return self._auto_thread

    def _on_auto_done(self, index_df, n_done):
        self._auto_spinner.stop()
        self.btn_auto_process.setEnabled(True)
        self.btn_save_export.setEnabled(True)
        if self._lib_root is not None:
            self._write_index(index_df)
        self.refresh_list()
        stems = [f["stem"] for f in self._files]
        n_flagged = vc.status_counts(stems, self._status)["flagged"]
        msg = f"Auto-processed {n_done} sensor(s), {n_flagged} flagged for review."
        self.lbl_status.setText(msg)
        self.status.emit(msg, 5000)
        # straight into the review: the first flagged sensor, the list
        # focused for the arrow keys and Ctrl+V
        pending = [s for s in self.order() if vc.needs_review(s, self._status)]
        if pending and not vc.needs_review(self._stem or "", self._status):
            self.select(pending[0])
        self.sensor_list.setFocus()

    # ── Save and export ──────────────────────────────────────────────────────
    def save_and_export(self, confirm=True):
        """Asks first while flagged sensors are unreviewed - unless
        `confirm` is False (StrikeWorks's Next has just asked)."""
        if self._lib_root is None or self.exporter.running:
            return
        stems = [f["stem"] for f in self._files]
        if not stems:
            # (an empty selection would export the whole library)
            self.lbl_status.setText("No sensors listed to export.")
            return
        if confirm and self.parent_window.isVisible():
            outstanding = vc.outstanding_flagged(stems, self._status)
            if outstanding:
                n_flagged = vc.status_counts(stems, self._status)["flagged"]
                reply = QMessageBox.question(
                    self.parent_window, "Sensors flagged for review",
                    f"Caution, {len(outstanding)}/{n_flagged} flagged sensors "
                    "still need user-validation. Export anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No)
                if reply != QMessageBox.StandardButton.Yes:
                    return
        name = (self.export_name() if self.export_name is not None
                else None) or self._lib_root.name
        self.btn_save_export.setEnabled(False)
        self.lbl_status.setText("Building dataset…")
        self.exporter.start(self._lib_root, name,
                            selected=None if self._export_all else set(stems))

    def _on_export_done(self, df, path, message):
        self.btn_save_export.setEnabled(True)
        self.lbl_status.setText(message)
        self.status.emit(message, 6000)
        self.export_done.emit(df, path, message)

    # ── video ────────────────────────────────────────────────────────────────
    def _videos(self):
        if not self._stem or self._video_lookup is None:
            return []
        return self._video_lookup(self._stem)

    def _refresh_video_button(self):
        has = bool(self._videos())
        self.btn_video.setEnabled(has)
        self.btn_video.setToolTip(
            "This sensor's video, in LosslessCut." if has
            else "No video found for this sensor.")

    def _open_video(self):
        message = open_video(self.parent_window, self._stem, self._videos())
        if message:
            self.status.emit(message, 4000)
