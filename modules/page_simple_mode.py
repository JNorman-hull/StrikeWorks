# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Simple mode - a guided, one-window walkthrough of Deployment > Process >
Predict > Report (2026-09-01, spec: simple_spec/1.png-7.png).

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

Deliberately simplified from Advanced mode's Validate page: the signal
preview here is read-only (no draggable nadir line) - correcting a
specific sensor's nadir by hand is still what Validate itself is for;
this page's whole point is not needing to.
"""
import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyqtgraph as pg
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QScrollArea, QSizePolicy, QSpinBox, QSplitter, QStackedWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import deployment_index as di
from . import ml_figures, ml_report, sensor_config, settings
from .ml_widgets import (
    ACCENT, BAD, MUTED, OK, PALETTE, PINK, TEXT, WARN, MetaCard, RingCard,
    Section, apply_section_defaults,
)
from .page_dataset import OPT_SEGMENTED, _ExtractThread, _standardise
from .page_initiate_deployment import _README_TEXT, _TreatmentRow
from .page_process import _ProcessThread, _parse_name

pg.setConfigOptions(antialias=True, background="#21252b",
                    foreground="#c8cdd6")

_RAW_DIR = Path("raw_sens_data")
_CSV_DIR = Path("processed_sens_data") / "csv"
_INDEX_REL = di.INDEX_REL
_VIDEO_FOLDER_NAME = "VIDEO"
_NADIR_T_COL = "pres_min.time."
_NADIR_V_COL = "pres_min.kPa."
_VALIDATED_COL = "hstrike_processed"
_WIN_SEC = 0.2
_WIN_DIR = Path("processed_sens_data") / "nadir_window"
_NEW_DEPLOYMENT = "__new__"
_INPUT_DATA_DIR = Path(__file__).parent.parent / "input_data"

# Steps shown in the left list - Process covers two stack pages (file
# inventory, then validate/segment); Welcome and Finished are bookends
# reached only via Next/Back, not directly clickable.
_STEPS = ["Deployment", "Process", "Predict", "Report"]
_STEP_FOR_PAGE = {1: 0, 2: 1, 3: 1, 4: 2, 5: 3}
_FIRST_PAGE_FOR_STEP = {0: 1, 1: 2, 2: 4, 3: 5}


class SimpleModeDialog(QDialog):
    """Pop-up wizard for Simple mode. Built once (`main.py`), reopened via
    `exec()` each time - see `page_home.py._go_simple()`."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle("Simple mode")
        self.resize(1180, 660)

        self._lib_root = None
        self._deployments = []
        self._treatment_rows = []
        self._process_files = []
        self._process_treatment_by_stem = {}
        self._process_batch_done = []
        self._validate_files = []       # [{"stem","path"}]
        self._cur_validate_stem = None
        self._built_dataset_path = None
        self._process_thread = None
        self._extract_thread = None

        self._build()
        state = self.window.ml_prediction_page.state
        state.run_finished.connect(self._on_predict_finished)
        state.run_failed.connect(self._on_predict_failed)

    # ── top-level layout ────────────────────────────────────────────────────
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(10, 6, 10, 0)
        title = QLabel("Simple mode")
        title.setStyleSheet(f"color:{TEXT};font-weight:bold;")
        top_bar.addWidget(title)
        top_bar.addStretch()
        btn_gear = QPushButton("⚙")
        btn_gear.setToolTip("Adjustments")
        btn_gear.setFixedWidth(30)
        btn_gear.clicked.connect(self.window.openAdjustments)
        top_bar.addWidget(btn_gear)
        outer.addLayout(top_bar)

        body = QHBoxLayout()
        body.setContentsMargins(10, 10, 10, 0)
        body.setSpacing(10)

        self.step_list = QListWidget()
        self.step_list.setMaximumWidth(150)
        for step in _STEPS:
            self.step_list.addItem(step)
        self.step_list.itemClicked.connect(self._on_step_clicked)
        body.addWidget(self.step_list)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_welcome_page())
        self.stack.addWidget(self._build_deployment_page())
        self.stack.addWidget(self._build_process_inventory_page())
        self.stack.addWidget(self._build_process_validate_page())
        self.stack.addWidget(self._build_predict_page())
        self.stack.addWidget(self._build_report_page())
        self.stack.addWidget(self._build_finished_page())
        body.addWidget(self.stack, stretch=1)
        outer.addLayout(body, stretch=1)

        nav = QHBoxLayout()
        nav.setContentsMargins(10, 6, 10, 10)
        self.btn_back = QPushButton("< Back")
        self.btn_back.clicked.connect(self._go_back)
        self.btn_next = QPushButton("Next >")
        self.btn_next.clicked.connect(self._go_next)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.reject)
        nav.addWidget(self.btn_back)
        nav.addStretch()
        nav.addWidget(self.btn_next)
        nav.addWidget(btn_close)
        outer.addLayout(nav)

    def showEvent(self, event):
        super().showEvent(event)
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
            self._refresh_predict_step()
        elif idx == 4:
            self._refresh_report_step()
        if idx < self.stack.count() - 1:
            self.stack.setCurrentIndex(idx + 1)
            self._sync_step_highlight()

    def _go_back(self):
        idx = self.stack.currentIndex()
        if idx > 0:
            self.stack.setCurrentIndex(idx - 1)
            self._sync_step_highlight()

    def _on_step_clicked(self, item):
        step_idx = self.step_list.row(item)
        self.stack.setCurrentIndex(_FIRST_PAGE_FOR_STEP[step_idx])
        self._sync_step_highlight()

    def _sync_step_highlight(self):
        page = self.stack.currentIndex()
        step = _STEP_FOR_PAGE.get(page)
        self.step_list.blockSignals(True)
        self.step_list.setCurrentRow(step if step is not None else -1)
        self.step_list.blockSignals(False)
        self.btn_back.setEnabled(page > 0)
        self.btn_next.setText(
            "Finish" if page == self.stack.count() - 2 else "Next >")

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
        title = QLabel("Blade strike prediction")
        title.setStyleSheet(f"color:{TEXT};font-size:26px;font-weight:bold;")
        v.addWidget(title)
        subtitle = QLabel("Deploy. Process. Predict. Report")
        subtitle.setStyleSheet(f"color:{MUTED};font-size:14px;font-style:italic;")
        v.addWidget(subtitle)
        v.addStretch()
        return page

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

        self.btn_create_folder = QPushButton("Create & open data folder")
        self.btn_create_folder.setMinimumHeight(32)
        self.btn_create_folder.clicked.connect(self._create_and_open_folder)
        lv.addWidget(self.btn_create_folder)

        self.lbl_files_found = QLabel("")
        self.lbl_files_found.setStyleSheet(f"color:{OK};")
        lv.addWidget(self.lbl_files_found)
        lv.addStretch()
        row.addWidget(left, stretch=2)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        self.treatment_col = QVBoxLayout()
        rv.addLayout(self.treatment_col)
        self.btn_add_treatment = QPushButton("+ Add treatment")
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
        self._clear_treatments()
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
            values = (dict(self._treatment_rows[-1].values())
                      if self._treatment_rows else {})
            used = {r.name() for r in self._treatment_rows}
            n = len(self._treatment_rows) + 1
            while f"Treatment {n}" in used:
                n += 1
            values[di.TREATMENT_COL] = f"Treatment {n}"
        row = _TreatmentRow(values, on_change=self._refresh_treatment_summary,
                            on_remove=self._remove_treatment)
        self.treatment_col.addWidget(row)
        self._treatment_rows.append(row)
        self._refresh_treatment_summary()
        return row

    def _remove_treatment(self, row):
        if row not in self._treatment_rows:
            return
        self._treatment_rows.remove(row)
        row.setParent(None)
        row.deleteLater()
        self._refresh_treatment_summary()

    def _clear_treatments(self):
        for row in list(self._treatment_rows):
            row.setParent(None)
            row.deleteLater()
        self._treatment_rows = []

    def _refresh_treatment_summary(self, *_args):
        n_rows = sum(r.runs() for r in self._treatment_rows)
        self.lbl_treatment_summary.setText(
            f"{len(self._treatment_rows)} treatment(s), {n_rows} row(s)"
            if self._treatment_rows else "")

    def _refresh_files_found(self):
        ident = self.dep_edits[di.DEPLOYMENT_COL].text().strip()
        if self._lib_root is None or not ident:
            self.lbl_files_found.setText("")
            return
        dep_dir = self._lib_root / _RAW_DIR / ident
        n = len(list(dep_dir.rglob("*"))) if dep_dir.exists() else 0
        n_files = sum(1 for p in dep_dir.rglob("*") if p.is_file()
                     and p.name != "readme.txt") if dep_dir.exists() else 0
        self.lbl_files_found.setText(
            f"{n_files} sensor file(s) found in folder" if dep_dir.exists()
            else "")

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
        names = [r.name() for r in self._treatment_rows]
        if not names or any(not n for n in names):
            QMessageBox.warning(self.window, "Missing treatment",
                                "Add at least one named treatment.")
            return

        deployment = {c: e.text().strip() for c, e in self.dep_edits.items()}
        treatments = [r.values() for r in self._treatment_rows]
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
        for treatment_name, stems in by_treatment.items():
            row = next((r.values() for r in self._treatment_rows
                       if r.name() == treatment_name), None)
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

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)

        left = QWidget()
        lv = QVBoxLayout(left)
        self.validate_list = QListWidget()
        self.validate_list.itemClicked.connect(self._on_validate_file_clicked)
        lv.addWidget(self.validate_list, stretch=1)

        mark_row = QHBoxLayout()
        self.btn_mark = QPushButton("Mark")
        self.btn_mark.clicked.connect(self._mark_good_bad)
        mark_row.addWidget(self.btn_mark)
        self.chk_mark_bad = QCheckBox("Bad (unticked = Good)")
        mark_row.addWidget(self.chk_mark_bad)
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
        self.btn_jump_v = QPushButton("Jump to next unvalidated")
        self.btn_jump_v.clicked.connect(self._jump_next_unvalidated_validate)
        lv.addWidget(self.btn_jump_v)
        split.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
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
            angle=90, movable=False,
            pen=pg.mkPen(color=(255, 220, 0), width=2), label="Nadir",
            labelOpts={"position": 0.92, "color": (180, 150, 0)})
        pi.addItem(self._validate_nadir_line)
        self._validate_curve = None
        self._validate_curve2 = None
        rv.addWidget(self._pw_validate, stretch=1)
        split.addWidget(right)
        split.setSizes([1, 2])
        v.addWidget(split, stretch=1)

        bottom = QHBoxLayout()
        self.btn_auto_process_all = QPushButton("Auto process all")
        self.btn_auto_process_all.setStyleSheet(f"color:{OK};font-weight:bold;")
        self.btn_auto_process_all.clicked.connect(self._auto_process_all)
        bottom.addWidget(self.btn_auto_process_all)
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

    def _refresh_validate_list(self):
        index_df = self._validate_index()
        validated = set()
        if index_df is not None and _VALIDATED_COL in index_df.columns:
            validated = set(index_df[index_df[_VALIDATED_COL]
                            .astype(str).str.upper() == "Y"]["file"])
        self.validate_list.clear()
        for f in self._validate_files:
            item = QListWidgetItem(f["stem"])
            if f["stem"] in validated:
                item.setForeground(QColor(OK))
            self.validate_list.addItem(item)
        n_val = sum(1 for f in self._validate_files if f["stem"] in validated)
        self.lbl_validated_count.setText(
            f"Validated: {n_val} / {len(self._validate_files)}")
        self.lbl_all_validated.setText(
            "All sensors validated" if self._validate_files
            and n_val == len(self._validate_files) else "")

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
        half_n = int(round(_WIN_SEC / 2 * fs))
        start = max(0, nadir_idx - half_n)
        end = min(n - 1, nadir_idx + half_n)
        return start, end

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
        start, end = self._window_bounds(
            time, self._cur_validate_nadir_idx, len(self._cur_validate_df))
        self._validate_region.setRegion((time[start], time[end]))
        self._validate_nadir_line.setPos(time[self._cur_validate_nadir_idx])
        pi.enableAutoRange("x", True)
        pi.enableAutoRange("y", True)

    def _mark_good_bad(self):
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
        index_df.loc[mask, di.BAD_SENS_COL] = (
            "Y" if self.chk_mark_bad.isChecked() else "N")
        self._save_validate_index(index_df)
        self.lbl_all_validated.setText(
            f"{self._cur_validate_stem} marked "
            f"{'Bad' if self.chk_mark_bad.isChecked() else 'Good'}.")

    def _save_one_validated(self, index_df, stem, df, time, pres, nadir_idx):
        """Writes the ROI window CSV and updates `index_df` in place for
        one sensor - the same operation Validate's own Save+Next performs
        (page_validate.py._do_save_window/_do_update_index), reused here
        for both the single-file and Auto process all paths."""
        start, end = self._window_bounds(time, nadir_idx, len(df))
        ms = int(round(_WIN_SEC * 1000))
        out_dir = self._lib_root / _WIN_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        df.iloc[start:end + 1].to_csv(out_dir / f"{stem}_{ms}ms.csv", index=False)

        nadir_t = float(time[nadir_idx])
        nadir_v = float(pres[nadir_idx]) if pres is not None else float("nan")
        mask = index_df["file"] == stem
        if not mask.any():
            new_row = pd.DataFrame([{"file": stem}])
            index_df = pd.concat([index_df, new_row], ignore_index=True)
            mask = index_df["file"] == stem
        index_df.loc[mask, _NADIR_T_COL] = nadir_t
        index_df.loc[mask, _NADIR_V_COL] = nadir_v
        index_df.loc[mask, "nadir_window_start"] = time[start]
        index_df.loc[mask, "nadir_window_end"] = time[end]
        if _VALIDATED_COL not in index_df.columns:
            index_df[_VALIDATED_COL] = ""
        # a column read back as float (blank/NaN with no prior string
        # value) will not take "Y" in place without widening first -
        # pandas warns (soon errors) otherwise
        index_df[_VALIDATED_COL] = index_df[_VALIDATED_COL].astype(object)
        index_df.loc[mask, _VALIDATED_COL] = "Y"
        return index_df

    def _save_and_next_validate(self):
        if not self._cur_validate_stem:
            return
        index_df = self._validate_index()
        if index_df is None:
            return
        index_df = self._save_one_validated(
            index_df, self._cur_validate_stem, self._cur_validate_df,
            self._cur_validate_time, self._cur_validate_pres,
            self._cur_validate_nadir_idx)
        self._save_validate_index(index_df)
        self._refresh_validate_list()
        self._jump_next_unvalidated_validate()

    def _reset_current_validate(self):
        if self._cur_validate_stem:
            self._load_validate_file(self._cur_validate_stem)

    def _jump_next_unvalidated_validate(self):
        index_df = self._validate_index()
        validated = set()
        if index_df is not None and _VALIDATED_COL in index_df.columns:
            validated = set(index_df[index_df[_VALIDATED_COL]
                            .astype(str).str.upper() == "Y"]["file"])
        for f in self._validate_files:
            if f["stem"] not in validated:
                self._load_validate_file(f["stem"])
                return

    def _auto_process_all(self):
        if self._lib_root is None or not self._validate_files:
            return
        index_df = self._validate_index()
        if index_df is None:
            index_df = pd.DataFrame({"file": []})
        validated = set()
        if _VALIDATED_COL in index_df.columns:
            validated = set(index_df[index_df[_VALIDATED_COL]
                            .astype(str).str.upper() == "Y"]["file"])
        n_done = 0
        for f in self._validate_files:
            if f["stem"] in validated:
                continue
            try:
                df = pd.read_csv(f["path"], low_memory=False)
            except Exception:
                continue
            time = (df["time_s"].to_numpy(dtype=float) if "time_s" in df.columns
                    else np.arange(len(df), dtype=float))
            pres = (df["pressure_kpa"].to_numpy(dtype=float)
                    if "pressure_kpa" in df.columns else None)
            nadir_idx = self._detect_nadir_idx(f["stem"], df, time, pres)
            index_df = self._save_one_validated(
                index_df, f["stem"], df, time, pres, nadir_idx)
            n_done += 1
        self._save_validate_index(index_df)
        self._refresh_validate_list()
        self.lbl_all_validated.setText(f"Auto-processed {n_done} sensor(s).")

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
            return
        ident = self.dep_edits[di.DEPLOYMENT_COL].text().strip() or "dataset"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        _INPUT_DATA_DIR.mkdir(parents=True, exist_ok=True)
        out_path = _INPUT_DATA_DIR / f"{ident}_{stamp}.csv"
        try:
            df.to_csv(out_path, index=False)
        except Exception as e:
            self.lbl_all_validated.setText(f"Save failed: {e}")
            return
        self._built_dataset_path = out_path
        self.lbl_all_validated.setText(
            f"Saved and exported {n_rows} row(s) to {out_path.name}")
        # feed straight into the shared PredictionState (window.
        # ml_prediction_page.state) - Advanced mode's Dataset creation
        # wires its own dataset_ready the same way
        self.window.ml_prediction_page.on_dataset_ready(
            df, f"Simple mode - {ident}")

    # ── page 4: predict ──────────────────────────────────────────────────────
    def _build_predict_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(10)
        title = QLabel("Predict blade strike from sensor data…")
        title.setStyleSheet(f"color:{TEXT};font-weight:bold;")
        v.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(10)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)

        self.btn_load_dataset = QPushButton("Load dataset CSV…")
        self.btn_load_dataset.setMinimumHeight(32)
        self.btn_load_dataset.clicked.connect(self._load_dataset_csv)
        lv.addWidget(self.btn_load_dataset)

        grp_ds = Section("Dataset")
        dv = QVBoxLayout(grp_ds)
        self.card_predict_dataset = MetaCard("Curated sensor dataset")
        dv.addWidget(self.card_predict_dataset)
        lv.addWidget(grp_ds)

        grp_run = Section("Run")
        rv = QVBoxLayout(grp_run)
        self.btn_run_predict = QPushButton("Run prediction")
        self.btn_run_predict.setMinimumHeight(32)
        self.btn_run_predict.clicked.connect(self._run_predict)
        rv.addWidget(self.btn_run_predict)
        self.lbl_predict_status = QLabel("")
        self.lbl_predict_status.setStyleSheet(f"color:{MUTED};")
        self.lbl_predict_status.setWordWrap(True)
        rv.addWidget(self.lbl_predict_status)
        lv.addWidget(grp_run)
        lv.addStretch()
        row.addWidget(left, stretch=1)

        right = QWidget()
        rv2 = QVBoxLayout(right)
        rv2.setContentsMargins(0, 0, 0, 0)
        self.lbl_predict_done = QLabel("")
        self.lbl_predict_done.setStyleSheet(f"color:{OK};font-weight:bold;")
        rv2.addWidget(self.lbl_predict_done)
        self.card_predicted_strikes = RingCard("Predicted strikes")
        rv2.addWidget(self.card_predicted_strikes)
        rv2.addStretch()
        row.addWidget(right, stretch=1)

        v.addLayout(row, stretch=1)
        return page

    def _refresh_predict_step(self):
        state = self.window.ml_prediction_page.state
        self._auto_select_model(state)
        self._refresh_predict_dataset_card()
        self.btn_run_predict.setEnabled(state.dataset_df is not None)

    def _auto_select_model(self, state):
        if not state.bin_candidates:
            state.load_models_from_dir(state.models_dir)
        candidates = state.bin_candidates
        if not candidates:
            return
        default = settings.get_default_model()
        if default is not None and Path(default) in candidates:
            if state.bin_model_path != Path(default):
                state.select_bin_model(Path(default))
            return
        newest = max(candidates, key=lambda p: p.stat().st_mtime)
        if state.bin_model_path != newest:
            state.select_bin_model(newest)

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

    # ── page 6: finished ─────────────────────────────────────────────────────
    def _build_finished_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.addStretch()
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
            self.window, "Download StrikeWorks report to folder", "")
        if not dirpath:
            return
        try:
            out = ml_report.export_analysis(state, dirpath)
        except Exception as e:
            QMessageBox.critical(self.window, "Download failed", str(e))
            return
        QMessageBox.information(
            self.window, "Report downloaded", f"Saved to:\n{out}")
