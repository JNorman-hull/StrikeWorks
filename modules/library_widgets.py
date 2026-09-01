# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Shared Library / Deployment / Treatment selector.

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
Process works from raw stems (`raw_stems()`) rather than processed CSVs and
has no per-sensor bad/done status, so it uses the picker alone
(`sensor_list=False`, the default). Annotate and Export animations both
opt into the sensor-list panel (`sensor_list=True`) - one "Show bad
sensors" checkbox, one progress counter, one coloured table, with the same
show/hide-when-unticked filtering and white/green/red/amber colouring
everywhere it appears, driven by `populate_sensor_list()`.
"""
from pathlib import Path

from PySide6.QtCore import QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import settings
from .ml_widgets import BAD, MUTED, OK, WARN, Section, style_table

RAW_DIR = Path("raw_sens_data")
CSV_DIR = Path("processed_sens_data") / "csv"
VIDEO_FOLDER_NAME = "VIDEO"
UNGROUPED = "(ungrouped)"
ALL_DEPLOYMENTS = None   # combo data sentinel for "All deployments"/"All treatments"

# canonical rules for what counts as a "sensor" CSV versus a derived/scratch
# output - the single definition every page (Validate, this widget, and
# hence Annotate/Export/Process) agrees on
_EXCL_SUFFIXES = {"_min", "_delineated"}
_EXCL_NAMES = {"global_sensor_index.csv"}


class _DirsOnlyProxy(QSortFilterProxyModel):
    """Show directories only. Shared by every folder-tree browser in the
    app (Validate's file tree, Process's deployment/metadata trees)."""

    def filterAcceptsRow(self, row, parent):
        idx = self.sourceModel().index(row, 0, parent)
        return self.sourceModel().isDir(idx)


class LibrarySelector(QWidget):
    """Library / Deployment / Treatment picker, embeddable in any page.

    Wraps a `Section("Library")` panel with the three combos and the
    "Libraries…" folder-change button - visually and behaviourally
    identical everywhere it's used. Callers connect to `library_changed`
    (the library root itself switched - reload anything keyed to the whole
    library, e.g. the deployment index) and `filters_changed` (deployment/
    treatment changed, or the library just changed too - re-list sensors);
    `library_changed` always fires before `filters_changed` on a library
    switch, so a host's index/dataset reload runs before it repopulates
    its sensor table.
    """

    library_changed = Signal()
    filters_changed = Signal()
    selection_changed = Signal()       # tbl_sensors selection changed
    row_activated = Signal(int, int)   # row, column - tbl_sensors double-click

    def __init__(self, parent=None, sensor_list=False, list_columns=(),
                session_state=None):
        super().__init__(parent)
        self._lib_dir = settings.get_libraries_dir()
        self._lib_root = None
        self._deployment_map = {}   # stem (upper) -> (deployment, treatment)
        self._list_columns = list(list_columns)
        self._cache = None           # last populate_sensor_list() call, for re-filtering
        self._session_state = session_state
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
        self.section = Section("Library")
        fv = QVBoxLayout(self.section)
        fv.setSpacing(6)
        # exposed so a host page can append its own controls into the same
        # visual panel, above the sensor list if there is one
        self.section_layout = fv

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
        self.cmb_treatment.currentIndexChanged.connect(
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
        return self._deployment_map

    def wanted_deployment(self):
        return self.cmb_deployment.currentData()

    def wanted_treatment(self):
        return self.cmb_treatment.currentData()

    def _populate_libraries(self, select=None):
        # signals stay blocked through setCurrentIndex too - _on_library_
        # changed() is called explicitly, once, at the end regardless;
        # without this, an index that actually changes fires it a second
        # time via currentIndexChanged, doubling every status message and
        # re-scan this triggers (very visible once several pages soft-
        # sync to the same session library change at once)
        self.cmb_library.blockSignals(True)
        self.cmb_library.clear()
        try:
            libs = sorted(p for p in self._lib_dir.iterdir() if p.is_dir())
        except Exception:
            libs = []
        for lib in libs:
            self.cmb_library.addItem(lib.name, str(lib))
        self.btn_change_libs.setToolTip(str(self._lib_dir))
        if not libs:
            self._lib_root = None
            self.cmb_library.blockSignals(False)
            return
        idx = self.cmb_library.findData(str(select)) if select else 0
        self.cmb_library.setCurrentIndex(max(0, idx))
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
        self._scan_deployments()
        self.library_changed.emit()
        self.filters_changed.emit()

    # ── deployments (raw_sens_data subfolders, one level) ─────────────────────
    def _scan_deployments(self):
        """Map each raw sensor stem to (deployment, treatment).

        `raw_sens_data/<deployment>/<treatment>/` is the normal shape; a
        deployment with no treatment subfolders (files directly inside
        it), or a library with no deployment subfolders at all, still
        work - they just bucket under UNGROUPED at whichever level is
        missing, rather than being dropped.
        """
        self._deployment_map = {}
        current_dep = self.cmb_deployment.currentData()
        self.cmb_deployment.blockSignals(True)
        self.cmb_deployment.clear()
        self.cmb_deployment.addItem("All deployments", ALL_DEPLOYMENTS)

        raw_dir = self._lib_root / RAW_DIR if self._lib_root else None
        if raw_dir is None or not raw_dir.exists():
            self.cmb_deployment.blockSignals(False)
            self._rebuild_treatment_combo()
            return

        deployments = set()
        for entry in sorted(raw_dir.iterdir()):
            if entry.is_file():
                self._deployment_map.setdefault(
                    entry.stem.upper(), (UNGROUPED, UNGROUPED))
                deployments.add(UNGROUPED)
                continue
            if not entry.is_dir():
                continue
            deployments.add(entry.name)
            for child in sorted(entry.iterdir()):
                if child.is_dir():
                    if child.name.upper() == VIDEO_FOLDER_NAME:
                        continue   # VIDEO with no treatment level in between
                    for f in child.rglob("*"):
                        if f.is_file():
                            self._deployment_map.setdefault(
                                f.stem.upper(), (entry.name, child.name))
                elif child.is_file():
                    self._deployment_map.setdefault(
                        child.stem.upper(), (entry.name, UNGROUPED))

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
        self.cmb_treatment.addItem("All treatments", ALL_DEPLOYMENTS)
        treatments = sorted({
            treatment for (deployment, treatment) in self._deployment_map.values()
            if wanted_deployment is None or deployment == wanted_deployment})
        for name in treatments:
            self.cmb_treatment.addItem(name, name)
        idx = self.cmb_treatment.findData(current)
        self.cmb_treatment.setCurrentIndex(idx if idx >= 0 else 0)
        self.cmb_treatment.blockSignals(False)

    # ── video lookup ─────────────────────────────────────────────────────────
    def video_dir_for(self, stem):
        info = self._deployment_map.get(stem.upper())
        if not info or self._lib_root is None:
            return None
        deployment, treatment = info
        base = self._lib_root / RAW_DIR
        if deployment != UNGROUPED:
            base = base / deployment
        if treatment != UNGROUPED:
            base = base / treatment
        if not base.exists():
            return None
        for entry in base.iterdir():
            # case-insensitive: "video"/"Video"/"VIDEO" all match
            if entry.is_dir() and entry.name.upper() == VIDEO_FOLDER_NAME:
                return entry
        return None

    def video_matches_for(self, stem):
        video_dir = self.video_dir_for(stem)
        if video_dir is None:
            return []
        return sorted(video_dir.glob(f"{stem}_vid_*.mp4"))

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
        wanted_deployment = self.wanted_deployment() if apply_filters else None
        wanted_treatment = self.wanted_treatment() if apply_filters else None
        rows = []
        for p in sorted(csv_dir.rglob("*.csv")):
            if p.name in _EXCL_NAMES or any(
                    p.stem.endswith(s) for s in _EXCL_SUFFIXES):
                continue
            deployment, treatment = self._deployment_map.get(
                p.stem.upper(), (UNGROUPED, UNGROUPED))
            if wanted_deployment is not None and deployment != wanted_deployment:
                continue
            if wanted_treatment is not None and treatment != wanted_treatment:
                continue
            rows.append({"path": p, "stem": p.stem,
                        "deployment": deployment, "treatment": treatment})
        return rows

    def raw_stems(self, apply_filters=True):
        """Every raw sensor stem known from the deployment scan, tagged and
        filtered the same way as `list_sensor_csvs` - for callers (Process)
        that work from raw files rather than processed CSVs. Stems come
        back upper-cased (as scanned); callers matching against real
        on-disk filenames should compare case-insensitively."""
        wanted_deployment = self.wanted_deployment() if apply_filters else None
        wanted_treatment = self.wanted_treatment() if apply_filters else None
        rows = []
        for stem, (deployment, treatment) in sorted(self._deployment_map.items()):
            if wanted_deployment is not None and deployment != wanted_deployment:
                continue
            if wanted_treatment is not None and treatment != wanted_treatment:
                continue
            rows.append({"stem": stem, "deployment": deployment,
                        "treatment": treatment})
        return rows

    # ── sensor list panel (opt-in via sensor_list=True) ─────────────────────────
    def selected_path(self):
        """The `path` of the currently-selected sensor row, or None."""
        items = self.tbl_sensors.selectedItems()
        if not items:
            return None
        return self.tbl_sensors.item(items[0].row(), 0).data(
            Qt.ItemDataRole.UserRole)

    def _on_show_flags_toggled(self, _checked):
        # re-render from the cached call rather than making the host rescan
        # the filesystem just to react to this checkbox
        if self._cache is not None:
            rows, is_bad, is_done, done_label, extra = self._cache
            self.populate_sensor_list(rows, is_bad=is_bad, is_done=is_done,
                                      done_label=done_label, extra=extra)

    def populate_sensor_list(self, rows, is_bad=None, is_done=None,
                             done_label="In dataset", extra=None):
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
        """
        self._cache = (rows, is_bad, is_done, done_label, extra)
        is_bad = is_bad or (lambda _s: False)
        is_done = is_done or (lambda _s: False)
        extra = extra or (lambda _r: [])
        show_flags = self.chk_show_flags.isChecked()

        visible = [r for r in rows if show_flags or not is_bad(r["stem"])]

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
                    item.setForeground(QColor(WARN))
                else:
                    item.setForeground(QColor(OK))
            elif bad:
                item.setForeground(QColor(BAD))
            self.tbl_sensors.setItem(i, 0, item)
            for c, val in enumerate(extra(row), start=1):
                self.tbl_sensors.setItem(i, c, QTableWidgetItem(str(val)))
        self.tbl_sensors.resizeColumnsToContents()

        suffix = f" ({n_done_bad} bad)" if n_done_bad and show_flags else ""
        self.lbl_progress.setText(f"{done_label}: {n_done} / {len(rows)}{suffix}")
