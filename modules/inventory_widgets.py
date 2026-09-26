# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""The raw file inventory - one widget shared by Simple mode's Process step
and Advanced mode's Raw data processing page.

Lists every raw recording under a folder (a whole deployment in Simple
mode; whatever the Deployment/Treatment/Run filters select in Advanced
mode) with its sensor/date/time parsed from the filename, whether all of
its files are present, whether it has been processed, and the
Deployment, Treatment and Run it sits under (raw_layout.locate). Because
every file carries its own labels, a batch spanning several treatments or
runs is processed in one go and each recording is stamped with the right
conditions afterwards (deployment_index.stamp_by_location), instead of the
whole batch getting whatever one treatment/run picker said.

Processing itself is processing.py's `ProcessThread`, running the reader
the sensor configuration names; its log streams into the console below
the table.
"""
from collections import Counter
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from . import deployment_index as di
from . import raw_layout, sensor_config
from .cards import Spinner
from .layout import Section
from .tables import fill_table_width, style_table
from .theme import ACCENT, ACCENT_BUTTON, BAD, CONSOLE_STYLE, MUTED, OK, WARN


COLUMNS = ["Filename", "Sensor", "Date", "Time", "Deployment", "Treatment",
           "Run", "Complete", "Processed"]
_COL_COMPLETE = COLUMNS.index("Complete")
_COL_PROCESSED = COLUMNS.index("Processed")


class _Notifier(QObject):
    """Emits a library root once a processing batch has finished and been
    labelled - pages listing processed sensors (Annotate, Export
    animations) rescan instead of waiting for a filter change."""
    processed = Signal(str)


notifier = _Notifier()


def scan_raw(lib_root, folder, config=None, tree=None):
    """Every recording under `folder` (a folder inside the library's
    raw_sens_data), keyed by upper-case stem so its files pair however the
    device cased them, each tagged with its deployment/treatment/run.

    `tree` (a raw_layout.RawTree someone already built - Raw data
    processing's filter box has one) skips walking the folder again."""
    cfg = config or sensor_config.active()
    exts = [e.lower() for e in (cfg.required_extensions or [".imp"])]
    primary = exts[0]
    raw_dir = raw_layout.raw_root(lib_root)
    if tree is None:
        if folder is None or not Path(folder).exists():
            return []
        tree = raw_layout.scan_tree(raw_dir, folder)

    processed_names = {p.stem.upper() for p in raw_layout.processed_csvs(lib_root)}

    records = []
    for stem_up in sorted(tree.files):
        paths = {}
        for p in tree.files[stem_up]:
            paths.setdefault(p.suffix.lower(), p)
        main_path = paths.get(primary)
        if main_path is None:
            continue
        paths = {ext: paths[ext] for ext in exts if ext in paths}
        sensor, date, time = cfg.parse_stem(main_path.stem)
        deployment, treatment, run, _p = tree.locations.get(
            stem_up, (raw_layout.UNGROUPED, raw_layout.UNGROUPED,
                      raw_layout.DEFAULT_RUN, None))
        records.append(dict(
            stem=main_path.stem, stem_up=stem_up, sensor=sensor, date=date,
            time=time, complete=len(paths) == len(exts),
            processed=stem_up in processed_names, paths=paths,
            deployment=deployment, treatment=treatment, run=run))
    return records


class _InventoryScanThread(QThread):
    done = Signal(int, object)   # generation, records

    def __init__(self, gen, lib_root, folder, config):
        super().__init__()
        self._args = (gen, lib_root, folder, config)

    def run(self):
        gen, lib_root, folder, config = self._args
        try:
            records = scan_raw(lib_root, folder, config)
        except Exception:
            records = []
        self.done.emit(gen, records)


class FileInventory(QWidget):
    """Inventory table + Process selected + console log.

    Host API: `set_source(lib_root, folder, row_filter=None)` then
    `refresh()`; `files` is the current list (each a dict - see
    `scan_raw`). `processing_done(code, stems)` fires once a batch has
    finished *and* been labelled (0 = every file succeeded).

    `log_inside=False` leaves the console out of this widget - it's built
    as `log_section` for the host to place itself (Raw data processing
    puts it full width under the filters and the table)."""

    processing_started = Signal()
    processing_done = Signal(int, list)
    files_changed = Signal()

    def __init__(self, parent=None, orientation=Qt.Orientation.Horizontal,
                 inventory_title="File inventory", log_title="Console output",
                 log_inside=True):
        super().__init__(parent)
        self._lib_root = None
        self._folder = None
        self._row_filter = None
        self._tree = None
        self._files = []
        self._thread = None
        self._batch = []
        self._batch_done = []
        self._scan_gen = 0
        self._scan_threads = []
        self._build(orientation, inventory_title, log_title, log_inside)

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, orientation, inventory_title, log_title, log_inside=True):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        split = QSplitter(orientation)
        split.setChildrenCollapsible(False)
        outer.addWidget(split)

        grp = Section(inventory_title)
        gv = QVBoxLayout(grp)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        style_table(self.table)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        gv.addWidget(self.table)
        sel_row = QHBoxLayout()
        self.chk_select_all = QCheckBox("Select / unselect all")
        self.chk_select_all.toggled.connect(self._on_select_all)
        sel_row.addWidget(self.chk_select_all)
        self._spinner = Spinner(size=16)
        self._spinner.setVisible(False)
        sel_row.addWidget(self._spinner)
        self.lbl_counts = QLabel("")
        self.lbl_counts.setStyleSheet(f"color:{MUTED};")
        sel_row.addWidget(self.lbl_counts)
        sel_row.addStretch()
        self.btn_process = QPushButton("Process selected")
        self.btn_process.setStyleSheet(ACCENT_BUTTON)
        self.btn_process.setEnabled(False)
        self.btn_process.clicked.connect(self.process_selected)
        sel_row.addWidget(self.btn_process)
        gv.addLayout(sel_row)
        split.addWidget(grp)

        grp_log = Section(log_title)
        lv = QVBoxLayout(grp_log)
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(5000)
        self.console.setFont(QFont("Consolas", 9))
        self.console.setStyleSheet(CONSOLE_STYLE)
        lv.addWidget(self.console, stretch=1)
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet(f"color:{OK};font-weight:bold;")
        self.lbl_status.setWordWrap(True)
        lv.addWidget(self.lbl_status)
        self.log_section = grp_log
        if not log_inside:
            return                 # the host places log_section
        split.addWidget(grp_log)

        if orientation == Qt.Orientation.Horizontal:
            split.setSizes([3, 2])
        else:
            split.setSizes([3, 2])
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)

    # ── source ───────────────────────────────────────────────────────────────
    @property
    def files(self):
        return self._files

    @property
    def lib_root(self):
        return self._lib_root

    @property
    def scan_dir(self):
        return self._folder

    @property
    def running(self):
        return self._thread is not None and self._thread.isRunning()

    def set_source(self, lib_root, folder, row_filter=None, tree=None):
        """`row_filter(deployment, treatment, run) -> bool` narrows the scan
        further (Advanced mode's Run filter); `tree` is an already-built
        raw_layout.RawTree to list from instead of walking `folder`."""
        self._lib_root = Path(lib_root) if lib_root else None
        self._folder = Path(folder) if folder else None
        self._row_filter = row_filter
        self._tree = tree

    def refresh(self, block=False):
        """Re-list. With a pre-built tree that's instant; otherwise the
        folder is walked in the background behind a spinner (a big
        OneDrive deployment can take a while) - `block=True` walks right
        here instead (demo runner). `files_changed` fires once it's done."""
        self._scan_gen += 1
        gen = self._scan_gen
        if self._lib_root is None or (self._folder is None and self._tree is None):
            self._apply_files(gen, [])
            return
        if self._tree is not None or block:
            self._apply_files(gen, scan_raw(self._lib_root, self._folder,
                                            tree=self._tree))
            return
        self._spinner.start()
        self.lbl_counts.setText("Scanning folders…")
        self.btn_process.setEnabled(False)
        thread = _InventoryScanThread(gen, self._lib_root, self._folder,
                                      sensor_config.active())
        thread.done.connect(self._apply_files)
        thread.finished.connect(lambda t=thread: self._scan_threads.remove(t)
                                if t in self._scan_threads else None)
        self._scan_threads.append(thread)
        thread.start()

    def _apply_files(self, gen, files):
        if gen != self._scan_gen:
            return   # superseded by a newer refresh
        self._spinner.stop()
        if self._row_filter is not None:
            files = [f for f in files if self._row_filter(
                f["deployment"], f["treatment"], f["run"])]
        self._files = files
        self._refresh_table()
        self.files_changed.emit()

    def _refresh_table(self):
        t = self.table
        t.setRowCount(len(self._files))
        for row, f in enumerate(self._files):
            vals = [f["stem"], f["sensor"], f["date"], f["time"],
                    f["deployment"], f["treatment"], f"Run {f['run']}",
                    "Yes" if f["complete"] else "No",
                    "Yes" if f["processed"] else "No"]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                if col == _COL_COMPLETE:
                    item.setForeground(QColor(OK if f["complete"] else BAD))
                elif col == _COL_PROCESSED:
                    item.setForeground(QColor(OK if f["processed"] else WARN))
                t.setItem(row, col, item)
        fill_table_width(t)
        n = len(self._files)
        n_proc = sum(1 for f in self._files if f["processed"])
        self.lbl_counts.setText(f"{n} recording(s), {n_proc} processed" if n else "")
        self._on_selection_changed()

    # ── selection ────────────────────────────────────────────────────────────
    def _on_select_all(self, checked):
        if checked:
            self.table.selectAll()
        else:
            self.table.clearSelection()

    def select_all(self):
        self.table.selectAll()

    def selected_files(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self._files[r] for r in rows if r < len(self._files)]

    def _on_selection_changed(self):
        self.btn_process.setEnabled(
            bool(self.table.selectedItems()) and self._lib_root is not None
            and not self.running)

    # ── console ──────────────────────────────────────────────────────────────
    def log(self, text):
        self.console.appendPlainText(text)
        sb = self.console.verticalScrollBar()
        sb.setValue(sb.maximum())

    def clear_log(self):
        self.console.clear()

    # ── processing ───────────────────────────────────────────────────────────
    def process_selected(self):
        self.process(self.selected_files())

    def process(self, files):
        """Process `files` (records from `files`); returns the thread, or
        None when there was nothing complete to process."""
        from .processing import ProcessThread
        if self.running or self._lib_root is None:
            return None
        complete = [f for f in files if f["complete"]]
        skipped = len(files) - len(complete)
        if not complete:
            self.lbl_status.setStyleSheet(f"color:{WARN};font-weight:bold;")
            self.lbl_status.setText("No complete recordings selected.")
            return None
        cfg = sensor_config.active()
        out_dir = self._lib_root / raw_layout.PROCESSED_DIR
        self.clear_log()
        self.log(f"Sensor: {cfg.name}  ({cfg.output_rate_hz:g} Hz, "
                 f"parser '{cfg.parser}')")
        if skipped:
            self.log(f"Note: {skipped} incomplete recording(s) skipped.")
        groups = Counter((f["deployment"], f["treatment"], f["run"])
                         for f in complete)
        self.log("Labels from folders:")
        for (dep, treat, run), n in sorted(groups.items()):
            self.log(f"   {dep} / {treat} / Run {run}: {n} recording(s)")
        self.log(f"Output → {out_dir}\n")

        self._batch = complete
        self._batch_done = []
        self.lbl_status.setStyleSheet(f"color:{ACCENT};font-weight:bold;")
        self.lbl_status.setText("Processing…")
        self.btn_process.setEnabled(False)
        self._thread = ProcessThread(complete, out_dir, self._lib_root, cfg)
        self._thread.log.connect(self.log)
        self._thread.processed.connect(self._batch_done.append)
        self._thread.done.connect(self._on_done)
        self.processing_started.emit()
        self._thread.start()
        return self._thread

    def _on_done(self, code):
        done = set(self._batch_done)
        located = [f for f in self._batch if f["stem"] in done]
        try:
            n = di.stamp_by_location(self._lib_root, located)
            if n:
                self.log(f"\nLabelled {n} sensor(s) with the deployment, "
                         "treatment and run of the folder each came from.")
        except Exception as e:
            self.log(f"\nCould not label the batch: {e}")
        self.lbl_status.setStyleSheet(
            f"color:{OK if code == 0 else WARN};font-weight:bold;")
        self.lbl_status.setText(
            "All sensors processed" if code == 0
            else "Processing finished with errors")
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log(f"[{stamp}] {len(done)}/{len(self._batch)} processed.")
        self.refresh()
        notifier.processed.emit(str(self._lib_root))
        self.processing_done.emit(code, sorted(done))
