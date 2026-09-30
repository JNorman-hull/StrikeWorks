# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Annotate (Validate and annotate): the sensor list and filters on the
left, the signal plot and the Validate / Annotations boxes on the right.

A sensor's deployment and treatment are the folders its raw file sits in,
`raw_sens_data/<deployment>/<treatment>/[Run n/]`, which need not match a
planned deployment; a missing level shows as "(ungrouped)". Video is
`<treatment>/VIDEO/<stem>_vid_*.mp4`, matched case-insensitively.

Saving a sensor also adds it to the library's running dataset,
`processed_sens_data/model_features.csv` (`dataset_build.standardise`),
replacing its block if it's already there; opening a library reads that
file back, so review resumes where it stopped. Annotations are optional
per sensor ("No annotations for this sensor").

Validation is validation_core.py, shared with Simple mode: "Auto process
all" saves every sensor's detected window and flags weak HIG peaks for
review; flagged-and-unreviewed sensors list first (amber), then
user-validated (green), auto-validated (purple) and bad (red). Save + next
records the review and moves to the next flagged sensor. "Save and export"
binds every listed sensor's window and annotations into one dataset and
hands it to Model prediction; "Import annotations CSV…" stamps a
spreadsheet of annotations onto the index.
"""
import subprocess
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyqtgraph as pg

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QInputDialog,
    QLabel, QMessageBox, QPlainTextEdit, QPushButton, QSizePolicy, QSplitter,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from . import annotation_schema as asch
from . import deployment_index as di
from . import sensor_config, settings
from . import raw_layout
from . import validation_core as vc
from .annotation_widgets import AnnotationValueEditor, VariableListDialog
from .inventory_widgets import notifier as inventory_notifier
from .library_widgets import LibrarySelector
from .cards import MetaCard, Spinner
from .layout import (
    apply_section_defaults, discard_widget, scroll_page, Section,
    when_visible,
)
from .theme import (
    ACCENT, BAD, NADIR, OK, REGION_EDGE, REGION_FILL, TEXT, TRACE, TRACE2,
    WARN, muted_label, style,
)
from .dataset_build import META_COLS, standardise
from .plot_style import (
    add_export_button, build_export_data, reserve_top_margin,
    set_right_axis_active,
)
from .plot_widgets import (
    CHANNEL_ORDER, CHANNELS, MAX_RIGHT_PTS, CsvLoadThread, NavViewBox,
    decimate, find_col,
)


_BAD_SENS_COL = di.BAD_SENS_COL
_NOTES_COL = "notes"

_FS = 2000
_WIN_SEC = 0.2

# video review opens clips in LosslessCut (not shipped - 900 MB): in
# external_software/ at the repo root from source, beside StrikeWorks.exe
# once packaged (the build puts a readme there saying what to copy in)
LOSSLESSCUT_EXE = settings.app_root() / "external_software" / "LosslessCut.exe"
LOSSLESSCUT_MISSING = (
    "Video review opens clips in LosslessCut, which isn't installed.\n\n"
    f"Copy LosslessCut.exe and all the files that come with it into\n"
    f"{LOSSLESSCUT_EXE.parent}\n\n"
    "(readme.txt in that folder has the download link).")


class _ReviewedOnly(Exception):
    """Save + next with nothing annotated: the review is saved, the
    dataset append is skipped."""


class AnnotationPage(QObject):
    """Binds the Annotate page widgets to ``ui.content_annotate``."""

    status = Signal(str, int)

    def __init__(self, ui, window, session_state=None):
        super().__init__(window)
        self.ui = ui
        self.window = window
        self.session_state = session_state

        self._index_df = None
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
        self._loaded_nadir_idx = None
        self._auto_thread = None
        self._status = (set(), set(), set(), set())   # validation_core.validation_status
        self._exporter = vc.DatasetExporter(self)

        self._build(ui.content_annotate)
        self._connect()
        self._on_lib_changed()
        self._populate_sensor_table()
        self._rebuild_annotation_panel()
        self._set_loaded_enabled(False)

    # ── library selector (shared widget - see library_widgets.py) ────────────
    @property
    def _lib_root(self):
        return self.lib_selector.lib_root

    def _on_lib_changed(self):
        self._load_index()
        self._load_dataset_stems()
        if self.lib_selector.lib_root and not self.lib_selector.syncing:
            self.status.emit(f"Library: {self.lib_selector.lib_root.name}", 4000)

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, frame):
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        outer.addWidget(self.tabs)

        tab_annotate = QWidget()
        self._build_annotate_tab(tab_annotate)
        self.tabs.addTab(tab_annotate, "Annotate")
        self._save_next_shortcut = vc.install_save_next_shortcut(
            tab_annotate, self.tbl_sensors, self._save_and_next)

        tab_report = QWidget()
        self._build_reporting_tab(tab_report)
        self.tabs.addTab(tab_report, "Reporting")
        # hidden for now - its summary still feeds the central report
        # (report_center.annotation_section); with one tab left, no tab bar
        self.tabs.setTabVisible(self.tabs.indexOf(tab_report), False)
        self.tabs.tabBar().setVisible(False)

        apply_section_defaults(frame)

    def _build_annotate_tab(self, frame):
        root = QHBoxLayout(frame)
        root.setContentsMargins(4, 6, 4, 6)
        root.setSpacing(0)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        root.addWidget(split)

        split.addWidget(self._build_browser())

        # laid out like Misclassification analysis: no page-level scroll -
        # the Annotations/Notes boxes keep their natural height, the signal
        # plot takes all the rest (with a minimum so it can't be squeezed
        # away), and this side has a minimum width so the browser can't
        # take the page over
        detail = QWidget()
        detail.setMinimumWidth(560)
        dv = QVBoxLayout(detail)
        dv.setContentsMargins(5, 0, 0, 0)
        dv.setSpacing(8)
        self._build_plot_side(dv)

        lower = QSplitter(Qt.Orientation.Horizontal)
        lower.setChildrenCollapsible(False)
        lower.addWidget(self._build_annotation_side())
        lower.addWidget(self._build_notes_side())
        lower.setSizes([1000, 1000])
        dv.addWidget(lower, stretch=0)

        split.addWidget(detail)
        # stretch factors, not just initial sizes - the browser keeps its
        # share, and any spare width goes to the signal plot
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)
        split.setSizes([1000, 3000])

    def _build_reporting_tab(self, frame):
        v = scroll_page(frame)

        grp_sum = Section("Annotation summary")
        sv = QVBoxLayout(grp_sum)
        self.card_report = MetaCard("Library")
        sv.addWidget(self.card_report)
        v.addWidget(grp_sum)

        grp_vars = Section("By annotation variable")
        vv = QVBoxLayout(grp_vars)
        self.tbl_report_vars = QTableWidget(0, 3)
        self.tbl_report_vars.setHorizontalHeaderLabels(
            ["Variable", "Value", "Count"])
        self.tbl_report_vars.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_report_vars.setMinimumHeight(180)
        vv.addWidget(self.tbl_report_vars)
        v.addWidget(grp_vars, stretch=1)

        grp_gen = Section("Dataset report")
        gv = QVBoxLayout(grp_gen)
        self.lbl_report_status = QLabel("")
        style(self.lbl_report_status, role="muted")
        self.lbl_report_status.setWordWrap(True)
        gv.addWidget(self.lbl_report_status)
        self.btn_generate_report = QPushButton("Generate dataset report")
        self.btn_generate_report.setMinimumHeight(30)
        style(self.btn_generate_report, role="primary")
        self.btn_generate_report.clicked.connect(self._generate_report)
        gv.addWidget(self.btn_generate_report)
        v.addWidget(grp_gen)

        v.addStretch()

    def _build_browser(self):
        left = QWidget()
        left.setMinimumWidth(360)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 5, 0)
        lv.setSpacing(8)

        self.lib_selector = LibrarySelector(self.session_state, sensor_list=True,
                                            list_columns=["Video", "In dataset"])
        lv.addWidget(self.lib_selector, stretch=1)
        # kept as aliases so the rest of this module's existing references
        # (chk_show_flags, tbl_sensors, lbl_progress) keep working unchanged
        self.chk_show_flags = self.lib_selector.chk_show_flags
        self.tbl_sensors = self.lib_selector.tbl_sensors
        self.lbl_progress = self.lib_selector.lbl_progress

        self.lbl_loading = QLabel("")
        style(self.lbl_loading, role="muted")
        lv.addWidget(self.lbl_loading)

        grp_val = Section("Validate")
        gv = QVBoxLayout(grp_val)
        gv.setSpacing(4)
        auto_row = QHBoxLayout()
        self.btn_auto_process = QPushButton("Auto process all")
        style(self.btn_auto_process, role="strong", tone="ok")
        self.btn_auto_process.setToolTip(
            "Accept every listed sensor's detected nadir and save its window "
            "- sensors whose window shows a weak HIG peak are flagged for "
            "you to review. Sensors already validated are left alone.\n\n"
            "Tip: press Auto process all first, then review the sensors it "
            "flagged (orange, at the top of the list) with Save + next "
            f"({vc.SAVE_NEXT_KEYS}) - the arrow keys move through the list.")
        self.btn_auto_process.clicked.connect(self._auto_process_all)
        auto_row.addWidget(self.btn_auto_process)
        self._auto_spinner = Spinner(size=18)
        self._auto_spinner.setVisible(False)
        auto_row.addWidget(self._auto_spinner)
        auto_row.addStretch()
        gv.addLayout(auto_row)
        lbl_legend = QLabel(vc.legend_html(OK, WARN, BAD, ACCENT, TEXT,
                                           columns=2))
        lbl_legend.setToolTip(vc.legend_html(OK, WARN, BAD, ACCENT, TEXT))
        style(lbl_legend, role="muted")
        lbl_legend.setWordWrap(True)
        gv.addWidget(lbl_legend)

        # the current sensor's review: Good/Bad, then Save + next / Reset
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

        act = QHBoxLayout()
        self.btn_save_next = QPushButton(f"Save + next  ({vc.SAVE_NEXT_KEYS})")
        self.btn_save_next.setToolTip(
            f"Save + next ({vc.SAVE_NEXT_KEYS}) records your review of this "
            "sensor's window - clearing its flag - with its Good/Bad flag "
            "and any annotations or notes, extracts the ROI window for model "
            "training and/or blade strike prediction (appending it to the "
            "dataset when it's annotated), and moves on to the next sensor "
            "in the list.")
        style(self.btn_save_next, role="primary")
        self.btn_save_next.clicked.connect(self._save_and_next)
        self.btn_reset = QPushButton("Reset sensor")
        self.btn_reset.setToolTip("Reload this sensor's file without saving.")
        self.btn_reset.clicked.connect(self._reset_current)
        act.addWidget(self.btn_save_next)
        act.addWidget(self.btn_reset)
        act.addStretch()
        gv.addLayout(act)
        self.lbl_validate_status = QLabel("")
        style(self.lbl_validate_status, role="muted")
        self.lbl_validate_status.setWordWrap(True)
        gv.addWidget(self.lbl_validate_status)
        ds_row = QHBoxLayout()
        self.btn_save_export = QPushButton("Save and export")
        style(self.btn_save_export, role="strong", tone="bad")
        self.btn_save_export.setToolTip(
            "Bind every listed sensor's saved window, with its annotations, "
            "into one dataset - written to the input data folder and the "
            "library's running dataset, and passed to Model prediction.")
        self.btn_save_export.clicked.connect(self._save_and_export)
        ds_row.addWidget(self.btn_save_export)
        self.btn_import_annotations = QPushButton("Import annotations CSV…")
        self.btn_import_annotations.setToolTip(
            "Stamp a spreadsheet of per-sensor annotations (a 'file' column "
            "plus annotation columns) onto this library's sensors.")
        self.btn_import_annotations.clicked.connect(self._import_annotations)
        ds_row.addWidget(self.btn_import_annotations)
        ds_row.addStretch()
        gv.addLayout(ds_row)
        lv.addWidget(grp_val)
        return left

    def _build_plot_side(self, v):
        grp_sig = Section("Signal")
        sv = QVBoxLayout(grp_sig)
        sv.setSpacing(6)

        axis_row = QHBoxLayout()
        self.cmb_left = QComboBox()
        for key in CHANNEL_ORDER:
            self.cmb_left.addItem(CHANNELS[key][1], key)
        self.cmb_left.setCurrentIndex(CHANNEL_ORDER.index(self._left_key))
        self.cmb_right = QComboBox()
        self.cmb_right.addItem("None", None)
        for key in CHANNEL_ORDER:
            self.cmb_right.addItem(CHANNELS[key][1], key)
        axis_row.addWidget(muted_label("Left"))
        axis_row.addWidget(self.cmb_left, stretch=1)
        axis_row.addWidget(muted_label("Right"))
        axis_row.addWidget(self.cmb_right, stretch=1)
        sv.addLayout(axis_row)

        win_row = QHBoxLayout()
        win_row.addWidget(muted_label("ROI window"))
        self.cmb_window = QComboBox()
        win_row.addWidget(self.cmb_window)
        self._spinner = Spinner(size=18)
        self._spinner.setVisible(False)
        win_row.addWidget(self._spinner)
        win_row.addStretch()
        add_export_button(win_row, self._export_data, self.window,
                          file_stub="annotate")
        sv.addLayout(win_row)

        plot_holder = QWidget()
        plot_holder.setSizePolicy(QSizePolicy.Policy.Expanding,
                                  QSizePolicy.Policy.Expanding)
        ph = QVBoxLayout(plot_holder)
        ph.setContentsMargins(0, 0, 0, 0)
        self._pw = pg.PlotWidget(viewBox=NavViewBox())
        self._pw.setMinimumHeight(260)
        pi = self._pw.plotItem
        pi.getViewBox().setMouseMode(pg.ViewBox.RectMode)
        pi.setLabel("bottom", "Time (s)")
        reserve_top_margin(pi)
        ph.addWidget(self._pw)
        sv.addWidget(plot_holder, stretch=1)

        self._vb2 = pg.ViewBox()
        pi.scene().addItem(self._vb2)
        pi.getAxis("right").linkToView(self._vb2)
        self._vb2.setXLink(pi)
        set_right_axis_active(pi, False)
        pi.vb.sigResized.connect(self._sync_vb2)
        pi.vb.sigXRangeChanged.connect(self._on_xrange_changed)

        self._nadir_line = pg.InfiniteLine(
            angle=90, movable=True,
            pen=pg.mkPen(color=NADIR, width=3),
            label="Nadir",
            labelOpts={"position": 0.92, "color": (180, 150, 0)})
        self._nadir_line.sigPositionChanged.connect(self._on_nadir_moved)
        self._region = pg.LinearRegionItem(
            movable=False, brush=pg.mkBrush(*REGION_FILL),
            pen=pg.mkPen(*REGION_EDGE))
        pi.addItem(self._region)
        pi.addItem(self._nadir_line)

        v.addWidget(grp_sig, stretch=1)

    def _build_annotation_side(self):
        grp = Section("Annotations")
        gv = QVBoxLayout(grp)
        gv.setSpacing(6)

        self.annotation_grid = QGridLayout()
        self.annotation_grid.setVerticalSpacing(6)
        self.annotation_grid.setColumnStretch(1, 1)
        gv.addLayout(self.annotation_grid)

        self.chk_no_annotations = QCheckBox("No annotations for this sensor")
        gv.addWidget(self.chk_no_annotations)

        btn_row = QHBoxLayout()
        self.btn_save_annotations = QPushButton("Save annotations")
        self.btn_save_annotations.setToolTip(
            "Save the Good/Bad flag, annotation values and notes for this "
            "sensor and stay here - for a quick pass through a library's "
            "annotations without also finalising each window.")
        self.btn_save_annotations.clicked.connect(self._save_annotations)
        btn_row.addWidget(self.btn_save_annotations)
        self.btn_manage_vars = QPushButton("Manage variables…")
        self.btn_manage_vars.clicked.connect(self._manage_variables)
        btn_row.addWidget(self.btn_manage_vars)
        btn_row.addStretch()
        gv.addLayout(btn_row)

        self.lbl_annotation_status = QLabel("")
        style(self.lbl_annotation_status, role="muted")
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
    def _row(label, widget):
        r = QHBoxLayout()
        r.addWidget(label)
        r.addWidget(widget, stretch=1)
        return r

    def _connect(self):
        self.lib_selector.library_changed.connect(self._on_lib_changed)
        self.lib_selector.filters_changed.connect(self._populate_sensor_table)
        # "Show bad sensors" re-renders from LibrarySelector's own cache
        # (no filesystem rescan needed) - see populate_sensor_list()
        self.tbl_sensors.itemSelectionChanged.connect(self._on_row_selected)
        self.tbl_sensors.itemDoubleClicked.connect(self._on_sensor_double_clicked)

        self.cmb_left.currentIndexChanged.connect(self._on_axis_changed)
        self.cmb_right.currentIndexChanged.connect(self._on_axis_changed)
        self.cmb_window.currentIndexChanged.connect(self._on_win_size_changed)
        sensor_config.notifier.changed.connect(self._on_sensor_changed)
        asch.notifier.changed.connect(self._rebuild_annotation_panel)
        self._exporter.finished.connect(self._on_export_done)
        inventory_notifier.processed.connect(self._on_library_processed)
        self._fill_window_combo()

    def _set_loaded_enabled(self, enabled):
        for b in (self.btn_save_next, self.btn_save_annotations, self.btn_reset):
            b.setEnabled(enabled)
        for c in (self.chk_good, self.chk_bad):
            c.setEnabled(enabled)

    # ── libraries ────────────────────────────────────────────────────────────
    # ── index ────────────────────────────────────────────────────────────────
    def _load_index(self):
        self._index_df = di.read_index(self._lib_root) if self._lib_root else None
        self._status = vc.validation_status(self._index_df)

    def _is_bad(self, stem: str) -> bool:
        # the precomputed bad set, not a dataframe filter per sensor
        # (thousands of those for a big library, on every re-list)
        return stem in self._status[3]

    # ── the running dataset (resume support) ─────────────────────────────────
    def _dataset_path(self):
        return self._lib_root / raw_layout.DATASET_REL

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
        except (OSError, ValueError) as e:
            self.status.emit(f"Could not read the running dataset: {e}", 6000)
            self._dataset_stems = set()

    def _append_to_dataset(self, block: pd.DataFrame):
        vc.merge_into_running_dataset(self._lib_root, block)
        self._dataset_stems.add(self._cur_stem)

    # ── sensor table ─────────────────────────────────────────────────────────
    def _populate_sensor_table(self):
        if self._lib_root is None:
            self._sensor_rows = []
            self.tbl_sensors.setRowCount(0)
            self.lbl_progress.setText("")
            self._refresh_report()
            return

        rows = []
        for row in self.lib_selector.list_sensor_csvs():
            matches = self.lib_selector.video_matches_for(row["stem"])
            rows.append({
                **row,
                "video": "; ".join(m.name for m in matches) if matches else "-",
            })
        self._sensor_rows = rows
        self._status = vc.validation_status(self._index_df)
        status = self._status

        def progress(all_rows):
            stems = [r["stem"] for r in all_rows]
            n_ds = sum(1 for s in stems if s in self._dataset_stems)
            return (vc.counts_text(stems, status).replace("\n", "   ")
                    + f"   In dataset: {n_ds}/{len(stems)}")

        # flagged-and-unreviewed first, coloured by validation state -
        # validation_core's one convention, the same as Simple mode's list
        self.lib_selector.populate_sensor_list(
            rows, is_bad=self._is_bad,
            is_done=lambda stem: stem in self._dataset_stems,
            extra=lambda r: [r["video"],
                             "Yes" if r["stem"] in self._dataset_stems else "-"],
            colour=lambda stem: vc.status_colour(stem, status, OK, WARN, BAD, ACCENT),
            order_key=lambda r: not vc.needs_review(r["stem"], status),
            progress=progress)
        self._refresh_report()

    # ── reporting tab ────────────────────────────────────────────────────────
    def _library_sensor_rows(self):
        """Every sensor index row for the whole library, plan rows dropped -
        the Reporting tab summarises the library, not the current
        deployment/treatment filter the browser happens to be showing."""
        if self._index_df is None:
            return None
        return di.sensor_rows(self._index_df)

    def _variable_value_counts(self, df):
        """[(variable label, value, count), ...] across every annotated
        sensor row, one group per variable - numeric levels (concentric
        pump region) in their own order (1, 2, 3...), anything else most
        common value first."""
        from .ml_train_state import level_key
        rows = []
        for var in asch.all_variables():
            if var.name not in df.columns:
                continue
            values = df[var.name].astype(str).str.strip()
            values = values[values.astype(bool) & (values.str.lower() != "nan")]
            # a numeric-looking annotation column (e.g. concentric_pump_region)
            # round-trips through the index CSV as float ("2.0") even when
            # the value stored was the plain string "2" - normalise so
            # in-session and reloaded-from-disk values count identically,
            # same rule the training pipeline already applies (level_key)
            values = values.map(level_key)
            counts = list(values.value_counts().items())
            try:
                counts.sort(key=lambda vc: float(vc[0]))
            except ValueError:
                pass   # text levels - keep most common first
            for value, count in counts:
                rows.append((var.label, value, int(count)))
        return rows

    def _refresh_report(self):
        df = self._library_sensor_rows()
        if self._lib_root is None or df is None:
            self.card_report.set_title("Library")
            self.card_report.set_rows([])
            self.tbl_report_vars.setRowCount(0)
            self.lbl_report_status.setText(
                "Open a library to see its annotation summary.")
            return

        total = len(df)
        in_dataset = len(self._dataset_stems)
        bad = 0
        if _BAD_SENS_COL in df.columns:
            bad = int((df[_BAD_SENS_COL].astype(str).str.strip().str.upper()
                      == "Y").sum())

        self.card_report.set_title(f"Library: {self._lib_root.name}")
        self.card_report.set_rows([
            ("Sensors in index", total or None),
            ("In dataset (annotated + saved)", in_dataset or None),
            ("Not yet in dataset", (total - in_dataset) or None),
            ("Flagged bad", bad or None),
        ] + self._review_rows(df))

        rows = self._variable_value_counts(df)
        self.tbl_report_vars.setRowCount(len(rows))
        for r, (label, value, count) in enumerate(rows):
            self.tbl_report_vars.setItem(r, 0, QTableWidgetItem(label))
            self.tbl_report_vars.setItem(r, 1, QTableWidgetItem(str(value)))
            item = QTableWidgetItem(str(count))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tbl_report_vars.setItem(r, 2, item)
        self.tbl_report_vars.resizeColumnsToContents()

        self.lbl_report_status.setText(
            f"{in_dataset} of {total} sensor(s) in the dataset. Updates "
            "live as you annotate.")
        style(self.lbl_report_status, role="muted")

    def _generate_report(self):
        df = self._library_sensor_rows()
        if self._lib_root is None or df is None:
            return

        total = len(df)
        in_dataset = len(self._dataset_stems)
        bad = 0
        if _BAD_SENS_COL in df.columns:
            bad = int((df[_BAD_SENS_COL].astype(str).str.strip().str.upper()
                      == "Y").sum())

        lines = [
            f"# Annotation report - {self._lib_root.name}",
            "",
            f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "## Summary",
            "",
            f"- Sensors in index: {total}",
            f"- In dataset (annotated + saved): {in_dataset}",
            f"- Not yet in dataset: {total - in_dataset}",
            f"- Flagged bad: {bad}",
            "",
            "## Validation",
            "",
        ]
        review = self._review_rows(df)
        lines += ([f"- {label}: {value}" for label, value in review]
                  or ["No sensors validated yet."])
        lines += [
            "",
            "## By annotation variable",
            "",
        ]
        by_var = {}
        for label, value, count in self._variable_value_counts(df):
            by_var.setdefault(label, []).append((value, count))
        if by_var:
            for label, values in by_var.items():
                lines.append(f"### {label}")
                lines.append("")
                for value, count in values:
                    lines.append(f"- {value}: {count}")
                lines.append("")
        else:
            lines.append("No annotation values recorded yet.")

        out_path = self._lib_root / raw_layout.PROCESSED_DIR / "annotation_report.md"
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text("\n".join(lines))
        except Exception as e:
            QMessageBox.critical(self.window, "Report failed", str(e))
            return

        self.lbl_report_status.setText(f"Report written to {out_path}")
        style(self.lbl_report_status, tone="ok")
        self.status.emit(f"Dataset report saved to {out_path}", 5000)

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

        loader = CsvLoadThread(path)
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
        time_col = find_col(df, ["time_s", "time"], keyword="time")
        pres_col = find_col(df, ["pressure_kpa", vc.NADIR_V_COL], keyword="pressure")

        time = (df[time_col].to_numpy(dtype=float) if time_col
                else np.arange(len(df), dtype=float) / self._fs())

        self._df = df
        self._time = time
        self._pres = df[pres_col].to_numpy(dtype=float) if pres_col else None
        self._cur_file = path
        self._cur_stem = path.stem

        self._nadir_idx = vc.detect_nadir_idx(self._cur_stem, df, time,
                                              self._pres, self._index_df)
        # the as-loaded nadir - Save + next compares against it to record
        # whether a person actually moved it (validation_core user adjusted)
        self._loaded_nadir_idx = self._nadir_idx

        self._draw_plot()
        self._load_flag_state()
        self._load_annotations_for_current()
        self._set_loaded_enabled(True)
        self.status.emit(f"Loaded: {path.name}", 3000)

    # ── plot (left/right axis) ─────────────────────────────────────────────
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
            self._curve = self._pw.plot(
                self._time, y, pen=pg.mkPen(TRACE, width=1))
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

    def _export_data(self):
        (x0, x1), _ = self._pw.plotItem.vb.viewRange()
        left_label = CHANNELS[self._left_key][1] if self._left_key else ""
        right_label = CHANNELS[self._right_key][1] if self._right_key else ""
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
        # read the stem from the clicked row itself (column 0's text), not
        # by list index - "Show bad sensors" unticked hides rows from the
        # table, so a visible row's index no longer matches its position
        # in the unfiltered self._sensor_rows
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
                                LOSSLESSCUT_MISSING)
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
                discard_widget(w)
        self._editors = {}
        for row, var in enumerate(asch.all_variables()):
            lab = muted_label(var.label)
            editor = AnnotationValueEditor(var.name)
            self.annotation_grid.addWidget(lab, row, 0)
            self.annotation_grid.addWidget(editor, row, 1)
            self._editors[var.name] = editor
        if self._cur_stem:
            self._load_annotations_for_current()

    def _load_annotations_for_current(self):
        from .ml_train_state import level_key
        row = None
        if self._index_df is not None and "file" in self._index_df.columns:
            match = self._index_df[self._index_df["file"] == self._cur_stem]
            if not match.empty:
                row = match.iloc[0]
        for name, editor in self._editors.items():
            value = row.get(name, "") if row is not None else ""
            value = "" if pd.isna(value) else level_key(value)
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
        return vc.window_bounds(self._nadir_idx, len(self._df), self._win_sec,
                                self._fs())

    def _annotation_values(self):
        return {name: editor.current() for name, editor in self._editors.items()}

    def _has_annotation_content(self, values):
        return (any(v for v in values.values())
                or bool(self.txt_notes.toPlainText().strip())
                or self.chk_no_annotations.isChecked())

    def _has_content_to_save(self, values):
        """Shared gate for both save actions: at least one annotation
        value, a note, or an explicit "no annotations" tick - a note alone
        (no formal annotation) is enough, since Save annotations exists
        specifically to let a note stand on its own."""
        has_any = any(v for v in values.values())
        has_notes = bool(self.txt_notes.toPlainText().strip())
        if has_any or has_notes or self.chk_no_annotations.isChecked():
            return True
        QMessageBox.warning(
            self.window, "Nothing to save",
            "Enter at least one annotation value or a note, or tick "
            "\"No annotations for this sensor\" to save without any.")
        return False

    def _save_annotations(self):
        """Flag + annotation values + notes only - no window extraction, no
        dataset entry, no jump to the next sensor. For working through a
        library's annotations/notes without also finalising each ROI
        window every time, or to save a note mid-review without losing
        your place."""
        if self._df is None or self._lib_root is None:
            return
        values = self._annotation_values()
        if not self._has_content_to_save(values):
            return

        flag_value = "Y" if self.chk_bad.isChecked() else "N"
        index_values = {
            _BAD_SENS_COL: flag_value,
            _NOTES_COL: self.txt_notes.toPlainText().strip(),
        }
        for name, value in values.items():
            if value:
                index_values[name] = value
        try:
            di.set_row_values(self._lib_root, self._cur_stem, index_values)
        except Exception as e:
            QMessageBox.critical(self.window, "Save error", str(e))
            return

        self._load_index()
        self._populate_sensor_table()
        self.status.emit(f"Saved annotations for {self._cur_stem}.", 4000)

    def _save_and_next(self):
        """Save + next (Ctrl+V): records a human review of the window -
        which clears the sensor's flag - and moves to the next sensor in
        the list. With annotation values or a note entered they're saved
        and the window is appended to the dataset too; without, it's just
        the review (no empty annotations written)."""
        if self._df is None or self._lib_root is None:
            return
        # a sensor still loading (in the background) would otherwise have
        # Ctrl+V re-save the previous one - the buttons are off meanwhile
        if not self.btn_save_next.isEnabled():
            return

        values = self._annotation_values()
        annotated = self._has_annotation_content(values)
        stem = self._cur_stem
        order = [self.tbl_sensors.item(r, 0).text()
                 for r in range(self.tbl_sensors.rowCount())]

        try:
            start, end = self._window_bounds()
            sliced = self._df.iloc[start:end + 1].copy()

            # window + nadir + validation state through validation_core
            # (the same save Simple mode's Save + Next does - a human review:
            # user validated, and user adjusted if the nadir was moved)
            index_df = di.read_index(self._lib_root)
            index_df = vc.save_window(
                self._lib_root, index_df, self._cur_stem, self._df,
                self._nadir_idx, self._win_sec, user_validated=True,
                nadir_changed=(self._loaded_nadir_idx is not None
                               and self._nadir_idx != self._loaded_nadir_idx))
            flag_value = "Y" if self.chk_bad.isChecked() else "N"
            index_values = {_BAD_SENS_COL: flag_value}
            if annotated:
                index_values[_NOTES_COL] = self.txt_notes.toPlainText().strip()
                for name, value in values.items():
                    if value:
                        index_values[name] = value
            mask = index_df["file"].astype(str) == self._cur_stem
            for col, value in index_values.items():
                if col not in index_df.columns:
                    index_df[col] = ""
                index_df[col] = index_df[col].astype(object)
                index_df.loc[mask, col] = value
            vc.write_index(self._lib_root, index_df)
            self._index_df = index_df
            if not annotated:
                raise _ReviewedOnly()

            target_rows = sensor_config.active().window_samples(self._win_sec)
            block = standardise(sliced, target_rows)
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
            for col in META_COLS:
                if col in meta_cols:
                    val = meta_row.get(col, "") if meta_row is not None else ""
                    block.insert(insert_at, col, val)
                    insert_at += 1
            for name in self._editors:
                block[name] = values.get(name, "")
            self._append_to_dataset(block)
            message = (f"Saved {stem} ({len(self._dataset_stems)} in "
                       "dataset).")
        except _ReviewedOnly:
            message = f"Reviewed {stem} (no annotations entered)."
        except Exception as e:
            QMessageBox.critical(self.window, "Save error", str(e))
            return

        self._load_index()
        self._populate_sensor_table()
        self.status.emit(message, 4000)
        self.lbl_validate_status.setText(message)
        target = vc.next_after_save(order, stem, self._status)
        row = next((r for r in self._sensor_rows if r["stem"] == target), None)
        if row is not None:
            self._select_row(row)
        else:
            self.status.emit(f"{stem} saved - end of the list.", 4000)
        # keep the arrow keys / Ctrl+V on the list after a button click
        self.tbl_sensors.setFocus()

    def _select_row(self, row):
        for r in range(self.tbl_sensors.rowCount()):
            if self.tbl_sensors.item(r, 0).text() == row["stem"]:
                self.tbl_sensors.setCurrentCell(r, 0)
                break
        # after a save the table is rebuilt and the next sensor can slide
        # into the row that's already selected - selecting it again then
        # changes nothing and loads nothing, so load it here instead
        if (self._cur_stem != row["stem"]
                and self._pending_path != row["path"]):
            self._load_sensor(row["path"])

    # ── validation (validation_core.py) ──────────────────────────────────────
    def _review_rows(self, df):
        stems = [str(s) for s in df["file"]] if df is not None and "file" in df.columns else []
        return vc.processing_review_rows(stems, self._index_df)

    def _auto_process_all(self):
        """Auto process all over the listed sensors (the filters apply) -
        returns the thread, or None with nothing to do."""
        if self._lib_root is None or not self._sensor_rows:
            return None
        if self._auto_thread is not None and self._auto_thread.isRunning():
            return self._auto_thread
        self.btn_auto_process.setEnabled(False)
        self.btn_save_export.setEnabled(False)
        self._auto_spinner.start()
        self.lbl_validate_status.setText("Auto-processing…")
        files = [{"stem": r["stem"], "path": r["path"]} for r in self._sensor_rows]
        self._auto_thread = vc.AutoProcessThread(
            self._lib_root, self._win_sec, files, di.read_index(self._lib_root))
        self._auto_thread.progress.connect(
            lambda d, t: self.lbl_validate_status.setText(f"Auto-processing… {d}/{t}"))
        self._auto_thread.done.connect(self._on_auto_done)
        self._auto_thread.start()
        return self._auto_thread

    def _on_auto_done(self, index_df, n_done):
        self._auto_spinner.stop()
        self.btn_auto_process.setEnabled(True)
        self.btn_save_export.setEnabled(True)
        if self._lib_root is not None:
            vc.write_index(self._lib_root, index_df)
        self._load_index()
        self._populate_sensor_table()
        stems = [r["stem"] for r in self._sensor_rows]
        n_flagged = vc.status_counts(stems, self._status)["flagged"]
        msg = f"Auto-processed {n_done} sensor(s), {n_flagged} flagged for review."
        self.lbl_validate_status.setText(msg)
        self.status.emit(msg, 5000)

    def _save_and_export(self):
        if self._lib_root is None or self._exporter.running or not self._sensor_rows:
            return
        stems = [r["stem"] for r in self._sensor_rows]
        outstanding = vc.outstanding_flagged(stems, self._status)
        if outstanding and self.window.isVisible():
            n_flagged = vc.status_counts(stems, self._status)["flagged"]
            reply = QMessageBox.question(
                self.window, "Sensors flagged for review",
                f"Caution, {len(outstanding)}/{n_flagged} flagged sensors "
                "still need user-validation. Export anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return
        dep = self.lib_selector.wanted_deployment()
        name = self._lib_root.name + (f"_{dep}" if dep else "")
        self.btn_save_export.setEnabled(False)
        self.lbl_validate_status.setText("Building dataset…")
        self._exporter.start(self._lib_root, name, selected=set(stems))

    def _on_export_done(self, df, path, message):
        self.btn_save_export.setEnabled(True)
        self.lbl_validate_status.setText(message)
        if df is None:
            self.status.emit(message, 6000)
            return
        settings.add_recent_training_dataset(path)
        self.window.ml_prediction_page.on_dataset_ready(
            df, f"Annotate - {path.stem}")
        self._load_dataset_stems()
        self._populate_sensor_table()
        self.status.emit(message, 6000)

    def _import_annotations(self, path=None):
        """`path` skips the file picker (demo runner)."""
        if self._lib_root is None:
            return 0
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                self.window, "Import annotations CSV", str(self._lib_root),
                "CSV files (*.csv)")
            if not path:
                return 0
        try:
            n, names = vc.import_annotations_csv(self._lib_root, path)
        except Exception as e:
            QMessageBox.warning(self.window, "Import failed", str(e))
            return 0
        self._load_index()
        self._populate_sensor_table()
        if self._cur_stem:
            self._load_annotations_for_current()
        msg = (f"Imported {', '.join(names)} for {n} sensor(s) from "
               f"{Path(path).name}.")
        self.lbl_validate_status.setText(msg)
        self.status.emit(msg, 6000)
        return n

    def _on_library_processed(self, root):
        """A processing batch just finished somewhere (Raw data processing
        or Simple mode) - pick up its new sensors if it was this library."""
        if self._lib_root is not None and Path(root) == Path(self._lib_root):
            # a rescan re-emits library_changed, which reloads the index and
            # dataset stems too - deferred until this page is looked at
            when_visible(self.lib_selector, self.lib_selector.rescan, key="scan")
