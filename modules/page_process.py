# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Raw data processing (Sensor processing).

Rebuilt around the pieces Simple mode's Process step uses:

  Filters        - the shared LibrarySelector (library_widgets.py) with
                   the session library, narrowed by Deployment / Treatment
                   / Run - the same filter box Annotate and Export
                   animations show.
  Summary cards  - recordings found, processed, validated, flagged bad,
                   for whatever the filters select.
  File inventory - inventory_widgets.FileInventory: every recording with
                   the deployment, treatment and run of the folder it sits
                   in, Process selected, and the console log. Each
                   processed recording is labelled from its own folder, so
                   one batch can span several treatments and runs.

The old per-batch treatment/run pickers and the Metadata tab are gone: a
recording's labels come from its folder, and a deployment's details are
edited in one place - Create and edit deployment, whose Update relabels
already-processed sensors.

Processing itself is processing.py; the file extensions, filename pattern
and parser come from the active sensor configuration.
"""
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from . import deployment_index as di
from . import sensor_config
from . import validation_core as vc
from .inventory_widgets import FileInventory
from .library_widgets import LibrarySelector
from .ml_widgets import BAD, INFO, MUTED, OK, PINK, WARN, Section, when_visible

# theme colours kept under their old names (StatCard is imported elsewhere)
_ACCENT = PINK
_OK = OK
_WARN = WARN
_BAD = BAD
_INFO = INFO
_MUTED = MUTED


class StatCard(QFrame):
    """Small themed summary tile."""

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setStyleSheet(
            "#statCard{background-color:rgb(33,37,43);border-radius:5px;}")
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 8, 12, 8)
        v.setSpacing(2)
        # title and detail at the app's standard text size (they used to be
        # scaled down to 10px); the value is the standard font, bolder and
        # a few points larger
        self._title = QLabel(title)
        self._title.setStyleSheet(f"color:{_MUTED};")
        self._value = QLabel("-")
        f = QFont(self._title.font())
        f.setPointSize(max(f.pointSize(), 9) + 5)
        f.setBold(True)
        self._value.setFont(f)
        self._value.setStyleSheet("color:rgb(221,221,221);")
        self._detail = QLabel("")
        self._detail.setStyleSheet(f"color:{_MUTED};")
        self._detail.setWordWrap(True)
        v.addWidget(self._title)
        v.addWidget(self._value)
        v.addWidget(self._detail)

    def set(self, value, detail="", colour=None):
        self._value.setText(str(value))
        self._value.setStyleSheet(f"color:{colour or 'rgb(221,221,221)'};")
        self._detail.setText(detail)

    def clear(self):
        self.set("-", "")


# ═════════════════════════════════════════════════════════════════════════════
class ProcessPage(QObject):
    """Builds Raw data processing into `ui.content_process` (the Designer
    tab widget that used to live there is hidden - see module docstring)."""

    status = Signal(str, int)

    def __init__(self, ui, window, session_state=None):
        super().__init__(window)
        self.ui = ui
        self.window = window
        self.session_state = session_state

        ui.tabs_process.hide()
        self._build(ui.layout_content_process)
        self._connect()
        self._on_lib_changed()
        self._on_filters_changed()

    # ── report_center.py's Raw data processing section reads these ──────────
    @property
    def _files(self):
        return self.inventory.files

    @property
    def _scan_dir(self):
        return self.inventory.scan_dir

    @property
    def _root(self):
        return self.lib_selector.lib_root

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, layout):
        page = QWidget()
        row = QHBoxLayout(page)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        left = QWidget()
        left.setFixedWidth(300)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        self.lib_selector = LibrarySelector(session_state=self.session_state,
                                            show_picker=False)
        btn_rescan = QPushButton("Rescan folders")
        btn_rescan.setToolTip("Pick up files added to the library's raw "
                              "folders since it was opened.")
        btn_rescan.clicked.connect(self.lib_selector.rescan)
        self.lib_selector.section_layout.addWidget(btn_rescan)
        lv.addWidget(self.lib_selector)

        grp_cards = Section("Summary")
        cv = QVBoxLayout(grp_cards)
        cv.setSpacing(6)
        self.card_recordings = StatCard("Recordings")
        self.card_processed = StatCard("Processed")
        self.card_validated = StatCard("Validated")
        self.card_bad = StatCard("Flagged bad")
        for c in (self.card_recordings, self.card_processed,
                  self.card_validated, self.card_bad):
            cv.addWidget(c)
        lv.addWidget(grp_cards)
        lv.addStretch()
        row.addWidget(left)

        self.inventory = FileInventory(orientation=Qt.Orientation.Vertical,
                                       log_inside=False)
        row.addWidget(self.inventory, stretch=1)

        # filters/summary and the file inventory on top, the console full
        # width underneath (draggable)
        split = QSplitter(Qt.Orientation.Vertical)
        split.setChildrenCollapsible(False)
        split.addWidget(page)
        split.addWidget(self.inventory.log_section)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 1)
        split.setSizes([2000, 1000])
        layout.addWidget(split)

    def _connect(self):
        self.lib_selector.library_changed.connect(self._on_lib_changed)
        self.lib_selector.filters_changed.connect(self._on_filters_changed)
        self.inventory.files_changed.connect(self._refresh_cards)
        self.inventory.processing_done.connect(self._on_processing_done)
        sensor_config.notifier.changed.connect(
            lambda _k: when_visible(self.inventory, self._on_filters_changed,
                                    key="sensor"))
        di.notifier.plan_saved.connect(self._on_plan_saved)

    # ── filters ──────────────────────────────────────────────────────────────
    def _on_lib_changed(self):
        root = self.lib_selector.lib_root
        if root is not None and not self.lib_selector.syncing:
            self.status.emit(f"Library: {root.name}", 4000)

    def _on_filters_changed(self):
        # lists from the filter box's own scan of the library (one walk,
        # done in the background when the library opens) - until that has
        # finished there's nothing to list yet, rather than a second walk
        tree = self.lib_selector.raw_tree
        self.inventory.set_source(self.lib_selector.lib_root,
                                  self.lib_selector.scan_folder(),
                                  row_filter=self.lib_selector.matches_filters,
                                  tree=tree)
        if tree is None:
            self.inventory.set_source(None, None)
        self.inventory.refresh()

    def _on_plan_saved(self, root):
        # a deployment created/renamed on Create and edit deployment changes
        # the folder tree this page filters over
        if self._root is not None and Path(root) == Path(self._root):
            when_visible(self.lib_selector, self.lib_selector.rescan, key="scan")

    def _on_processing_done(self, code, stems):
        msg = ("Processing complete." if code == 0
               else "Processing finished with errors.")
        self.status.emit(f"{msg} {len(stems)} sensor(s) processed.", 5000)

    # ── cards ────────────────────────────────────────────────────────────────
    def _refresh_cards(self):
        files = self.inventory.files
        n = len(files)
        if not n:
            for c in (self.card_recordings, self.card_processed,
                      self.card_validated, self.card_bad):
                c.clear()
            return
        n_complete = sum(1 for f in files if f["complete"])
        self.card_recordings.set(
            n, f"{n_complete}/{n} complete", _OK if n_complete == n else _WARN)
        processed = [f["stem"] for f in files if f["processed"]]
        n_proc = len(processed)
        self.card_processed.set(f"{n_proc}/{n}", f"{n - n_proc} unprocessed",
                                _OK if n_proc == n else _INFO)

        index_df = di.read_index(self._root) if self._root else None
        status = vc.validation_status(index_df)
        c = vc.status_counts(processed, status)
        self.card_validated.set(
            f"{c['auto']}/{n_proc}" if n_proc else "-",
            f"{c['flagged']} flagged, {c['flagged_reviewed']} reviewed, "
            f"{c['user']} user-validated",
            _OK if n_proc and c["auto"] == n_proc else _INFO)
        self.card_bad.set(c["bad"], "bad_sens = Y",
                          _BAD if c["bad"] else _OK)
