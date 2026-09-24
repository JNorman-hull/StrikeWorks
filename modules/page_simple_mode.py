# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Simple mode - a guided, one-window walkthrough of Deployment > Process >
Predict > Report, and (2026-09-11) the app's default landing experience -
main.py opens it automatically on launch, ahead of the full Advanced GUI.
Spec: simple_spec/Home.png, Deploy.png, Validate.png, Predict.png
(2026-09-11, superseding the earlier simple_spec/1.png-7.png drafts).

Every step below calls the *same* backend pieces Advanced mode's pages
use - `deployment_index`, `sensor_config`, `_ProcessThread` (page_process.py),
`_ExtractThread` (page_dataset.py), the shared `PredictionState`
(`window.ml_prediction_page.state`), `ml_figures`, `ml_report` - nothing
new was invented at the data layer, only a much smaller front end sits on
top of it, per the spec images.

Two things this pass adds that Advanced mode doesn't have an equivalent
of, both from the spec:

  Auto process all  - accepts every processed sensor's own already-
                      detected nadir/ROI (the same detection Validate
                      falls back to - `pres_min.time.` from the index, or
                      the pressure minimum) and saves it, with zero
                      per-file manual review. Sensors already flagged
                      bad_sens=Y by Process (not computed here - that
                      flag already exists in the index by this point)
                      stay flagged; nothing here overrides it to "good".
  Save and export   - Dataset creation's "bind segmented windows" step,
                      folded into one click that also writes straight
                      into input_data/ instead of a save-file dialog.

