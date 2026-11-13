"""The Deployment / Treatment / Run filters used by Raw data processing,
Annotate, Export animations and Model comparison, with an optional sensor
list (Annotate, Export animations): a "Show bad sensors" box, a progress
count and a table coloured by status (`populate_sensor_list()`).

Where a recording sits under raw_sens_data - deployment / treatment / run -
is `raw_layout.py`'s one definition; a file with no run folder above it is
Run 1.
"""
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import raw_layout, sensor_sort
from .cards import Spinner
from .layout import Section, when_visible
from .theme import BAD, OK, WARN, muted_label, style
from .raw_layout import RAW_DIR, UNGROUPED

ALL_DEPLOYMENTS = None   # combo data sentinel for "All deployments"/"All treatments"/"All runs"


def library_picker(combo):
    """Give a session-library dropdown (item data: the library's folder)
    its folder as the tooltip - in place of a path label under it - and a
    right-click "Open folder". Hosts that change the selection with the
    signals blocked call `show_library_path` themselves."""
    combo.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def menu(pos):
        from .layout import popup_menu
        from .win_utils import open_folder
        path = combo.currentData()
        m = popup_menu(combo)
        act = m.addAction("Open folder")
        act.setEnabled(bool(path) and Path(path).is_dir())
        chosen = m.exec(combo.mapToGlobal(pos))
        m.deleteLater()
        if chosen is act:
            open_folder(path)

    combo.customContextMenuRequested.connect(menu)
    combo.currentIndexChanged.connect(lambda _i: show_library_path(combo))
    show_library_path(combo)


def show_library_path(combo):
    path = combo.currentData()
    combo.setToolTip(str(path) if path else "No library selected.")


class RawScanThread(QThread):
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
        except Exception as e:
            print(f"Could not scan {self._raw_dir}: {e}")
            tree = raw_layout.RawTree()
        self.done.emit(self._gen, tree)


class FilterCombo(QComboBox):
    """A filter combo as wide as its longest name where there's room, but
    able to shrink to a few characters rather than hold its column wide;
    its list still opens wide enough to read every name."""

    MIN_CHARS = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(self.MIN_CHARS)

    def sizeHint(self):
        hint = super().sizeHint()       # MIN_CHARS wide
        fm = self.fontMetrics()
        frame = hint.width() - self.MIN_CHARS * fm.horizontalAdvance("X")
        names = max((fm.horizontalAdvance(self.itemText(i))
                     for i in range(self.count())), default=0)
        return QSize(max(hint.width(), frame + names), hint.height())

    def showPopup(self):
        view = self.view()
        view.setMinimumWidth(view.sizeHintForColumn(0) + 2 * view.frameWidth()
                             + view.verticalScrollBar().sizeHint().width())
        super().showPopup()


