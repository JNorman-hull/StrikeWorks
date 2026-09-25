# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Shared Library / Deployment / Treatment / Run selector.

Before this module existed, Annotate and Export animations each carried
their own copy of this logic (library combo, deployment scan, treatment
combo, sensor-CSV listing), built by copy-paste. The copies silently
diverged: Export animations' local exclusion list
(`{"global_sensor_index.csv", "model_features.csv"}` /
`("_nadir_window",)`) was missing the canonical `page_validate.py`
exclusions (`_min`, `_delineated`), so `_min` output files started
appearing in its sensor list where Annotate correctly filtered them out.

`LibrarySelector` is the fix: one `QWidget`, one copy of the scan/filter
logic, used identically by every page that needs to pick a library and
list its sensors - Annotate, Export animations, and (raw data) Process.
Process works from the raw folders rather than processed CSVs and
has no per-sensor bad/done status, so it uses the picker alone
(`sensor_list=False`, the default). Annotate and Export animations both
opt into the sensor-list panel (`sensor_list=True`) - one "Show bad
sensors" checkbox, one progress counter, one coloured table, with the same
show/hide-when-unticked filtering and white/green/red/amber colouring
everywhere it appears, driven by `populate_sensor_list()`.

Where a recording sits under raw_sens_data - deployment / treatment / run -
is `raw_layout.py`'s one definition; the Run filter is the third level of
it (a file with no run folder above it is Run 1).
"""
import os
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import raw_layout, settings
from .ml_widgets import (
    BAD, MUTED, OK, WARN, Section, Spinner, style_table, when_visible,
)
from .raw_layout import RAW_DIR, UNGROUPED

CSV_DIR = Path("processed_sens_data") / "csv"
ALL_DEPLOYMENTS = None   # combo data sentinel for "All deployments"/"All treatments"/"All runs"


def _same_path(a, b) -> bool:
    """Path equality that survives case/separator differences (a session
    library remembered as C:\\users\\... vs the folder scan's C:\\Users\\...)."""
    if not a or not b:
        return False
    return (os.path.normcase(os.path.normpath(str(a)))
            == os.path.normcase(os.path.normpath(str(b))))


def _run_sort_key(run):
    """Numeric runs in numeric order, anything else after them by name."""
    try:
        return (0, int(float(run)), "")
    except (TypeError, ValueError):
        return (1, 0, str(run))

# canonical rules for what counts as a "sensor" CSV versus a derived/scratch
# output - the single definition every page (Validate, this widget, and
# hence Annotate/Export/Process) agrees on
_EXCL_SUFFIXES = {"_min", "_delineated"}
_EXCL_NAMES = {"global_sensor_index.csv"}


class _RawScanThread(QThread):
    """raw_layout.scan_tree off the GUI thread. `done(generation, tree)` -
    the selector ignores a generation a newer scan has superseded."""

    done = Signal(int, object)

    def __init__(self, gen, raw_dir):
        super().__init__()
        self._gen = gen
        self._raw_dir = raw_dir

    def run(self):
        try:
            tree = raw_layout.scan_tree(self._raw_dir)
        except Exception:
            tree = raw_layout.RawTree()
        self.done.emit(self._gen, tree)


class LibrarySelector(QWidget):
    """Library / Deployment / Treatment picker, embeddable in any page.

    Library selection is app-wide now (Home / session_state.py, plus the
    libraries folder itself in Adjustments) - `show_picker=False` (Process,
    Annotate, Export animations) hides this widget's own library combo and
    "Libraries…" button, leaving just the Deployment/Treatment filters and
    a read-only "Library: X" label; the library still comes from
    `session_state` via `set_library()` exactly as before, just with no
    way to override it locally any more. `show_picker=True` (the default,
    for standalone/legacy use) keeps the full three-combo panel.

    Callers connect to `library_changed` (the library root itself switched
    - reload anything keyed to the whole library, e.g. the deployment
    index) and `filters_changed` (deployment/treatment changed, or the
    library just changed too - re-list sensors); `library_changed` always
    fires before `filters_changed` on a library switch, so a host's index/
    dataset reload runs before it repopulates its sensor table.
    """

    library_changed = Signal()
    filters_changed = Signal()
    selection_changed = Signal()       # tbl_sensors selection changed
    row_activated = Signal(int, int)   # row, column - tbl_sensors double-click

    def __init__(self, parent=None, sensor_list=False, list_columns=(),
                session_state=None, show_picker=True):
        super().__init__(parent)
        self._lib_dir = settings.get_libraries_dir()
        self._lib_root = None
        # stem (upper) -> (deployment, treatment, run, raw file path)
        self._locations = {}
        self._tree = None            # raw_layout.RawTree of the last finished scan
        self._scan_gen = 0           # newer scans supersede older ones
        self._scan_threads = []
        self._scan_from_sync = False
        self._list_columns = list(list_columns)
        self._cache = None           # last populate_sensor_list() call, for re-filtering
        self._session_state = session_state
        self._show_picker = show_picker
        self._syncing = False        # True while set_library() is soft-syncing this
                                      # picker to the session library - hosts check
                                      # this to skip their own "Library: X" status
                                      # message, which the session change already
                                      # gets exactly once from wherever it originated
        self._build(sensor_list)
        self._connect()
        start = session_state.library if session_state is not None else None
        self._populate_libraries(select=start)
        if session_state is not None:
            session_state.library_changed.connect(self.set_library)

    # ── session library soft-sync (session_state.py) ─────────────────────────
    def set_library(self, path):
        """Selects `path` in the library combo if it's one of the
        libraries currently listed. `path=None` (New Session) clears this
        picker's own selection too, rather than leaving it dangling on
        whatever library it had before - a fresh session should read as
        fresh everywhere it's reflected, not just on Home. Also how
        `SessionState.library_changed` re-syncs this picker when the
        session library changes elsewhere."""
        self._syncing = True
        try:
            if path is None:
                self.cmb_library.blockSignals(True)
                self.cmb_library.setCurrentIndex(-1)
                self.cmb_library.blockSignals(False)
                self._on_library_changed()
                return
            self._populate_libraries(select=path)
        finally:
            self._syncing = False

    @property
    def syncing(self):
        """True while a soft-sync (`set_library()`, from the session
        library changing elsewhere) is driving this picker, as opposed to
        the user changing this page's own combo directly. Checked by host
        pages before emitting their own "Library: X" status message, so
        one session-wide library change doesn't produce one such message
        per soft-synced page."""
        return self._syncing

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, sensor_list):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.section = Section("Library" if self._show_picker else "Filters")
        fv = QVBoxLayout(self.section)
        fv.setSpacing(6)
        # exposed so a host page can append its own controls into the same
        # visual panel, above the sensor list if there is one
        self.section_layout = fv

        # cmb_library/btn_change_libs still exist and still drive every bit
        # of internal scanning logic below even with show_picker=False -
        # library selection just isn't done *here* any more (Home/session_
        # state is the only place now), so the row is simply never added to
        # the visible layout in that mode, in favour of a read-only label
        self.cmb_library = QComboBox()
        self.cmb_library.setMinimumWidth(140)
        self.btn_change_libs = QPushButton("Libraries…")
        if self._show_picker:
            lib_row = QHBoxLayout()
            lib_row.addWidget(self.cmb_library, stretch=1)
            lib_row.addWidget(self.btn_change_libs)
            fv.addLayout(lib_row)
        else:
            self.lbl_current_library = QLabel("No library selected.")
            self.lbl_current_library.setStyleSheet(f"color:{MUTED};")
            self.lbl_current_library.setWordWrap(True)
            fv.addWidget(self.lbl_current_library)

        # shown while the library's raw folder is being scanned (in the
        # background - a big OneDrive library can take a while)
        loading_row = QHBoxLayout()
        self._spinner = Spinner(size=16)
        self._spinner.setVisible(False)
        loading_row.addWidget(self._spinner)
        self.lbl_loading = QLabel("")
        self.lbl_loading.setStyleSheet(f"color:{MUTED};")
        loading_row.addWidget(self.lbl_loading, stretch=1)
        fv.addLayout(loading_row)

        self.cmb_deployment = QComboBox()
        fv.addLayout(self._row(self._muted("Deployment"), self.cmb_deployment))
        self.cmb_treatment = QComboBox()
        fv.addLayout(self._row(self._muted("Treatment"), self.cmb_treatment))
        self.cmb_run = QComboBox()
        fv.addLayout(self._row(self._muted("Run"), self.cmb_run))
        v.addWidget(self.section)

        if sensor_list:
            self._build_sensor_list(v)

    def _build_sensor_list(self, v):
        self.chk_show_flags = QCheckBox("Show bad sensors")
        self.chk_show_flags.setChecked(True)
        self.chk_show_flags.toggled.connect(self._on_show_flags_toggled)
        v.addWidget(self.chk_show_flags)

        self.lbl_progress = QLabel("")
        self.lbl_progress.setStyleSheet(f"color:{MUTED};")
        # wraps, so a long counter line can't set the whole column's width
        self.lbl_progress.setWordWrap(True)
        v.addWidget(self.lbl_progress)

        self.tbl_sensors = QTableWidget(0, 1 + len(self._list_columns))
        self.tbl_sensors.setHorizontalHeaderLabels(["Sensor"] + self._list_columns)
        style_table(self.tbl_sensors)
        self.tbl_sensors.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_sensors.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl_sensors.itemSelectionChanged.connect(
            self.selection_changed.emit)
        self.tbl_sensors.itemDoubleClicked.connect(
            lambda item: self.row_activated.emit(item.row(), item.column()))
        v.addWidget(self.tbl_sensors, stretch=1)

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
        self.cmb_deployment.currentIndexChanged.connect(self._rebuild_treatment_combo)
        self.cmb_deployment.currentIndexChanged.connect(
            lambda _i: self.filters_changed.emit())
        self.cmb_treatment.currentIndexChanged.connect(self._rebuild_run_combo)
        self.cmb_treatment.currentIndexChanged.connect(
            lambda _i: self.filters_changed.emit())
        self.cmb_run.currentIndexChanged.connect(
            lambda _i: self.filters_changed.emit())

    # ── libraries ────────────────────────────────────────────────────────────
    @property
    def lib_root(self):
        return self._lib_root

    @property
    def lib_dir(self):
        return self._lib_dir

    @property
    def deployment_map(self):
        """stem (upper) -> (deployment, treatment) - the two-level view
        callers used before runs existed."""
        return {s: (d, t) for s, (d, t, _r, _p) in self._locations.items()}

    @property
    def locations(self):
        """stem (upper) -> (deployment, treatment, run, raw file path)."""
        return self._locations

    def wanted_deployment(self):
        return self.cmb_deployment.currentData()

    def wanted_treatment(self):
        return self.cmb_treatment.currentData()

    def wanted_run(self):
        return self.cmb_run.currentData()

    def _populate_libraries(self, select=None):
        # signals stay blocked through setCurrentIndex too - _on_library_
        # changed() is called explicitly, once, at the end regardless;
        # without this, an index that actually changes fires it a second
        # time via currentIndexChanged, doubling every status message and
        # re-scan this triggers (very visible once several pages soft-
        # sync to the same session library change at once)
        #
        # The libraries folder is re-read every time, not cached from
        # construction: a cached copy is what left Raw data processing,
        # Annotate and Export animations stuck on a library from the *old*
        # folder after it was changed in Adjustments. And a session library
        # this list can't find is never silently swapped for "the first
        # library in the list" any more (that fallback is exactly what
        # showed up as these pages not following Home) - it's added as its
        # own entry instead, or with no session library, nothing is picked.
        self._lib_dir = settings.get_libraries_dir()
        self.cmb_library.blockSignals(True)
        self.cmb_library.clear()
        libs = settings.list_libraries()
        for lib in libs:
            self.cmb_library.addItem(lib.name, str(lib))
        self.btn_change_libs.setToolTip(str(self._lib_dir))
        idx = -1
        if select:
            idx = next((i for i in range(self.cmb_library.count())
                        if _same_path(self.cmb_library.itemData(i), select)), -1)
            if idx < 0 and Path(select).is_dir():
                self.cmb_library.addItem(Path(select).name, str(select))
                idx = self.cmb_library.count() - 1
        elif self._session_state is None and libs:
            idx = 0   # standalone picker with no session to follow
        self.cmb_library.setCurrentIndex(idx)
        self.cmb_library.blockSignals(False)
        self._on_library_changed()

    def _change_libraries(self):
        chosen = QFileDialog.getExistingDirectory(
            self, "Select libraries folder", str(self._lib_dir))
        if not chosen:
            return
        self._lib_dir = settings.set_libraries_dir(chosen)
        self._populate_libraries()

    def _on_library_changed(self, *_args):
        path = self.cmb_library.currentData()
        self._lib_root = Path(path) if path else None
        if not self._show_picker:
            self.lbl_current_library.setText(
                f"Library: {self._lib_root.name}" if self._lib_root
                else "No library selected.")
        # the library itself is known straight away; scanning its raw
        # folder (and the host re-listing its sensors) waits until this
        # page is actually on screen - a library switch costs a page that
        # isn't being looked at nothing, however big the library
        self._scan_from_sync = self._syncing
        self._scan_gen += 1
        self._tree = None
        when_visible(self, self._start_scan, key="scan")

    # ── deployments / treatments / runs (raw_layout.py) ──────────────────────
    @property
    def raw_tree(self):
        """The last finished scan (raw_layout.RawTree), or None while the
        library hasn't been scanned yet."""
        return self._tree

    def rescan(self, wait=False):
        """Re-read the raw folder tree (files added or moved since the
        library was opened) and tell the host to re-list. `wait=True`
        scans right here instead of in the background (demo runner)."""
        self._scan_from_sync = False
        self._start_scan(wait=wait)

    def _start_scan(self, wait=False):
        """Scan the raw folder in the background with a loading spinner -
        one os.walk (raw_layout.scan_tree) - then rebuild the filters and
        tell the host (`library_changed`, then `filters_changed`)."""
        self._scan_gen += 1
        gen = self._scan_gen
        raw_dir = self._lib_root / RAW_DIR if self._lib_root else None
        if raw_dir is None or not raw_dir.exists():
            self._apply_tree(gen, raw_layout.RawTree())
            return
        if wait:
            self._apply_tree(gen, raw_layout.scan_tree(raw_dir))
            return
        self._set_loading(True)
        thread = _RawScanThread(gen, raw_dir)
        thread.done.connect(self._apply_tree)
        thread.finished.connect(lambda t=thread: self._scan_threads.remove(t)
                                if t in self._scan_threads else None)
        self._scan_threads.append(thread)
        thread.start()

    def _set_loading(self, on):
        if on:
            self._spinner.start()
            self.lbl_loading.setText(
                f"Loading {self._lib_root.name}…" if self._lib_root else "Loading…")
        else:
            self._spinner.stop()
            self.lbl_loading.setText("")
        for cmb in (self.cmb_deployment, self.cmb_treatment, self.cmb_run):
            cmb.setEnabled(not on)

    def _apply_tree(self, gen, tree):
        if gen != self._scan_gen:
            return   # a newer scan (another library switch) supersedes this one
        self._set_loading(False)
        self._tree = tree
        self._scan_deployments()
        self._syncing = self._scan_from_sync
        try:
            self.library_changed.emit()
            self.filters_changed.emit()
        finally:
            self._syncing = False

    def _scan_deployments(self):
        """Rebuild the Deployment/Treatment/Run filters from the last scan
        (raw_layout.scan_tree): `raw_sens_data/<deployment>/<treatment>/
        Run <n>/` is the normal shape; a missing run level is Run 1, and a
        missing deployment/treatment level buckets as UNGROUPED rather than
        being dropped. Anything inside a VIDEO folder is a clip, not a
        recording.
        """
        self._locations = dict(self._tree.locations) if self._tree else {}
        current_dep = self.cmb_deployment.currentData()
        self.cmb_deployment.blockSignals(True)
        self.cmb_deployment.clear()
        self.cmb_deployment.addItem("All deployments", ALL_DEPLOYMENTS)

        for name in sorted({d for d, _t, _r, _p in self._locations.values()}):
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
        self.cmb_treatment.addItem("All treatments", ALL_DEPLOYMENTS)
        treatments = sorted({
            treatment for (deployment, treatment, _r, _p) in self._locations.values()
            if wanted_deployment is None or deployment == wanted_deployment})
        for name in treatments:
            self.cmb_treatment.addItem(name, name)
        idx = self.cmb_treatment.findData(current)
        self.cmb_treatment.setCurrentIndex(idx if idx >= 0 else 0)
        self.cmb_treatment.blockSignals(False)
        self._rebuild_run_combo()

    def _rebuild_run_combo(self):
        wanted_deployment = self.cmb_deployment.currentData()
        wanted_treatment = self.cmb_treatment.currentData()
        current = self.cmb_run.currentData()
        self.cmb_run.blockSignals(True)
        self.cmb_run.clear()
        self.cmb_run.addItem("All runs", ALL_DEPLOYMENTS)
        runs = {
            run for (deployment, treatment, run, _p) in self._locations.values()
            if (wanted_deployment is None or deployment == wanted_deployment)
            and (wanted_treatment is None or treatment == wanted_treatment)}
        for run in sorted(runs, key=_run_sort_key):
            self.cmb_run.addItem(f"Run {run}", run)
        idx = self.cmb_run.findData(current)
        self.cmb_run.setCurrentIndex(idx if idx >= 0 else 0)
        self.cmb_run.blockSignals(False)

    def _matches_filters(self, deployment, treatment, run):
        want_d, want_t, want_r = (self.wanted_deployment(),
                                  self.wanted_treatment(), self.wanted_run())
        return ((want_d is None or deployment == want_d)
                and (want_t is None or treatment == want_t)
                and (want_r is None or run == want_r))

    # ── video lookup ─────────────────────────────────────────────────────────
    # From the scan's own video index (every `<stem>_vid_*.mp4` in any VIDEO
    # folder, collected during the one walk) - a dict lookup per sensor, not
    # a directory listing per sensor, which on OneDrive was most of the time
    # a big library took to open.
    def video_matches_for(self, stem):
        if self._tree is None:
            return []
        return sorted(self._tree.videos.get(stem.upper(), []))

    # ── sensor listing ───────────────────────────────────────────────────────
    def list_sensor_csvs(self, apply_filters=True):
        """Every processed sensor CSV in the current library, tagged with
        its (deployment, treatment) and filtered to the current
        deployment/treatment selection unless `apply_filters` is False.

        The exclusion rules (`_EXCL_NAMES`/`_EXCL_SUFFIXES`) come from
        `page_validate.py` - the single canonical definition of what counts
        as a "sensor" CSV versus a derived/scratch output (nadir windows,
        delineation, minimal/reduced variants) - so every caller of this
        widget always agrees with Validate about what a sensor is.
        """
        if self._lib_root is None:
            return []
        csv_dir = self._lib_root / CSV_DIR
        if not csv_dir.exists():
            return []
        rows = []
        for p in sorted(csv_dir.rglob("*.csv")):
            if p.name in _EXCL_NAMES or any(
                    p.stem.endswith(s) for s in _EXCL_SUFFIXES):
                continue
            deployment, treatment, run, _raw = self._locations.get(
                p.stem.upper(), (UNGROUPED, UNGROUPED, raw_layout.DEFAULT_RUN, None))
            if apply_filters and not self._matches_filters(deployment, treatment, run):
                continue
            rows.append({"path": p, "stem": p.stem, "deployment": deployment,
                        "treatment": treatment, "run": run})
        return rows

    def scan_folder(self):
        """The raw folder the current Deployment/Treatment filters narrow
        to (the whole raw_sens_data folder for "All"), for callers that
        scan raw files themselves - the Run filter is applied per file by
        `_matches_filters`, since a legacy treatment folder with no run
        subfolders is still Run 1."""
        if self._lib_root is None:
            return None
        folder = self._lib_root / RAW_DIR
        dep = self.wanted_deployment()
        if dep and dep != UNGROUPED:
            folder = folder / dep
            treat = self.wanted_treatment()
            if treat and treat != UNGROUPED:
                folder = folder / treat
        return folder

    def matches_filters(self, deployment, treatment, run):
        return self._matches_filters(deployment, treatment, run)

    # ── sensor list panel (opt-in via sensor_list=True) ─────────────────────────
    def _on_show_flags_toggled(self, _checked):
        # re-render from the cached call rather than making the host rescan
        # the filesystem just to react to this checkbox
        if self._cache is not None:
            rows, kwargs = self._cache
            self.populate_sensor_list(rows, **kwargs)

    def populate_sensor_list(self, rows, is_bad=None, is_done=None,
                             done_label="In dataset", extra=None,
                             colour=None, order_key=None, progress=None):
        """Render `rows` (each a dict with at least "stem", usually also
        "path") into the sensor table - the one behaviour every list of
        sensors in the app should share:

          - never flagged bad, not yet done -> white
          - never flagged bad, done         -> green
          - flagged bad, not yet done       -> red   (hidden if unticked)
          - flagged bad, done               -> amber (hidden if unticked;
            stays visually distinct from a plain "done" row rather than
            disappearing into green, since bad-but-done still needs
            attention)

        "Show bad sensors" unticked doesn't just stop colouring bad rows -
        it drops them from the list entirely, so the count of visible rows
        is the count of rows actually worth looking at right now.

        `is_bad(stem)`/`is_done(stem)` are optional predicates (default:
        never bad / never done - a caller that only wants the picker's list
        without status tracking can leave both out). `extra(row)` returns
        the values for any extra columns configured via `list_columns`, in
        order. `done_label` is the counter's prefix, e.g. "In dataset" or
        "Synced" - whatever "done" means for this page.

        A host with its own status model (Annotate's auto/flagged/user-
        validated states) can override the defaults: `colour(stem)` returns
        the row's colour (or None for plain), `order_key(row)` sorts the
        rows (a stable sort - e.g. "needs review" first), and
        `progress(rows)` returns the counter text.
        """
        self._cache = (rows, dict(is_bad=is_bad, is_done=is_done,
                                  done_label=done_label, extra=extra,
                                  colour=colour, order_key=order_key,
                                  progress=progress))
        is_bad = is_bad or (lambda _s: False)
        is_done = is_done or (lambda _s: False)
        extra = extra or (lambda _r: [])
        show_flags = self.chk_show_flags.isChecked()

        visible = [r for r in rows if show_flags or not is_bad(r["stem"])]
        if order_key is not None:
            visible = sorted(visible, key=order_key)

        self.tbl_sensors.setRowCount(len(visible))
        n_done = n_done_bad = 0
        for i, row in enumerate(visible):
            stem = row["stem"]
            bad, done = is_bad(stem), is_done(stem)
            item = QTableWidgetItem(stem)
            item.setData(Qt.ItemDataRole.UserRole, row.get("path"))
            if done:
                n_done += 1
                if bad:
                    n_done_bad += 1
            if colour is not None:
                c = colour(stem)
                if c:
                    item.setForeground(QColor(c))
            elif done:
                item.setForeground(QColor(WARN if bad else OK))
            elif bad:
                item.setForeground(QColor(BAD))
            self.tbl_sensors.setItem(i, 0, item)
            for c, val in enumerate(extra(row), start=1):
                self.tbl_sensors.setItem(i, c, QTableWidgetItem(str(val)))
        self.tbl_sensors.resizeColumnsToContents()

        if progress is not None:
            self.lbl_progress.setText(progress(rows))
            return
        suffix = f" ({n_done_bad} bad)" if n_done_bad and show_flags else ""
        self.lbl_progress.setText(f"{done_label}: {n_done} / {len(rows)}{suffix}")
