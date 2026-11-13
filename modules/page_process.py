"""Raw data processing: the library filters, summary cards (found,
processed, validated, flagged bad) and the file inventory
(inventory_widgets.FileInventory, as in StrikeWorks's Process step). Each
recording is labelled from its own folder and read as its deployment's
saved sensor.
"""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
    QWidget,
)

from . import deployment_index as di
from . import sensor_config
from . import validation_core as vc
from .inventory_widgets import FileInventory
from .library_widgets import LibrarySelector
from .layout import Page, Section, when_visible
from .theme import style

class StatCard(QFrame):
    """Small themed summary tile."""

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 6, 10, 6)
        v.setSpacing(1)
        # title and detail at the standard text size; the value a few
        # points larger
        self._title = QLabel(title)
        style(self._title, role="muted")
        self._value = QLabel("-")
        f = QFont(self._title.font())
        f.setPointSize(max(f.pointSize(), 9) + 3)
        self._value.setFont(f)
        self._detail = QLabel("")
        style(self._detail, role="muted")
        self._detail.setWordWrap(True)
        v.addWidget(self._title)
        v.addWidget(self._value)
        v.addWidget(self._detail)

    def set(self, value, detail="", tone=None):
        self._value.setText(str(value))
        style(self._value, tone=tone)
        self._detail.setText(detail)

    def clear(self):
        self.set("-", "")


class ProcessPage(Page):
    """Raw data processing."""

    def __init__(self, main_window, session_state=None):
        super().__init__(main_window)
        self.session_state = session_state

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._build(outer)
        self._connect()
        self._on_lib_changed()
        self._on_filters_changed()

    # report_center.py's Raw data processing section reads these
    @property
    def _files(self):
        return self.inventory.files

    @property
    def _scan_dir(self):
        return self.inventory.scan_dir

    @property
    def _root(self):
        return self.lib_selector.lib_root

    # layout
    def _build(self, layout):
        page = QWidget()
        row = QHBoxLayout(page)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        left = QWidget()
        left.setFixedWidth(300)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        self.lib_selector = LibrarySelector(self.session_state)
        btn_rescan = QPushButton("Rescan folders")
        btn_rescan.setToolTip("Pick up files added to the library's raw "
                              "folders since it was opened.")
        btn_rescan.clicked.connect(self.lib_selector.rescan)
        self.lib_selector.section_layout.addWidget(btn_rescan)
        lv.addWidget(self.lib_selector)

        # the four cards two by two, so the column stays short enough for
        # a laptop screen
        grp_cards = Section("Summary")
        cv = QGridLayout(grp_cards)
        cv.setSpacing(6)
        self.card_recordings = StatCard("Recordings")
        self.card_processed = StatCard("Processed")
        self.card_validated = StatCard("Validated")
        self.card_bad = StatCard("Flagged bad")
        for i, c in enumerate((self.card_recordings, self.card_processed,
                               self.card_validated, self.card_bad)):
            cv.addWidget(c, i // 2, i % 2)
        lv.addWidget(grp_cards)
        lv.addStretch()
        row.addWidget(left)

        # the processing log goes to the app console - a button beside
        # Process selected
        self.inventory = FileInventory(orientation=Qt.Orientation.Vertical,
                                       open_console=self._open_console)
        row.addWidget(self.inventory, stretch=1)
        layout.addWidget(page)

    def _open_console(self):
        console = getattr(self.main_window, "dev_console", None)
        if console is not None:
            console.bring_up()

    def _connect(self):
        self.lib_selector.library_changed.connect(self._on_lib_changed)
        self.lib_selector.filters_changed.connect(self._on_filters_changed)
        self.inventory.files_changed.connect(self._refresh_cards)
        self.inventory.processing_done.connect(self._on_processing_done)
        sensor_config.notifier.changed.connect(
            lambda _k: when_visible(self.inventory, self._on_filters_changed,
                                    key="sensor"))
        di.notifier.plan_saved.connect(self._on_plan_saved)

    # filters
    def _on_lib_changed(self):
        root = self.lib_selector.lib_root
        if root is not None and not self.lib_selector.syncing:
            self.status.emit(f"Library: {root.name}", 4000)

    def _on_filters_changed(self):
        # uses the filter box's background scan; empty until it finishes
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
               else "Processing stopped." if code == 2
               else "Processing finished with errors.")
        self.status.emit(f"{msg} {len(stems)} sensor(s) processed.", 5000)

    # cards
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
            n, f"{n_complete}/{n} complete", "ok" if n_complete == n else "warn")
        processed = [f["stem"] for f in files if f["processed"]]
        n_proc = len(processed)
        self.card_processed.set(f"{n_proc}/{n}", f"{n - n_proc} unprocessed",
                                "ok" if n_proc == n else "info")

        index_df = di.read_index(self._root) if self._root else None
        status = vc.validation_status(index_df)
        c = vc.status_counts(processed, status)
        self.card_validated.set(
            f"{c['auto']}/{n_proc}" if n_proc else "-",
            f"{c['flagged']} flagged, {c['flagged_reviewed']} reviewed, "
            f"{c['user']} user-validated",
            "ok" if n_proc and c["auto"] == n_proc else "info")
        self.card_bad.set(c["bad"], "marked bad",
                          "bad" if c["bad"] else "ok")
