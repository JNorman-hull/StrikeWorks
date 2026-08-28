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
Each host page still builds its own sensor table (columns differ: Annotate
wants Sensor/Video, Export wants Sensor/Video/Synced, Process works from
raw stems rather than processed CSVs) by calling `list_sensor_csvs()` /
`raw_stems()` after connecting to `filters_changed`.
"""
from pathlib import Path

from PySide6.QtCore import QSortFilterProxyModel, Signal
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
    QWidget,
)

from . import settings
from .ml_widgets import MUTED, Section

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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lib_dir = settings.get_libraries_dir()
        self._lib_root = None
        self._deployment_map = {}   # stem (upper) -> (deployment, treatment)
        self._build()
        self._connect()
        self._populate_libraries()

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.section = Section("Library")
        fv = QVBoxLayout(self.section)
        fv.setSpacing(6)
        # exposed so a host page can append its own controls (e.g. Annotate's
        # "Show bad sensors" checkbox) into the same visual panel
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
