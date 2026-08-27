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

from PySide6.QtCore import Qt, QObject, QThread, QUrl, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
    QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSizePolicy, QSpinBox, QSplitter, QStackedWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget

from . import deployment_index as di
from . import settings, video_sync
from .ml_widgets import ACCENT, MUTED, OK, Section, apply_section_defaults
from .page_annotate import LOSSLESSCUT_EXE, _RAW_DIR, _VIDEO_FOLDER_NAME
from .page_validate import (
    _CsvLoadThread, _NavViewBox, _find_col,
)
from .plot_style import reserve_top_margin, set_right_axis_active

import pyqtgraph as pg

pg.setConfigOptions(antialias=True, background="#21252b",
                    foreground="#c8cdd6")

_CSV_DIR = Path("processed_sens_data") / "csv"
_EXCL_NAMES = {"global_sensor_index.csv", "model_features.csv"}
_EXCL_SUFFIXES = ("_nadir_window",)
_UNGROUPED = "(ungrouped)"
_ALL_DEPLOYMENTS = None

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

        self._lib_dir = settings.get_libraries_dir()
        self._lib_root = None
        self._deployment_map = {}
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
        self._worker = None

        self._build(ui.content_export_animations)
        self._connect()
        self._populate_libraries()
        self._set_loaded_enabled(False)

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

        grp = Section("Library")
        fv = QVBoxLayout(grp)
        fv.setSpacing(6)

        lib_row = QHBoxLayout()
        self.cmb_library = QComboBox()
        self.cmb_library.setMinimumWidth(140)
        lib_row.addWidget(self.cmb_library, stretch=1)
        self.btn_change_libs = QPushButton("Libraries…")
        lib_row.addWidget(self.btn_change_libs)
        fv.addLayout(lib_row)

        self.cmb_deployment = QComboBox()
        fv.addLayout(self._row(self._muted("Deployment"), self.cmb_deployment))
        self.cmb_treatment = QComboBox()
        fv.addLayout(self._row(self._muted("Treatment"), self.cmb_treatment))
        lv.addWidget(grp)

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
        self.chk_labels = QCheckBox("Add labels")
        self.chk_labels.setChecked(True)

        for row, (label, widget) in enumerate([
                ("Sync frame (video)", self.spin_nadir_frame),
                ("Real fps (camera)", self.spin_real_fps),
                ("Graph window (s)", self.spin_window),
                ("Zoom", self.spin_zoom)]):
            gv.addWidget(self._muted(label), row, 0)
            gv.addWidget(widget, row, 1)
        gv.addWidget(self.chk_labels, 4, 0, 1, 2)
        return grp

    @staticmethod
    def _muted(text):
        lab = QLabel(text)
        lab.setStyleSheet(f"color:{MUTED};")
        return lab

    @staticmethod
    def _row(label, widget):
        r = QHBoxLayout()
        r.addWidget(label)
        r.addWidget(widget, stretch=1)
        return r

    def _connect(self):
        self.cmb_library.currentIndexChanged.connect(self._on_library_changed)
        self.btn_change_libs.clicked.connect(self._change_libraries)
        self.cmb_deployment.currentIndexChanged.connect(
            self._rebuild_treatment_combo)
        self.cmb_deployment.currentIndexChanged.connect(
            self._populate_sensor_table)
        self.cmb_treatment.currentIndexChanged.connect(
            self._populate_sensor_table)
        self.tbl_sensors.itemSelectionChanged.connect(self._on_row_selected)
        self.btn_process.clicked.connect(self._process)
        self.btn_save.clicked.connect(self._save_config)
        self.btn_cancel.clicked.connect(self._cancel_process)
        self.btn_play.clicked.connect(self._toggle_play)
        self._player.playbackStateChanged.connect(self._on_playback_changed)

    def _set_loaded_enabled(self, enabled):
        for b in (self.btn_process, self.btn_save):
            b.setEnabled(enabled)
        # apply_section_defaults() force-shows every widget in an open
        # Section after _build() runs, undoing the constructor's
        # setVisible(False) - reassert it here, which also covers loading
        # a new sensor while a previous one's Cancel button was showing
        self.btn_cancel.setVisible(False)

    # ── libraries (same shape as Annotate) ────────────────────────────────────
    def _populate_libraries(self, select=None):
        self.cmb_library.blockSignals(True)
        self.cmb_library.clear()
        try:
            libs = sorted(p for p in self._lib_dir.iterdir() if p.is_dir())
        except Exception:
            libs = []
        for lib in libs:
            self.cmb_library.addItem(lib.name, str(lib))
        self.cmb_library.blockSignals(False)
        if not libs:
            self._lib_root = None
            return
        idx = self.cmb_library.findData(str(select)) if select else 0
        self.cmb_library.setCurrentIndex(max(0, idx))
        self._on_library_changed()

    def _change_libraries(self):
        chosen = QFileDialog.getExistingDirectory(
            self.window, "Select libraries folder", str(self._lib_dir))
        if not chosen:
            return
        self._lib_dir = settings.set_libraries_dir(chosen)
        self._populate_libraries()

    def _on_library_changed(self, *_args):
        path = self.cmb_library.currentData()
        self._lib_root = Path(path) if path else None
        self._scan_deployments()
        self._populate_sensor_table()
        if self._lib_root:
            self.status.emit(f"Library: {self._lib_root.name}", 4000)

    def _scan_deployments(self):
        self._deployment_map = {}
        current_dep = self.cmb_deployment.currentData()
        self.cmb_deployment.blockSignals(True)
        self.cmb_deployment.clear()
        self.cmb_deployment.addItem("All deployments", _ALL_DEPLOYMENTS)

        raw_dir = self._lib_root / _RAW_DIR if self._lib_root else None
        if raw_dir is None or not raw_dir.exists():
            self.cmb_deployment.blockSignals(False)
            self._rebuild_treatment_combo()
            return

        deployments = set()
        for entry in sorted(raw_dir.iterdir()):
            if entry.is_file():
                self._deployment_map.setdefault(
                    entry.stem.upper(), (_UNGROUPED, _UNGROUPED))
                deployments.add(_UNGROUPED)
                continue
            if not entry.is_dir():
                continue
            deployments.add(entry.name)
            for child in sorted(entry.iterdir()):
                if child.is_dir():
                    if child.name.upper() == _VIDEO_FOLDER_NAME:
                        continue
                    for f in child.rglob("*"):
                        if f.is_file():
                            self._deployment_map.setdefault(
                                f.stem.upper(), (entry.name, child.name))
                elif child.is_file():
                    self._deployment_map.setdefault(
                        child.stem.upper(), (entry.name, _UNGROUPED))

        for name in sorted(deployments):
            self.cmb_deployment.addItem(name, name)
        idx = self.cmb_deployment.findData(current_dep)
        self.cmb_deployment.setCurrentIndex(idx if idx >= 0 else 0)
        self.cmb_deployment.blockSignals(False)
        self._rebuild_treatment_combo()

    def _rebuild_treatment_combo(self):
        wanted_deployment = self.cmb_deployment.currentData()
        current = self.cmb_treatment.currentData()
        self.cmb_treatment.blockSignals(True)
        self.cmb_treatment.clear()
        self.cmb_treatment.addItem("All treatments", _ALL_DEPLOYMENTS)
        treatments = sorted({
            treatment for (deployment, treatment) in self._deployment_map.values()
            if wanted_deployment is None or deployment == wanted_deployment})
        for name in treatments:
            self.cmb_treatment.addItem(name, name)
        idx = self.cmb_treatment.findData(current)
        self.cmb_treatment.setCurrentIndex(idx if idx >= 0 else 0)
        self.cmb_treatment.blockSignals(False)

    def _video_dir_for(self, stem):
        info = self._deployment_map.get(stem.upper())
        if not info or self._lib_root is None:
            return None
        deployment, treatment = info
        base = self._lib_root / _RAW_DIR
        if deployment != _UNGROUPED:
            base = base / deployment
        if treatment != _UNGROUPED:
            base = base / treatment
        if not base.exists():
            return None
        for entry in base.iterdir():
            if entry.is_dir() and entry.name.upper() == _VIDEO_FOLDER_NAME:
                return entry
        return None

    def _video_matches_for(self, stem):
        video_dir = self._video_dir_for(stem)
        if video_dir is None:
            return []
        return sorted(video_dir.glob(f"{stem}_vid_*.mp4"))

    # ── sensor table ─────────────────────────────────────────────────────────
    def _populate_sensor_table(self):
        self.tbl_sensors.setRowCount(0)
        self._sensor_rows = []
        if self._lib_root is None:
            return
        csv_dir = self._lib_root / _CSV_DIR
        if not csv_dir.exists():
            return

        wanted_deployment = self.cmb_deployment.currentData()
        wanted_treatment = self.cmb_treatment.currentData()
        valid = [p for p in sorted(csv_dir.rglob("*.csv"))
                 if p.name not in _EXCL_NAMES
                 and not any(p.stem.endswith(s) for s in _EXCL_SUFFIXES)]

        rows = []
        for p in valid:
            deployment, treatment = self._deployment_map.get(
                p.stem.upper(), (_UNGROUPED, _UNGROUPED))
            if wanted_deployment is not None and deployment != wanted_deployment:
                continue
            if wanted_treatment is not None and treatment != wanted_treatment:
                continue
            matches = self._video_matches_for(p.stem)
            rows.append({
                "path": p, "stem": p.stem,
                "video": "; ".join(m.name for m in matches) if matches else "—",
                "synced": _synced_path_for(p.stem).exists(),
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
        self._video_matches = self._video_matches_for(self._cur_stem)

        self._draw_plot()
        self._load_config()
        self._set_loaded_enabled(True)
        self.status.emit(f"Loaded: {path.name}", 3000)

        synced = _synced_path_for(self._cur_stem)
        if synced.exists():
            self._show_video(synced)

    def _draw_plot(self):
        pi = self._pw.plotItem
        if self._curve is not None:
            pi.removeItem(self._curve)
            self._curve = None
        if self._time is None or "pressure_kpa" not in self._df.columns:
            return
        y = self._df["pressure_kpa"].to_numpy(dtype=float)
        self._curve = self._pw.plot(self._time, y, pen=pg.mkPen("#dddddd", width=1))
        self._curve.setDownsampling(auto=True, method="peak")
        self._curve.setClipToView(True)
        pi.enableAutoRange("x", True)
        pi.enableAutoRange("y", True)

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
            "add_labels": self.chk_labels.isChecked(),
        }

    def _load_config(self):
        index_df = di.read_index(self._lib_root) if self._lib_root else None
        treatment = ""
        if index_df is not None and "file" in index_df.columns:
            match = index_df[index_df["file"] == self._cur_stem]
            if not match.empty and "treatment" in match.columns:
                treatment = str(match.iloc[0].get("treatment", "") or "")

        cfg = _read_json(_config_path_for(self._cur_stem)) or {}
        self.ed_pump.setText(cfg.get("pump", ""))
        self.ed_shaft_speed.setText(cfg.get("shaft_speed", treatment))
        self.ed_camera.setText(cfg.get("camera", self.ed_camera.text()))
        self.ed_sensor.setText(cfg.get("sensor", self.ed_sensor.text()))
        self.spin_nadir_frame.setValue(int(cfg.get("nadir_frame", 0)))
        self.spin_real_fps.setValue(int(cfg.get("real_fps", 1000)))
        self.spin_window.setValue(float(cfg.get("graph_window_s", 0.3)))
        self.spin_zoom.setValue(float(cfg.get("zoom", 1.0)))
        self.chk_labels.setChecked(bool(cfg.get("add_labels", True)))

    def _save_config(self):
        if not self._cur_stem:
            return
        path = _config_path_for(self._cur_stem)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._config_values(), indent=2))
        self.status.emit(f"Sync configuration saved for {self._cur_stem}.", 4000)

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
            zoom=cfg["zoom"], add_labels=cfg["add_labels"])
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
