# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Controller for Export animations (Validate and annotate).

Ports `Scripts/Time series video sync/video_sync.py` (pure logic lives in
`modules/video_sync.py`, GUI-free) - a synced sensor-graph overlay burned
into the high-speed video, frame by frame. Same page skeleton as Annotate
(library -> deployment -> treatment -> sensor/video browser on the left),
but:
  * the Annotations box is replaced by Text inputs - the overlay's text
    lines (pump, shaft speed, camera, sensor), typed in rather than the
    original script's hardcoded strings
  * the Notes box is replaced by Code options - the sync frame, real fps,
    graph window/zoom, and whether to draw the text overlay at all
  * the Signal container shows the plotted sensor signal until a video has
    been processed, then swaps to a play/pause video player for it
  * single sensor at a time, and there's no ROI/nadir-window saving - this
    page produces a video, not a training window

Sync point: the original script anchored on a `frames.txt`-supplied row
index into a combined dataset external to the sensor itself; here the
sensor's own processed CSV already carries its nadir time (the same
`pres_min.time.` index column Annotate and Validate read), so only the
*video frame number* the nadir appears at needs entering - that pairing
can't be automated without watching the footage.

`processed_video/` is one folder at the app root, not per-library (a
video's sync config doesn't belong to any one library's folder tree any
more than a deployed model does) - `_load_config`/`_save_config` read and
write a `<stem>_sync_config.json` there alongside the synced output, so
reopening a sensor already exported restores the frame/text/option values
that produced it rather than starting blank. "Process" renders the video
(slow - runs off the GUI thread via `_VideoSyncWorker`) and always saves
its config alongside it, so the two never drift apart; "Save" persists an
in-progress edit without paying for a render.
"""
import json
from pathlib import Path

import cv2

from PySide6.QtCore import Qt, QObject, QThread, QUrl, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDoubleSpinBox, QFileDialog,
    QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSizePolicy, QSpinBox, QSplitter, QStackedWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget

from . import deployment_index as di
from . import sensor_config, video_sync
from .library_widgets import LibrarySelector
from .ml_widgets import ACCENT, MUTED, OK, TEXT, Section, apply_section_defaults
from .page_annotate import LOSSLESSCUT_EXE
from .page_validate import (
    _CsvLoadThread, _NavViewBox, _find_col,
)
from .plot_style import reserve_top_margin, set_right_axis_active

import pyqtgraph as pg

_MAX_WINDOW_S = 15.0

pg.setConfigOptions(antialias=True, background="#21252b",
                    foreground="#c8cdd6")

_PROCESSED_VIDEO_DIR = Path(__file__).parent.parent / "processed_video"
_NADIR_T_COL = "pres_min.time."


class _VideoSyncWorker(QThread):
    """Runs `video_sync.process_video` off the GUI thread - the original
    script's frame loop does a full matplotlib render per frame, easily
    minutes of work for a real clip."""

    progress = Signal(int, int)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, video_path, df, nadir_time_s, nadir_frame, fields,
                output_path, opts, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self.df = df
        self.nadir_time_s = nadir_time_s
        self.nadir_frame = nadir_frame
        self.fields = fields
        self.output_path = output_path
        self.opts = opts
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        def progress_cb(f, total):
            if self._cancelled:
                raise InterruptedError
            self.progress.emit(f, total)
        try:
            video_sync.process_video(
                self.video_path, self.df, self.nadir_time_s,
                self.nadir_frame, self.fields, self.output_path, self.opts,
                progress_cb=progress_cb)
        except InterruptedError:
            self.failed.emit("Cancelled.")
            return
        except Exception as e:
            self.failed.emit(str(e))
            return
        self.finished_ok.emit(str(self.output_path))


class ExportAnimationsPage(QObject):
    """Binds Export animations to `ui.content_export_animations`."""

    status = Signal(str, int)

    def __init__(self, ui, window):
        super().__init__(window)
        self.ui = ui
        self.window = window

        self._sensor_rows = []

        self._df = None
        self._time = None
        self._cur_path = None
        self._cur_stem = ""
        self._nadir_idx = None
        self._curve = None
        self._right_curve = None
        self._loaders = []
        self._pending_path = None
        self._video_matches = []
        self._video_frames = None
        self._video_duration_s = None
        self._worker = None

        self._build(ui.content_export_animations)
        self._connect()
        self._on_lib_changed()
        self._populate_sensor_table()
        self._set_loaded_enabled(False)

    # ── library selector (shared widget - see library_widgets.py) ────────────
    @property
    def _lib_root(self):
        return self.lib_selector.lib_root

    def _on_lib_changed(self):
        if self.lib_selector.lib_root:
            self.status.emit(f"Library: {self.lib_selector.lib_root.name}", 4000)

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, frame):
        root = QHBoxLayout(frame)
        root.setContentsMargins(4, 6, 4, 6)
        root.setSpacing(0)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        root.addWidget(split)
        split.addWidget(self._build_browser())

        detail = QWidget()
        dv = QVBoxLayout(detail)
        dv.setContentsMargins(5, 0, 0, 0)
        dv.setSpacing(8)
        self._build_signal_side(dv)

        lower = QSplitter(Qt.Orientation.Horizontal)
        lower.setChildrenCollapsible(False)
        lower.addWidget(self._build_text_side())
        lower.addWidget(self._build_options_side())
        lower.setSizes([1, 1])
        dv.addWidget(lower, stretch=1)

        split.addWidget(detail)
        split.setSizes([1, 3])
        apply_section_defaults(frame)

    def _build_browser(self):
        left = QWidget()
        left.setMinimumWidth(360)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 5, 0)
        lv.setSpacing(8)

        self.lib_selector = LibrarySelector()
        lv.addWidget(self.lib_selector)

        self.tbl_sensors = QTableWidget(0, 3)
        self.tbl_sensors.setHorizontalHeaderLabels(["Sensor", "Video", "Synced"])
        self.tbl_sensors.verticalHeader().setVisible(False)
        self.tbl_sensors.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_sensors.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_sensors.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl_sensors.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive)
        lv.addWidget(self.tbl_sensors, stretch=1)

        self.lbl_loading = QLabel("")
        self.lbl_loading.setStyleSheet(f"color:{MUTED};")
        lv.addWidget(self.lbl_loading)
        return left

    def _build_signal_side(self, v):
        grp = Section("Signal")
        sv = QVBoxLayout(grp)
        sv.setSpacing(6)

        self.lbl_video_info = QLabel("No matching video.")
        self.lbl_video_info.setStyleSheet(f"color:{TEXT};font-weight:bold;")
        sv.addWidget(self.lbl_video_info)

        self.stack_signal = QStackedWidget()

        self._pw = pg.PlotWidget(viewBox=_NavViewBox())
        pi = self._pw.plotItem
        pi.getViewBox().setMouseMode(pg.ViewBox.RectMode)
        pi.setLabel("bottom", "Time (s)")
        pi.setLabel("left", "Pressure (kPa)")
        reserve_top_margin(pi)
        self._vb2 = pg.ViewBox()
        pi.scene().addItem(self._vb2)
        pi.getAxis("right").linkToView(self._vb2)
        self._vb2.setXLink(pi)
        set_right_axis_active(pi, False)
        pi.vb.sigResized.connect(self._sync_vb2)

        # shades the sensor-time span the matched video is assumed to
        # cover (video duration, centred on the nadir - the video's own
        # start isn't known yet, that's what this page helps figure out),
        # so scrubbing the video in LosslessCut alongside this plot makes
        # frame-to-data-row alignment easier to eyeball
        self._video_region = pg.LinearRegionItem(
            movable=False, brush=pg.mkBrush(120, 170, 255, 35),
            pen=pg.mkPen(120, 170, 255, 90))
        self._video_region.setVisible(False)
        pi.addItem(self._video_region)

        self.stack_signal.addWidget(self._pw)

        video_holder = QWidget()
        vh = QVBoxLayout(video_holder)
        vh.setContentsMargins(0, 0, 0, 0)
        self._video_widget = QVideoWidget()
        self._player = QMediaPlayer()
        self._player.setVideoOutput(self._video_widget)
        vh.addWidget(self._video_widget, stretch=1)
        play_row = QHBoxLayout()
        self.btn_play = QPushButton("Play")
        self.btn_play.setEnabled(False)
        play_row.addWidget(self.btn_play)
        play_row.addStretch()
        vh.addLayout(play_row)
        self.stack_signal.addWidget(video_holder)

        sv.addWidget(self.stack_signal, stretch=1)

        act = QHBoxLayout()
        self.btn_process = QPushButton("Process")
        self.btn_process.setStyleSheet(
            f"QPushButton{{background-color:{ACCENT};color:#ffffff;"
            "border-radius:5px;padding:4px 14px;font-weight:bold;}"
            "QPushButton:disabled{background-color:#3a4150;color:#8a95aa;}")
        self.btn_save = QPushButton("Save")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setVisible(False)
        act.addWidget(self.btn_process)
        act.addWidget(self.btn_save)
        act.addWidget(self.btn_cancel)
        act.addStretch()
        sv.addLayout(act)

        self.lbl_progress = QLabel("")
        self.lbl_progress.setStyleSheet(f"color:{MUTED};")
        self.lbl_progress.setWordWrap(True)
        sv.addWidget(self.lbl_progress)
        v.addWidget(grp, stretch=1)

    def _build_text_side(self):
        grp = Section("Text inputs")
        gv = QGridLayout(grp)
        gv.setVerticalSpacing(6)
        gv.setColumnStretch(1, 1)
        self.ed_pump = QLineEdit()
        self.ed_shaft_speed = QLineEdit()
        self.ed_camera = QLineEdit("Chronos HD 2.1 (1000 fps)")
        self.ed_sensor = QLineEdit("RAPID - pressure (100 Hz), acceleration (2000 Hz)")
        for row, (label, edit) in enumerate([
                ("Pump", self.ed_pump),
                ("Shaft speed", self.ed_shaft_speed),
                ("Video camera", self.ed_camera),
                ("Passive sensor", self.ed_sensor)]):
            gv.addWidget(self._muted(label), row, 0)
            gv.addWidget(edit, row, 1)
        return grp

    def _build_options_side(self):
        grp = Section("Code options")
        gv = QGridLayout(grp)
        gv.setVerticalSpacing(6)
        gv.setColumnStretch(1, 1)

        self.spin_nadir_frame = QSpinBox()
        self.spin_nadir_frame.setRange(0, 1_000_000)
        self.spin_real_fps = QSpinBox()
        self.spin_real_fps.setRange(1, 20000)
        self.spin_real_fps.setValue(1000)
        self.spin_window = QDoubleSpinBox()
        self.spin_window.setRange(0.05, 5.0)
        self.spin_window.setSingleStep(0.05)
        self.spin_window.setValue(0.3)
        self.spin_zoom = QDoubleSpinBox()
        self.spin_zoom.setRange(0.1, 10.0)
        self.spin_zoom.setSingleStep(0.1)
        self.spin_zoom.setValue(1.0)
        self.spin_video_nudge = QSpinBox()
        self.spin_video_nudge.setRange(-2000, 2000)
        self.spin_video_nudge.setToolTip(
            "Shifts the video content vertically (pixels) before the graph "
            "strip is stacked underneath it - use if the crop clips the "
            "footage or leaves a gap.")
        self.chk_labels = QCheckBox("Add labels")
        self.chk_labels.setChecked(True)

        for row, (label, widget) in enumerate([
                ("Sync frame (video)", self.spin_nadir_frame),
                ("Real fps (camera)", self.spin_real_fps),
                ("Graph window (s)", self.spin_window),
                ("Zoom", self.spin_zoom),
                ("Frame nudge (px)", self.spin_video_nudge)]):
            gv.addWidget(self._muted(label), row, 0)
            gv.addWidget(widget, row, 1)
        gv.addWidget(self.chk_labels, 5, 0, 1, 2)

        logo_row = QHBoxLayout()
        self.lbl_logo_path = QLabel("No overlay image")
        self.lbl_logo_path.setStyleSheet(f"color:{MUTED};")
        self.lbl_logo_path.setWordWrap(True)
        logo_row.addWidget(self.lbl_logo_path, stretch=1)
        self.btn_choose_logo = QPushButton("Browse…")
        logo_row.addWidget(self.btn_choose_logo)
        self.btn_clear_logo = QPushButton("Clear")
        logo_row.addWidget(self.btn_clear_logo)
        gv.addLayout(logo_row, 6, 0, 1, 2)

        gv.addWidget(self._muted("Overlay opacity"), 7, 0)
        self.spin_logo_opacity = QDoubleSpinBox()
        self.spin_logo_opacity.setRange(0.0, 1.0)
        self.spin_logo_opacity.setSingleStep(0.1)
        self.spin_logo_opacity.setValue(1.0)
        gv.addWidget(self.spin_logo_opacity, 7, 1)

        self._logo_path = None
        return grp

    @staticmethod
    def _muted(text):
        lab = QLabel(text)
        lab.setStyleSheet(f"color:{MUTED};")
        return lab

    def _connect(self):
        self.lib_selector.library_changed.connect(self._on_lib_changed)
        self.lib_selector.filters_changed.connect(self._populate_sensor_table)
        self.tbl_sensors.itemSelectionChanged.connect(self._on_row_selected)
        self.btn_process.clicked.connect(self._process)
        self.btn_save.clicked.connect(self._save_config)
        self.btn_cancel.clicked.connect(self._cancel_process)
        self.btn_play.clicked.connect(self._toggle_play)
        self._player.playbackStateChanged.connect(self._on_playback_changed)
        self.btn_choose_logo.clicked.connect(self._choose_logo)
        self.btn_clear_logo.clicked.connect(self._clear_logo)

    def _set_loaded_enabled(self, enabled):
        for b in (self.btn_process, self.btn_save):
            b.setEnabled(enabled)
        # apply_section_defaults() force-shows every widget in an open
        # Section after _build() runs, undoing the constructor's
        # setVisible(False) - reassert it here, which also covers loading
        # a new sensor while a previous one's Cancel button was showing
        self.btn_cancel.setVisible(False)

    # ── sensor table ─────────────────────────────────────────────────────────
    def _populate_sensor_table(self):
        self.tbl_sensors.setRowCount(0)
        self._sensor_rows = []
        if self._lib_root is None:
            return

        rows = []
        for row in self.lib_selector.list_sensor_csvs():
            matches = self.lib_selector.video_matches_for(row["stem"])
            rows.append({
                **row,
                "video": "; ".join(m.name for m in matches) if matches else "—",
                "synced": _synced_path_for(row["stem"]).exists(),
            })
        self._sensor_rows = rows

        self.tbl_sensors.setRowCount(len(rows))
        for r, row in enumerate(rows):
            sensor_item = QTableWidgetItem(row["stem"])
            sensor_item.setData(Qt.ItemDataRole.UserRole, row["path"])
            self.tbl_sensors.setItem(r, 0, sensor_item)
            self.tbl_sensors.setItem(r, 1, QTableWidgetItem(row["video"]))
            synced_item = QTableWidgetItem("Yes" if row["synced"] else "—")
            if row["synced"]:
                synced_item.setForeground(QColor(OK))
            self.tbl_sensors.setItem(r, 2, synced_item)
        self.tbl_sensors.resizeColumnsToContents()

    def _on_row_selected(self):
        items = self.tbl_sensors.selectedItems()
        if not items:
            return
        path = self.tbl_sensors.item(items[0].row(), 0).data(
            Qt.ItemDataRole.UserRole)
        if path is not None:
            self._load_sensor(path)

    # ── sensor loading ───────────────────────────────────────────────────────
    def _load_sensor(self, path):
        if not path.exists():
            QMessageBox.warning(self.window, "File missing", f"Cannot find:\n{path}")
            return
        self.stack_signal.setCurrentIndex(0)
        self._player.stop()
        self._pending_path = path
        self.lbl_loading.setText(f"Loading {path.name} …")
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

    def _on_csv_failed(self, path, msg):
        if path != self._pending_path:
            return
        self.lbl_loading.setText("")
        QMessageBox.warning(self.window, "Load error", f"Cannot load {path.name}:\n{msg}")

    def _on_csv_loaded(self, path, df):
        if path != self._pending_path:
            return
        self.lbl_loading.setText("")
        if len(df) == 0:
            self.status.emit(f"{path.name} is empty - skipping.", 5000)
            return
        self._apply_loaded_df(path, df)

    def _apply_loaded_df(self, path, df):
        time_col = _find_col(df, ["time_s", "time"], keyword="time")
        self._df = df
        self._time = (df[time_col].to_numpy(dtype=float) if time_col
                      else None)
        self._cur_path = path
        self._cur_stem = path.stem
        self._video_matches = self.lib_selector.video_matches_for(self._cur_stem)

        self._update_video_info()
        self._draw_plot()
        self._load_config()
        self._set_loaded_enabled(True)
        self.status.emit(f"Loaded: {path.name}", 3000)

        synced = _synced_path_for(self._cur_stem)
        if synced.exists():
            self._show_video(synced)

    def _video_frame_count_and_duration(self):
        """(frames, seconds) for the current sensor's matched video, from
        its own metadata - no frames decoded. (None, None) if there's no
        video, or (frames, None) if the container doesn't report an fps."""
        if not self._video_matches:
            return None, None
        try:
            cap = cv2.VideoCapture(str(self._video_matches[0]))
            frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS) or 0
            cap.release()
        except Exception:
            return None, None
        return frames, (frames / fps if fps > 0 else None)

    def _update_video_info(self):
        frames, duration = self._video_frame_count_and_duration()
        self._video_frames = frames
        self._video_duration_s = duration
        if frames is None:
            self.lbl_video_info.setText("No matching video.")
        elif duration is None:
            self.lbl_video_info.setText(
                f"Video: {frames} frames (frame rate unknown)")
        else:
            self.lbl_video_info.setText(
                f"Video: {frames} frames, {duration:.4f} s "
                f"({frames / duration:.1f} fps)")

    def _draw_plot(self):
        pi = self._pw.plotItem
        if self._curve is not None:
            pi.removeItem(self._curve)
            self._curve = None
        if self._time is None or "pressure_kpa" not in self._df.columns:
            self._video_region.setVisible(False)
            return
        y = self._df["pressure_kpa"].to_numpy(dtype=float)
        self._curve = self._pw.plot(self._time, y, pen=pg.mkPen("#dddddd", width=1))
        self._curve.setDownsampling(auto=True, method="peak")
        self._curve.setClipToView(True)
        pi.enableAutoRange("y", True)

        nadir_t = self._nadir_time_s()
        duration = getattr(self, "_video_duration_s", None)
        if nadir_t is None:
            self._video_region.setVisible(False)
            pi.enableAutoRange("x", True)
            return

        # default view: nadir-centred, sized to the matched video's length
        # (most videos run 6-10s) but never more than _MAX_WINDOW_S, so a
        # long recording's full range never gets crammed into one crop -
        # the shaded region still shows the video's *true* span even past
        # that cap, since it - not the view - is the thing being aligned
        window = min(duration, _MAX_WINDOW_S) if duration else _MAX_WINDOW_S
        pi.setXRange(nadir_t - window / 2, nadir_t + window / 2, padding=0)
        if duration:
            self._video_region.setRegion(
                [nadir_t - duration / 2, nadir_t + duration / 2])
            self._video_region.setVisible(True)
        else:
            self._video_region.setVisible(False)

    def _sync_vb2(self):
        pi = self._pw.plotItem
        self._vb2.setGeometry(pi.vb.sceneBoundingRect())
        self._vb2.linkedViewChanged(pi.vb, self._vb2.XAxis)

    # ── config (Text inputs + Code options) persistence ─────────────────────
    def _config_values(self):
        return {
            "pump": self.ed_pump.text().strip(),
            "shaft_speed": self.ed_shaft_speed.text().strip(),
            "camera": self.ed_camera.text().strip(),
            "sensor": self.ed_sensor.text().strip(),
            "nadir_frame": self.spin_nadir_frame.value(),
            "real_fps": self.spin_real_fps.value(),
            "graph_window_s": self.spin_window.value(),
            "zoom": self.spin_zoom.value(),
            "video_nudge_px": self.spin_video_nudge.value(),
            "add_labels": self.chk_labels.isChecked(),
            "logo_path": self._logo_path,
            "logo_opacity": self.spin_logo_opacity.value(),
        }

    @staticmethod
    def _pump_default_from_row(row):
        """Pump/turbine model + type, straight from the index
        (`deployment_index.DEPLOYMENT_FIELDS`) - same source Setup and
        deploy's Create and edit deployment page writes."""
        if row is None:
            return ""
        blank = {"", "na", "nan", "none"}
        model = str(row.get("pump_turbine", "") or "").strip()
        kind = str(row.get("type", "") or "").strip()
        model = "" if model.lower() in blank else model
        kind = "" if kind.lower() in blank else kind
        if model and kind:
            return f"{model} ({kind})"
        return model or kind

    @staticmethod
    def _sensor_default():
        cfg = sensor_config.active()
        return f"{cfg.name} ({cfg.output_rate_hz:g} Hz)"

    def _load_config(self):
        index_df = di.read_index(self._lib_root) if self._lib_root else None
        row = None
        if index_df is not None and "file" in index_df.columns:
            match = index_df[index_df["file"] == self._cur_stem]
            if not match.empty:
                row = match.iloc[0]
        treatment = str(row.get("treatment", "") or "") if row is not None else ""

        cfg = _read_json(_config_path_for(self._cur_stem)) or {}
        # index-sourced defaults are only used when nothing was saved
        # before - text inputs stay editable either way
        self.ed_pump.setText(cfg.get("pump") or self._pump_default_from_row(row))
        self.ed_shaft_speed.setText(cfg.get("shaft_speed") or treatment)
        self.ed_camera.setText(cfg.get("camera", self.ed_camera.text()))
        self.ed_sensor.setText(cfg.get("sensor") or self._sensor_default())
        self.spin_nadir_frame.setValue(int(cfg.get("nadir_frame", 0)))
        self.spin_real_fps.setValue(int(cfg.get("real_fps", 1000)))
        self.spin_window.setValue(float(cfg.get("graph_window_s", 0.3)))
        self.spin_zoom.setValue(float(cfg.get("zoom", 1.0)))
        self.spin_video_nudge.setValue(int(cfg.get("video_nudge_px", 0)))
        self.chk_labels.setChecked(bool(cfg.get("add_labels", True)))
        self._set_logo_path(cfg.get("logo_path"))
        self.spin_logo_opacity.setValue(float(cfg.get("logo_opacity", 1.0)))

    def _save_config(self):
        if not self._cur_stem:
            return
        path = _config_path_for(self._cur_stem)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._config_values(), indent=2))
        self.status.emit(f"Sync configuration saved for {self._cur_stem}.", 4000)

    # ── overlay image ────────────────────────────────────────────────────────
    def _set_logo_path(self, path):
        self._logo_path = path or None
        self.lbl_logo_path.setText(Path(path).name if path else "No overlay image")

    def _choose_logo(self):
        path, _ = QFileDialog.getOpenFileName(
            self.window, "Choose an overlay image", "",
            "Images (*.png *.PNG)")
        if path:
            self._set_logo_path(path)

    def _clear_logo(self):
        self._set_logo_path(None)

    # ── nadir time (from the sensor's own processed CSV) ────────────────────
    def _nadir_time_s(self):
        if self._df is None or "pressure_kpa" not in self._df.columns:
            return None
        index_df = di.read_index(self._lib_root) if self._lib_root else None
        if index_df is not None and "file" in index_df.columns:
            match = index_df[index_df["file"] == self._cur_stem]
            if not match.empty and _NADIR_T_COL in match.columns:
                val = match.iloc[0].get(_NADIR_T_COL)
                if val == val and val not in (None, ""):
                    return float(val)
        pres = self._df["pressure_kpa"].to_numpy(dtype=float)
        if self._time is None or not len(pres):
            return None
        return float(self._time[int(pres.argmin())])

    # ── process ──────────────────────────────────────────────────────────────
    def _process(self):
        if self._df is None or self._cur_stem == "":
            return
        if not self._video_matches:
            QMessageBox.warning(self.window, "No video",
                                "No matching video for this sensor.")
            return
        video_path = self._video_matches[0]
        nadir_time_s = self._nadir_time_s()
        if nadir_time_s is None:
            QMessageBox.warning(self.window, "No nadir",
                                "Couldn't determine this sensor's nadir time.")
            return

        self._save_config()
        cfg = self._config_values()
        opts = video_sync.SyncOptions(
            real_fps=cfg["real_fps"], graph_window_s=cfg["graph_window_s"],
            zoom=cfg["zoom"], add_labels=cfg["add_labels"],
            video_nudge_px=cfg["video_nudge_px"], logo_path=cfg["logo_path"],
            logo_opacity=cfg["logo_opacity"])
        output_path = _synced_path_for(self._cur_stem)

        self.btn_process.setEnabled(False)
        self.btn_cancel.setVisible(True)
        self.lbl_progress.setText("Processing… 0%")
        self._worker = _VideoSyncWorker(
            video_path, self._df, nadir_time_s, cfg["nadir_frame"], cfg,
            output_path, opts)
        self._worker.progress.connect(self._on_process_progress)
        self._worker.finished_ok.connect(self._on_process_done)
        self._worker.failed.connect(self._on_process_failed)
        self._worker.start()

    def _cancel_process(self):
        if self._worker is not None:
            self._worker.cancel()
            self.btn_cancel.setEnabled(False)

    def _on_process_progress(self, frame, total):
        pct = int(frame / total * 100) if total else 0
        self.lbl_progress.setText(f"Processing… {pct}% ({frame}/{total})")

    def _reset_process_buttons(self):
        self.btn_process.setEnabled(True)
        self.btn_cancel.setVisible(False)
        self.btn_cancel.setEnabled(True)
        self._worker = None

    def _on_process_done(self, output_path):
        self._reset_process_buttons()
        self.lbl_progress.setText(f"Done: {output_path}")
        self.status.emit(f"Synced video saved to {output_path}", 6000)
        self._populate_sensor_table()
        self._show_video(Path(output_path))

    def _on_process_failed(self, msg):
        self._reset_process_buttons()
        self.lbl_progress.setText(f"Failed: {msg}")
        if msg != "Cancelled.":
            QMessageBox.critical(self.window, "Processing failed", msg)

    # ── video playback ───────────────────────────────────────────────────────
    def _show_video(self, path):
        self.stack_signal.setCurrentIndex(1)
        self._player.setSource(QUrl.fromLocalFile(str(path)))
        self.btn_play.setEnabled(True)
        self.btn_play.setText("Play")

    def _toggle_play(self):
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_playback_changed(self, state):
        self.btn_play.setText(
            "Pause" if state == QMediaPlayer.PlaybackState.PlayingState
            else "Play")


def _read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return None


def _config_path_for(stem):
    return _PROCESSED_VIDEO_DIR / f"{stem}_sync_config.json"


def _synced_path_for(stem):
    return _PROCESSED_VIDEO_DIR / f"{stem}_synced.mp4"
