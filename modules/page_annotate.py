# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Controller for the Annotate page (Annotation & Video Analysis).

Built on the same shape Inspect uses (`ml_tab_inspect.py`): a fixed-width
browser on the left, a detail area filling the rest. The browser here is
library -> deployment -> treatment -> sensor, mirroring Inspect's
filter-combo pattern; the detail area is itself split half signal-plot /
half annotation panel.

A sensor's "deployment" and "treatment" are the two levels of subfolder
under `raw_sens_data` its raw file lives under (the same folder Process
scans) - `raw_sens_data/<deployment>/<treatment>/` - not the study-design
deployment/treatment from Prepare > Study design, which need not exist yet
when a recording is only reviewed. A folder missing one of these levels
(files directly under the deployment, or no deployment folder at all)
still works - it just buckets under "(ungrouped)" at whichever level is
absent. Video lives inside the treatment folder, its own name matched
case-insensitively: `raw_sens_data/<deployment>/<treatment>/VIDEO/
<stem>_vid_*.mp4`.

The nadir/ROI tool (left/right axis, ROI window, save + next, reset
current) is ported from `page_validate.py` rather than imported wholesale:
`page_validate.py` stays under Sensor Processing untouched, since it is the
page slated to grow into the Delineation tool later, and the two pages
temporarily overlap in what they do. The already-standalone
`_CsvLoadThread`/`_NavViewBox`/`_Spinner`/`_decimate` are reused directly
(the same reuse `ml_tab_inspect.py` already makes), the rest is rebuilt
here because Annotate's save action does more than Validate's: it also
appends the sensor to a running dataset.