The signal preview's nadir line is draggable, same as Advanced mode's
Validate page - Auto process all handles the bulk case with zero
per-file review, but any sensor (already validated or not) can still be
corrected by hand and re-saved with Save + Next.
"""
import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyqtgraph as pg
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QGridLayout, QHBoxLayout,
    QLabel, QLayout, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QScrollArea, QSizePolicy, QSpinBox, QStackedWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import deployment_index as di
from . import ml_figures, ml_report, sensor_config, settings, win_utils
from .ml_widgets import (
    ACCENT, BAD, MUTED, OK, PALETTE, PINK, TEXT, WARN, MetaCard, RingCard,
    Section, Spinner, apply_section_defaults, style_table,
)
from .page_dataset import OPT_SEGMENTED, _ExtractThread, _standardise
from .plot_style import add_export_button, build_export_data
from .page_home import library_status_rows
from .page_initiate_deployment import _README_TEXT
from .page_process import _ProcessThread, _parse_name

pg.setConfigOptions(antialias=True, background="#21252b",
                    foreground="#c8cdd6")

_RAW_DIR = Path("raw_sens_data")
_CSV_DIR = Path("processed_sens_data") / "csv"
_INDEX_REL = di.INDEX_REL
_VIDEO_FOLDER_NAME = "VIDEO"
_NADIR_T_COL = "pres_min.time."
_NADIR_V_COL = "pres_min.kPa."
_VALIDATED_COL = "hstrike_processed"   # Y once a window's been saved at all - auto OR user
_USER_VALIDATED_COL = "hstrike_user_validated"   # Y only once a human reviewed it
_FLAGGED_COL = "hstrike_flagged"   # Y = auto process's own "worth a look" heuristic
_USER_ADJUSTED_COL = "hstrike_user_adjusted"   # Y = human moved the nadir and re-saved
_HIG_WINDOW_MAX_COL = "hstrike_hig_window_max_g"
# Auto process all's one heuristic for "this nadir position might be
# wrong": a real blade-strike window should show a real HIG (impact
# accelerometer) peak - a low one inside the saved window suggests Auto
# process picked a window that missed the actual event. Ad hoc, and
# deliberately just one check for now (not a hard science threshold) -
# the goal is to point a human at the sensors worth a second look, not to
# auto-reject anything; Auto process all still saves every sensor's
# window regardless of this flag.
_FLAG_HIG_THRESHOLD_G = 95.0
_WIN_SEC = 0.2
_WIN_DIR = Path("processed_sens_data") / "nadir_window"
_NEW_DEPLOYMENT = "__new__"
_IMAGES_DIR = Path(__file__).parent.parent / "images" / "images"
_ICON_PATH = Path(__file__).parent.parent / "icon.ico"

# The left step list: (label, indent level, stack page index or None).
# None means a non-clickable group heading - "Process" and "Report" are
# each a heading over two real pages (file inventory/validate,
# report-view/download) rather than a page of their own.
_LIST_ITEMS = [
    ("Home",     0, 0),
    ("Deploy",   0, 1),
    ("Process",  0, None),
    ("Process",  1, 2),
    ("Validate", 1, 3),
    ("Predict",  0, 4),
    ("Report",   0, None),
    ("Output",   1, 5),
    ("Download", 1, 6),
]

# pages that already show their own big logo - the small horizontal one
# (fixed bottom-left, present on every other page) would just duplicate it
_NO_SMALL_LOGO_PAGES = {0, 6}

# the guidance line shown above Back/Next/Close, per stack page index -
# spec text where the mockups (simple_spec/Home.png, Deploy.png,
# Validate.png, Predict.png) give it, short consistent text of the same
# kind for the three steps they don't cover
_GUIDANCE = {
    0: "Pressing next continues with blade strike prediction…",
    1: "Create a deployment and add data to continue…",
    2: "Select files and process them to continue…",
    3: "Pressing next continues with data saved here or an existing dataset…",
    4: "Continue to plot and export data…",
    5: "Review the report, then continue to download…",
    6: "Download your report to finish, or close.",
}


class _TreatmentTable(QTableWidget):
    """Editable table of treatments - simple_spec/Deploy.png's table view
    ("MAKE TREATMENT ENTRY LIKE AN ACTUAL TABLE? WOULD BE CLEANER"),
    replacing the stacked _TreatmentRow cards (page_initiate_deployment.py)
    Advanced mode still uses - those got visually noisy once a deployment
    has more than a couple of treatments, since each card re-renders its
    own column headers. Simple-mode-only; Advanced mode is untouched.

    One header row, one real data row per treatment: plain editable cells
    for the di.TREATMENT_FIELDS columns, a QSpinBox for the run count, a
    Remove button - deliberately shaped like _TreatmentRow's own
    values()/name() so the call sites barely change.
    """

    changed = Signal()

    _RUNS_COL = len(di.TREATMENT_FIELDS)
    _REMOVE_COL = len(di.TREATMENT_FIELDS) + 1

    def __init__(self, parent=None):
        headers = ([label for _c, label in di.TREATMENT_FIELDS]
                  + ["Number of runs", ""])
        super().__init__(0, len(headers), parent)
        self.setHorizontalHeaderLabels(headers)
        self.verticalHeader().setVisible(False)
        style_table(self)
        self.itemChanged.connect(lambda _i: self.changed.emit())

    def add_row(self, values=None):
        values = values or {}
        row = self.rowCount()
        self.insertRow(row)
        for col, (column, _label) in enumerate(di.TREATMENT_FIELDS):
            self.setItem(row, col, QTableWidgetItem(str(values.get(column, ""))))

        spin = QSpinBox()
        spin.setRange(1, di.MAX_RUNS)
        spin.setValue(int(values.get("runs", 1) or 1))
        spin.setToolTip("Runs can be assigned during processing.")
        spin.valueChanged.connect(lambda _v: self.changed.emit())
        self.setCellWidget(row, self._RUNS_COL, spin)

        btn_remove = QPushButton("Remove")
        btn_remove.setToolTip("Remove this treatment")
        btn_remove.clicked.connect(lambda: self._remove_row_with_widget(btn_remove))
        self.setCellWidget(row, self._REMOVE_COL, btn_remove)

        self.resizeColumnsToContents()
        self.changed.emit()

    def _remove_row_with_widget(self, btn):
        for r in range(self.rowCount()):
            if self.cellWidget(r, self._REMOVE_COL) is btn:
                self.removeRow(r)
                self.changed.emit()
                return

    def row_values(self, row):
        out = {}
        for col, (column, _label) in enumerate(di.TREATMENT_FIELDS):
            item = self.item(row, col)
            out[column] = item.text().strip() if item is not None else ""
        spin = self.cellWidget(row, self._RUNS_COL)
        out["runs"] = spin.value() if spin is not None else 1
        return out

    def all_values(self):
        return [self.row_values(r) for r in range(self.rowCount())]

    def names(self):
        col = next(i for i, (c, _l) in enumerate(di.TREATMENT_FIELDS)
                  if c == di.TREATMENT_COL)
        names = []
        for r in range(self.rowCount()):
            item = self.item(r, col)
            names.append(item.text().strip() if item is not None else "")
        return names

    def clear_rows(self):
        self.setRowCount(0)


class _AutoProcessThread(QThread):
    """Auto process all's own per-sensor loop (nadir detect, save the ROI
    window CSV, update the index, compute the HIG-in-window flag), off
    the GUI thread. Reading + writing 70+ sensors' CSVs one at a time,
    over a library that can be OneDrive-synced, used to run synchronously
    on the GUI thread and simply freeze the app for however long that
    took - no progress, no way to tell it hadn't hung, and pressing
    anything (including trying to close the app) did nothing until it
    finished.

    Self-contained rather than calling back into SimpleModeDialog's own
    _detect_nadir_idx/_window_bounds/_save_one_validated - those are safe
    to call cross-thread in principle (no widget access), but duplicating
    the handful of lines that matter here keeps this thread's contract
    to plain data in, an updated index DataFrame out, with nothing
    implicitly depending on dialog state that could change underneath it
    while it runs."""

    progress = Signal(int, int)          # n done so far, total
    done = Signal(object, int)           # updated index_df, n_done

    def __init__(self, lib_root, win_sec, validate_files, index_df, parent=None):
        super().__init__(parent)
        self._lib_root = lib_root
        self._win_sec = win_sec
        self._validate_files = validate_files
        self._index_df = index_df

    @staticmethod
    def _detect_nadir_idx(stem, df, time, pres, index_df):
        if (index_df is not None and "file" in index_df.columns
                and _NADIR_T_COL in index_df.columns):
            row = index_df[index_df["file"] == stem]
            if not row.empty:
                val = row[_NADIR_T_COL].iloc[0]
                if pd.notna(val):
                    return int(np.argmin(np.abs(time - float(val))))
        if pres is not None and len(pres):
            return int(np.argmin(pres))
        return len(df) // 2

    def run(self):
        index_df = self._index_df
        validated = set()
        if _VALIDATED_COL in index_df.columns:
            validated = set(index_df[index_df[_VALIDATED_COL]
                            .astype(str).str.upper() == "Y"]["file"])

        fs = sensor_config.active().output_rate_hz or 2000
        half_n = int(round(self._win_sec / 2 * fs))
        ms = int(round(self._win_sec * 1000))
        out_dir = self._lib_root / _WIN_DIR
        out_dir.mkdir(parents=True, exist_ok=True)

        for col in (_VALIDATED_COL, _FLAGGED_COL):
            if col not in index_df.columns:
                index_df[col] = ""
            index_df[col] = index_df[col].astype(object)

        total = len(self._validate_files)
        n_done = 0
        for i, f in enumerate(self._validate_files):
            stem = f["stem"]
            if stem in validated:
                self.progress.emit(i + 1, total)
                continue
            try:
                df = pd.read_csv(f["path"], low_memory=False)
            except Exception:
                self.progress.emit(i + 1, total)
                continue
            time = (df["time_s"].to_numpy(dtype=float) if "time_s" in df.columns
                    else np.arange(len(df), dtype=float))
            pres = (df["pressure_kpa"].to_numpy(dtype=float)
                    if "pressure_kpa" in df.columns else None)
            hig = (df["higacc_mag_g"].to_numpy(dtype=float)
                  if "higacc_mag_g" in df.columns else None)
            nadir_idx = self._detect_nadir_idx(stem, df, time, pres, index_df)
            start = max(0, nadir_idx - half_n)
            end = min(len(df) - 1, nadir_idx + half_n)
            df.iloc[start:end + 1].to_csv(out_dir / f"{stem}_{ms}ms.csv", index=False)

            nadir_t = float(time[nadir_idx])
            nadir_v = float(pres[nadir_idx]) if pres is not None else float("nan")
            hig_window_max = (float(np.max(hig[start:end + 1]))
                              if hig is not None and len(hig) else float("nan"))

            mask = index_df["file"] == stem
            if not mask.any():
                new_row = pd.DataFrame([{"file": stem}])
                index_df = pd.concat([index_df, new_row], ignore_index=True)
                index_df[_VALIDATED_COL] = index_df[_VALIDATED_COL].astype(object)
                index_df[_FLAGGED_COL] = index_df[_FLAGGED_COL].astype(object)
                mask = index_df["file"] == stem
            index_df.loc[mask, _NADIR_T_COL] = nadir_t
            index_df.loc[mask, _NADIR_V_COL] = nadir_v
            index_df.loc[mask, "nadir_window_start"] = time[start]
            index_df.loc[mask, "nadir_window_end"] = time[end]
            index_df.loc[mask, _HIG_WINDOW_MAX_COL] = hig_window_max
            index_df.loc[mask, _VALIDATED_COL] = "Y"
            is_flagged = (not np.isnan(hig_window_max)
                         and hig_window_max < _FLAG_HIG_THRESHOLD_G)
            index_df.loc[mask, _FLAGGED_COL] = "Y" if is_flagged else "N"
            n_done += 1
            self.progress.emit(i + 1, total)

        self.done.emit(index_df, n_done)


class SimpleModeDialog(QDialog):
    """Pop-up wizard for Simple mode - the app's default landing
    experience (main.py opens it automatically, right after MainWindow is
    shown). Built once, reopened via `exec()` each time; "Development
    toolkit" on its own Home page (`_go_development_toolkit`) is what
    switches to the full Advanced GUI instead."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle("StrikeWorks")
        self.setWindowIcon(QIcon(str(_ICON_PATH)))
        # resizable, not setFixedSize() - fixing it at exactly 1340x700
        # forced every page's own layout to compress into that regardless
        # of what its content actually needed, which is what was causing
        # overlapping/clipped labels (worst on Deploy, now the tallest
        # page - see its own left column, wrapped in a QScrollArea below
        # for exactly this reason). resize() only sets the *initial* size
        # and setMinimumSize() the floor the user can still shrink it to
        # by hand - it can still grow if a page genuinely needs more.
        #
        # 700 content height doesn't actually fit a 1366x768 screen once
        # the taskbar (~48px) and this window's own title bar (~32px) are
        # accounted for - confirmed directly (a real screenshot showed
        # Back/Next/Close and the logo clipped behind the taskbar), and
        # the old minimum of 650 left almost no real headroom to shrink
        # out of that state by hand. 640/560 both sit comfortably inside
        # a 768-tall screen's usable work area; the real layout-driven
        # minimum (every page's own content) is smaller still (~556x475
        # measured directly), so 900x560 as an explicit floor is a chosen
        # "don't get uncomfortably cramped" limit, not one forced by any
        # page's content.
        self.resize(1340, 640)
        self.setMinimumSize(900, 560)
        # a hard ceiling too - confirmed directly (user testing) that the
        # SetNoConstraint fix above didn't fully stop the jump-while-
        # dragging-by-the-title-bar bug, narrowing it to specifically
        # Deploy/Validate/Predict (the pages with the most dynamic child
        # content: MetaCard.set_rows() rebuilding its grid, pyqtgraph's
        # PlotWidget, RingCard). Whatever the exact trigger turns out to
        # be, Windows' native interactive-move loop negotiates window
        # size against Qt's minimum/maximum directly (WM_GETMINMAXINFO) -
        # a QLayout's own SetConstraint has no say over that - so an
        # explicit maximum is what actually stops it from being able to
        # jump to some larger "natural" size mid-drag, regardless of
        # which internal mechanism was asking for one.
        self.setMaximumSize(1600, 900)
        # this dialog, not MainWindow, is the app's first visible window
        # now (main.py's __main__) - same missing-taskbar-button issue
        # MainWindow itself had and for the same underlying reason (see
        # win_utils.py), just triggered by MainWindow staying hidden as
        # its owner rather than by FramelessWindowHint
        win_utils.ensure_taskbar_button(self)

        self._lib_root = None
        self._deployments = []
        self._process_files = []
        self._process_treatment_by_stem = {}
        self._process_batch_done = []
        self._validate_files = []       # [{"stem","path"}]
        self._cur_validate_stem = None
        # the rest of the currently-loaded sensor's data - previously only
        # ever set inside _load_validate_file() itself, so anything that
        # read them (this Export button included) before a file had ever
        # been loaded hit a bare AttributeError instead of behaving like
        # "nothing loaded yet"
        self._cur_validate_df = None
        self._cur_validate_time = None
        self._cur_validate_pres = None
        self._cur_validate_hig = None
        self._cur_validate_nadir_idx = None
        self._loaded_nadir_idx = None
        self._auto_process_thread = None
        self._validate_dirty = False    # written since the last Save and export
        self._advance_after_export = False   # "Save and continue" on the unsaved-data prompt
        self.went_to_dev_toolkit = False
        self._built_dataset_path = None
        self._win_sec = _WIN_SEC   # ROI window width - user-adjustable via cmb_window
        self._process_thread = None
        self._extract_thread = None

        self._build()
        state = self.window.ml_prediction_page.state
        state.run_finished.connect(self._on_predict_finished)
        state.run_failed.connect(self._on_predict_failed)
        self.window.session_state.library_changed.connect(
            self._on_session_library_changed_simple)

    # ── top-level layout ────────────────────────────────────────────────────
    def _build(self):
        outer = QVBoxLayout(self)
        # a plain 5px border on every side - not the old 0px outer +
        # top_bar's own (10, 6, 10, 0) margins, which existed to frame
        # the heading text that's since been removed (DELETE THIS HEADING
        # TEXT, Home.png) and left ~40px of dead space above the page
        # list once that text was gone. About/Settings moved into the
        # top of the right-hand column below instead of their own row -
        # level with where the page list itself starts, not above it.
        outer.setContentsMargins(5, 5, 5, 5)
        outer.setSpacing(0)
        # SetNoConstraint - otherwise this top-level layout can resize the
        # whole dialog to fit whatever the *current* stack page's own
        # size hint is, and Qt/Windows can apply that queued resize mid-
        # drag during a native interactive title-bar move (which runs its
        # own nested message loop, unlike anything a plain script-driven
        # move()/resize() call ever triggers). Confirmed to only happen
        # navigating away from Home - the one page with no Section/
        # QScrollArea/PlotWidget of its own to have a "current page size
        # hint" that could differ enough from the window's actual size to
        # provoke it. This makes the window's size purely a function of
        # resize()/the user's own dragging, never of which page is showing.
        outer.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)

        body = QHBoxLayout()
        body.setContentsMargins(5, 0, 5, 0)
        body.setSpacing(10)

        left_col = QVBoxLayout()
        left_col.setSpacing(6)
        self.step_list = QListWidget()
        self.step_list.setSizePolicy(QSizePolicy.Policy.Fixed,
                                     QSizePolicy.Policy.Fixed)
        for label, indent, page in _LIST_ITEMS:
            item = QListWidgetItem(("    " if indent else "") + label)
            item.setData(Qt.ItemDataRole.UserRole, page)
            if page is None:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                f = item.font()
                f.setBold(True)
                item.setFont(f)
            self.step_list.addItem(item)
        self.step_list.itemClicked.connect(self._on_step_clicked)
        # size the container to exactly what the list needs - no leftover
        # empty space below the last item, no wasted width either
        fm = self.step_list.fontMetrics()
        width = max(fm.horizontalAdvance(("    " if i else "") + t)
                    for t, i, _p in _LIST_ITEMS) + 36
        self.step_list.setFixedWidth(width)
        height = (sum(self.step_list.sizeHintForRow(i)
                      for i in range(self.step_list.count()))
                 + 2 * self.step_list.frameWidth())
        self.step_list.setFixedHeight(height)
        left_col.addWidget(self.step_list)
        left_col.addStretch()
        body.addLayout(left_col)

        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.addStretch()
        btn_about = QPushButton("About")
        # autoDefault(True) is a QPushButton's own default - the first
        # button added to a QDialog with no default button set otherwise
        # picks it up automatically, which is what was reading as
        # "stuck active" (most Windows styles draw the default button
        # with a permanent highlighted border, not just while pressed).
        # Neither About nor Settings should ever be Enter-triggered.
        btn_about.setAutoDefault(False)
        btn_about.setDefault(False)
        btn_about.clicked.connect(self._show_about)
        top_row.addWidget(btn_about)
        btn_settings = QPushButton("Settings")
        btn_settings.setAutoDefault(False)
        btn_settings.setDefault(False)
        btn_settings.setToolTip("Adjustments")
        btn_settings.clicked.connect(self.window.openAdjustments)
        top_row.addWidget(btn_settings)
        right_col.addLayout(top_row)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_welcome_page())
        self.stack.addWidget(self._build_deployment_page())
        self.stack.addWidget(self._build_process_inventory_page())
        self.stack.addWidget(self._build_process_validate_page())
        self.stack.addWidget(self._build_predict_page())
        self.stack.addWidget(self._build_report_page())
        self.stack.addWidget(self._build_finished_page())
        right_col.addWidget(self.stack, stretch=1)
        body.addLayout(right_col, stretch=1)
        outer.addLayout(body, stretch=1)

        guidance_row = QHBoxLayout()
        guidance_row.setContentsMargins(10, 0, 10, 0)
        guidance_row.addStretch()
        self.lbl_guidance = QLabel("")
        self.lbl_guidance.setStyleSheet(f"color:{MUTED};font-style:italic;")
        guidance_row.addWidget(self.lbl_guidance)
        outer.addLayout(guidance_row)

        nav = QHBoxLayout()
        nav.setContentsMargins(10, 6, 10, 10)
        self.logo_h = self._make_logo("PyDracula_horizontal.png", width=160)
        if self.logo_h is not None:
            nav.addWidget(self.logo_h)
        self.btn_next = QPushButton("Next >")
        self.btn_next.clicked.connect(self._go_next)
        self.btn_back = QPushButton("< Back")
        self.btn_back.clicked.connect(self._go_back)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.reject)
        nav.addStretch()
        nav.addWidget(self.btn_back)
        nav.addWidget(self.btn_next)
        nav.addWidget(btn_close)
        outer.addLayout(nav)

    def _show_about(self):
        QMessageBox.information(
            self, "About",
            "Copyright Hull University - contact J.Norman2@hull.ac.uk")

    @staticmethod
    def _make_logo(filename, width):
        """Loads an images/images/<filename> logo scaled to `width`, or
        None if it's missing - callers skip adding the widget rather than
        show a broken image."""
        path = _IMAGES_DIR / filename
        if not path.exists():
            return None
        pix = QPixmap(str(path))
        if pix.isNull():
            return None
        lbl = QLabel()
        lbl.setPixmap(pix.scaledToWidth(
            width, Qt.TransformationMode.SmoothTransformation))
        return lbl

    def showEvent(self, event):
        super().showEvent(event)
        self.went_to_dev_toolkit = False
        self.stack.setCurrentIndex(0)
        self._sync_step_highlight()
        self._refresh_deployment_step()

    # ── navigation ───────────────────────────────────────────────────────────
    def _go_next(self):
        idx = self.stack.currentIndex()
        if idx == 1:
            self._refresh_process_inventory()
        elif idx == 2:
            self._refresh_validate_step()
        elif idx == 3:
            if not self._confirm_leave_validate():
                return
            action = self._confirm_unsaved_dataset()
            if action == "cancel":
                return
            if action == "save":
                # advancing happens once the export actually finishes -
                # _on_extract_done, guarded by _advance_after_export
                self._advance_after_export = True
                self._save_and_export()
                return
            self._refresh_predict_step()
        elif idx == 4:
            self._refresh_report_step()
        if idx < self.stack.count() - 1:
            self.stack.setCurrentIndex(idx + 1)
            self._sync_step_highlight()

    def _confirm_unsaved_dataset(self):
        """Whether it's safe to leave Validate for Predict without first
        (re-)running Save and export - Predict otherwise runs against
        whatever dataset CSV happened to be exported last, silently
        stale against anything validated/flagged since. Returns "proceed"
        (nothing outstanding), "save" (user chose Save and continue -
        _go_next must not advance the page itself; _on_extract_done does,
        once export actually finishes), or "cancel" (stay on Validate)."""
        if self._built_dataset_path is not None and not self._validate_dirty:
            return "proceed"
        box = QMessageBox(self.window)
        box.setWindowTitle("Unsaved processed data")
        box.setText("Processed data not saved or has unsaved changes. Continue?")
        btn_save = box.addButton("Save and continue",
                                 QMessageBox.ButtonRole.AcceptRole)
        btn_continue = box.addButton("Continue",
                                     QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(btn_save)
        box.exec()
        clicked = box.clickedButton()
        if clicked is btn_save:
            return "save"
        if clicked is btn_continue:
            return "proceed"
        return "cancel"

    def _confirm_leave_validate(self):
        """Flagged sensors are the ones Auto process all itself couldn't
        be sure about - the user may well only need to check those and
        trust the rest, so this only counts flagged-and-unreviewed (not
        every un-user-validated sensor) and only prompts when that count
        is non-zero. True = proceed (nothing outstanding, or the user
        said Yes); False = stay on Validate."""
        _auto, user_validated, flagged, _bad = self._validation_status()
        outstanding = [f for f in self._validate_files
                       if f["stem"] in flagged and f["stem"] not in user_validated]
        if not outstanding:
            return True
        reply = QMessageBox.question(
            self.window, "Sensors flagged for review",
            f"Caution, {len(outstanding)}/{len(flagged)} flagged sensors "
            "still need user-validation. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        return reply == QMessageBox.StandardButton.Yes

    def _go_back(self):
        idx = self.stack.currentIndex()
        if idx > 0:
            self.stack.setCurrentIndex(idx - 1)
            self._sync_step_highlight()

    def _on_step_clicked(self, item):
        page = item.data(Qt.ItemDataRole.UserRole)
        if page is None:
            return   # a group heading ("Process"/"Report") - not clickable
        self.stack.setCurrentIndex(page)
        self._sync_step_highlight()

    def _sync_step_highlight(self):
        page = self.stack.currentIndex()
        self.step_list.blockSignals(True)
        target_row = next(
            (i for i in range(self.step_list.count())
             if self.step_list.item(i).data(Qt.ItemDataRole.UserRole) == page),
            -1)
        self.step_list.setCurrentRow(target_row)
        self.step_list.blockSignals(False)
        self.btn_back.setEnabled(page > 0)
        last_page = self.stack.count() - 1
        self.btn_next.setText(
            "Finish" if page == last_page - 1 else "Next >")
        self.btn_next.setEnabled(page != last_page)
        if self.logo_h is not None:
            self.logo_h.setVisible(page not in _NO_SMALL_LOGO_PAGES)
        self.lbl_guidance.setText(_GUIDANCE.get(page, ""))

    @staticmethod
    def _muted(text):
        lab = QLabel(text)
        lab.setStyleSheet(f"color:{MUTED};")
        lab.setWordWrap(True)
        return lab

    # ── page 0: welcome ──────────────────────────────────────────────────────
    def _build_welcome_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.addStretch()
        logo = self._make_logo("PyDracula_vertical.png", width=220)
        if logo is not None:
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v.addWidget(logo)
        subtitle = QLabel("Deploy. Process. Predict.")
        subtitle.setStyleSheet(f"color:{MUTED};font-size:28px;font-style:italic;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(subtitle)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_blade_strike = QPushButton("Blade strike\n(next)")
        btn_blade_strike.setMinimumSize(140, 44)
        btn_blade_strike.setStyleSheet(
            f"QPushButton{{background-color:{ACCENT};color:#ffffff;"
            "border-radius:5px;font-weight:bold;}")
        btn_blade_strike.clicked.connect(self._go_next)
        btn_row.addWidget(btn_blade_strike)
        btn_dev_toolkit = QPushButton("Development\ntoolkit")
        btn_dev_toolkit.setMinimumSize(140, 44)
        btn_dev_toolkit.setStyleSheet(
            f"QPushButton{{background-color:{BAD};color:#ffffff;"
            "border-radius:5px;font-weight:bold;}")
        btn_dev_toolkit.clicked.connect(self._go_development_toolkit)
        btn_row.addWidget(btn_dev_toolkit)
        btn_row.addStretch()
        v.addSpacing(20)
        v.addLayout(btn_row)

        v.addStretch()
        return page

    def _go_development_toolkit(self):
        """"Development toolkit" (Home.png) - the opt-in door to the full
        Advanced GUI, reusing HomePage's own entry logic exactly
        (expand_sidebar + land on Setup/deploy) rather than duplicating
        it. MainWindow is never shown by default any more (main.py) - set
        its state *then* show it, so it appears already in Advanced mode
        rather than flashing the (still-narrow) Home page first - and only
        then close this wizard so it's what the user actually sees.

        went_to_dev_toolkit records that this, specifically, is why the
        wizard closed - MainWindow.openSimpleMode() reads it back so
        main.py's own startup call can tell "chose Development toolkit"
        (show MainWindow, already done above) from "closed any other way"
        (Close button, window X - quit the whole app instead; see that
        module's own comment)."""
        self.went_to_dev_toolkit = True
        self.window.home_page._go_advanced()
        self.window.show()
        self.reject()

    # ── page 1: deployment ───────────────────────────────────────────────────
    def _build_deployment_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(10)
        title = QLabel("Build a sensor deployment by adding a test site, "
                       "treatment condition and sensor files…")
        title.setStyleSheet(f"color:{TEXT};font-weight:bold;")
        title.setWordWrap(True)
        v.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(10)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)

        grp_lib = Section("Session library")
        libv = QVBoxLayout(grp_lib)
        self.cmb_library_deploy = QComboBox()
        self.cmb_library_deploy.currentIndexChanged.connect(
            self._on_library_combo_deploy_changed)
        libv.addWidget(self.cmb_library_deploy)
        self.lbl_library_path_deploy = QLabel("No library selected.")
        self.lbl_library_path_deploy.setStyleSheet(f"color:{MUTED};")
        self.lbl_library_path_deploy.setWordWrap(True)
        libv.addWidget(self.lbl_library_path_deploy)
        lib_action_row = QHBoxLayout()
        btn_new_library = QPushButton("New library")
        btn_new_library.setFlat(True)
        btn_new_library.setStyleSheet(f"color:{ACCENT};text-align:left;")
        btn_new_library.clicked.connect(
            lambda: self.window.home_page._new_library(parent=self))
        lib_action_row.addWidget(btn_new_library)
        lib_action_row.addStretch()
        btn_new_session = QPushButton("New session")
        btn_new_session.setFlat(True)
        btn_new_session.setStyleSheet(f"color:{ACCENT};text-align:right;")
        btn_new_session.clicked.connect(
            lambda: self.window.home_page._new_session(parent=self))
        lib_action_row.addWidget(btn_new_session)
        libv.addLayout(lib_action_row)
        lv.addWidget(grp_lib)

        grp_lib_status = Section("Library status")
        lsv = QVBoxLayout(grp_lib_status)
        self.card_library_status = MetaCard("Nothing selected yet")
        lsv.addWidget(self.card_library_status)
        lv.addWidget(grp_lib_status)

        grp_sensor = Section("Sensors")
        sv = QVBoxLayout(grp_sensor)
        self.cmb_sensor = QComboBox()
        for cfg in sensor_config.all_configs():
            self.cmb_sensor.addItem(cfg.name, cfg.key)
        idx = self.cmb_sensor.findData(sensor_config.active().key)
        self.cmb_sensor.setCurrentIndex(max(idx, 0))
        self.cmb_sensor.currentIndexChanged.connect(self._on_sensor_config_changed)
        sv.addWidget(self.cmb_sensor)
        lv.addWidget(grp_sensor)

        grp_dep = Section("Deployment")
        dv = QVBoxLayout(grp_dep)
        self.cmb_deployment = QComboBox()
        self.cmb_deployment.currentIndexChanged.connect(
            self._on_deployment_selected)
        dv.addWidget(self.cmb_deployment)

        form = QGridLayout()
        form.setColumnStretch(1, 1)
        self.dep_edits = {}
        for i, (column, label) in enumerate(di.DEPLOYMENT_FIELDS):
            form.addWidget(self._muted(label), i, 0)
            edit = QLineEdit()
            form.addWidget(edit, i, 1)
            self.dep_edits[column] = edit
        dv.addLayout(form)
        lv.addWidget(grp_dep)

        self.btn_create_folder = QPushButton("Create & open\ndata folder")
        self.btn_create_folder.setMinimumHeight(40)
        self.btn_create_folder.setFixedWidth(120)
        self.btn_create_folder.setToolTip("Create & open data folder")
        self.btn_create_folder.clicked.connect(self._create_and_open_folder)
        lv.addWidget(self.btn_create_folder)

        self.lbl_files_found = QLabel("")
        self.lbl_files_found.setStyleSheet(f"color:{OK};")
        lv.addWidget(self.lbl_files_found)
        lv.addStretch()

        # scrolls internally rather than forcing the whole dialog taller -
        # this column grew to four stacked sections (Session library,
        # Library status, Sensors, Deployment) and was the actual reason
        # the window needed to keep growing past a fixed 1340x700 to
        # avoid squeezing/overlapping its own labels
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setStyleSheet(
            "QScrollArea{border:none;background:transparent;}")
        left_scroll.setWidget(left)
        row.addWidget(left_scroll, stretch=2)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        self.treatment_table = _TreatmentTable()
        self.treatment_table.changed.connect(self._refresh_treatment_summary)
        rv.addWidget(self.treatment_table, stretch=1)
        self.btn_add_treatment = QPushButton("+ Add treatment")
        self.btn_add_treatment.setFixedWidth(120)
        self.btn_add_treatment.clicked.connect(lambda: self._add_treatment())
        rv.addWidget(self.btn_add_treatment)
        self.lbl_treatment_summary = QLabel("")
        self.lbl_treatment_summary.setStyleSheet(f"color:{MUTED};")
        rv.addWidget(self.lbl_treatment_summary)
        rv.addStretch()
        row.addWidget(right, stretch=3)

        v.addLayout(row, stretch=1)
        return page

    # -- deployment step logic -----------------------------------------------
    def _refresh_deployment_step(self):
        self._lib_root = self.window.session_state.library
        self._refresh_library_combo_deploy(select=self._lib_root)
        self._refresh_library_status_card()
        self._load_deployments()

    # -- session library (soft-synced to session_state, like every other
    # page's own picker - see page_home.py's docstring) ---------------------
    def _refresh_library_combo_deploy(self, select=None):
        self.cmb_library_deploy.blockSignals(True)
        self.cmb_library_deploy.clear()
        for lib in settings.list_libraries():
            self.cmb_library_deploy.addItem(lib.name, str(lib))
        want = str(select) if select else None
        idx = self.cmb_library_deploy.findData(want) if want else -1
        if idx >= 0:
            self.cmb_library_deploy.setCurrentIndex(idx)
        self.cmb_library_deploy.blockSignals(False)
        self.lbl_library_path_deploy.setText(
            str(self._lib_root) if self._lib_root else "No library selected.")

    def _refresh_library_status_card(self):
        title, rows = library_status_rows(
            self._lib_root, self.window.session_state)
        self.card_library_status.set_title(title)
        self.card_library_status.set_rows(rows)

    def _on_library_combo_deploy_changed(self, _idx):
        path = self.cmb_library_deploy.currentData()
        self.window.session_state.set_library(path)

    def _on_session_library_changed_simple(self, path):
        """Soft-sync for this page's own library combo - fires whenever
        the session library changes from anywhere (this combo, the
        Advanced Home page, New library/New session) so Deploy always
        reflects the one true session library, same as every other
        soft-synced page in the app."""
        self._lib_root = path
        self._refresh_library_combo_deploy(select=path)
        self._refresh_library_status_card()
        self._load_deployments()

    def _on_sensor_config_changed(self, *_args):
        key = self.cmb_sensor.currentData()
        if key:
            sensor_config.set_active(key)

    def _load_deployments(self, select=None):
        self.cmb_deployment.blockSignals(True)
        self.cmb_deployment.clear()
        self._deployments = []
        if self._lib_root is not None:
            self._deployments = di.deployments(self._lib_root)
            for dep in self._deployments:
                self.cmb_deployment.addItem(
                    di.describe_deployment(dep), dep.get(di.DEPLOYMENT_COL, ""))
        self.cmb_deployment.addItem("New deployment…", _NEW_DEPLOYMENT)
        idx = (self.cmb_deployment.findData(select) if select is not None
               else 0)
        self.cmb_deployment.setCurrentIndex(max(0, idx))
        self.cmb_deployment.blockSignals(False)
        self._show_deployment(self.cmb_deployment.currentData())

    def _on_deployment_selected(self, *_args):
        self._show_deployment(self.cmb_deployment.currentData())

    def _show_deployment(self, ident):
        self.treatment_table.clear_rows()
        is_new = ident is None or ident == _NEW_DEPLOYMENT
        if is_new:
            for edit in self.dep_edits.values():
                edit.setText("")
            self._add_treatment()
            self._refresh_files_found()
            return
        dep = next((d for d in self._deployments
                    if d.get(di.DEPLOYMENT_COL, "") == ident), {})
        for column, edit in self.dep_edits.items():
            edit.setText(dep.get(column, ""))
        planned = di.treatments(self._lib_root, ident) if self._lib_root else []
        for treatment in (planned or [None]):
            self._add_treatment(treatment)
        self._refresh_files_found()

    def _add_treatment(self, values=None):
        if values is None:
            existing = self.treatment_table.all_values()
            values = dict(existing[-1]) if existing else {}
            used = set(self.treatment_table.names())
            n = self.treatment_table.rowCount() + 1
            while f"Treatment {n}" in used:
                n += 1
            values[di.TREATMENT_COL] = f"Treatment {n}"
        self.treatment_table.add_row(values)

    def _refresh_treatment_summary(self, *_args):
        values = self.treatment_table.all_values()
        n_rows = sum(int(v.get("runs", 1) or 1) for v in values)
        self.lbl_treatment_summary.setText(
            f"{len(values)} treatment(s), {n_rows} row(s)" if values else "")

    def _refresh_files_found(self):
        ident = self.dep_edits[di.DEPLOYMENT_COL].text().strip()
        if self._lib_root is None or not ident:
            self.lbl_files_found.setText("")
            return
        dep_dir = self._lib_root / _RAW_DIR / ident
        if not dep_dir.exists():
            self.lbl_files_found.setText("")
            return
        # a RAPID recording is always 2 files (.IMP + .HIG) - counting raw
        # files directly overstates "how many sensors" 2x (and VIDEO
        # clips would inflate it further, so those are excluded too)
        n_exts = max(1, len(sensor_config.active().required_extensions or [".imp"]))
        n_files = sum(
            1 for p in dep_dir.rglob("*")
            if p.is_file() and p.name != "readme.txt"
            and _VIDEO_FOLDER_NAME not in p.relative_to(dep_dir).parts)
        n_recordings = n_files // n_exts
        self.lbl_files_found.setText(
            f"{n_recordings} sensor recording(s) found in folder "
            f"({n_files} file(s))")

    def _create_and_open_folder(self):
        if self._lib_root is None:
            QMessageBox.warning(
                self.window, "No library",
                "Select or create a library on Home first.")
            return
        ident = self.dep_edits[di.DEPLOYMENT_COL].text().strip()
        if not ident:
            QMessageBox.warning(self.window, "Missing deployment ID",
                                "The deployment needs an ID.")
            return
        names = self.treatment_table.names()
        if not names or any(not n for n in names):
            QMessageBox.warning(self.window, "Missing treatment",
                                "Add at least one named treatment.")
            return

        deployment = {c: e.text().strip() for c, e in self.dep_edits.items()}
        treatments = self.treatment_table.all_values()
        try:
            di.save_plan(self._lib_root, deployment, treatments)
            dep_dir = self._lib_root / _RAW_DIR / ident
            for name in names:
                (dep_dir / name / _VIDEO_FOLDER_NAME).mkdir(
                    parents=True, exist_ok=True)
            (dep_dir / "readme.txt").write_text(_README_TEXT, encoding="utf-8")
        except Exception as e:
            QMessageBox.critical(self.window, "Could not build folder", str(e))
            return

        try:
            os.startfile(str(dep_dir))
        except Exception:
            pass
        QMessageBox.information(
            self.window, "Deployment folder ready", _README_TEXT)
        self._load_deployments(select=ident)

    # ── page 2: process (file inventory) ────────────────────────────────────
    def _build_process_inventory_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(8)
        title = QLabel("Process, validate and segment sensor data…")
        title.setStyleSheet(f"color:{TEXT};font-weight:bold;")
        v.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(10)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        grp = Section("File inventory")
        gv = QVBoxLayout(grp)
        self.tbl_inventory = QTableWidget(0, 6)
        self.tbl_inventory.setHorizontalHeaderLabels(
            ["Filename", "Sensor", "Date", "Time", "Complete", "Processed"])
        gv.addWidget(self.tbl_inventory)
        sel_row = QHBoxLayout()
        self.chk_select_all_inv = QCheckBox("Select / unselect all")
        self.chk_select_all_inv.toggled.connect(self._on_select_all_inventory)
        sel_row.addWidget(self.chk_select_all_inv)
        sel_row.addStretch()
        self.btn_process_selected = QPushButton("Process selected")
        self.btn_process_selected.setStyleSheet(
            f"QPushButton{{background-color:{ACCENT};color:#ffffff;"
            "border-radius:5px;padding:4px 14px;font-weight:bold;}"
            "QPushButton:disabled{background-color:#3a4150;color:#8a95aa;}")
        self.btn_process_selected.clicked.connect(self._process_selected)
        sel_row.addWidget(self.btn_process_selected)
        gv.addLayout(sel_row)
        lv.addWidget(grp, stretch=1)
        row.addWidget(left, stretch=3)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        self.txt_process_log = QLabel("")
        self.txt_process_log.setStyleSheet(f"color:{MUTED};")
        self.txt_process_log.setWordWrap(True)
        self.txt_process_log.setAlignment(Qt.AlignmentFlag.AlignTop)
        log_scroll = QScrollArea()
        log_scroll.setWidgetResizable(True)
        log_scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        log_scroll.setWidget(self.txt_process_log)
        rv.addWidget(log_scroll, stretch=1)
        self.lbl_process_status = QLabel("")
        self.lbl_process_status.setStyleSheet(f"color:{OK};font-weight:bold;")
        self.lbl_process_status.setWordWrap(True)
        rv.addWidget(self.lbl_process_status)
        row.addWidget(right, stretch=2)

        v.addLayout(row, stretch=1)
        return page

    def _refresh_process_inventory(self):
        ident = self.dep_edits[di.DEPLOYMENT_COL].text().strip()
        self._process_files = []
        if self._lib_root is not None and ident:
            dep_dir = self._lib_root / _RAW_DIR / ident
            self._process_files = self._scan_raw_files(dep_dir)
        self._refresh_inventory_table()

    def _scan_raw_files(self, folder):
        """Like page_process.py's own `_scan`, but additionally tags each
        record with which treatment subfolder it came from (folder/
        <treatment>/<file>, the same one level `_create_and_open_folder`
        builds) - Advanced mode gets this from a picked deployment/
        treatment filter instead, but Simple mode processes a whole
        deployment (every treatment) in one pass, so it has to read the
        treatment back out of the path itself. Needed so `_on_process_done`
        can stamp each batch with `deployment_index.apply_treatment` -
        without it, every recording's dataset row comes back with no
        treatment at all."""
        if not folder.exists():
            return []
        cfg = sensor_config.active()
        exts = cfg.required_extensions or [".imp"]
        primary, secondary = exts[0], exts[1:]

        def files_by_stem(ext):
            suffix = ext.lstrip(".")
            out = {p.stem.upper(): p for p in folder.rglob(f"*.{suffix.upper()}")}
            for p in folder.rglob(f"*.{suffix.lower()}"):
                out.setdefault(p.stem.upper(), p)
            return out

        found = {ext: files_by_stem(ext) for ext in exts}
        csv_dir = (self._lib_root / _CSV_DIR) if self._lib_root else None
        processed_names = ({p.stem.upper() for p in csv_dir.glob("*.csv")
                            if not p.stem.endswith("_min")}
                           if csv_dir and csv_dir.exists() else set())

        records = []
        for stem_up, main_path in sorted(found[primary].items()):
            sensor, date, time = _parse_name(main_path.stem, cfg)
            paths = {primary: main_path}
            for ext in secondary:
                match = found[ext].get(stem_up)
                if match is not None:
                    paths[ext] = match
            try:
                rel = main_path.relative_to(folder)
                treatment = rel.parts[0] if len(rel.parts) > 1 else ""
            except ValueError:
                treatment = ""
            records.append(dict(
                stem=main_path.stem, stem_up=stem_up, sensor=sensor,
                date=date, time=time, complete=len(paths) == len(exts),
                processed=stem_up in processed_names, paths=paths,
                treatment=treatment))
        return records

    def _refresh_inventory_table(self):
        t = self.tbl_inventory
        t.setRowCount(len(self._process_files))
        for row, f in enumerate(self._process_files):
            vals = [f["stem"], f["sensor"], f["date"], f["time"],
                    "Yes" if f["complete"] else "No",
                    "Yes" if f["processed"] else "No"]
            for col, val in enumerate(vals):
                t.setItem(row, col, QTableWidgetItem(str(val)))
        t.resizeColumnsToContents()

    def _on_select_all_inventory(self, checked):
        if checked:
            self.tbl_inventory.selectAll()
        else:
            self.tbl_inventory.clearSelection()

    def _process_selected(self):
        rows = sorted({i.row() for i in self.tbl_inventory.selectedIndexes()})
        files = [self._process_files[r] for r in rows
                if r < len(self._process_files)]
        self._run_process(files)

    def _run_process(self, files):
        complete = [f for f in files if f["complete"]]
        if not complete:
            self.lbl_process_status.setText("No complete recordings to process.")
            return
        out_dir = self._lib_root / "processed_sens_data"
        self.txt_process_log.setText("")
        self.lbl_process_status.setText("Processing…")
        self.btn_process_selected.setEnabled(False)
        # stem -> treatment, so _on_file_processed can group the batch by
        # treatment once processing finishes (apply_treatment() needs one
        # call per treatment, not per file)
        self._process_treatment_by_stem = {f["stem"]: f["treatment"]
                                           for f in complete}
        self._process_batch_done = []
        cfg = sensor_config.active()
        self._process_thread = _ProcessThread(complete, out_dir, self._lib_root, cfg)
        self._process_thread.log.connect(self._on_process_log)
        self._process_thread.processed.connect(self._on_file_processed)
        self._process_thread.done.connect(self._on_process_done)
        self._process_thread.start()

    def _on_process_log(self, text):
        self.txt_process_log.setText(
            (self.txt_process_log.text() + "\n" + text).strip())

    def _on_file_processed(self, stem):
        self._process_batch_done.append(stem)

    def _on_process_done(self, code):
        self.btn_process_selected.setEnabled(True)
        self.lbl_process_status.setText(
            "All sensors processed" if code == 0
            else "Processing finished with errors")
        self._apply_treatments_to_batch()
        self._refresh_process_inventory()

    def _apply_treatments_to_batch(self):
        """Stamps every successfully processed file with the treatment
        its raw file was found under (deployment_index.apply_treatment) -
        the same step page_process.py._apply_treatment() does after a
        processing run, just grouped by treatment here since Simple mode
        processes a whole deployment (every treatment) in one pass rather
        than one treatment at a time. Without this, a file's dataset row
        carries no treatment at all - the prediction worker then has
        nothing to group by, and its own per-treatment summary output
        comes back empty ("No columns to parse from file")."""
        if self._lib_root is None or not self._process_batch_done:
            return
        deployment = {c: e.text().strip() for c, e in self.dep_edits.items()}
        by_treatment = {}
        for stem in self._process_batch_done:
            t = self._process_treatment_by_stem.get(stem, "")
            by_treatment.setdefault(t, []).append(stem)
        all_treatments = self.treatment_table.all_values()
        for treatment_name, stems in by_treatment.items():
            row = next((v for v in all_treatments
                       if v.get(di.TREATMENT_COL) == treatment_name), None)
            if row is None:
                continue
            treatment_values = dict(deployment)
            treatment_values.update(row)
            di.apply_treatment(self._lib_root, stems, treatment_values)

    # ── page 3: process (validate/segment) ──────────────────────────────────
    def _build_process_validate_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(8)
        title = QLabel("Process, validate and segment sensor data…")
        title.setStyleSheet(f"color:{TEXT};font-weight:bold;")
        v.addWidget(title)

        # a fixed-width left pane, not a draggable QSplitter -
        # setSizes([1, 2]) below only ever set an *initial* proportion,
        # never a constraint, so the list kept growing wider than
        # intended and had to be dragged back by hand every time
        # (simple_spec/Validate.png shows no splitter handle - a plain
        # fixed-width column instead)
        split = QHBoxLayout()
        split.setContentsMargins(0, 0, 0, 0)
        split.setSpacing(10)

        left = QWidget()
        left.setFixedWidth(240)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        self.validate_list = QListWidget()
        self.validate_list.itemClicked.connect(self._on_validate_file_clicked)
        lv.addWidget(self.validate_list, stretch=1)

        mark_row = QHBoxLayout()
        self.btn_mark = QPushButton("Mark bad")
        self.btn_mark.setStyleSheet(f"color:{BAD};font-weight:bold;")
        self.btn_mark.clicked.connect(self._mark_good_bad)
        mark_row.addWidget(self.btn_mark)
        self.chk_show_bad = QCheckBox("Show bad")
        self.chk_show_bad.toggled.connect(self._refresh_validate_list)
        mark_row.addWidget(self.chk_show_bad)
        lv.addLayout(mark_row)

        self.lbl_validated_count = QLabel("Validated: 0 / 0")
        self.lbl_validated_count.setStyleSheet(f"color:{TEXT};")
        lv.addWidget(self.lbl_validated_count)

        self.btn_save_next_v = QPushButton("Save + Next")
        self.btn_save_next_v.clicked.connect(self._save_and_next_validate)
        lv.addWidget(self.btn_save_next_v)
        self.btn_reset_v = QPushButton("Reset current sensor")
        self.btn_reset_v.clicked.connect(self._reset_current_validate)
        lv.addWidget(self.btn_reset_v)
        self.btn_jump_v = QPushButton("Jump to next flagged")
        self.btn_jump_v.clicked.connect(self._jump_next_unvalidated_validate)
        lv.addWidget(self.btn_jump_v)
        split.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        toolbar = QHBoxLayout()
        toolbar.addStretch()
        add_export_button(toolbar, self._validate_export_data, self.window,
                          file_stub="validate_signal")
        rv.addLayout(toolbar)
        self._pw_validate = pg.PlotWidget()
        pi = self._pw_validate.plotItem
        pi.setLabel("bottom", "Time (s)")
        pi.setLabel("left", "Pressure (kPa)")
        self._vb2_validate = pg.ViewBox()
        pi.scene().addItem(self._vb2_validate)
        pi.getAxis("right").linkToView(self._vb2_validate)
        self._vb2_validate.setXLink(pi)
        pi.showAxis("right")
        pi.getAxis("right").setLabel("HIG acc mag (g)")
        pi.vb.sigResized.connect(self._sync_vb2_validate)
        self._validate_region = pg.LinearRegionItem(
            movable=False, brush=pg.mkBrush(120, 170, 255, 35),
            pen=pg.mkPen(120, 170, 255, 90))
        pi.addItem(self._validate_region)
        self._validate_nadir_line = pg.InfiniteLine(
            angle=90, movable=True,
            pen=pg.mkPen(color=(255, 220, 0), width=2), label="Nadir",
            labelOpts={"position": 0.92, "color": (180, 150, 0)})
        self._validate_nadir_line.sigPositionChanged.connect(
            self._on_validate_nadir_moved)
        pi.addItem(self._validate_nadir_line)
        self._validate_curve = None
        self._validate_curve2 = None
        rv.addWidget(self._pw_validate, stretch=1)
        split.addWidget(right, stretch=1)
        v.addLayout(split, stretch=1)

        bottom = QHBoxLayout()
        auto_col = QVBoxLayout()
        auto_col.setSpacing(2)
        auto_row = QHBoxLayout()
        self.btn_auto_process_all = QPushButton("Auto process all")
        self.btn_auto_process_all.setStyleSheet(f"color:{OK};font-weight:bold;")
        self.btn_auto_process_all.clicked.connect(self._auto_process_all)
        auto_row.addWidget(self.btn_auto_process_all)
        self._auto_spinner = Spinner(size=20)
        self._auto_spinner.setVisible(False)
        auto_row.addWidget(self._auto_spinner)
        auto_col.addLayout(auto_row)
        auto_col.addWidget(self._muted(
            "Tip: press Auto process all first, then check the sensors "
            "it flagged for review."))
        bottom.addLayout(auto_col)
        bottom.addWidget(self._muted("ROI window:"))
        self.cmb_window = QComboBox()
        self.cmb_window.currentIndexChanged.connect(self._on_validate_win_size_changed)
        bottom.addWidget(self.cmb_window)
        self._fill_validate_window_combo()
        self.lbl_all_validated = QLabel("")
        self.lbl_all_validated.setStyleSheet(f"color:{MUTED};")
        bottom.addWidget(self.lbl_all_validated)
        bottom.addStretch()
        self.btn_save_export = QPushButton("Save and export")
        self.btn_save_export.setStyleSheet(f"color:{BAD};font-weight:bold;")
        self.btn_save_export.clicked.connect(self._save_and_export)
        bottom.addWidget(self.btn_save_export)
        v.addLayout(bottom)
        return page

    def _sync_vb2_validate(self):
        pi = self._pw_validate.plotItem
        self._vb2_validate.setGeometry(pi.vb.sceneBoundingRect())
        self._vb2_validate.linkedViewChanged(pi.vb, self._vb2_validate.XAxis)

    def _validate_export_data(self):
        """Feeds the "Export ▾" toolbar button (plot_style.add_export_button,
        the same one Advanced mode's own Validate page uses) - None while
        nothing is loaded yet, matching build_export_data's own contract."""
        time = self._cur_validate_time
        if time is None or not len(time):
            return None
        return build_export_data(
            time, "Pressure (kPa)", self._cur_validate_pres,
            "HIG acc mag (g)", self._cur_validate_hig,
            (float(time[0]), float(time[-1])))

    # -- process-validate step logic ------------------------------------------
    def _validate_index(self):
        return di.read_index(self._lib_root) if self._lib_root else None

    def _save_validate_index(self, df):
        path = di.index_path(self._lib_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)

    def _refresh_validate_step(self):
        self._validate_files = []
        csv_dir = (self._lib_root / _CSV_DIR) if self._lib_root else None
        if csv_dir and csv_dir.exists():
            for p in sorted(csv_dir.glob("*.csv")):
                if p.stem.endswith("_min"):
                    continue
                self._validate_files.append({"stem": p.stem, "path": p})
        self._refresh_validate_list()

    def _validation_status(self):
        """(auto_validated, user_validated, flagged, bad) stem sets from
        the current index - the one place every Validate-step method
        reads these from, so the list, the counts, Jump, and the Next
        confirmation can't quietly disagree with each other."""
        index_df = self._validate_index()
        auto_validated = set()
        user_validated = set()
        flagged = set()
        bad = set()
        if index_df is not None:
            if _VALIDATED_COL in index_df.columns:
                auto_validated = set(index_df[index_df[_VALIDATED_COL]
                                     .astype(str).str.upper() == "Y"]["file"])
            if _USER_VALIDATED_COL in index_df.columns:
                user_validated = set(index_df[index_df[_USER_VALIDATED_COL]
                                     .astype(str).str.upper() == "Y"]["file"])
            if _FLAGGED_COL in index_df.columns:
                flagged = set(index_df[index_df[_FLAGGED_COL]
                              .astype(str).str.upper() == "Y"]["file"])
            if di.BAD_SENS_COL in index_df.columns:
                bad = set(index_df[index_df[di.BAD_SENS_COL]
                          .astype(str).str.upper() == "Y"]["file"])
        return auto_validated, user_validated, flagged, bad

    def _refresh_validate_list(self):
        auto_validated, user_validated, flagged, bad = self._validation_status()
        show_bad = self.chk_show_bad.isChecked()

        # flagged-and-not-yet-user-validated first (what actually needs
        # attention), then everything else in its normal order - stable
        # sort keeps each group's own relative order unchanged
        needs_review = lambda f: f["stem"] in flagged and f["stem"] not in user_validated
        ordered = sorted(self._validate_files, key=lambda f: not needs_review(f))

        self.validate_list.clear()
        for f in ordered:
            stem = f["stem"]
            is_bad = stem in bad
            if is_bad and not show_bad:
                continue
            # plain stem, no decoration - WARN colour alone marks
            # "flagged, needs review" below; a text prefix here used to
            # break _on_validate_file_clicked/_load_validate_file's own
            # item.text() == stem lookups for exactly the flagged rows,
            # so clicking (or Jump to next flagged landing on) one
            # silently did nothing
            item = QListWidgetItem(stem)
            if is_bad:
                item.setForeground(QColor(BAD))
            elif stem in user_validated:
                item.setForeground(QColor(OK))
            elif needs_review(f):
                item.setForeground(QColor(WARN))
            elif stem in auto_validated:
                item.setForeground(QColor(ACCENT))
            self.validate_list.addItem(item)

        total = len(self._validate_files)
        n_auto = sum(1 for f in self._validate_files if f["stem"] in auto_validated)
        n_flagged = sum(1 for f in self._validate_files if f["stem"] in flagged)
        n_user = sum(1 for f in self._validate_files if f["stem"] in user_validated)
        self.lbl_validated_count.setText(
            f"Auto-validated: {n_auto}/{total}\n"
            f"Flagged: {n_flagged}\n"
            f"User-validated: {n_user}/{total}"
            + (f"\n({len(bad)} bad)" if bad else ""))
        self.lbl_all_validated.setText(
            "All sensors validated" if total and n_auto == total
            and (n_flagged == 0 or n_user >= n_flagged) else "")

    def _on_validate_file_clicked(self, item):
        stem = item.text()
        self._load_validate_file(stem)

    def _load_validate_file(self, stem):
        match = next((f for f in self._validate_files if f["stem"] == stem), None)
        if match is None:
            return
        try:
            df = pd.read_csv(match["path"], low_memory=False)
        except Exception as e:
            QMessageBox.warning(self.window, "Load failed", str(e))
            return
        self._cur_validate_stem = stem
        self._cur_validate_df = df
        self._cur_validate_time = (df["time_s"].to_numpy(dtype=float)
                                   if "time_s" in df.columns
                                   else np.arange(len(df), dtype=float))
        self._cur_validate_pres = (df["pressure_kpa"].to_numpy(dtype=float)
                                   if "pressure_kpa" in df.columns else None)
        self._cur_validate_hig = (df["higacc_mag_g"].to_numpy(dtype=float)
                                  if "higacc_mag_g" in df.columns else None)
        self._cur_validate_nadir_idx = self._detect_nadir_idx(stem, df,
                                                               self._cur_validate_time,
                                                               self._cur_validate_pres)
        # the as-loaded nadir, before any dragging - compared against at
        # save time to tell "human re-confirmed this" from "human moved
        # it" (_USER_ADJUSTED_COL, surfaced in the Report step)
        self._loaded_nadir_idx = self._cur_validate_nadir_idx
        self._draw_validate_plot()
        # select it in the list too, for Jump/Auto-process consistency
        for i in range(self.validate_list.count()):
            if self.validate_list.item(i).text() == stem:
                self.validate_list.setCurrentRow(i)
                break

    def _detect_nadir_idx(self, stem, df, time, pres):
        index_df = self._validate_index()
        if (index_df is not None and "file" in index_df.columns
                and _NADIR_T_COL in index_df.columns):
            row = index_df[index_df["file"] == stem]
            if not row.empty:
                val = row[_NADIR_T_COL].iloc[0]
                if pd.notna(val):
                    return int(np.argmin(np.abs(time - float(val))))
        if pres is not None and len(pres):
            return int(np.argmin(pres))
        return len(df) // 2

    def _window_bounds(self, time, nadir_idx, n):
        fs = sensor_config.active().output_rate_hz or 2000
        half_n = int(round(self._win_sec / 2 * fs))
        start = max(0, nadir_idx - half_n)
        end = min(n - 1, nadir_idx + half_n)
        return start, end

    def _update_validate_region(self, t: float):
        self._validate_region.setRegion(
            (t - self._win_sec / 2, t + self._win_sec / 2))

    def _fill_validate_window_combo(self):
        """Offer 100-1000 ms, defaulting to this page's own width - same
        convention as Advanced mode's Validate page (page_validate.py's
        own _fill_window_combo)."""
        cmb = self.cmb_window
        want = int(round(self._win_sec * 1000))
        options = sorted(set(range(100, 1001, 100)) | {want})
        cmb.blockSignals(True)
        cmb.clear()
        for ms in options:
            cmb.addItem(f"{ms} ms", ms)
        cmb.setCurrentIndex(max(0, cmb.findData(want)))
        cmb.blockSignals(False)

    def _on_validate_win_size_changed(self):
        ms = self.cmb_window.currentData()
        if ms is None:
            return
        self._win_sec = ms / 1000.0
        if self._cur_validate_time is not None and self._cur_validate_nadir_idx is not None:
            self._update_validate_region(
                float(self._cur_validate_time[self._cur_validate_nadir_idx]))

    def _on_validate_nadir_moved(self):
        """The nadir line is user-draggable (movable=True) so any sensor -
        already validated or not - can be corrected: dragging snaps to the
        nearest sample and moves the ROI window preview with it; nothing
        is written to disk until Save + Next."""
        time = self._cur_validate_time
        if time is None:
            return
        raw_t = self._validate_nadir_line.value()
        idx = int(np.argmin(np.abs(time - raw_t)))
        self._cur_validate_nadir_idx = idx
        t_snap = float(time[idx])
        self._validate_nadir_line.blockSignals(True)
        self._validate_nadir_line.setPos(t_snap)
        self._validate_nadir_line.blockSignals(False)
        self._update_validate_region(t_snap)

    def _draw_validate_plot(self):
        pi = self._pw_validate.plotItem
        if self._validate_curve is not None:
            pi.removeItem(self._validate_curve)
            self._validate_curve = None
        if self._validate_curve2 is not None:
            self._vb2_validate.removeItem(self._validate_curve2)
            self._validate_curve2 = None
        time = self._cur_validate_time
        if self._cur_validate_pres is not None:
            self._validate_curve = self._pw_validate.plot(
                time, self._cur_validate_pres, pen=pg.mkPen("#dddddd", width=1))
        if self._cur_validate_hig is not None:
            self._validate_curve2 = pg.PlotCurveItem(
                pen=pg.mkPen("#ff5555", width=1))
            self._vb2_validate.addItem(self._validate_curve2)
            self._validate_curve2.setData(time, self._cur_validate_hig)
            self._vb2_validate.enableAutoRange("y", True)
        t = float(time[self._cur_validate_nadir_idx])
        self._validate_nadir_line.blockSignals(True)
        self._validate_nadir_line.setPos(t)
        self._validate_nadir_line.blockSignals(False)
        self._update_validate_region(t)
        pi.enableAutoRange("x", True)
        pi.enableAutoRange("y", True)

    def _mark_good_bad(self):
        """Always marks the current sensor Bad - marking bad doesn't
        un-validate it (Save and export excludes bad sensors from the
        dataset separately, via the same bad_sens=N filter every other
        dataset-building path already uses)."""
        if not self._cur_validate_stem or self._lib_root is None:
            return
        index_df = self._validate_index()
        if index_df is None or "file" not in index_df.columns:
            return
        mask = index_df["file"] == self._cur_validate_stem
        if not mask.any():
            new_row = pd.DataFrame([{"file": self._cur_validate_stem}])
            index_df = pd.concat([index_df, new_row], ignore_index=True)
            mask = index_df["file"] == self._cur_validate_stem
        if di.BAD_SENS_COL not in index_df.columns:
            index_df[di.BAD_SENS_COL] = ""
        index_df[di.BAD_SENS_COL] = index_df[di.BAD_SENS_COL].astype(object)
        index_df.loc[mask, di.BAD_SENS_COL] = "Y"
        self._save_validate_index(index_df)
        self.lbl_all_validated.setText(f"{self._cur_validate_stem} marked Bad.")
        self._refresh_validate_list()

    def _save_one_validated(self, index_df, stem, df, time, pres, hig, nadir_idx,
                            user_validated=False, nadir_changed=False):
        """Writes the ROI window CSV and updates `index_df` in place for
        one sensor - the same operation Validate's own Save+Next performs
        (page_validate.py._do_save_window/_do_update_index), reused here
        for both the single-file and Auto process all paths.

        `user_validated=True` means a human reviewed and (re-)saved this
        sensor via Save+Next, as opposed to Auto process all - see the
        module-level _VALIDATED_COL/_USER_VALIDATED_COL/_FLAGGED_COL
        comments for what each column tracks. `nadir_changed` records
        whether the saved nadir differs from what was loaded (a human
        actually moved it, not just re-confirmed it) - both flow into the
        Report step's "Processing review"."""
        start, end = self._window_bounds(time, nadir_idx, len(df))
        ms = int(round(self._win_sec * 1000))
        out_dir = self._lib_root / _WIN_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        df.iloc[start:end + 1].to_csv(out_dir / f"{stem}_{ms}ms.csv", index=False)

        nadir_t = float(time[nadir_idx])
        nadir_v = float(pres[nadir_idx]) if pres is not None else float("nan")
        hig_window_max = (float(np.max(hig[start:end + 1]))
                          if hig is not None and len(hig) else float("nan"))
        mask = index_df["file"] == stem
        if not mask.any():
            new_row = pd.DataFrame([{"file": stem}])
            index_df = pd.concat([index_df, new_row], ignore_index=True)
            mask = index_df["file"] == stem
        index_df.loc[mask, _NADIR_T_COL] = nadir_t
        index_df.loc[mask, _NADIR_V_COL] = nadir_v
        index_df.loc[mask, "nadir_window_start"] = time[start]
        index_df.loc[mask, "nadir_window_end"] = time[end]
        index_df.loc[mask, _HIG_WINDOW_MAX_COL] = hig_window_max

        # a column read back as float (blank/NaN with no prior string
        # value) will not take "Y" in place without widening first -
        # pandas warns (soon errors) otherwise
        for col in (_VALIDATED_COL, _FLAGGED_COL, _USER_VALIDATED_COL,
                   _USER_ADJUSTED_COL):
            if col not in index_df.columns:
                index_df[col] = ""
            index_df[col] = index_df[col].astype(object)

        index_df.loc[mask, _VALIDATED_COL] = "Y"
        is_flagged = not np.isnan(hig_window_max) and hig_window_max < _FLAG_HIG_THRESHOLD_G
        index_df.loc[mask, _FLAGGED_COL] = "Y" if is_flagged else "N"
        if user_validated:
            index_df.loc[mask, _USER_VALIDATED_COL] = "Y"
            if nadir_changed:
                index_df.loc[mask, _USER_ADJUSTED_COL] = "Y"
        return index_df

    def _save_and_next_validate(self):
        if not self._cur_validate_stem:
            return
        index_df = self._validate_index()
        if index_df is None:
            return
        stem = self._cur_validate_stem
        nadir_changed = (self._loaded_nadir_idx is not None
                         and self._cur_validate_nadir_idx != self._loaded_nadir_idx)
        index_df = self._save_one_validated(
            index_df, stem, self._cur_validate_df,
            self._cur_validate_time, self._cur_validate_pres, self._cur_validate_hig,
            self._cur_validate_nadir_idx, user_validated=True,
            nadir_changed=nadir_changed)
        self._validate_dirty = True
        self._save_validate_index(index_df)
        self._refresh_validate_list()
        self._jump_next_in_list_validate(stem)

    def _reset_current_validate(self):
        if self._cur_validate_stem:
            self._load_validate_file(self._cur_validate_stem)

    def _jump_next_in_list_validate(self, from_stem):
        """Advances to the next sensor in on-screen list order (whatever
        is currently visible, respecting Show bad) - unlike "Jump to next
        unvalidated" below, this doesn't skip already-validated sensors,
        so Save + Next keeps stepping through the list even after Auto
        process all has already validated everything."""
        index_df = self._validate_index()
        bad = set()
        if index_df is not None and di.BAD_SENS_COL in index_df.columns:
            bad = set(index_df[index_df[di.BAD_SENS_COL]
                      .astype(str).str.upper() == "Y"]["file"])
        show_bad = self.chk_show_bad.isChecked()
        visible = [f["stem"] for f in self._validate_files
                  if show_bad or f["stem"] not in bad]
        if from_stem in visible:
            idx = visible.index(from_stem)
            if idx + 1 < len(visible):
                self._load_validate_file(visible[idx + 1])

    def _jump_next_unvalidated_validate(self):
        """Flagged-and-unreviewed first (what actually needs a look),
        then anything Auto process all hasn't even auto-validated yet
        (e.g. it was skipped or added after the last Auto process all
        run) - matches the list's own sort order in _refresh_validate_list."""
        auto_validated, user_validated, flagged, _bad = self._validation_status()
        for f in self._validate_files:
            if f["stem"] in flagged and f["stem"] not in user_validated:
                self._load_validate_file(f["stem"])
                return
        for f in self._validate_files:
            if f["stem"] not in auto_validated:
                self._load_validate_file(f["stem"])
                return

    def _auto_process_all(self):
        if self._lib_root is None or not self._validate_files:
            return
        index_df = self._validate_index()
        if index_df is None:
            index_df = pd.DataFrame({"file": []})
        self.btn_auto_process_all.setEnabled(False)
        self.btn_save_export.setEnabled(False)
        self._auto_spinner.start()
        self.lbl_all_validated.setText("Auto-processing…")
        self._auto_process_thread = _AutoProcessThread(
            self._lib_root, self._win_sec, list(self._validate_files), index_df)
        self._auto_process_thread.progress.connect(self._on_auto_process_progress)
        self._auto_process_thread.done.connect(self._on_auto_process_done)
        self._auto_process_thread.start()

    def _on_auto_process_progress(self, done, total):
        self.lbl_all_validated.setText(f"Auto-processing… {done}/{total}")

    def _on_auto_process_done(self, index_df, n_done):
        self._auto_spinner.stop()
        self.btn_auto_process_all.setEnabled(True)
        self.btn_save_export.setEnabled(True)
        self._validate_dirty = True
        self._save_validate_index(index_df)
        self._refresh_validate_list()
        _auto, _user, flagged, _bad = self._validation_status()
        n_flagged = sum(1 for f in self._validate_files if f["stem"] in flagged)
        self.lbl_all_validated.setText(
            f"Auto-processed {n_done} sensor(s), {n_flagged} flagged for review.")

    def _save_and_export(self):
        if self._lib_root is None:
            return
        index_df = self._validate_index()
        cfg = sensor_config.active()
        self.btn_save_export.setEnabled(False)
        self.lbl_all_validated.setText("Building dataset…")
        self._extract_thread = _ExtractThread(
            self._lib_root, OPT_SEGMENTED, set(), index_df, cfg)
        self._extract_thread.done.connect(self._on_extract_done)
        self._extract_thread.start()

    def _on_extract_done(self, n_ok, n_skip, n_rows):
        self.btn_save_export.setEnabled(True)
        df = self._extract_thread.result if self._extract_thread else None
        if df is None or not len(df):
            self.lbl_all_validated.setText("Dataset build produced no rows.")
            self._advance_after_export = False
            return
        ident = self.dep_edits[di.DEPLOYMENT_COL].text().strip() or "dataset"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = settings.get_input_data_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{ident}_{stamp}.csv"
        try:
            df.to_csv(out_path, index=False)
        except Exception as e:
            self.lbl_all_validated.setText(f"Save failed: {e}")
            self._advance_after_export = False
            return
        self._built_dataset_path = out_path
        self._validate_dirty = False
        self.lbl_all_validated.setText(
            f"Saved and exported {n_rows} row(s) to {out_path.name}")
        # feed straight into the shared PredictionState (window.
        # ml_prediction_page.state) - Advanced mode's Dataset creation
        # wires its own dataset_ready the same way
        self.window.ml_prediction_page.on_dataset_ready(
            df, f"Simple mode - {ident}")
        if self._advance_after_export:
            # "Save and continue" on the unsaved-data prompt (_go_next) -
            # the advance it deferred happens here, now that the export
            # this needed has actually finished
            self._advance_after_export = False
            self._refresh_predict_step()
            self.stack.setCurrentIndex(4)
            self._sync_step_highlight()

    # ── page 4: predict ──────────────────────────────────────────────────────
    def _build_predict_page(self):
        """Centred, single-column layout (simple_spec/Predict.png) -
        Dataset card, then Load/Run buttons, then status text, then the
        two result rings side by side ("Predicted strikes" and "Strike
        classes" - the per-region/class breakdown a multiclass run
        produces, mirroring Advanced mode's own card_regions ring;
        ml_tab_predict.py._refresh_cards)."""
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(10)
        title = QLabel("Predict blade strike from sensor data…")
        title.setStyleSheet(f"color:{TEXT};font-weight:bold;")
        v.addWidget(title)

        # equal stretch above/below - unequal (1 above, 2 below, as this
        # briefly was) pins the content block near the top since most of
        # any extra room the dialog is resized into only ever grows the
        # larger side, reading as if the content itself had a fixed
        # height/position rather than genuinely centring
        v.addStretch(1)

        grp_ds = Section("Dataset")
        grp_ds.setMaximumWidth(430)
        dv = QVBoxLayout(grp_ds)
        self.card_predict_dataset = MetaCard("Curated sensor dataset")
        dv.addWidget(self.card_predict_dataset)
        ds_row = QHBoxLayout()
        ds_row.addStretch()
        ds_row.addWidget(grp_ds)
        ds_row.addStretch()
        v.addLayout(ds_row)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_load_dataset = QPushButton("Load dataset CSV…")
        self.btn_load_dataset.setMinimumSize(180, 40)
        self.btn_load_dataset.clicked.connect(self._load_dataset_csv)
        btn_row.addWidget(self.btn_load_dataset)
        self.btn_run_predict = QPushButton("Run prediction")
        self.btn_run_predict.setMinimumSize(180, 40)
        self.btn_run_predict.clicked.connect(self._run_predict)
        btn_row.addWidget(self.btn_run_predict)
        btn_row.addStretch()
        v.addLayout(btn_row)

        self.lbl_predict_status = QLabel("")
        self.lbl_predict_status.setStyleSheet(f"color:{MUTED};")
        self.lbl_predict_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.lbl_predict_status)

        self.lbl_predict_done = QLabel("")
        self.lbl_predict_done.setStyleSheet(f"color:{OK};font-weight:bold;")
        self.lbl_predict_done.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.lbl_predict_done)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(16)
        cards_row.addStretch()
        self.card_predicted_strikes = RingCard("Predicted strikes")
        cards_row.addWidget(self.card_predicted_strikes)
        self.card_strike_classes = RingCard("Strike classes")
        cards_row.addWidget(self.card_strike_classes)
        cards_row.addStretch()
        v.addLayout(cards_row)

        v.addStretch(1)
        return page

    def _refresh_predict_step(self):
        state = self.window.ml_prediction_page.state
        self._auto_select_model(state)
        self._refresh_predict_dataset_card()
        self.btn_run_predict.setEnabled(state.dataset_df is not None)

    def _auto_select_model(self, state):
        """Defaults to the stable 'binary1'/'multiclass1' models in the
        shared app-root models folder (settings.get_models_dir()) - the
        one place both of the real, named production models actually
        live - not "whatever finished training most recently" and not a
        per-library deploy folder (Advanced mode's own Deploy tab writes
        versioned models like binary1_0/binary1_1 into the *session
        library's* StrikeWorks_user_output/models/, which is a different,
        per-run destination Simple mode was never meant to follow). The
        only way to deviate from the shared folder is a deliberate pin in
        Adjustments (settings.get_default_model/get_default_mc_model),
        which can point anywhere.

        Always rescans rather than trusting `state.bin_candidates` already
        being non-empty - some earlier load (construction time, or a demo
        run switching libraries) may have pointed `state.models_dir`
        somewhere else entirely."""
        models_dir = settings.get_models_dir()
        state.load_models_from_dir(models_dir)

        bin_candidates = state.bin_candidates
        if bin_candidates:
            default = settings.get_default_model()
            if default is not None and Path(default) in bin_candidates:
                chosen = Path(default)
            else:
                chosen = (next((p for p in bin_candidates if p.stem == "binary1"),
                               None)
                          or max(bin_candidates, key=lambda p: p.stat().st_mtime))
            if state.bin_model_path != chosen:
                state.select_bin_model(chosen)

        mc_candidates = state.mc_candidates
        if mc_candidates:
            mc_default = settings.get_default_mc_model()
            if mc_default is not None and Path(mc_default) in mc_candidates:
                mc_chosen = Path(mc_default)
            else:
                mc_chosen = (next((p for p in mc_candidates
                                   if p.stem == "multiclass1"), None)
                             or max(mc_candidates, key=lambda p: p.stat().st_mtime))
            if state.mc_model_path != mc_chosen:
                state.select_mc_model(mc_chosen)

    def _load_dataset_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self.window, "Load dataset CSV", str(Path.cwd()),
            "CSV files (*.csv)")
        if not path:
            return
        state = self.window.ml_prediction_page.state
        ok, msg = state.load_dataset_csv(path)
        self.lbl_predict_status.setText(msg)
        self._refresh_predict_dataset_card()
        self.btn_run_predict.setEnabled(ok)

    def _refresh_predict_dataset_card(self):
        state = self.window.ml_prediction_page.state
        m = state.dataset_meta
        if not m:
            self.card_predict_dataset.set_rows([("Dataset", "No dataset loaded")])
            return
        sr = m.get("sampling_rate_hz")
        seq = None
        if m.get("seq_len_min") is not None:
            if m["seq_len_min"] == m["seq_len_max"]:
                seq = f"{m['seq_len_max']} samples"
                if sr:
                    seq += f" ({m['seq_len_max'] / sr * 1000:.0f} ms)"
            else:
                seq = f"{m['seq_len_min']}-{m['seq_len_max']} samples (varying)"
        req = set(state.required_channels())
        n_chan_present = (len([c for c in m.get("columns", []) if c in req])
                          if req else None)
        self.card_predict_dataset.set_rows([
            ("Dataset",       m.get("name")),
            ("Source",        state.dataset_source),
            ("Recordings",    m.get("n_files")),
            ("Sensor rows",   f"{m.get('n_rows'):,}" if m.get("n_rows") else None),
            ("Treatments",    f"{len(m['treatments'])} "
                              f"({', '.join(m['treatments'])})"
                              if m.get("treatments") else None),
            ("Sampling rate", f"{sr} Hz" if sr else None),
            ("Window length", seq),
            ("Model channels",
             f"{n_chan_present}/{len(req)} present" if req else None),
            ("Annotations",   f"ground-truth labels present "
                              f"({m['annotation_column']})"
                              if m.get("annotated") else "none"),
        ])

    def _run_predict(self):
        state = self.window.ml_prediction_page.state
        self.btn_run_predict.setEnabled(False)
        self.lbl_predict_status.setText("Running…")
        self.lbl_predict_status.setStyleSheet(f"color:{ACCENT};")
        state.run_prediction()

    def _on_predict_finished(self):
        state = self.window.ml_prediction_page.state
        self.btn_run_predict.setEnabled(True)
        meta = state.run_meta
        n = meta.get("n_files", 0)
        self.lbl_predict_status.setStyleSheet(f"color:{OK};")
        self.lbl_predict_status.setText(f"Predicting {n} recordings… done.")
        self.lbl_predict_done.setText("Blade strike predicted")
        df = state.summary
        if df is not None and len(df):
            n_total = int(df["n"].sum())
            n_strike = int(df["n_strike"].sum())
            self.card_predicted_strikes.set_segments([
                ("Strike", n_strike, PINK),
                ("No strike", n_total - n_strike, PALETTE[0]),
            ])

        mc_run = meta.get("mode") == "multiclass"
        have_classes = (mc_run and df is not None and len(df) and state.class_names
                        and all(f"n_{cn}" in df.columns for cn in state.class_names))
        self.card_strike_classes.setVisible(bool(have_classes))
        if have_classes:
            self.card_strike_classes.set_segments([
                (cn, int(df[f"n_{cn}"].sum()), PALETTE[i % len(PALETTE)])
                for i, cn in enumerate(state.class_names)
            ])
        else:
            self.card_strike_classes.clear()

    def _on_predict_failed(self, msg):
        self.btn_run_predict.setEnabled(True)
        self.lbl_predict_status.setStyleSheet(f"color:{BAD};")
        self.lbl_predict_status.setText(f"Prediction failed: {msg.splitlines()[-1]}")

    # ── page 5: report ───────────────────────────────────────────────────────
    def _build_report_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(10)
        title = QLabel("Report blade strike from sensor data…")
        title.setStyleSheet(f"color:{TEXT};font-weight:bold;")
        v.addWidget(title)

        self.tbl_report = QTableWidget(0, 0)
        self.tbl_report.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        v.addWidget(self.tbl_report)

        grp_figs = Section("Prediction figures")
        fv = QHBoxLayout(grp_figs)
        self.fig_report_bin = Figure(figsize=(4.3, 3.2), dpi=100)
        self.canvas_report_bin = FigureCanvas(self.fig_report_bin)
        self.fig_report_mc = Figure(figsize=(4.3, 3.2), dpi=100)
        self.canvas_report_mc = FigureCanvas(self.fig_report_mc)
        for c in (self.canvas_report_bin, self.canvas_report_mc):
            c.setSizePolicy(QSizePolicy.Policy.Expanding,
                            QSizePolicy.Policy.Expanding)
            fv.addWidget(c)
        v.addWidget(grp_figs, stretch=1)
        return page

    def _refresh_report_step(self):
        state = self.window.ml_prediction_page.state
        df = state.summary
        mc_run = state.run_meta.get("mode") == "multiclass"
        class_names = (state.class_names if mc_run and state.class_names
                       and df is not None
                       and all(f"n_{cn}" in df.columns for cn in state.class_names)
                       else [])
        headers = (["Treatment", "N", "Strikes", "No strike", "Strike rate",
                    "95% CI", "Mean prob", "Mean conf"] + list(class_names))
        self.tbl_report.setColumnCount(len(headers))
        self.tbl_report.setHorizontalHeaderLabels(headers)
        self.tbl_report.setRowCount(0 if df is None else len(df))
        if df is not None:
            for row, (_, r) in enumerate(df.iterrows()):
                n_strike = int(r["n_strike"])
                vals = [
                    str(r["treatment"]), str(int(r["n"])), str(n_strike),
                    str(int(r["n_no_strike"])),
                    f"{r['strike_rate'] * 100:.1f}%",
                    f"{r['ci_lo'] * 100:.1f}% - {r['ci_hi'] * 100:.1f}%",
                    f"{r['mean_prob']:.3f}", f"{r['mean_conf']:.3f}",
                ]
                for cn in class_names:
                    nc = int(r[f"n_{cn}"])
                    pct = nc / n_strike * 100 if n_strike else 0
                    vals.append(f"{nc} ({pct:.0f}%)")
                for col, val in enumerate(vals):
                    self.tbl_report.setItem(row, col, QTableWidgetItem(val))
        self.tbl_report.resizeColumnsToContents()

        ml_figures.draw_strike_rate(self.fig_report_bin, df, dark=True)
        self.canvas_report_bin.draw()
        ml_figures.draw_region(self.fig_report_mc, df,
                               class_names if mc_run else [], dark=True)
        self.canvas_report_mc.draw()

    def _processing_review_rows(self):
        """How Validate actually went for this library - auto vs. user
        validation, how many sensors Auto process all's own HIG-in-window
        check flagged for a second look, and how many of those a human
        actually moved the nadir on (not just re-confirmed). Not shown in
        this wizard's own Report step (that page is prediction output,
        not processing history) - fed into the *downloaded* report
        instead (_download_report -> ml_report.export_analysis), which is
        what "added to the report" actually meant."""
        total = len(self._validate_files)
        if not total:
            return []
        auto_validated, user_validated, flagged, _bad = self._validation_status()
        index_df = self._validate_index()
        n_adjusted = 0
        if index_df is not None and _USER_ADJUSTED_COL in index_df.columns:
            n_adjusted = int((index_df[_USER_ADJUSTED_COL]
                             .astype(str).str.upper() == "Y").sum())
        n_flagged = sum(1 for f in self._validate_files if f["stem"] in flagged)
        n_flagged_reviewed = sum(1 for f in self._validate_files
                                 if f["stem"] in flagged and f["stem"] in user_validated)
        return [
            ("Auto-validated",
             f"{sum(1 for f in self._validate_files if f['stem'] in auto_validated)}/{total}"),
            ("Flagged for review (HIG < "
             f"{_FLAG_HIG_THRESHOLD_G:.0f}g)", n_flagged),
            ("Flagged sensors reviewed", f"{n_flagged_reviewed}/{n_flagged}"),
            ("User-validated (any sensor)",
             f"{sum(1 for f in self._validate_files if f['stem'] in user_validated)}/{total}"),
            ("Nadir moved by user", n_adjusted),
        ]

    # ── page 6: finished ─────────────────────────────────────────────────────
    def _build_finished_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.addStretch()
        logo = self._make_logo("PyDracula_vertical.png", width=220)
        if logo is not None:
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v.addWidget(logo)
        title = QLabel("Finished!")
        title.setStyleSheet(f"color:{TEXT};font-size:20px;font-style:italic;"
                            "font-weight:bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(title)
        btn_download = QPushButton("Download StrikeWorks report")
        btn_download.setMinimumHeight(36)
        btn_download.clicked.connect(self._download_report)
        wrap = QHBoxLayout()
        wrap.addStretch()
        wrap.addWidget(btn_download)
        wrap.addStretch()
        v.addLayout(wrap)
        v.addStretch()
        return page

    def _download_report(self):
        state = self.window.ml_prediction_page.state
        if state.summary is None or state.run_id is None:
            QMessageBox.information(
                self.window, "Nothing to report",
                "Run a prediction first (Predict step).")
            return
        dirpath = QFileDialog.getExistingDirectory(
            self.window, "Download StrikeWorks report to folder",
            str(settings.get_output_dir()))
        if not dirpath:
            return
        try:
            out = ml_report.export_analysis(
                state, dirpath,
                processing_review=self._processing_review_rows())
        except Exception as e:
            QMessageBox.critical(self.window, "Download failed", str(e))
            return
        QMessageBox.information(
            self.window, "Report downloaded", f"Saved to:\n{out}")