class LibrarySelector(QWidget):
    """The Deployment / Treatment / Run filters for the session library
    (chosen on Home), with an optional sensor list below them.

    Hosts connect to `library_changed` (reload anything keyed to the
    library, such as the index) and `filters_changed` (re-list sensors).
    On a library switch `library_changed` fires first.
    """

    library_changed = Signal()
    filters_changed = Signal()
    selection_changed = Signal()       # tbl_sensors selection changed
    row_activated = Signal(int, int)   # row, column - tbl_sensors double-click

    def __init__(self, session_state, parent=None, sensor_list=False,
                 list_columns=()):
        super().__init__(parent)
        self._lib_root = None
        # stem (upper) -> (deployment, treatment, run, raw file path)
        self._locations = {}
        self._tree = None            # raw_layout.RawTree of the last finished scan
        self._scan_gen = 0           # newer scans supersede older ones
        self._scan_threads = []
        self._scan_from_sync = False
        self._list_columns = list(list_columns)
        self._cache = None           # last populate_sensor_list() call, for re-filtering
        self._syncing = False
        self._pending_deployment = None   # select_deployment() before a scan
        self._build(sensor_list)
        self._connect()
        self._select_library(session_state.library)
        session_state.library_changed.connect(self.set_library)

    # the session library
    def set_library(self, path):
        """Follow the session library (`None` clears it)."""
        self._syncing = True
        try:
            self._select_library(path)
        finally:
            self._syncing = False

    @property
    def syncing(self):
        """True while following a session library change - hosts skip their
        own "Library: X" status message then, so one change isn't reported
        once per page."""
        return self._syncing

    # layout
    def _build(self, sensor_list):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.section = Section("Filters")
        fv = QVBoxLayout(self.section)
        fv.setSpacing(6)
        # a host page can add its own controls to the same box
        self.section_layout = fv

        # one line, not wrapped: a wrapping label has the page's scroll area
        # size the page at its preferred height, so it scrolls when it needn't
        self.lbl_current_library = muted_label("No library selected.")
        fv.addWidget(self.lbl_current_library)

        # shown while the raw folder is scanned in the background (a big
        # OneDrive library takes a while)
        loading_row = QHBoxLayout()
        self._spinner = Spinner(size=16)
        self._spinner.setVisible(False)
        loading_row.addWidget(self._spinner)
        self.lbl_loading = QLabel("")
        style(self.lbl_loading, role="muted")
        # takes no room until there's something to say
        self.lbl_loading.setVisible(False)
        loading_row.addWidget(self.lbl_loading, stretch=1)
        fv.addLayout(loading_row)

        # "All ..." until the library's first scan fills them in
        self.cmb_deployment = FilterCombo()
        self.cmb_deployment.addItem("All deployments", ALL_DEPLOYMENTS)
        fv.addLayout(self._row(muted_label("Deployment"), self.cmb_deployment))
        self.cmb_treatment = FilterCombo()
        self.cmb_treatment.addItem("All treatments", ALL_DEPLOYMENTS)
        fv.addLayout(self._row(muted_label("Treatment"), self.cmb_treatment))
        self.cmb_run = FilterCombo()
        self.cmb_run.addItem("All runs", ALL_DEPLOYMENTS)
        fv.addLayout(self._row(muted_label("Run"), self.cmb_run))
        v.addWidget(self.section)

        if sensor_list:
            self._build_sensor_list(v)

    def _build_sensor_list(self, v):
        top = QHBoxLayout()
        self.chk_show_flags = QCheckBox("Show bad sensors")
        self.chk_show_flags.setChecked(True)
        self.chk_show_flags.toggled.connect(self._on_show_flags_toggled)
        top.addWidget(self.chk_show_flags)
        top.addStretch()
        # the one Sort by every sensor list shares (sensor_sort.py)
        self.sort_control = sensor_sort.SortControl()
        self.sort_control.changed.connect(self._on_show_flags_toggled)
        top.addWidget(self.sort_control)
        v.addLayout(top)

        self.lbl_progress = QLabel("")
        style(self.lbl_progress, role="muted")
        # wraps, so a long counter line can't set the whole column's width
        self.lbl_progress.setWordWrap(True)
        v.addWidget(self.lbl_progress)

        self.tbl_sensors = QTableWidget(0, 1 + len(self._list_columns))
        self.tbl_sensors.setHorizontalHeaderLabels(["Sensor"] + self._list_columns)
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
    def _row(label, widget):
        r = QHBoxLayout()
        r.addWidget(label)
        r.addWidget(widget, stretch=1)
        return r

    def _connect(self):
        self.cmb_deployment.currentIndexChanged.connect(self._rebuild_treatment_combo)
        self.cmb_deployment.currentIndexChanged.connect(
            lambda _i: self.filters_changed.emit())
        self.cmb_treatment.currentIndexChanged.connect(self._rebuild_run_combo)
        self.cmb_treatment.currentIndexChanged.connect(
            lambda _i: self.filters_changed.emit())
        self.cmb_run.currentIndexChanged.connect(
            lambda _i: self.filters_changed.emit())

    # libraries
    @property
    def lib_root(self):
        return self._lib_root

    @property
    def locations(self):
        """stem (upper) -> (deployment, treatment, run, raw file path)."""
        return self._locations

    def wanted_deployment(self):
        return self.cmb_deployment.currentData()

    def select_deployment(self, name):
        """Filter to deployment `name` (a raw_sens_data folder) - now, or
        once the library's scan has filled the filter in."""
        idx = self.cmb_deployment.findData(name)
        if self._tree is not None and idx >= 0:
            self._pending_deployment = None
            self.cmb_deployment.setCurrentIndex(idx)
        else:
            self._pending_deployment = name

    def wanted_treatment(self):
        return self.cmb_treatment.currentData()

    def wanted_run(self):
        return self.cmb_run.currentData()

    def _select_library(self, path):
        self._lib_root = Path(path) if path and Path(path).is_dir() else None
        self.lbl_current_library.setText(
            f"Library: {self._lib_root.name}" if self._lib_root
            else "No library selected.")
        self.lbl_current_library.setToolTip(str(self._lib_root or ""))
        # the raw folder is only scanned once the page is on screen
        self._scan_from_sync = self._syncing
        self._scan_gen += 1
        self._tree = None
        when_visible(self, self._start_scan, key="scan")

    # deployments / treatments / runs (raw_layout.py)
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
        thread = RawScanThread(gen, raw_dir)
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
            self.lbl_loading.setVisible(True)
        else:
            self._spinner.stop()
            self.lbl_loading.setText("")
            self.lbl_loading.setVisible(False)
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
        current_dep = self._pending_deployment or self.cmb_deployment.currentData()
        self._pending_deployment = None
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
        for run in sorted(runs, key=raw_layout.run_sort_key):
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

    # video lookup, from the scan's video index (a directory listing per
    # sensor was slow on OneDrive)
    def video_matches_for(self, stem):
        if self._tree is None:
            return []
        return sorted(self._tree.videos.get(stem.upper(), []))

    # sensor listing
    def list_sensor_csvs(self, apply_filters=True):
        """Every processed sensor CSV in the current library, tagged with
        its (deployment, treatment) and filtered to the current
        deployment/treatment selection unless `apply_filters` is False.

        Which CSVs count as sensors is raw_layout.processed_csvs' rule.
        """
        if self._lib_root is None:
            return []
        rows = []
        for p in raw_layout.processed_csvs(self._lib_root):
            deployment, treatment, run, _raw = self._locations.get(
                p.stem.upper(), (UNGROUPED, UNGROUPED, raw_layout.DEFAULT_RUN, None))
            if apply_filters and not self._matches_filters(deployment, treatment, run):
                continue
            rows.append({"path": p, "stem": p.stem, "deployment": deployment,
                        "treatment": treatment, "run": run})
        return rows

    def scan_folder(self):
        """The raw folder the Deployment/Treatment filters narrow to (all of
        raw_sens_data for "All"), for callers that scan raw files. The Run
        filter is applied per file by `_matches_filters`: a treatment folder
        without run subfolders is Run 1."""
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

    # sensor list panel (opt-in via sensor_list=True)
    def _on_show_flags_toggled(self, _value):
        # re-render from the cached rows, no rescan
        if self._cache is not None:
            rows, kwargs = self._cache
            self.populate_sensor_list(rows, **kwargs)

    def populate_sensor_list(self, rows, is_bad=None, is_done=None,
                             done_label="In dataset", extra=None,
                             colour=None, order_key=None, progress=None):
        """Fill the sensor table with `rows` (dicts with "stem", usually "path").

        Default colours: white to do, green done, red bad, amber bad but done.
        Bad rows are left out while "Show bad sensors" is unticked.
        `is_bad(stem)` / `is_done(stem)` default to never; `extra(row)` gives the
        values for `list_columns`; `done_label` prefixes the counter ("In
        dataset", "Synced").

        A host with its own states can pass `colour(stem)` (None for plain),
        `order_key(row)` (the "Needs review first" order) and `progress(rows)`
        (the counter text). Rows follow the Sort by choice (sensor_sort).
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
        how = sensor_sort.current()
        if how != sensor_sort.REVIEW:
            visible = sensor_sort.sort_rows(visible, how)
        elif order_key is not None:
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