Dataset auto-build: the first sensor saved in a library starts
`processed_sens_data/model_features.csv` (the same shape Dataset creation
already produces - `page_dataset.py`'s `_standardise`/`_META_COLS`, reused
directly); each further "Save + next" appends (or replaces, if re-saving a
sensor already in it) that sensor's block. Opening a library reads this
file back to know which sensors are already done, so review can resume
where it left off. Annotation values are optional per sensor - a "No
annotations for this sensor" tick lets a sensor through with none, so a
dataset collected without annotations still works.
"""
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pyqtgraph as pg

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QGridLayout,
    QHBoxLayout, QHeaderView, QInputDialog, QLabel, QMessageBox,
    QPlainTextEdit, QPushButton, QSizePolicy, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import annotation_schema as asch
from . import deployment_index as di
from . import sensor_config, settings
from .annotation_widgets import AnnotationValueEditor, VariableListDialog
from .ml_widgets import (
    ACCENT, BAD, BORDER, CARD_BG, MUTED, OK, Section, apply_section_defaults,
)
from .page_dataset import _META_COLS, _standardise
from .page_validate import (
    _CHANNEL_ORDER, _CHANNELS, _MAX_RIGHT_PTS, _CsvLoadThread, _EXCL_NAMES,
    _EXCL_SUFFIXES, _NavViewBox, _Spinner, _decimate, _find_col,
)

pg.setConfigOptions(antialias=True, background="#21252b",
                    foreground="#c8cdd6")

_RAW_DIR = Path("raw_sens_data")
_CSV_DIR = Path("processed_sens_data") / "csv"
_WIN_DIR = Path("processed_sens_data") / "nadir_window"
_DATASET_REL = Path("processed_sens_data") / "model_features.csv"
_VIDEO_FOLDER_NAME = "VIDEO"
_UNGROUPED = "(ungrouped)"
_ALL_DEPLOYMENTS = None

_NADIR_T_COL = "pres_min.time."
_NADIR_V_COL = "pres_min.kPa."
_VALIDATED_COL = "hstrike_processed"
_BAD_SENS_COL = "bad_sens"
_NOTES_COL = "notes"

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

        self._lib_dir = settings.get_libraries_dir()
        self._lib_root = None
        self._index_df = None
        self._deployment_map = {}      # stem (upper) -> (deployment, treatment)
        self._sensor_rows = []          # [{"path", "stem", "deployment", "video"}]
        self._dataset_stems = set()

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
        self._editors = {}

        self._build(ui.content_annotate)
        self._connect()
        self._populate_libraries()
        self._rebuild_annotation_panel()
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
        self._build_plot_side(dv)

        lower = QSplitter(Qt.Orientation.Horizontal)
        lower.setChildrenCollapsible(False)
        lower.addWidget(self._build_annotation_side())
        lower.addWidget(self._build_notes_side())
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

        self.chk_show_flags = QCheckBox("Show bad sensors")
        self.chk_show_flags.setChecked(True)
        fv.addWidget(self.chk_show_flags)

        self.lbl_progress = QLabel("")
        self.lbl_progress.setStyleSheet(f"color:{MUTED};")
        fv.addWidget(self.lbl_progress)
        lv.addWidget(grp)

        self.tbl_sensors = QTableWidget(0, 2)
        self.tbl_sensors.setHorizontalHeaderLabels(["Sensor", "Video"])
        self.tbl_sensors.verticalHeader().setVisible(False)
        self.tbl_sensors.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_sensors.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_sensors.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl_sensors.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive)
        self.tbl_sensors.horizontalHeader().setStretchLastSection(False)
        self.tbl_sensors.setStyleSheet(
            f"QTableWidget{{background-color:{CARD_BG};"
            f"border:1px solid {BORDER};border-radius:5px;}}")
        lv.addWidget(self.tbl_sensors, stretch=1)

        self.lbl_loading = QLabel("")
        self.lbl_loading.setStyleSheet(f"color:{MUTED};")
        lv.addWidget(self.lbl_loading)
        return left

    def _build_plot_side(self, v):
        grp_sig = Section("Signal")
        sv = QVBoxLayout(grp_sig)
        sv.setSpacing(6)

        axis_row = QHBoxLayout()
        self.cmb_left = QComboBox()
        for key in _CHANNEL_ORDER:
            self.cmb_left.addItem(_CHANNELS[key][1], key)
        self.cmb_left.setCurrentIndex(_CHANNEL_ORDER.index(self._left_key))
        self.cmb_right = QComboBox()
        self.cmb_right.addItem("None", None)
        for key in _CHANNEL_ORDER:
            self.cmb_right.addItem(_CHANNELS[key][1], key)
        axis_row.addWidget(self._muted("Left"))
        axis_row.addWidget(self.cmb_left, stretch=1)
        axis_row.addWidget(self._muted("Right"))
        axis_row.addWidget(self.cmb_right, stretch=1)
        sv.addLayout(axis_row)

        win_row = QHBoxLayout()
        win_row.addWidget(self._muted("ROI window"))
        self.cmb_window = QComboBox()
        win_row.addWidget(self.cmb_window)
        self._spinner = _Spinner(size=18)
        self._spinner.setVisible(False)
        win_row.addWidget(self._spinner)
        win_row.addStretch()
        sv.addLayout(win_row)

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

        self._vb2 = pg.ViewBox()
        pi.scene().addItem(self._vb2)
        pi.getAxis("right").linkToView(self._vb2)
        self._vb2.setXLink(pi)
        pi.hideAxis("right")
        pi.vb.sigResized.connect(self._sync_vb2)
        pi.vb.sigXRangeChanged.connect(self._on_xrange_changed)

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
        self.btn_save_next = QPushButton("Save + next")
        self.btn_save_next.setStyleSheet(
            f"QPushButton{{background-color:{ACCENT};color:#ffffff;"
            "border-radius:5px;padding:4px 14px;font-weight:bold;}"
            "QPushButton:disabled{background-color:#3a4150;color:#8a95aa;}")
        self.btn_save_next.clicked.connect(self._save_and_next)
        self.btn_reset = QPushButton("Reset sensor")
        self.btn_reset.clicked.connect(self._reset_current)
        act.addWidget(self.btn_save_next)
        act.addWidget(self.btn_reset)
        act.addStretch()
        sv.addLayout(act)

        lbl_save_help = self._muted(
            "Save + next extracts the ROI window for model training and/or "
            "blade strike prediction. Annotations are appended unless "
            "turned off. Use Reset sensor to reload this file without "
            "saving.")
        lbl_save_help.setWordWrap(True)
        sv.addWidget(lbl_save_help)
        v.addWidget(grp_sig)

    def _build_annotation_side(self):
        grp = Section("Annotations")
        gv = QVBoxLayout(grp)
        gv.setSpacing(6)

        flag_row = QHBoxLayout()
        self.chk_good = QCheckBox("Good")
        self.chk_good.setChecked(True)
        self.chk_bad = QCheckBox("Bad")
        self.chk_good.toggled.connect(self._on_good_toggled)
        self.chk_bad.toggled.connect(self._on_bad_toggled)
        flag_row.addWidget(self.chk_good)
        flag_row.addWidget(self.chk_bad)
        flag_row.addStretch()
        gv.addLayout(flag_row)

        self.annotation_grid = QGridLayout()
        self.annotation_grid.setVerticalSpacing(6)
        self.annotation_grid.setColumnStretch(1, 1)
        gv.addLayout(self.annotation_grid)

        self.chk_no_annotations = QCheckBox("No annotations for this sensor")
        gv.addWidget(self.chk_no_annotations)

        self.btn_manage_vars = QPushButton("Manage variables…")
        self.btn_manage_vars.clicked.connect(self._manage_variables)
        gv.addWidget(self.btn_manage_vars)

        self.lbl_annotation_status = QLabel("")
        self.lbl_annotation_status.setStyleSheet(f"color:{MUTED};")
        self.lbl_annotation_status.setWordWrap(True)
        gv.addWidget(self.lbl_annotation_status)
        gv.addStretch()
        return grp

    def _build_notes_side(self):
        grp = Section("Notes")
        gv = QVBoxLayout(grp)
        self.txt_notes = QPlainTextEdit()
        self.txt_notes.setPlaceholderText(
            "Free-text notes for this sensor…")
        gv.addWidget(self.txt_notes)
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
        self.chk_show_flags.toggled.connect(self._populate_sensor_table)
        self.tbl_sensors.itemSelectionChanged.connect(self._on_row_selected)
        self.tbl_sensors.itemDoubleClicked.connect(self._on_sensor_double_clicked)

        self.cmb_left.currentIndexChanged.connect(self._on_axis_changed)
        self.cmb_right.currentIndexChanged.connect(self._on_axis_changed)
        self.cmb_window.currentIndexChanged.connect(self._on_win_size_changed)
        sensor_config.notifier.changed.connect(self._on_sensor_changed)
        asch.notifier.changed.connect(self._rebuild_annotation_panel)
        self._fill_window_combo()

    def _set_loaded_enabled(self, enabled):
        for b in (self.btn_save_next, self.btn_reset):
            b.setEnabled(enabled)
        for c in (self.chk_good, self.chk_bad):
            c.setEnabled(enabled)

    # ── libraries ────────────────────────────────────────────────────────────
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
        self.btn_change_libs.setToolTip(str(self._lib_dir))
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
        self._load_index()
        self._scan_deployments()
        self._load_dataset_stems()
        self._populate_sensor_table()
        if self._lib_root:
            self.status.emit(f"Library: {self._lib_root.name}", 4000)

    # ── index ────────────────────────────────────────────────────────────────
    def _load_index(self):
        self._index_df = di.read_index(self._lib_root) if self._lib_root else None

    def _is_bad(self, stem: str) -> bool:
        if self._index_df is None or "file" not in self._index_df.columns:
            return False
        row = self._index_df[self._index_df["file"] == stem]
        if row.empty or _BAD_SENS_COL not in self._index_df.columns:
            return False
        return str(row[_BAD_SENS_COL].iloc[0]).strip().upper() == "Y"

    # ── deployments (raw_sens_data subfolders, one level) ────────────────────
    def _scan_deployments(self):
        """Map each raw sensor stem to (deployment, treatment).

        `raw_sens_data/<deployment>/<treatment>/` is the normal shape;
        a deployment with no treatment subfolders (files directly inside
        it), or a library with no deployment subfolders at all, still work
        - they just bucket under `_UNGROUPED` at whichever level is
        missing, rather than being dropped.
        """
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
                        continue   # VIDEO with no treatment level in between
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

    def _video_dir_for(self, stem: str):
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
            # case-insensitive: "video"/"Video"/"VIDEO" all match
            if entry.is_dir() and entry.name.upper() == _VIDEO_FOLDER_NAME:
                return entry
        return None

    def _video_matches_for(self, stem: str):
        video_dir = self._video_dir_for(stem)
        if video_dir is None:
            return []
        return sorted(video_dir.glob(f"{stem}_vid_*.mp4"))

    # ── the running dataset (resume support) ─────────────────────────────────
    def _dataset_path(self):
        return self._lib_root / _DATASET_REL

    def _load_dataset_stems(self):
        self._dataset_stems = set()
        if self._lib_root is None:
            return
        path = self._dataset_path()
        if not path.exists():
            return
        try:
            df = pd.read_csv(path, usecols=["file"], low_memory=False)
            self._dataset_stems = set(df["file"].astype(str).unique())
        except Exception:
            self._dataset_stems = set()

    def _append_to_dataset(self, block: pd.DataFrame):
        path = self._dataset_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = None
        if path.exists():
            try:
                existing = pd.read_csv(path, low_memory=False)
            except Exception:
                existing = None
        if existing is not None and "file" in existing.columns:
            existing = existing[existing["file"].astype(str) != self._cur_stem]
            out = pd.concat([existing, block], ignore_index=True)
        else:
            out = block
        out.to_csv(path, index=False)
        self._dataset_stems.add(self._cur_stem)

    # ── sensor table ─────────────────────────────────────────────────────────
    def _populate_sensor_table(self):
        self.tbl_sensors.setRowCount(0)
        self._sensor_rows = []
        if self._lib_root is None:
            self.lbl_progress.setText("")
            return
        csv_dir = self._lib_root / _CSV_DIR
        if not csv_dir.exists():
            self.lbl_progress.setText("")
            return

        wanted_deployment = self.cmb_deployment.currentData()
        wanted_treatment = self.cmb_treatment.currentData()
        show_flags = self.chk_show_flags.isChecked()

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
                "path": p, "stem": p.stem, "deployment": deployment,
                "treatment": treatment,
                "video": "; ".join(m.name for m in matches) if matches else "—",
            })
        self._sensor_rows = rows

        self.tbl_sensors.setRowCount(len(rows))
        for r, row in enumerate(rows):
            sensor_item = QTableWidgetItem(row["stem"])
            sensor_item.setData(Qt.ItemDataRole.UserRole, row["path"])
            if row["stem"] in self._dataset_stems:
                sensor_item.setForeground(QColor(OK))
            elif show_flags and self._is_bad(row["stem"]):
                sensor_item.setForeground(QColor(BAD))
            self.tbl_sensors.setItem(r, 0, sensor_item)
            self.tbl_sensors.setItem(r, 1, QTableWidgetItem(row["video"]))
        self.tbl_sensors.resizeColumnsToContents()

        n_done = sum(1 for row in rows if row["stem"] in self._dataset_stems)
        self.lbl_progress.setText(f"In dataset: {n_done} / {len(rows)}")

    def _on_row_selected(self):
        items = self.tbl_sensors.selectedItems()
        if not items:
            return
        path = self.tbl_sensors.item(items[0].row(), 0).data(
            Qt.ItemDataRole.UserRole)
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

    # ── plot (left/right axis, ported from page_validate.py) ────────────────
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
            self._curve = self._pw.plot(
                self._time, y, pen=pg.mkPen("#dddddd", width=1))
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
            pi.hideAxis("right")
            return
        pi.showAxis("right")
        pi.setLabel("right", _CHANNELS[self._right_key][1])
        self._right_curve = pg.PlotCurveItem(pen=pg.mkPen("#ff5555", width=1))
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

    # ── reset ────────────────────────────────────────────────────────────────
    def _reset_current(self):
        if self._cur_file:
            self._load_sensor(self._cur_file)

    # ── flag (Good / Bad, mutually exclusive) ────────────────────────────────
    def _load_flag_state(self):
        bad = self._is_bad(self._cur_stem)
        self.chk_good.blockSignals(True)
        self.chk_bad.blockSignals(True)
        self.chk_good.setChecked(not bad)
        self.chk_bad.setChecked(bad)
        self.chk_good.blockSignals(False)
        self.chk_bad.blockSignals(False)

    def _on_good_toggled(self, checked):
        if checked and self.chk_bad.isChecked():
            self.chk_bad.setChecked(False)
        elif not checked and not self.chk_bad.isChecked():
            self.chk_good.setChecked(True)

    def _on_bad_toggled(self, checked):
        if checked and self.chk_good.isChecked():
            self.chk_good.setChecked(False)
        elif not checked and not self.chk_good.isChecked():
            self.chk_bad.setChecked(True)

    # ── video ────────────────────────────────────────────────────────────────
    def _on_sensor_double_clicked(self, item):
        if item.column() != 1:
            return
        row = item.row()
        if row < 0 or row >= len(self._sensor_rows):
            return
        stem = self._sensor_rows[row]["stem"]
        matches = self._video_matches_for(stem)
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
                f"{len(names)} videos match {stem}:",
                names, 0, False)
            if not ok:
                return
            video_path = matches[names.index(choice)]
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
        if self._index_df is not None and "file" in self._index_df.columns:
            match = self._index_df[self._index_df["file"] == self._cur_stem]
            if not match.empty:
                row = match.iloc[0]
        for name, editor in self._editors.items():
            value = row.get(name, "") if row is not None else ""
            value = "" if pd.isna(value) else value
            editor.set_current(value)
        self.chk_no_annotations.setChecked(False)

        notes = row.get(_NOTES_COL, "") if row is not None else ""
        notes = "" if pd.isna(notes) else str(notes)
        self.txt_notes.setPlainText(notes)

    def _manage_variables(self):
        dlg = VariableListDialog(self.window)
        dlg.exec()

    # ── save + next (window, flag, annotations, dataset) ────────────────────
    @staticmethod
    def _fs():
        return sensor_config.active().output_rate_hz or _FS

    def _window_bounds(self):
        n = len(self._df)
        half_n = int(round(self._win_sec / 2 * self._fs()))
        start = max(0, self._nadir_idx - half_n)
        end = min(n - 1, self._nadir_idx + half_n)
        return start, end

    def _annotation_values(self):
        return {name: editor.current() for name, editor in self._editors.items()}

    def _save_and_next(self):
        if self._df is None or self._lib_root is None:
            return

        values = self._annotation_values()
        has_any = any(v for v in values.values())
        if not has_any and not self.chk_no_annotations.isChecked():
            QMessageBox.warning(
                self.window, "No annotations entered",
                "Enter at least one annotation value, or tick "
                "\"No annotations for this sensor\" to save without any.")
            return

        try:
            start, end = self._window_bounds()
            sliced = self._df.iloc[start:end + 1].copy()

            ms = int(round(self._win_sec * 1000))
            out_dir = self._lib_root / _WIN_DIR
            out_dir.mkdir(parents=True, exist_ok=True)
            sliced.to_csv(out_dir / f"{self._cur_stem}_{ms}ms.csv", index=False)

            nadir_t = float(self._time[self._nadir_idx])
            nadir_v = (float(self._pres[self._nadir_idx])
                      if self._pres is not None else float("nan"))
            flag_value = "Y" if self.chk_bad.isChecked() else "N"
            index_values = {
                _NADIR_T_COL: nadir_t,
                _NADIR_V_COL: nadir_v,
                "nadir_window_start": self._time[start],
                "nadir_window_end": self._time[end],
                _VALIDATED_COL: "Y",
                _BAD_SENS_COL: flag_value,
                _NOTES_COL: self.txt_notes.toPlainText().strip(),
            }
            for name, value in values.items():
                if value:
                    index_values[name] = value
            n = di.set_row_values(self._lib_root, self._cur_stem, index_values)

            target_rows = sensor_config.active().window_samples(self._win_sec)
            block = _standardise(sliced, target_rows)
            if block is None:
                raise ValueError(
                    f"Only {len(sliced)} rows in the window (expected "
                    f"~{target_rows}) - too far from the sensor's boundary.")
            block = block.copy()
            block.insert(0, "file", self._cur_stem)
            insert_at = 1
            meta_cols = self._index_df.columns if self._index_df is not None else []
            meta_row = None
            if self._index_df is not None and "file" in self._index_df.columns:
                match = self._index_df[self._index_df["file"] == self._cur_stem]
                if not match.empty:
                    meta_row = match.iloc[0]
            for col in _META_COLS:
                if col in meta_cols:
                    val = meta_row.get(col, "") if meta_row is not None else ""
                    block.insert(insert_at, col, val)
                    insert_at += 1
            for name in self._editors:
                block[name] = values.get(name, "")
            self._append_to_dataset(block)
        except Exception as e:
            QMessageBox.critical(self.window, "Save error", str(e))
            return

        self._load_index()
        self._populate_sensor_table()
        self.status.emit(
            f"Saved {self._cur_stem} "
            f"({len(self._dataset_stems)} in dataset).", 4000)
        self._jump_next()

    def _jump_next(self):
        pending = [r for r in self._sensor_rows
                  if r["stem"] not in self._dataset_stems]
        if not pending:
            self.status.emit("Every sensor here is in the dataset.", 5000)
            return
        next_row = pending[0]
        for r in range(self.tbl_sensors.rowCount()):
            if self.tbl_sensors.item(r, 0).text() == next_row["stem"]:
                self.tbl_sensors.setCurrentCell(r, 0)
                break
        else:
            self._load_sensor(next_row["path"])
