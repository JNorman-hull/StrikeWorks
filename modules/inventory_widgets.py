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

Each recording's Frequency is listed too. For a sensor whose files state
their own rate (the EEL tag) it is read in the background once the list is
up: from the index for a processed recording, otherwise from the recording's
own file. A selection mixing frequencies asks what to process
(frequency_dialog.py).

A deployment's recordings are read as the sensor saved on that deployment
(deployment_editor.py), whichever sensor is selected; the selected one only
answers for a deployment with none saved. A batch can span deployments, so
each record carries its own `config`.

Processing itself is processing.py's `ProcessThread`, running the reader
each recording's sensor configuration names; its log streams into the
console below the table.
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
from . import frequency_dialog, raw_layout, sensor_config
from .cards import Spinner
from .layout import Section
from .tables import fill_table_width
from .theme import BAD, OK, WARN, style


COLUMNS = ["Filename", "Sensor", "Frequency", "Date", "Time", "Deployment",
           "Treatment", "Run", "Complete", "Processed"]
_COL_FREQUENCY = COLUMNS.index("Frequency")
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

    `config` reads everything as that one sensor; without it, each recording
    is read as its deployment's saved sensor, or the selected sensor for a
    deployment with none saved.

    `tree` (a raw_layout.RawTree someone already built - Raw data
    processing's filter box has one) skips walking the folder again."""
    raw_dir = raw_layout.raw_root(lib_root)
    if tree is None:
        if folder is None or not Path(folder).exists():
            return []
        tree = raw_layout.scan_tree(raw_dir, folder)

    processed_names = {p.stem.upper() for p in raw_layout.processed_csvs(lib_root)}
    saved = {} if config else di.deployment_sensors(lib_root)
    fallback = config or sensor_config.active()

    records = []
    for stem_up in sorted(tree.files):
        deployment, treatment, run, _p = tree.locations.get(
            stem_up, (raw_layout.UNGROUPED, raw_layout.UNGROUPED,
                      raw_layout.DEFAULT_RUN, None))
        cfg = sensor_config.get(saved.get(deployment)) or fallback
        exts = [e.lower() for e in (cfg.required_extensions or [".imp"])]
        primary = exts[0]
        paths = {}
        for p in tree.files[stem_up]:
            paths.setdefault(p.suffix.lower(), p)
        main_path = paths.get(primary)
        if main_path is None:
            continue
        paths = {ext: paths[ext] for ext in exts if ext in paths}
        sensor, date, time = cfg.parse_stem(main_path.stem)
        records.append(dict(
            config=cfg,
            stem=main_path.stem, stem_up=stem_up, sensor=sensor, date=date,
            time=time, complete=len(paths) == len(exts),
            # filled in afterwards for a sensor whose files state it
            frequency=None if cfg.rate_in_file else cfg.output_rate_hz,
            processed=stem_up in processed_names, paths=paths,
            deployment=deployment, treatment=treatment, run=run))
    return records


def _by_sensor(files):
    """`files` grouped as {sensor key: records}."""
    groups = {}
    for f in files:
        groups.setdefault(f["config"].key, []).append(f)
    return groups


class _InventoryScanThread(QThread):
    done = Signal(int, object)   # generation, records

    def __init__(self, gen, lib_root, folder):
        super().__init__()
        self._args = (gen, lib_root, folder)

    def run(self):
        gen, lib_root, folder = self._args
        try:
            records = scan_raw(lib_root, folder)
        except Exception as e:
            print(f"Could not scan {folder}: {e}")
            records = []
        self.done.emit(gen, records)


def _frequency_text(f):
    """What the Frequency column shows: the rate, "…" while it's being read."""
    if f["frequency"]:
        return frequency_dialog.rate_text(f["frequency"])
    return "…" if f["complete"] else ""


class _FrequencyThread(QThread):
    """Each listed recording's rate, one at a time as it's found. Off the GUI
    thread: on OneDrive, opening a file that's only in the cloud downloads
    it. The index answers for what's already processed, so only unprocessed
    recordings - which are about to be needed anyway - get opened."""
    found = Signal(int, str, float)   # generation, stem (upper), rate

    def __init__(self, gen, lib_root, files):
        super().__init__()
        self._args = (gen, lib_root, files)

    def run(self):
        gen, lib_root, files = self._args
        try:
            known = {stem.upper(): rate for stem, rate
                     in di.index_rates(di.read_index(lib_root)).items()}
        except Exception as e:
            print(f"Could not read frequencies from the index: {e}")
            known = {}
        for f in files:
            if self.isInterruptionRequested():
                return
            rate = known.get(f["stem_up"]) if f["processed"] else None
            try:
                self.found.emit(gen, f["stem_up"],
                                float(rate or f["config"].recording_rate(f["paths"])))
            except Exception as e:
                print(f"Could not read the frequency of {f['stem']}: {e}")


class FileInventory(QWidget):
    """Inventory table + Process selected + console log.

    Host API: `set_source(lib_root, folder, row_filter=None)` then
    `refresh()`; `files` is the current list (each a dict - see
    `scan_raw`). `processing_done(code, stems)` fires once a batch has
    finished *and* been labelled (0 = every file succeeded).

    Every log line is also printed, so it reaches the app console. Given
    `open_console` (a no-arg callable), there is no log box: a Console
    button beside Process selected opens the app console instead (Raw
    data processing)."""

    processing_started = Signal()
    processing_done = Signal(int, list)
    files_changed = Signal()

    def __init__(self, parent=None, orientation=Qt.Orientation.Horizontal,
                 inventory_title="File inventory", log_title="Console output",
                 open_console=None):
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
        self._frequency_threads = []
        self._row_of = {}
        self._build(orientation, inventory_title, log_title, open_console)

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, orientation, inventory_title, log_title, open_console):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        split = QSplitter(orientation)
        split.setChildrenCollapsible(False)
        outer.addWidget(split)

        grp = Section(inventory_title)
        gv = QVBoxLayout(grp)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
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
        style(self.lbl_counts, role="muted")
        sel_row.addWidget(self.lbl_counts)
        sel_row.addStretch()
        self.btn_process = QPushButton("Process selected")
        style(self.btn_process, role="primary")
        self.btn_process.setEnabled(False)
        self.btn_process.clicked.connect(self.process_selected)
        sel_row.addWidget(self.btn_process)
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setToolTip("Stop after the recording being processed "
                                 "now; those already done are kept.")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop)
        sel_row.addWidget(self.btn_stop)
        gv.addLayout(sel_row)
        split.addWidget(grp)

        self.lbl_status = QLabel("")
        style(self.lbl_status, tone="ok")
        self.lbl_status.setWordWrap(True)
        if open_console is not None:
            # no log box - the app console, a button away
            btn_console = QPushButton("Console")
            btn_console.setToolTip("Everything the app prints - the "
                                   "processing log included.")
            btn_console.clicked.connect(open_console)
            sel_row.addWidget(btn_console)
            gv.addWidget(self.lbl_status)
            self.console = None
            return

        grp_log = Section(log_title)
        lv = QVBoxLayout(grp_log)
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(5000)
        self.console.setFont(QFont("Consolas", 9))
        style(self.console, role="console")
        lv.addWidget(self.console, stretch=1)
        lv.addWidget(self.lbl_status)
        split.addWidget(grp_log)

        # the inventory about three quarters, the log the rest - and kept
        # in that ratio as the window resizes
        split.setSizes([880, 260])
        split.setStretchFactor(0, 10)
        split.setStretchFactor(1, 3)

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
        thread = _InventoryScanThread(gen, self._lib_root, self._folder)
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
        self._read_frequencies(gen)
        self.files_changed.emit()

    def _read_frequencies(self, gen):
        """Fill in the Frequency column, in the background."""
        for thread in self._frequency_threads:
            thread.requestInterruption()
        wanted = [f for f in self._files
                  if f["complete"] and f["frequency"] is None]
        if not wanted:
            return
        thread = _FrequencyThread(gen, self._lib_root, wanted)
        thread.found.connect(self._on_frequency)
        thread.finished.connect(lambda: fill_table_width(self.table))
        thread.finished.connect(
            lambda t=thread: self._frequency_threads.remove(t)
            if t in self._frequency_threads else None)
        self._frequency_threads.append(thread)
        thread.start()

    def _on_frequency(self, gen, stem_up, rate):
        row = self._row_of.get(stem_up)
        if gen != self._scan_gen or row is None:
            return
        self._files[row]["frequency"] = rate
        self.table.item(row, _COL_FREQUENCY).setText(_frequency_text(self._files[row]))

    def _refresh_table(self):
        t = self.table
        t.setRowCount(len(self._files))
        self._row_of = {f["stem_up"]: row for row, f in enumerate(self._files)}
        for row, f in enumerate(self._files):
            vals = [f["stem"], f["sensor"], _frequency_text(f), f["date"], f["time"],
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
        try:
            print(text)            # the app console tees print
        except UnicodeError:       # a console that can't show "→"
            print(text.encode("ascii", "replace").decode("ascii"))
        if self.console is None:
            return
        self.console.appendPlainText(text)
        sb = self.console.verticalScrollBar()
        sb.setValue(sb.maximum())

    def clear_log(self):
        if self.console is not None:
            self.console.clear()

    # ── processing ───────────────────────────────────────────────────────────
    def process_selected(self):
        files = self._choose_frequency(self.selected_files())
        if files is not None:
            self.process(files)

    def _choose_frequency(self, files):
        """`files`, narrowed to what the user chose if their frequencies are
        mixed; None if they cancelled."""
        complete = [f for f in files if f["complete"]]
        for f in complete:
            if not f["frequency"]:      # selected before the column filled in
                f["frequency"] = float(f["config"].recording_rate(f["paths"]))
        keep = frequency_dialog.choose_for_processing(
            self, {f["stem"]: f["frequency"] for f in complete})
        if keep is None:
            return None
        return [f for f in files if f["stem"] in keep or not f["complete"]]

    def process(self, files):
        """Process `files` (records from `files`); returns the thread, or
        None when there was nothing complete to process."""
        from .processing import ProcessThread
        if self.running or self._lib_root is None:
            return None
        complete = [f for f in files if f["complete"]]
        skipped = len(files) - len(complete)
        if not complete:
            style(self.lbl_status, role="strong", tone="warn")
            self.lbl_status.setText("No complete recordings selected.")
            return None
        out_dir = self._lib_root / raw_layout.PROCESSED_DIR
        self.clear_log()
        for group in _by_sensor(complete).values():
            cfg = group[0]["config"]
            rates = sorted({f["frequency"] for f in group if f.get("frequency")})
            self.log(f"Sensor: {cfg.name}  ("
                     + ", ".join(frequency_dialog.rate_text(r) for r in rates)
                     + (", " if rates else "") + f"parser '{cfg.parser}')")
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
        style(self.lbl_status, role="strong", tone="accent")
        self.lbl_status.setText("Processing…")
        self.btn_process.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._thread = ProcessThread(complete, out_dir, self._lib_root)
        self._thread.log.connect(self.log)
        self._thread.processed.connect(self._batch_done.append)
        self._thread.done.connect(self._on_done)
        self.processing_started.emit()
        self._thread.start()
        return self._thread

    def stop(self):
        """Stop the batch before its next recording."""
        if not self.running:
            return
        self._thread.request_stop()
        self.btn_stop.setEnabled(False)
        style(self.lbl_status, role="strong", tone="warn")
        self.lbl_status.setText("Stopping after this recording…")

    def _on_done(self, code):
        from .processing import DONE_OK, DONE_STOPPED
        self.btn_stop.setEnabled(False)
        done = set(self._batch_done)
        located = [f for f in self._batch if f["stem"] in done]
        try:
            n = sum(di.stamp_by_location(self._lib_root, group, sensor_key=key)
                    for key, group in _by_sensor(located).items())
            if n:
                self.log(f"\nLabelled {n} sensor(s) with the deployment, "
                         "treatment and run of the folder each came from.")
        except Exception as e:
            self.log(f"\nCould not label the batch: {e}")
        style(self.lbl_status, role="strong",
              tone="ok" if code == DONE_OK else "warn")
        self.lbl_status.setText(
            "All sensors processed" if code == DONE_OK
            else f"Stopped - {len(done)} of {len(self._batch)} processed"
            if code == DONE_STOPPED
            else "Processing finished with errors")
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log(f"[{stamp}] {len(done)}/{len(self._batch)} processed.")
        self.refresh()
        notifier.processed.emit(str(self._lib_root))
        self.processing_done.emit(code, sorted(done))
