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
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from PySide6.QtCore import Qt, QObject, QThread, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog,
    QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox,
    QPushButton, QScrollArea, QSizePolicy, QSlider, QSpinBox, QSplitter,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import deployment_index as di
from . import sensor_config, video_sync
from .library_widgets import LibrarySelector
from .session_state import OUTPUT_DIR_NAME
from .ml_widgets import ACCENT, MUTED, TEXT, Section, apply_section_defaults
from .page_annotate import LOSSLESSCUT_EXE
from .page_validate import (
    _CsvLoadThread, _NavViewBox, _find_col,
)
from .plot_style import reserve_top_margin, set_right_axis_active

import pyqtgraph as pg

_MAX_WINDOW_S = 30.0

pg.setConfigOptions(antialias=True, background="#21252b",
                    foreground="#c8cdd6")

_PROCESSED_VIDEO_DIR = Path(__file__).parent.parent / "processed_video"
_NADIR_T_COL = "pres_min.time."
_DEFAULT_GRAPH_WINDOW_S = 0.3
_CHANNEL_COLORS = ["black", "red", "blue", "green", "orange", "purple",
                   "brown", "teal"]


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

    def __init__(self, ui, window, session_state=None):
        super().__init__(window)
        self.ui = ui
        self.window = window
        self.session_state = session_state

        self._sensor_rows = []
        self._index_df = None

        self._df = None
        self._time = None
        self._cur_path = None
        self._cur_stem = ""
        self._nadir_idx = None
        self._nadir_override_t = None
        self._curve = None
        self._right_curve = None
        self._loaders = []
        self._pending_path = None
        self._video_matches = []
        self._video_frames = None
        self._video_duration_s = None
        self._worker = None

        # frame scrubber (Video preview row) - cv2-backed, not QMediaPlayer:
        # the whole point of this page is picking the exact video frame the
        # nadir occurs at, and a time-based player seeks to the nearest
        # keyframe on a compressed container rather than the exact frame
        self._scrub_cap = None
        self._scrub_path = None
        self._scrub_frame_count = 0
        self._scrub_fps = None
        self._scrub_timer = QTimer(self)
        self._scrub_timer.timeout.connect(self._advance_scrub_frame)

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
        root = self.lib_selector.lib_root
        self._index_df = di.read_index(root) if root else None
        if root:
            self.status.emit(f"Library: {root.name}", 4000)

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, frame):
        root = QHBoxLayout(frame)
        root.setContentsMargins(4, 6, 4, 6)
        root.setSpacing(0)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        root.addWidget(split)
        split.addWidget(self._build_browser())
        split.addWidget(self._build_detail())
        split.setSizes([1, 3])
        apply_section_defaults(frame)

    def _build_browser(self):
        """Left column: the sensor picker on top, height-matched (via the
        splitter's default sizes) to the Signal box opposite it, and the
        merged Text/Code sync inputs box in the space freed up below -
        both user-resizable against each other, not fixed."""
        left = QWidget()
        left.setMinimumWidth(360)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 5, 0)
        lv.setSpacing(0)

        left_split = QSplitter(Qt.Orientation.Vertical)
        left_split.setChildrenCollapsible(False)

        top = QWidget()
        tv = QVBoxLayout(top)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.setSpacing(8)
        self.lib_selector = LibrarySelector(sensor_list=True,
                                            list_columns=["Video", "Synced"],
                                            session_state=self.session_state)
        tv.addWidget(self.lib_selector, stretch=1)
        self.tbl_sensors = self.lib_selector.tbl_sensors
        self.lbl_loading = QLabel("")
        self.lbl_loading.setStyleSheet(f"color:{MUTED};")
        tv.addWidget(self.lbl_loading)
        left_split.addWidget(top)

        # scrollable rather than squeezed by the splitter - the sync
        # inputs box (Text/Code options/Graph channels) has grown past
        # what fits comfortably in a fixed pane; the sensor picker above
        # doesn't need this, its own table already scrolls
        sync_scroll = QScrollArea()
        sync_scroll.setWidgetResizable(True)
        sync_scroll.setStyleSheet(
            "QScrollArea{border:none;background:transparent;}")
        sync_scroll.setWidget(self._build_sync_inputs())
        left_split.addWidget(sync_scroll)
        left_split.setSizes([2, 3])
        lv.addWidget(left_split, stretch=1)
        return left

    def _build_detail(self):
        """Right column: Signal (the sensor plot) and Video preview (the
        frame scrubber) as two stacked, independently resizable rows -
        both visible together, since matching a nadir point to a video
        frame means looking at both at once, not switching between them.
        The whole column is wrapped in a QScrollArea so a short window
        scrolls it instead of squeezing both rows down further."""
        outer = QWidget()
        outer_v = QVBoxLayout(outer)
        outer_v.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        outer_v.addWidget(scroll)

        detail = QWidget()
        detail.setStyleSheet("background:transparent;")
        scroll.setWidget(detail)
        dv = QVBoxLayout(detail)
        dv.setContentsMargins(5, 0, 0, 0)
        dv.setSpacing(8)

        right_split = QSplitter(Qt.Orientation.Vertical)
        right_split.setChildrenCollapsible(False)
        right_split.addWidget(self._build_signal_side())
        right_split.addWidget(self._build_video_side())
        right_split.setSizes([1, 1])
        right_split.setMinimumHeight(500)
        dv.addWidget(right_split, stretch=1)

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
        dv.addLayout(act)

        self.lbl_progress = QLabel("")
        self.lbl_progress.setStyleSheet(f"color:{MUTED};")
        self.lbl_progress.setWordWrap(True)
        dv.addWidget(self.lbl_progress)
        return outer

    def _build_signal_side(self):
        grp = Section("Signal")
        sv = QVBoxLayout(grp)
        sv.setSpacing(6)

        self.lbl_video_info = QLabel("No matching video.")
        self.lbl_video_info.setStyleSheet(f"color:{TEXT};font-weight:bold;")
        sv.addWidget(self.lbl_video_info)

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
        # cover (video duration, centred on the nadir), so the Video
        # preview row's current frame can be eyeballed against this plot
        self._video_region = pg.LinearRegionItem(
            movable=False, brush=pg.mkBrush(120, 170, 255, 35),
            pen=pg.mkPen(120, 170, 255, 90))
        self._video_region.setVisible(False)
        pi.addItem(self._video_region)

        # nadir line - yellow, draggable, snaps to the nearest sample -
        # same interaction as Validate's nadir tool (page_validate.py).
        # Starts at the sensor's own recorded nadir time; dragging it
        # overrides that for this page's video sync only, persisted in
        # this sensor's own sync config rather than the shared index -
        # Validate remains the place that edits the index itself
        self._nadir_line = pg.InfiniteLine(
            angle=90, movable=True,
            pen=pg.mkPen(color=(255, 220, 0), width=3),
            label="Nadir",
            labelOpts={"position": 0.92, "color": (180, 150, 0)})
        self._nadir_line.sigPositionChanged.connect(self._on_nadir_line_moved)
        pi.addItem(self._nadir_line)

        sv.addWidget(self._pw, stretch=1)

        reset_row = QHBoxLayout()
        reset_row.addStretch()
        self.btn_reset_nadir = QPushButton("Reset to detected nadir")
        self.btn_reset_nadir.clicked.connect(self._reset_nadir_override)
        reset_row.addWidget(self.btn_reset_nadir)
        sv.addLayout(reset_row)
        return grp

    def _build_video_side(self):
        """Frame-exact scrubber (cv2, not QMediaPlayer - see __init__'s
        comment) for the sensor's task: scroll to the frame where the
        nadir/strike visibly occurs, then "Use this frame as sync frame"
        copies it into Sync frame (video). Also hosts "Generate preview
        frame", which composites one frame exactly as the export would."""
        grp = Section("Video preview")
        gv = QVBoxLayout(grp)
        gv.setSpacing(6)

        self.lbl_scrub_frame = QLabel("No video to preview.")
        self.lbl_scrub_frame.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_scrub_frame.setStyleSheet(
            f"color:{MUTED};background-color:#15181d;border-radius:5px;")
        self.lbl_scrub_frame.setMinimumHeight(160)
        self.lbl_scrub_frame.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        gv.addWidget(self.lbl_scrub_frame, stretch=1)

        self.lbl_scrub_info = QLabel("")
        self.lbl_scrub_info.setStyleSheet(f"color:{MUTED};")
        gv.addWidget(self.lbl_scrub_info)

        scrub_row = QHBoxLayout()
        self.btn_scrub_play = QPushButton("Play")
        self.btn_scrub_play.setEnabled(False)
        scrub_row.addWidget(self.btn_scrub_play)
        self.slider_scrub = QSlider(Qt.Orientation.Horizontal)
        self.slider_scrub.setEnabled(False)
        scrub_row.addWidget(self.slider_scrub, stretch=1)
        gv.addLayout(scrub_row)

        action_row = QHBoxLayout()
        self.btn_use_as_sync = QPushButton("Use this frame as sync frame")
        self.btn_use_as_sync.setEnabled(False)
        action_row.addWidget(self.btn_use_as_sync)
        action_row.addStretch()
        self.btn_preview_frame = QPushButton("Generate preview frame")
        action_row.addWidget(self.btn_preview_frame)
        gv.addLayout(action_row)
        return grp

    def _build_sync_inputs(self):
        """Text inputs (overlay text) and Code options (sync/render
        settings), merged into one box in the space the height-capped
        sensor picker frees up above it - previously two separate boxes
        side by side."""
        grp = Section("Sensor sync inputs")
        gv = QVBoxLayout(grp)
        gv.setSpacing(10)

        gv.addWidget(self._muted_header("Text (overlay)"))
        text_grid = QGridLayout()
        text_grid.setVerticalSpacing(6)
        text_grid.setColumnStretch(1, 1)
        self.ed_pump = QLineEdit()
        self.ed_shaft_speed = QLineEdit()
        self.ed_camera = QLineEdit("Chronos HD 2.1 (1000 fps)")
        self.ed_sensor = QLineEdit("RAPID - pressure (100 Hz), acceleration (2000 Hz)")
        for row, (label, edit) in enumerate([
                ("Pump", self.ed_pump),
                ("Shaft speed", self.ed_shaft_speed),
                ("Video camera", self.ed_camera),
                ("Passive sensor", self.ed_sensor)]):
            text_grid.addWidget(self._muted(label), row, 0)
            text_grid.addWidget(edit, row, 1)
        gv.addLayout(text_grid)

        gv.addWidget(self._muted_header("Code options"))
        opt_grid = QGridLayout()
        opt_grid.setVerticalSpacing(6)
        opt_grid.setColumnStretch(1, 1)

        self.spin_nadir_frame = QSpinBox()
        self.spin_nadir_frame.setRange(0, 1_000_000)
        self.spin_real_fps = QSpinBox()
        self.spin_real_fps.setRange(1, 20000)
        self.spin_real_fps.setValue(1000)
        self.spin_window = QDoubleSpinBox()
        self.spin_window.setRange(0.05, 60.0)
        self.spin_window.setSingleStep(0.05)
        self.spin_window.setValue(0.3)
        self.spin_window.setToolTip(
            "Half-width of the rolling graph strip burned into the video "
            "(total span shown per frame is double this, divided by "
            "Zoom) - how much signal is visible around the current-time "
            "line at once. Smaller = more zoomed in, faster-looking "
            "scroll; larger = more context, slower-looking scroll.")
        self.spin_zoom = QDoubleSpinBox()
        self.spin_zoom.setRange(0.1, 10.0)
        self.spin_zoom.setSingleStep(0.1)
        self.spin_zoom.setValue(1.0)
        self.spin_zoom.setToolTip(
            "Stretches the graph strip's time axis: above 1 zooms in "
            "(narrower window, faster-looking scroll), below 1 zooms out "
            "(wider window, more context). Divides Graph window (s).")
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
            opt_grid.addWidget(self._muted(label), row, 0)
            opt_grid.addWidget(widget, row, 1)
        opt_grid.addWidget(self.chk_labels, 5, 0, 1, 2)

        logo_row = QHBoxLayout()
        self.lbl_logo_path = QLabel("No overlay image")
        self.lbl_logo_path.setStyleSheet(f"color:{MUTED};")
        self.lbl_logo_path.setWordWrap(True)
        logo_row.addWidget(self.lbl_logo_path, stretch=1)
        self.btn_choose_logo = QPushButton("Browse…")
        logo_row.addWidget(self.btn_choose_logo)
        self.btn_clear_logo = QPushButton("Clear")
        logo_row.addWidget(self.btn_clear_logo)
        opt_grid.addLayout(logo_row, 6, 0, 1, 2)

        opt_grid.addWidget(self._muted("Overlay opacity"), 7, 0)
        self.spin_logo_opacity = QDoubleSpinBox()
        self.spin_logo_opacity.setRange(0.0, 1.0)
        self.spin_logo_opacity.setSingleStep(0.1)
        self.spin_logo_opacity.setValue(1.0)
        opt_grid.addWidget(self.spin_logo_opacity, 7, 1)
        gv.addLayout(opt_grid)

        self._logo_path = None
        self._build_channels_box(gv)
        return grp

    def _build_channels_box(self, gv):
        """Configurable rolling-graph panels (up to `video_sync.
        MAX_CHANNELS`) - which signal each one plots, its label and
        colour - plus how they're laid out and whether there's a video
        underneath them at all. Was hardcoded to exactly pressure +
        acceleration magnitude, side by side, always over a video crop."""
        gv.addWidget(self._muted_header("Graph channels"))

        self.tbl_channels = QTableWidget(0, 3)
        self.tbl_channels.setHorizontalHeaderLabels(["Signal", "Label", "Colour"])
        self.tbl_channels.verticalHeader().setVisible(False)
        self.tbl_channels.setMaximumHeight(150)
        self.tbl_channels.horizontalHeader().setStretchLastSection(False)
        gv.addWidget(self.tbl_channels)

        ch_row = QHBoxLayout()
        self.btn_channel_add = QPushButton("Add channel")
        self.btn_channel_add.clicked.connect(self._add_channel_row)
        ch_row.addWidget(self.btn_channel_add)
        self.btn_channel_remove = QPushButton("Remove selected")
        self.btn_channel_remove.clicked.connect(self._remove_channel_row)
        ch_row.addWidget(self.btn_channel_remove)
        ch_row.addStretch()
        gv.addLayout(ch_row)

        opt_row = QHBoxLayout()
        opt_row.addWidget(self._muted("Layout"))
        self.cmb_channel_layout = QComboBox()
        self.cmb_channel_layout.addItem("Row (side by side)", "row")
        self.cmb_channel_layout.addItem("Grid (up to 3 rows of 2)", "grid")
        opt_row.addWidget(self.cmb_channel_layout)
        self.chk_no_video = QCheckBox("No video background (sensor animation)")
        self.chk_no_video.setToolTip(
            "Skip the video crop entirely - the graph panels fill the "
            "whole output frame, a pure sensor-signal animation rather "
            "than a video overlay.")
        opt_row.addWidget(self.chk_no_video)
        opt_row.addStretch()
        gv.addLayout(opt_row)

        # the two channels the export always used before this existed -
        # same default, just editable now
        for column, label, color in (
                ("pressure_kpa", "Pressure (kPa)", "black"),
                ("higacc_mag_g", "Acceleration magnitude (g)", "red")):
            self._add_channel_row(column=column, label=label, color=color)

    # ── graph channels ──────────────────────────────────────────────────────
    def _channel_columns(self):
        """Every plottable (numeric, non-time) column in the current
        sensor's CSV - falls back to the two original channel names when
        no sensor is loaded yet, so the picker isn't empty at start-up."""
        if self._df is None:
            return [c["column"] for c in video_sync.DEFAULT_CHANNELS]
        return [c for c in self._df.columns if c != "time_s"
               and pd.api.types.is_numeric_dtype(self._df[c])]

    def _add_channel_row(self, checked=False, column=None, label=None,
                         color=None):
        if self.tbl_channels.rowCount() >= video_sync.MAX_CHANNELS:
            self.status.emit(
                f"Up to {video_sync.MAX_CHANNELS} channels.", 4000)
            return
        r = self.tbl_channels.rowCount()
        self.tbl_channels.insertRow(r)

        combo = QComboBox()
        combo.setEditable(True)
        combo.addItems(self._channel_columns())
        if column:
            idx = combo.findText(column)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                combo.setEditText(column)
        self.tbl_channels.setCellWidget(r, 0, combo)
        self.tbl_channels.setItem(r, 1, QTableWidgetItem(label or ""))

        color_combo = QComboBox()
        color_combo.addItems(_CHANNEL_COLORS)
        if color in _CHANNEL_COLORS:
            color_combo.setCurrentText(color)
        self.tbl_channels.setCellWidget(r, 2, color_combo)

    def _remove_channel_row(self):
        rows = sorted({idx.row() for idx in self.tbl_channels.selectedIndexes()},
                      reverse=True)
        for r in rows:
            self.tbl_channels.removeRow(r)

    def _refresh_channel_columns(self):
        """Repopulates each channel row's signal picker with the newly
        loaded sensor's own columns, keeping the row's current choice if
        it's a free-typed value or still valid for the new sensor."""
        cols = self._channel_columns()
        for r in range(self.tbl_channels.rowCount()):
            combo = self.tbl_channels.cellWidget(r, 0)
            if combo is None:
                continue
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(cols)
            idx = combo.findText(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                combo.setEditText(current)
            combo.blockSignals(False)

    def _current_channels(self):
        channels = []
        for r in range(self.tbl_channels.rowCount()):
            combo = self.tbl_channels.cellWidget(r, 0)
            column = combo.currentText().strip() if combo else ""
            if not column:
                continue
            label_item = self.tbl_channels.item(r, 1)
            label = label_item.text().strip() if label_item else ""
            color_combo = self.tbl_channels.cellWidget(r, 2)
            color = color_combo.currentText() if color_combo else "black"
            channels.append({"column": column, "label": label or column,
                            "color": color})
        return channels or list(video_sync.DEFAULT_CHANNELS)

    @staticmethod
    def _muted(text):
        lab = QLabel(text)
        lab.setStyleSheet(f"color:{MUTED};")
        return lab

    @staticmethod
    def _muted_header(text):
        lab = QLabel(text)
        lab.setStyleSheet(f"color:{TEXT};font-weight:bold;")
        return lab

    def _connect(self):
        self.lib_selector.library_changed.connect(self._on_lib_changed)
        self.lib_selector.filters_changed.connect(self._populate_sensor_table)
        self.tbl_sensors.itemSelectionChanged.connect(self._on_row_selected)
        self.tbl_sensors.itemDoubleClicked.connect(self._on_video_double_clicked)
        self.btn_process.clicked.connect(self._process)
        self.btn_save.clicked.connect(self._save_config)
        self.btn_cancel.clicked.connect(self._cancel_process)
        self.btn_choose_logo.clicked.connect(self._choose_logo)
        self.btn_clear_logo.clicked.connect(self._clear_logo)
        self.spin_window.valueChanged.connect(self._update_view_range)
        self.spin_zoom.valueChanged.connect(self._update_view_range)
        self.slider_scrub.valueChanged.connect(self._on_scrub_slider_moved)
        self.btn_scrub_play.clicked.connect(self._toggle_scrub_play)
        self.btn_use_as_sync.clicked.connect(self._use_scrub_frame_as_sync)
        self.btn_preview_frame.clicked.connect(self._generate_preview_frame)

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
        if self._lib_root is None:
            self._sensor_rows = []
            self.tbl_sensors.setRowCount(0)
            return

        rows = []
        for row in self.lib_selector.list_sensor_csvs():
            matches = self.lib_selector.video_matches_for(row["stem"])
            rows.append({
                **row,
                "video": "; ".join(m.name for m in matches) if matches else "—",
                "synced": self._synced_path_for(row["stem"]).exists(),
            })
        self._sensor_rows = rows
        synced_by_stem = {r["stem"]: r["synced"] for r in rows}

        self.lib_selector.populate_sensor_list(
            rows, is_bad=lambda stem: di.is_bad(self._index_df, stem),
            is_done=lambda stem: synced_by_stem.get(stem, False),
            done_label="Synced",
            extra=lambda r: [r["video"], "Yes" if r["synced"] else "—"])

    def _on_row_selected(self):
        items = self.tbl_sensors.selectedItems()
        if not items:
            return
        path = self.tbl_sensors.item(items[0].row(), 0).data(
            Qt.ItemDataRole.UserRole)
        if path is not None:
            self._load_sensor(path)

    def _on_video_double_clicked(self, item):
        """Double-clicking the Video column opens the matched clip in
        LosslessCut - same pattern as Annotate/Misclassification's video
        columns, wired here via `tbl_sensors.itemDoubleClicked` directly
        (this page doesn't otherwise use `LibrarySelector.row_activated`)."""
        if item.column() != 1:
            return
        stem_item = self.tbl_sensors.item(item.row(), 0)
        if stem_item is None:
            return
        stem = stem_item.text()
        matches = self.lib_selector.video_matches_for(stem)
        if not matches:
            self.status.emit(f"No matching video for {stem}.", 4000)
            return
        if not LOSSLESSCUT_EXE.exists():
            QMessageBox.warning(self.window, "LosslessCut missing",
                                f"Missing: {LOSSLESSCUT_EXE}")
            return
        video_path = matches[0]
        if len(matches) > 1:
            names = [p.name for p in matches]
            choice, ok = QInputDialog.getItem(
                self.window, "Choose video",
                f"{len(names)} videos match {stem}:", names, 0, False)
            if not ok:
                return
            video_path = matches[names.index(choice)]
        try:
            subprocess.Popen([str(LOSSLESSCUT_EXE), str(video_path)])
        except Exception as e:
            QMessageBox.critical(self.window, "Could not open video", str(e))
            return
        self.status.emit(f"Opened {video_path.name} in LosslessCut", 4000)

    # ── sensor loading ───────────────────────────────────────────────────────
    def _load_sensor(self, path):
        if not path.exists():
            QMessageBox.warning(self.window, "File missing", f"Cannot find:\n{path}")
            return
        self._close_scrubber()
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
        self._nadir_override_t = None
        self._video_matches = self.lib_selector.video_matches_for(self._cur_stem)

        self._update_video_info()
        self._draw_plot()
        self._refresh_channel_columns()
        self._load_config()
        self._set_loaded_enabled(True)
        self.status.emit(f"Loaded: {path.name}", 3000)

        # scrub the synced output if one already exists (checking the
        # overlay/alignment that produced it), otherwise the raw matched
        # video (finding the sync frame in the first place)
        synced = self._synced_path_for(self._cur_stem)
        if synced.exists():
            self._open_scrubber(synced)
        elif self._video_matches:
            self._open_scrubber(self._video_matches[0])
        else:
            self._open_scrubber(None)

    # ── output location (session_state.py) ──────────────────────────────────
    def _video_output_dir(self):
        """`<the library this page is currently browsing>/
        StrikeWorks_user_output/processed_video/` - falls back to the
        original app-root `processed_video/` folder with no library
        selected, so this still works before Home has been used at all.
        Keyed off this page's own `_lib_root` (soft-synced from the
        session library but independently changeable) rather than the
        session library directly, so overriding this page's picker alone
        still writes to the right place. Loading/reviewing a video (the
        scrubber, LosslessCut) stays unaffected either way - only where a
        *new* export/config is written by default changes."""
        if self._lib_root is None:
            return _PROCESSED_VIDEO_DIR
        return self._lib_root / OUTPUT_DIR_NAME / "processed_video"

    def _config_path_for(self, stem):
        return self._video_output_dir() / f"{stem}_sync_config.json"

    def _synced_path_for(self, stem):
        return self._video_output_dir() / f"{stem}_synced.mp4"

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

    def _default_graph_window_s(self):
        """Half-width for the rolling graph strip `video_sync.
        make_graph_strip` burns into the export (total span per frame is
        double this, divided by Zoom).

        Deliberately NOT sized to the matched video's own length - that
        was tried and made the strip scroll far too slowly (a multi-
        second video's whole duration crammed into one view barely moves
        frame to frame). A small window is what makes the trace read as
        live and scrolling; "Zoom" (Code options) is the user's stretch
        control for it, not the video's length."""
        return _DEFAULT_GRAPH_WINDOW_S

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
        self._update_view_range()

    def _update_view_range(self):
        """Sizes the live preview's X-range, the nadir line's position and
        the shaded video-span region - split out of `_draw_plot()` so
        dragging Graph window/Zoom (Code options) re-scales the preview
        immediately instead of only ever showing up after a full (slow)
        re-render."""
        pi = self._pw.plotItem
        if self._time is None or self._curve is None:
            return
        nadir_t = self._nadir_time_s()
        duration = getattr(self, "_video_duration_s", None)
        if nadir_t is None:
            self._video_region.setVisible(False)
            pi.enableAutoRange("x", True)
            return
        self._nadir_line.blockSignals(True)
        self._nadir_line.setValue(nadir_t)
        self._nadir_line.blockSignals(False)

        # the view shows exactly what the export crops per frame (2x the
        # Graph window option, divided by Zoom, around the current-time
        # line) capped at _MAX_WINDOW_S so a large manual override can't
        # blow the preview out to something unreadable - the shaded
        # region still shows the video's *true* span even past that cap,
        # since it - not the view - is the thing being aligned
        zoom = max(self.spin_zoom.value(), 1e-6)
        window = min(2 * self.spin_window.value() / zoom, _MAX_WINDOW_S)
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
            "nadir_time_override": self._nadir_override_t,
            "channels": self._current_channels(),
            "layout": self.cmb_channel_layout.currentData(),
            "no_video": self.chk_no_video.isChecked(),
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

        cfg = _read_json(self._config_path_for(self._cur_stem)) or {}
        # index-sourced defaults are only used when nothing was saved
        # before - text inputs stay editable either way
        self.ed_pump.setText(cfg.get("pump") or self._pump_default_from_row(row))
        self.ed_shaft_speed.setText(cfg.get("shaft_speed") or treatment)
        self.ed_camera.setText(cfg.get("camera", self.ed_camera.text()))
        self.ed_sensor.setText(cfg.get("sensor") or self._sensor_default())
        self.spin_nadir_frame.setValue(int(cfg.get("nadir_frame", 0)))
        self.spin_real_fps.setValue(int(cfg.get("real_fps", 1000)))
        self.spin_window.setValue(
            float(cfg.get("graph_window_s", self._default_graph_window_s())))
        self.spin_zoom.setValue(float(cfg.get("zoom", 1.0)))
        self.spin_video_nudge.setValue(int(cfg.get("video_nudge_px", 0)))
        self.chk_labels.setChecked(bool(cfg.get("add_labels", True)))
        self._set_logo_path(cfg.get("logo_path"))
        self.spin_logo_opacity.setValue(float(cfg.get("logo_opacity", 1.0)))
        override = cfg.get("nadir_time_override")
        self._nadir_override_t = float(override) if override is not None else None
        self._update_view_range()

        # channels are a "how do my animations look" setting more than a
        # per-sensor one - only rebuild the table when this sensor has its
        # own saved choice, otherwise leave whatever's already there (the
        # defaults, or an earlier sensor's still-applicable customisation)
        channels_cfg = cfg.get("channels")
        if channels_cfg:
            self.tbl_channels.setRowCount(0)
            for ch in channels_cfg:
                self._add_channel_row(column=ch.get("column"),
                                      label=ch.get("label"),
                                      color=ch.get("color"))
            self._refresh_channel_columns()
        layout_idx = self.cmb_channel_layout.findData(cfg.get("layout", "row"))
        self.cmb_channel_layout.setCurrentIndex(max(layout_idx, 0))
        self.chk_no_video.setChecked(bool(cfg.get("no_video", False)))

    def _save_config(self):
        if not self._cur_stem:
            return
        path = self._config_path_for(self._cur_stem)
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

    # ── nadir time (from the sensor's own processed CSV, or a user pick) ────
    def _nadir_time_s(self):
        if self._df is None or "pressure_kpa" not in self._df.columns:
            return None
        if self._nadir_override_t is not None:
            return self._nadir_override_t
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

    def _on_nadir_line_moved(self):
        """Dragging the nadir line - snaps to the nearest actual sample,
        same as Validate's nadir tool - overrides the detected nadir time
        for this page's video sync (persisted per-sensor, see
        `_config_values`/`_load_config`)."""
        if self._time is None:
            return
        raw_t = self._nadir_line.value()
        idx = int(np.argmin(np.abs(self._time - raw_t)))
        t_snap = float(self._time[idx])
        self._nadir_override_t = t_snap
        self._nadir_line.blockSignals(True)
        self._nadir_line.setValue(t_snap)
        self._nadir_line.blockSignals(False)
        self._update_view_range()

    def _reset_nadir_override(self):
        self._nadir_override_t = None
        self._update_view_range()
        self.status.emit("Nadir reset to the detected value.", 3000)

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
            logo_opacity=cfg["logo_opacity"], channels=cfg["channels"],
            layout=cfg["layout"], no_video=cfg["no_video"])
        output_path = self._synced_path_for(self._cur_stem)

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
        self._open_scrubber(Path(output_path))

    def _on_process_failed(self, msg):
        self._reset_process_buttons()
        self.lbl_progress.setText(f"Failed: {msg}")
        if msg != "Cancelled.":
            QMessageBox.critical(self.window, "Processing failed", msg)

    # ── video preview (frame scrubber, Video preview row) ───────────────────
    def _open_scrubber(self, path):
        """Points the scrubber at `path` (the raw matched video before
        processing, or the synced output after) - a fresh `cv2.
        VideoCapture` per video, frame-seekable via the slider."""
        self._close_scrubber()
        if path is None or not Path(path).exists():
            self.lbl_scrub_frame.setText("No video to preview.")
            self.lbl_scrub_frame.setPixmap(QPixmap())
            self.lbl_scrub_info.setText("")
            return
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            cap.release()
            self.lbl_scrub_frame.setText(f"Could not open {Path(path).name}.")
            return
        self._scrub_path = Path(path)
        self._scrub_cap = cap
        self._scrub_frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        self._scrub_fps = fps if fps > 0 else None

        self.slider_scrub.blockSignals(True)
        self.slider_scrub.setRange(0, max(0, self._scrub_frame_count - 1))
        self.slider_scrub.setValue(0)
        self.slider_scrub.blockSignals(False)
        self.slider_scrub.setEnabled(self._scrub_frame_count > 1)
        self.btn_scrub_play.setEnabled(self._scrub_frame_count > 1)
        self.btn_use_as_sync.setEnabled(True)
        self._show_scrub_frame(0)

    def _close_scrubber(self):
        self._scrub_timer.stop()
        self.btn_scrub_play.setText("Play")
        if self._scrub_cap is not None:
            self._scrub_cap.release()
        self._scrub_cap = None
        self._scrub_path = None
        self._scrub_frame_count = 0
        self._scrub_fps = None

    def _show_scrub_frame(self, frame_idx):
        if self._scrub_cap is None:
            return
        frame_idx = max(0, min(int(frame_idx), max(self._scrub_frame_count - 1, 0)))
        self._scrub_cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = self._scrub_cap.read()
        if not ret:
            return
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, _ = rgb.shape
        pix = QPixmap.fromImage(
            QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy())
        target_h = max(self.lbl_scrub_frame.height(), 160)
        self.lbl_scrub_frame.setPixmap(pix.scaledToHeight(
            target_h, Qt.TransformationMode.SmoothTransformation))
        tail = (f", {frame_idx / self._scrub_fps:.4f}s" if self._scrub_fps
               else "")
        self.lbl_scrub_info.setText(
            f"Frame {frame_idx} / {max(self._scrub_frame_count - 1, 0)}{tail}")

    def _on_scrub_slider_moved(self, value):
        self._show_scrub_frame(value)

    def _toggle_scrub_play(self):
        if self._scrub_timer.isActive():
            self._scrub_timer.stop()
            self.btn_scrub_play.setText("Play")
            return
        if self._scrub_cap is None:
            return
        interval_ms = int(1000 / self._scrub_fps) if self._scrub_fps else 33
        self._scrub_timer.start(max(interval_ms, 10))
        self.btn_scrub_play.setText("Pause")

    def _advance_scrub_frame(self):
        nxt = self.slider_scrub.value() + 1
        if nxt > self.slider_scrub.maximum():
            self._scrub_timer.stop()
            self.btn_scrub_play.setText("Play")
            return
        self.slider_scrub.setValue(nxt)

    def _use_scrub_frame_as_sync(self):
        if self._scrub_cap is None:
            return
        frame = self.slider_scrub.value()
        self.spin_nadir_frame.setValue(frame)
        self.status.emit(f"Sync frame set to {frame}.", 4000)

    # ── preview-frame composite (sanity-check before a full render) ────────
    def _generate_preview_frame(self):
        if self._df is None or not self._video_matches:
            QMessageBox.warning(self.window, "Nothing to preview",
                                "Load a sensor with a matched video first.")
            return
        nadir_time_s = self._nadir_time_s()
        if nadir_time_s is None:
            QMessageBox.warning(self.window, "No nadir",
                                "Couldn't determine this sensor's nadir time.")
            return
        cfg = self._config_values()
        opts = video_sync.SyncOptions(
            real_fps=cfg["real_fps"], graph_window_s=cfg["graph_window_s"],
            zoom=cfg["zoom"], add_labels=cfg["add_labels"],
            video_nudge_px=cfg["video_nudge_px"], logo_path=cfg["logo_path"],
            logo_opacity=cfg["logo_opacity"], channels=cfg["channels"],
            layout=cfg["layout"], no_video=cfg["no_video"])
        frame_idx = (self.slider_scrub.value() if self._scrub_cap is not None
                    else cfg["nadir_frame"])
        try:
            combined = video_sync.render_preview_frame(
                self._video_matches[0], self._df, nadir_time_s,
                cfg["nadir_frame"], cfg, opts, frame_idx)
        except Exception as e:
            QMessageBox.critical(self.window, "Preview failed", str(e))
            return
        self._show_preview_dialog(combined, frame_idx)

    def _show_preview_dialog(self, frame_bgr, frame_idx):
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        h, w, _ = rgb.shape
        qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
        dlg = QDialog(self.window)
        dlg.setWindowTitle(f"Preview frame - {frame_idx}")
        lay = QVBoxLayout(dlg)
        lab = QLabel()
        pix = QPixmap.fromImage(qimg)
        if pix.height() > 720:
            pix = pix.scaledToHeight(720, Qt.TransformationMode.SmoothTransformation)
        lab.setPixmap(pix)
        lay.addWidget(lab)
        dlg.setLayout(lay)
        dlg.exec()


def _read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return None


