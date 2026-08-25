# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Behaviour for the Process page.

Tab 1 (Raw data processing) is a port of the MVP's ``bsm/pages/data_prep.py``.
The "processed" definition is unchanged from the MVP; the file extensions,
how many files make a recording, the filename pattern and which parser runs
come from the sensor configuration selected on the Prepare page
(``sensor_config.active()``), which for RAPID reproduces the MVP exactly.

Tab 2 (Metadata) reads the library's ``global_sensor_index.csv`` and writes
deployment information back into it.

The widgets themselves live in ``main.ui`` (edit them in Qt Designer); this
module only binds behaviour to them.
"""
import os
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd

from PySide6.QtCore import Qt, QDir, QObject, QThread, QSortFilterProxyModel, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QFileSystemModel, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QListWidgetItem, QMessageBox, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from . import sensor_config, settings

# ── paths inside a library root (unchanged from the MVP) ─────────────────────
_INDEX_REL = Path("processed_sens_data") / "index" / "global_sensor_index.csv"
_RAW_REL = Path("raw_sens_data")
_CSV_DIR = Path("processed_sens_data") / "csv"

# theme colours (match the PyDracula palette used by the app)
_ACCENT = "#ff79c6"
_OK = "#22c55e"
_WARN = "#f59e0b"
_BAD = "#ef4444"
_INFO = "#568af2"
_MUTED = "#8a95aa"

# deployment fields: widget attribute -> column in global_sensor_index.csv
DEPLOYMENT_FIELDS = [
    ("ed_deployment_config_label", "deployment_config"),
    ("ed_site", "site"),
    ("ed_deployment_id", "deployment_id"),
    ("ed_pump_turbine", "pump_turbine"),
    ("ed_type", "type"),
    ("ed_rpm", "rpm"),
    ("ed_head", "head"),
    ("ed_flow", "flow"),
    ("ed_point_bep", "point_bep"),
    ("ed_treatment", "treatment"),
    ("ed_run", "run"),
]


def _parse_name(stem: str, config=None):
    """Split a sensor filename stem into (sensor, DD/MM, HH:MM:SS).

    The pattern belongs to the sensor configuration, so a device that names
    its files differently needs only its pattern edited on Prepare.
    """
    return (config or sensor_config.active()).parse_stem(stem)


# ── processing thread (ported from the MVP; reader chosen by config) ─────────
class _ProcessThread(QThread):
    log = Signal(str)
    done = Signal(int)          # 0 = all ok, 1 = some failed
    processed = Signal(str)     # stem of each successfully processed file

    def __init__(self, files, out_dir, root, config):
        super().__init__()
        self._files = files
        self._out_dir = out_dir
        self._root = root
        self._config = config

    def run(self):
        # the reader is whichever one the sensor configuration names
        parse = sensor_config.get_parser(self._config.parser)

        # parsers read config/index_config.txt relative to cwd
        prev_cwd = os.getcwd()
        os.chdir(str(self._root))

        n_ok = n_fail = 0
        try:
            for f in self._files:
                self.log.emit(f"\n-- Processing: {f['stem']}")
                try:
                    _, summary = parse(f["paths"], self._out_dir, self._config)
                    msg = summary.get("messages", "")
                    bad = summary.get("bad_sens", "N")
                    self.log.emit(f"   Done.  bad_sens={bad}  {msg}")
                    self.processed.emit(f["stem"])
                    n_ok += 1
                except NotImplementedError as e:
                    self.log.emit(f"   FAILED: {e}")
                    n_fail += 1
                except FileNotFoundError as e:
                    if "index_config" in str(e):
                        self.log.emit(
                            "   FAILED: this library has no config/index_config.txt "
                            "- processing cannot update the global index.")
                    else:
                        self.log.emit(f"   FAILED: {e}")
                    n_fail += 1
                except Exception as e:
                    self.log.emit(f"   FAILED: {e}")
                    n_fail += 1
        finally:
            os.chdir(prev_cwd)

        self.log.emit(f"\n-- Complete: {n_ok} succeeded, {n_fail} failed.")
        self.done.emit(0 if n_fail == 0 else 1)


class _DirsOnlyProxy(QSortFilterProxyModel):
    """Show directories only."""

    def filterAcceptsRow(self, row, parent):
        idx = self.sourceModel().index(row, 0, parent)
        return self.sourceModel().isDir(idx)


class StatCard(QFrame):
    """Small themed summary tile used in 'Selection information'."""

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setStyleSheet(
            "#statCard{background-color:rgb(33,37,43);border-radius:5px;}"
        )
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 8, 12, 8)
        v.setSpacing(2)

        self._title = QLabel(title)
        self._title.setStyleSheet(f"color:{_MUTED};font-size:10px;")

        self._value = QLabel("—")
        f = QFont("Segoe UI", 18)
        f.setBold(True)
        self._value.setFont(f)
        self._value.setStyleSheet("color:rgb(221,221,221);")

        self._detail = QLabel("")
        self._detail.setStyleSheet(f"color:{_MUTED};font-size:10px;")
        self._detail.setWordWrap(True)

        v.addWidget(self._title)
        v.addWidget(self._value)
        v.addWidget(self._detail)

    def set(self, value, detail="", colour=None):
        self._value.setText(str(value))
        self._value.setStyleSheet(f"color:{colour or 'rgb(221,221,221)'};")
        self._detail.setText(detail)

    def clear(self):
        self.set("—", "")


# ═════════════════════════════════════════════════════════════════════════════
class ProcessPage(QObject):
    """Binds behaviour to the Process page widgets defined in main.ui."""

    status = Signal(str, int)

    def __init__(self, ui, window):
        super().__init__(window)
        self.ui = ui
        self.window = window

        self._root = None        # selected library root
        self._raw_dir = None
        self._index_df = None
        self._files = []
        self._scan_dir = None
        self._thread = None
        self._session_processed = []

        # a different sensor means different extensions and filename rules,
        # so the inventory is re-scanned when the Prepare page changes it
        sensor_config.notifier.changed.connect(self._on_sensor_changed)

        self._fs_model = QFileSystemModel()
        self._fs_model.setFilter(QDir.Filter.Dirs | QDir.Filter.NoDotAndDotDot)
        self._proxy = _DirsOnlyProxy()
        self._proxy.setSourceModel(self._fs_model)

        self._idx_model = QFileSystemModel()
        self._idx_model.setFilter(QDir.Filter.Dirs | QDir.Filter.NoDotAndDotDot)
        self._idx_proxy = _DirsOnlyProxy()
        self._idx_proxy.setSourceModel(self._idx_model)

        self._build_cards()
        self._configure_widgets()
        self._connect()
        self._init_tree()

    # ── setup ────────────────────────────────────────────────────────────────
    def _build_cards(self):
        holder = QVBoxLayout(self.ui.frame_cards)
        holder.setContentsMargins(0, 0, 0, 0)
        holder.setSpacing(6)
        self.card_deployments = StatCard("Deployments")
        self.card_files = StatCard("Sensor files")
        self.card_paired = StatCard("Complete recordings")
        self.card_processed = StatCard("Processed")
        for c in (self.card_deployments, self.card_files,
                  self.card_paired, self.card_processed):
            holder.addWidget(c)
        holder.addStretch()

    def _configure_widgets(self):
        u = self.ui

        u.tree_library.setModel(self._proxy)
        u.tree_library.setHeaderHidden(True)
        u.tree_index.setModel(self._idx_proxy)
        u.tree_index.setHeaderHidden(True)
        for tree in (u.tree_library, u.tree_index):
            for col in range(1, 4):
                tree.hideColumn(col)

        for tbl in (u.table_inventory, u.table_meta):
            tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            tbl.verticalHeader().setVisible(False)
            tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        # Always start on "Raw data processing".
        # Qt Designer writes tabs_process/currentIndex to whichever tab happened
        # to be showing on its canvas when the file was saved, so the .ui value
        # cannot be relied on. Set it here instead.
        u.tabs_process.setCurrentIndex(0)

        u.btn_process_selected.setEnabled(False)
        u.console_output.setFont(QFont("Consolas", 9))
        u.console_output.setStyleSheet(
            "QPlainTextEdit{background:#1b1e23;color:#d4d4d4;"
            "border:1px solid #2c313a;border-radius:4px;}")

        # theming for widgets the base stylesheet doesn't cover
        u.tabs_process.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid #2c313a;
                border-radius: 5px;
                background-color: rgb(40, 44, 52);
                top: -1px;
            }}
            QTabBar::tab {{
                background-color: rgb(33, 37, 43);
                color: {_MUTED};
                padding: 7px 18px;
                margin-right: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }}
            QTabBar::tab:selected {{
                background-color: rgb(40, 44, 52);
                color: rgb(221, 221, 221);
                border-bottom: 2px solid {_ACCENT};
            }}
            QTabBar::tab:hover:!selected {{ color: rgb(221, 221, 221); }}
        """)

        group_style = f"""
            QGroupBox {{
                color: {_MUTED};
                font: 700 9pt "Segoe UI";
                border: 1px solid #2c313a;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 6px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 10px;
                padding: 0 4px;
            }}
        """
        for box in self.window.findChildren(type(u.grp_library)):
            box.setStyleSheet(group_style)

        # metadata tab needs its own feedback line - the Tab 1 console is not
        # visible from here
        self._meta_status = QLabel("Select sensors, fill the fields, then apply.")
        self._meta_status.setWordWrap(True)
        self._meta_status.setStyleSheet(f"color:{_MUTED};font-size:11px;")
        u.grp_deployment.layout().addWidget(self._meta_status)

    def _connect(self):
        u = self.ui
        u.tree_library.selectionModel().selectionChanged.connect(self._on_library_select)
        u.tree_index.selectionModel().selectionChanged.connect(self._on_index_select)
        u.btn_change_libraries.clicked.connect(self._change_libraries)
        u.table_inventory.itemSelectionChanged.connect(self._on_table_select)
        u.chk_select_all.toggled.connect(self._on_select_all)
        u.btn_process_selected.clicked.connect(self._process)
        u.btn_save_deployment.clicked.connect(self._save_deployment)
        u.btn_apply_deployment.clicked.connect(self._load_deployment)
        u.chk_meta_select_all.toggled.connect(self._on_meta_select_all)

    def _init_tree(self):
        self._lib_dir = settings.get_libraries_dir()
        self.ui.btn_change_libraries.setToolTip(str(self._lib_dir))
        fs_root = self._fs_model.setRootPath(str(self._lib_dir))
        self.ui.tree_library.setRootIndex(self._proxy.mapFromSource(fs_root))
        self._log(f"Libraries: {self._lib_dir}")

    # ── library / index trees ────────────────────────────────────────────────
    def _change_libraries(self):
        chosen = QFileDialog.getExistingDirectory(
            self.window, "Select libraries folder", str(self._lib_dir))
        if not chosen:
            return
        settings.set_libraries_dir(chosen)
        self._root = None
        self._files = []
        self._index_df = None
        self._init_tree()
        self._refresh_cards()
        self._refresh_table()
        self.status.emit(f"Libraries folder: {chosen}", 5000)

    def _on_library_select(self, selected, _deselected):
        idxs = selected.indexes()
        if not idxs:
            return
        folder = Path(self._fs_model.filePath(self._proxy.mapToSource(idxs[0])))

        # the library root is always the direct child of the libraries dir
        try:
            rel = folder.relative_to(self._lib_dir)
            lib_root = self._lib_dir / rel.parts[0]
        except (ValueError, IndexError):
            lib_root = folder

        if lib_root != self._root:
            self._set_root(lib_root)

        self._scan_and_refresh(folder)

    def _set_root(self, root: Path):
        self._root = root
        self._raw_dir = root / _RAW_REL
        self._load_index()

        # re-root the deployment (Index) tree at raw_sens_data
        if self._raw_dir.exists():
            idx_root = self._idx_model.setRootPath(str(self._raw_dir))
            self.ui.tree_index.setRootIndex(self._idx_proxy.mapFromSource(idx_root))

        self._refresh_meta_tab()
        self.status.emit(f"Library: {root.name}", 4000)
        self._log(f"\nLibrary: {root}")
        if not (root / "config" / "index_config.txt").exists():
            self._log("   WARNING: no config/index_config.txt in this library - "
                      "processing will fail to update the global index.")

    def _on_index_select(self, selected, _deselected):
        idxs = selected.indexes()
        if not idxs:
            return
        folder = Path(self._idx_model.filePath(self._idx_proxy.mapToSource(idxs[0])))
        self._scan_and_refresh(folder)

    def _load_index(self):
        idx_path = self._root / _INDEX_REL if self._root else None
        if idx_path and idx_path.exists():
            try:
                self._index_df = pd.read_csv(idx_path, low_memory=False)
            except Exception as e:
                self._index_df = None
                self._log(f"   Could not read global index: {e}")
        else:
            self._index_df = None

    # ── scanning (unchanged rules) ───────────────────────────────────────────
    def _on_sensor_changed(self, _key):
        if self._scan_dir is not None:
            self._scan_and_refresh(self._scan_dir)

    def _scan_and_refresh(self, folder: Path):
        self._scan_dir = folder
        self._files = self._scan(folder)
        self._refresh_cards()
        self._refresh_table()

    def _scan(self, folder: Path):
        cfg = sensor_config.active()
        exts = cfg.required_extensions or [".imp"]
        primary, secondary = exts[0], exts[1:]

        # one map per extension, keyed by upper-case stem so a recording's
        # files pair however the device cased them
        found = {ext: self._files_by_stem(folder, ext) for ext in exts}

        index_names = set()
        if self._index_df is not None and "file" in self._index_df.columns:
            index_names = set(self._index_df["file"].astype(str).str.upper())
        csv_dir = (self._root / _CSV_DIR) if self._root else None
        csv_names = set()
        if csv_dir and csv_dir.exists():
            csv_names = {p.stem.upper() for p in csv_dir.glob("*.csv")
                         if not p.stem.endswith("_min")}
        processed_names = index_names & csv_names

        records = []
        for stem_up, main_path in sorted(found[primary].items()):
            sensor, date, time = _parse_name(main_path.stem, cfg)
            paths = {primary: main_path}
            for ext in secondary:
                match = found[ext].get(stem_up)
                if match is not None:
                    paths[ext] = match
            records.append(dict(
                stem=main_path.stem,
                stem_up=stem_up,
                sensor=sensor,
                date=date,
                time=time,
                complete=len(paths) == len(exts),
                processed=stem_up in processed_names,
                paths=paths,
            ))
        return records

    @staticmethod
    def _files_by_stem(folder: Path, ext: str):
        """Every file with `ext` under `folder`, keyed by upper-case stem."""
        suffix = ext.lstrip(".")
        out = {p.stem.upper(): p for p in folder.rglob(f"*.{suffix.upper()}")}
        for p in folder.rglob(f"*.{suffix.lower()}"):
            out.setdefault(p.stem.upper(), p)
        return out

    # ── cards ────────────────────────────────────────────────────────────────
    def _refresh_cards(self):
        files = self._files
        n = len(files)
        if not n:
            for c in (self.card_deployments, self.card_files,
                      self.card_paired, self.card_processed):
                c.clear()
            return

        cfg = sensor_config.active()
        sensors = Counter(f["sensor"] for f in files)
        top = ", ".join(f"{s} ({c})" for s, c in sensors.most_common(3))
        self.card_deployments.set(len(sensors), top, _INFO)

        primary = cfg.primary_extension.lstrip(".").upper()
        self.card_files.set(n, f"{n} {primary} file(s) found", _ACCENT)

        n_complete = sum(1 for f in files if f["complete"])
        n_needed = len(cfg.required_extensions)
        self.card_paired.set(
            f"{n_complete}/{n}",
            (f"{n - n_complete} incomplete" if n_needed > 1
             else f"{n_needed} file per recording"),
            _OK if n_complete == n else _WARN)

        n_proc = sum(1 for f in files if f["processed"])
        self.card_processed.set(
            f"{n_proc}/{n}", f"{n - n_proc} unprocessed",
            _OK if n_proc == n else _INFO)

    # ── inventory table ──────────────────────────────────────────────────────
    def _refresh_table(self):
        t = self.ui.table_inventory
        t.setRowCount(len(self._files))
        for row, f in enumerate(self._files):
            vals = [str(row + 1), f["stem"], f["sensor"], f["date"], f["time"],
                    "Yes" if f["complete"] else "No",
                    "Processed" if f["processed"] else "Unprocessed"]
            for col, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 5:
                    it.setForeground(QColor(_OK if f["complete"] else _BAD))
                if col == 6:
                    it.setForeground(QColor(_OK if f["processed"] else _WARN))
                t.setItem(row, col, it)
        self.ui.btn_process_selected.setEnabled(False)

    def _on_table_select(self):
        self.ui.btn_process_selected.setEnabled(
            bool(self.ui.table_inventory.selectedItems()) and self._root is not None)

    def _on_select_all(self, checked):
        if checked:
            self.ui.table_inventory.selectAll()
        else:
            self.ui.table_inventory.clearSelection()

    # ── processing ───────────────────────────────────────────────────────────
    def _process(self):
        rows = sorted({i.row() for i in self.ui.table_inventory.selectedIndexes()})
        files = [self._files[r] for r in rows if r < len(self._files)]
        if not files:
            return

        cfg = sensor_config.active()
        complete = [f for f in files if f["complete"]]
        skipped = len(files) - len(complete)
        if not complete:
            self.status.emit("No complete recordings selected.", 4000)
            self._log("No complete recordings selected.")
            return

        out_dir = self._root / "processed_sens_data"
        self.ui.console_output.clear()
        if skipped:
            self._log(f"Note: {skipped} incomplete recording(s) skipped.")
        self._log(f"Sensor: {cfg.name}  ({cfg.output_rate_hz:g} Hz, "
                  f"parser '{cfg.parser}')")
        self._log(f"Output -> {out_dir}\n")
        self.ui.btn_process_selected.setEnabled(False)

        self._thread = _ProcessThread(complete, out_dir, self._root, cfg)
        self._thread.log.connect(self._log)
        self._thread.processed.connect(self._on_file_processed)
        self._thread.done.connect(self._on_process_done)
        self._thread.start()

    def _on_file_processed(self, stem):
        self._session_processed.append(stem)
        stamp = datetime.now().strftime("%H:%M:%S")
        self.ui.list_processed.addItem(QListWidgetItem(f"{stamp}  {stem}"))

    def _on_process_done(self, code):
        self.ui.btn_process_selected.setEnabled(True)
        msg = "Processing complete." if code == 0 else "Processing finished with errors."
        self._log(f"\n{msg}")
        self.status.emit(msg, 5000)

        self._load_index()
        self._refresh_meta_tab()

        idxs = self.ui.tree_index.selectionModel().selectedIndexes()
        if idxs:
            folder = Path(self._idx_model.filePath(self._idx_proxy.mapToSource(idxs[0])))
        else:
            folder = self._raw_dir or self._root
        if folder:
            self._scan_and_refresh(folder)

    def _log(self, text):
        self.ui.console_output.appendPlainText(text)
        sb = self.ui.console_output.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ═════════════════════════════════════════════════════════════════════════
    # TAB 2 - METADATA
    # ═════════════════════════════════════════════════════════════════════════
    def _refresh_meta_tab(self):
        self._refresh_meta_table()
        self._refresh_dashboard()

    def _refresh_meta_table(self):
        t = self.ui.table_meta
        df = self._index_df
        if df is None or df.empty:
            t.setRowCount(0)
            return

        cols = {c: c for c in df.columns}
        t.setRowCount(len(df))
        for row in range(len(df)):
            r = df.iloc[row]
            complete = str(r.get("deployment_info", "N")).strip().upper() == "Y"
            vals = [str(row + 1),
                    str(r.get("file", "")),
                    str(r.get("sensor", "")),
                    str(r.get("date_deploy", "")),
                    "Complete" if complete else "Required"]
            for col, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                it.setForeground(QColor(_OK if complete else _WARN))
                t.setItem(row, col, it)

    def _refresh_dashboard(self):
        u = self.ui
        df = self._index_df

        def put(prefix, value, caption, detail):
            getattr(u, f"lbl_dash_{prefix}_value").setText(str(value))
            getattr(u, f"lbl_dash_{prefix}_caption").setText(caption)
            getattr(u, f"lbl_dash_{prefix}_detail").setText(detail)

        if df is None or df.empty:
            for p, cap in (("library", "Sensors in global index"),
                           ("coverage", "Complete deployment info"),
                           ("quality", "Flagged bad_sens"),
                           ("sites", "Distinct sites"),
                           ("delineated", "Delineated signals"),
                           ("treatments", "Distinct treatments")):
                put(p, "—", cap, "No library selected")
            return

        n = len(df)
        put("library", n, "Sensors in global index",
            f"Library: {self._root.name if self._root else '-'}")

        if "deployment_info" in df.columns:
            done = int((df["deployment_info"].astype(str).str.upper() == "Y").sum())
            pct = (done / n * 100) if n else 0
            put("coverage", f"{done}/{n}", "Complete deployment info",
                f"{pct:.0f}% complete, {n - done} outstanding")
        else:
            put("coverage", "—", "Complete deployment info", "column not present")

        if "bad_sens" in df.columns:
            bad = int((df["bad_sens"].astype(str).str.upper() == "Y").sum())
            put("quality", bad, "Flagged bad_sens",
                f"{n - bad} sensor(s) clean")
        else:
            put("quality", "—", "Flagged bad_sens", "column not present")

        if "site" in df.columns:
            sites = [s for s in df["site"].astype(str).unique()
                     if s and s.upper() not in ("NA", "NAN", "")]
            put("sites", len(sites), "Distinct sites",
                ", ".join(sites[:3]) if sites else "none recorded")
        else:
            put("sites", "—", "Distinct sites", "column not present")

        if "delineated" in df.columns:
            deline = int((df["delineated"].astype(str).str.upper() == "Y").sum())
            trimmed = (int((df["trimmed"].astype(str).str.upper() == "Y").sum())
                       if "trimmed" in df.columns else 0)
            put("delineated", f"{deline}/{n}", "Delineated signals",
                f"{trimmed} trimmed, {n - deline} awaiting delineation")
        else:
            put("delineated", "—", "Delineated signals", "column not present")

        if "treatment" in df.columns:
            treatments = [t for t in df["treatment"].astype(str).unique()
                          if t and t.upper() not in ("NA", "NAN", "")]
            runs = (len([r for r in df["run"].astype(str).unique()
                         if r and r.upper() not in ("NA", "NAN", "")])
                    if "run" in df.columns else 0)
            put("treatments", len(treatments), "Distinct treatments",
                f"{runs} distinct run(s): "
                + (", ".join(treatments[:3]) if treatments else "none recorded"))
        else:
            put("treatments", "—", "Distinct treatments", "column not present")

    def _on_meta_select_all(self, checked):
        if checked:
            self.ui.table_meta.selectAll()
        else:
            self.ui.table_meta.clearSelection()

    def _selected_meta_files(self):
        rows = sorted({i.row() for i in self.ui.table_meta.selectedIndexes()})
        out = []
        for r in rows:
            it = self.ui.table_meta.item(r, 1)
            if it:
                out.append(it.text())
        return out

    def _set_meta_status(self, text, colour=_MUTED):
        self._meta_status.setText(text)
        self._meta_status.setStyleSheet(f"color:{colour};font-size:11px;")

    def _load_deployment(self):
        """Populate the form from the first selected sensor's index row.

        This OVERWRITES whatever is currently typed in the form, so it warns
        first if any field has content.
        """
        files = self._selected_meta_files()
        if not files or self._index_df is None:
            self._set_meta_status("Select a sensor in the index first.", _WARN)
            return

        typed = [w for w, _ in DEPLOYMENT_FIELDS if getattr(self.ui, w).text().strip()]
        if typed:
            answer = QMessageBox.question(
                self.window, "Replace typed values?",
                f"Loading will overwrite {len(typed)} field(s) you have typed.\n\n"
                "Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return

        match = self._index_df[self._index_df["file"].astype(str) == files[0]]
        if match.empty:
            self._set_meta_status(f"{files[0]} is not in the index.", _WARN)
            return
        row = match.iloc[0]
        for widget_name, column in DEPLOYMENT_FIELDS:
            val = row.get(column, "")
            val = "" if pd.isna(val) or str(val).upper() == "NA" else str(val)
            getattr(self.ui, widget_name).setText(val)
        self._set_meta_status(f"Loaded values from {files[0]}.", _INFO)
        self.status.emit(f"Loaded deployment info from {files[0]}", 4000)

    def _save_deployment(self):
        """Write the form values into global_sensor_index.csv for selected rows."""
        if self._root is None or self._index_df is None:
            self._set_meta_status("No library selected.", _WARN)
            return

        files = self._selected_meta_files()
        if not files:
            self._set_meta_status(
                "Nothing applied - no sensors selected in the index.", _WARN)
            QMessageBox.information(
                self.window, "No sensors selected",
                "Select one or more sensors in the processed sensor index first.")
            return

        values = {col: getattr(self.ui, w).text().strip()
                  for w, col in DEPLOYMENT_FIELDS}
        filled = {c: v for c, v in values.items() if v}
        if not filled:
            self._set_meta_status(
                "Nothing applied - all deployment fields are empty.", _WARN)
            QMessageBox.information(
                self.window, "Nothing to save",
                "Enter at least one deployment field before applying.")
            return

        answer = QMessageBox.question(
            self.window, "Save deployment information",
            f"Write {len(filled)} field(s) to {len(files)} sensor(s) in\n"
            f"{self._root / _INDEX_REL}?\n\nA timestamped backup is taken first.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            self._set_meta_status("Cancelled - nothing was written.", _WARN)
            return

        idx_path = self._root / _INDEX_REL
        try:
            backup = idx_path.with_name(
                f"global_sensor_index.backup-{datetime.now():%Y%m%d-%H%M%S}.csv")
            shutil.copy2(idx_path, backup)

            df = pd.read_csv(idx_path, low_memory=False)
            mask = df["file"].astype(str).isin(files)
            for col, val in filled.items():
                if col not in df.columns:
                    df[col] = pd.NA
                # Index columns such as rpm/head/flow/run are read as numeric.
                # Keep them numeric when the entered value is a number, and widen
                # the column to object when it isn't, rather than letting pandas
                # coerce silently.
                if pd.api.types.is_numeric_dtype(df[col]):
                    try:
                        val = pd.to_numeric(val)
                    except (ValueError, TypeError):
                        df[col] = df[col].astype(object)
                df.loc[mask, col] = val
            if "deployment_info" not in df.columns:
                df["deployment_info"] = "N"
            df.loc[mask, "deployment_info"] = "Y"
            df.to_csv(idx_path, index=False)
        except Exception as e:
            QMessageBox.critical(self.window, "Save failed", str(e))
            self._set_meta_status(f"Save FAILED: {e}", _BAD)
            self._log(f"Deployment save FAILED: {e}")
            return

        self._load_index()
        self._refresh_meta_tab()
        summary = ", ".join(f"{c}={v}" for c, v in filled.items())
        self._set_meta_status(
            f"Applied {len(filled)} field(s) to {len(files)} sensor(s). "
            f"Backup: {backup.name}", _OK)
        self._log(f"Deployment info written for {len(files)} sensor(s). "
                  f"Backup: {backup.name}")
        QMessageBox.information(
            self.window, "Deployment information applied",
            f"Wrote to {len(files)} sensor(s) in {idx_path.name}.\n\n"
            f"{summary}\n\nBackup saved as {backup.name}")
        self.status.emit(f"Saved deployment info for {len(files)} sensor(s).", 5000)
