# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Behaviour for the Dataset creation page.

Port of the MVP's ``bsm/pages/feature_prep.py`` (Model Feature Preparation),
reduced to the two creation methods that are still wanted:

  Create from unsegmented (auto)
      MVP "Quick" option. Uses ``pres_min.time.`` from the global index,
      slices half the analysis window either side of the nadir out of the
      full sensor CSV and standardises to the window's row count.

  Create from segmented
      MVP "Bind nadir windows" option. Binds the saved window files the
      Validate page wrote into ``processed_sens_data/nadir_window``, keeping
      only sensors present in the index with ``bad_sens == N``.

The window stays 200 ms; the number of rows that becomes follows the rate
the selected sensor writes at (Prepare page) - 400 rows for RAPID at
2000 Hz, 1200 for a 6000 Hz device.

The MVP's third method (segmented ROI from ``*_delineated.csv``) is dropped.

Extraction maths, the row standardisation, the meta columns carried over
from the index, the annotation join and the three-panel summary figure are
unchanged from the MVP.
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from PySide6.QtCore import Qt, QObject, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QGroupBox,
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QTreeWidgetItem, QVBoxLayout,
)

from . import deployment_index as di
from . import sensor_config, settings
from .ml_widgets import MUTED

# paths relative to a library root
_CSV_DIR = Path("processed_sens_data") / "csv"
_INDEX_REL = di.INDEX_REL
_NADIR_WIN_DIR = Path("processed_sens_data") / "nadir_window"

# The window is 200 ms, as it has always been; how many rows that is
# depends on the rate the selected sensor writes its CSVs at (Prepare
# page) - 400 for RAPID at 2000 Hz, 1200 for a 6000 Hz device.
_WIN_SEC = 0.2
_TARGET_ROWS = 400        # fallback: 200 ms @ 2000 Hz
_NADIR_COL = "pres_min.time."
_NADIR_WIN_SUFFIX = "_200ms"
_WIN_SUFFIX_RE = re.compile(r"_\d+ms$")
_BAD_SENS_COL = "bad_sens"

# columns carried through from the index into the output
_META_COLS = ["deployment_id", "treatment", "run"]

# ── annotation join (model_labels.csv) ──────────────────────────────────────
_LABEL_FILE_COL = "sens_file"          # joins to feature 'file'
_LABEL_COLS = ["overall_passage_type", "leading_edge_type",
               "other_type", "concentric_pump_region"]
_STRIKE_TYPES = {"leading_edge", "other"}
_REGION_ORDER = [1, 2, 3, 4, 5]

_BLUES = ["#1e3a5f", "#2e5d9f", "#4a86c8", "#6fa8dc", "#9fc5e8"]
_DARK = "#1e3a5f"

# creation methods
OPT_UNSEGMENTED = 2   # keeps the MVP's option numbering
OPT_SEGMENTED = 3


def _standardise(df, target):
    """Trim or pad df to exactly `target` rows; tolerate a one-row shortfall."""
    n = len(df)
    if n >= target:
        return df.iloc[:target].copy()
    if n == target - 1:
        return pd.concat([df, df.iloc[[-1]]]).reset_index(drop=True)
    return None


def _init_item(item, tristate=False):
    flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
    if tristate:
        flags |= Qt.ItemFlag.ItemIsAutoTristate
    item.setFlags(flags)
    item.setCheckState(0, Qt.CheckState.Checked)


# ── extraction thread (ported) ──────────────────────────────────────────────
class _ExtractThread(QThread):
    log = Signal(str)
    done = Signal(int, int, int)   # n_ok, n_skip, n_rows

    def __init__(self, root, option, selected_files, index_df, config=None):
        super().__init__()
        self._root = root
        self._option = option
        self._selected_files = selected_files
        self._index_df = index_df
        self._config = config or sensor_config.active()
        self._result_df = None

    @property
    def _target_rows(self):
        return self._config.window_samples(_WIN_SEC) or _TARGET_ROWS

    @property
    def _win_suffix(self):
        return f"_{int(round(_WIN_SEC * 1000))}ms"

    def _strip_window_suffix(self, stem):
        """Recover the sensor stem from a saved window filename.

        Validate names the file after the width it was saved at, which need
        not be the width configured now, so any '_<n>ms' tail is removed -
        otherwise a window saved at 300 ms would never match the index.
        """
        if stem.endswith(self._win_suffix):
            return stem[: -len(self._win_suffix)]
        return _WIN_SUFFIX_RE.sub("", stem)

    @property
    def result(self):
        return self._result_df

    def run(self):
        try:
            if self._option == OPT_UNSEGMENTED:
                df, n_ok, n_skip = self._run_unsegmented()
            else:
                df, n_ok, n_skip = self._run_segmented()
            self._result_df = df
            self.done.emit(n_ok, n_skip, len(df) if df is not None else 0)
        except Exception as e:
            self.log.emit(f"\nFATAL: {e}")
            self.done.emit(0, 0, 0)

    def _meta_lookup(self):
        if self._index_df is None or "file" not in self._index_df.columns:
            return {}
        available = [c for c in _META_COLS if c in self._index_df.columns]
        return self._index_df.set_index("file")[available].to_dict(orient="index")

    def _attach_meta(self, df, stem, meta):
        info = meta.get(stem, {})
        insert_at = 1
        cols = self._index_df.columns if self._index_df is not None else []
        for col in _META_COLS:
            if col in cols:
                df.insert(insert_at, col, info.get(col, pd.NA))
                insert_at += 1
        return df

    # ── auto nadir +/- half a window out of the full sensor CSV ─────────────
    def _run_unsegmented(self):
        index_path = self._root / _INDEX_REL
        csv_dir = self._root / _CSV_DIR

        if not index_path.exists():
            raise FileNotFoundError(f"Sensor index not found:\n  {index_path}")
        if not csv_dir.exists():
            raise FileNotFoundError(f"Sensor CSV folder not found:\n  {csv_dir}")

        index = di.sensor_rows(pd.read_csv(index_path, low_memory=False))

        if _NADIR_COL not in index.columns:
            alt = next((c for c in index.columns
                        if "nadir" in c.lower() and "time" in c.lower()), None)
            if alt is None:
                raise ValueError(
                    f"Column '{_NADIR_COL}' not found in sensor index.")
            nadir_col = alt
            self.log.emit(f"Note: using '{nadir_col}' as nadir time column.\n")
        else:
            nadir_col = _NADIR_COL

        if "file" not in index.columns:
            raise ValueError("Sensor index has no 'file' column.")

        if self._selected_files:
            index = index[index["file"].isin(self._selected_files)]

        self.log.emit(f"Processing {len(index)} sensor file(s).\n")
        meta = self._meta_lookup()
        parts, n_ok, n_skip = [], 0, 0

        for _, row in index.iterrows():
            stem = str(row["file"])
            nadir_time = row[nadir_col]

            if pd.isna(nadir_time):
                self.log.emit(f"  SKIP {stem} - {nadir_col} is NaN")
                n_skip += 1
                continue

            sensor_path = csv_dir / f"{stem}.csv"
            if not sensor_path.exists():
                self.log.emit(f"  SKIP {stem} - sensor CSV not found")
                n_skip += 1
                continue

            try:
                half_sec = _WIN_SEC / 2
                t_start = float(nadir_time) - half_sec
                t_end = float(nadir_time) + half_sec

                sensor = pd.read_csv(sensor_path, low_memory=False)
                sliced = sensor[(sensor["time_s"] >= t_start)
                                & (sensor["time_s"] <= t_end)].copy()

                out = _standardise(sliced, self._target_rows)
                if out is None:
                    self.log.emit(
                        f"  SKIP {stem} - only {len(sliced)} rows in window "
                        f"(nadir near data boundary?)")
                    n_skip += 1
                    continue

                out.insert(0, "file", stem)
                out = self._attach_meta(out, stem, meta)
                parts.append(out)
                self.log.emit(f"  OK   {stem}")
                n_ok += 1
            except Exception as e:
                self.log.emit(f"  FAIL {stem} - {e}")
                n_skip += 1

        result = pd.concat(parts, ignore_index=True) if parts else None
        self.log.emit(f"\n-- Done: {n_ok} extracted, {n_skip} skipped.")
        return result, n_ok, n_skip

    # ── bind the saved nadir windows ────────────────────────────────────────
    def _run_segmented(self):
        win_dir = self._root / _NADIR_WIN_DIR
        if not win_dir.exists():
            raise FileNotFoundError(
                f"Nadir window folder not found:\n  {win_dir}\n"
                "Run the Validate & segment page first.")

        win_files = sorted(win_dir.glob("*.csv"))
        if not win_files:
            raise FileNotFoundError(f"No CSV files in:\n  {win_dir}")

        valid = None
        if self._index_df is not None and "file" in self._index_df.columns:
            if _BAD_SENS_COL in self._index_df.columns:
                ok = self._index_df[
                    self._index_df[_BAD_SENS_COL]
                    .astype(str).str.strip().str.upper() == "N"]
                valid = set(ok["file"].astype(str))
                self.log.emit(
                    f"Index: {len(valid)} sensor(s) with {_BAD_SENS_COL}=N.\n")
            else:
                self.log.emit(
                    f"Note: '{_BAD_SENS_COL}' not in index - binding all files.\n")
        else:
            self.log.emit("Note: no index - binding all files.\n")

        self.log.emit(f"Found {len(win_files)} nadir-window file(s).\n")
        meta = self._meta_lookup()
        parts, n_ok, n_skip = [], 0, 0

        for win_path in win_files:
            stem = self._strip_window_suffix(win_path.stem)

            if self._selected_files and stem not in self._selected_files:
                continue
            if valid is not None and stem not in valid:
                self.log.emit(f"  SKIP {stem} - not in index or bad_sens != N")
                n_skip += 1
                continue

            try:
                win = pd.read_csv(win_path, low_memory=False)
                out = _standardise(win, self._target_rows)
                if out is None:
                    self.log.emit(
                        f"  SKIP {stem} - only {len(win)} rows "
                        f"(expected >= {self._target_rows - 1})")
                    n_skip += 1
                    continue

                out.insert(0, "file", stem)
                out = self._attach_meta(out, stem, meta)
                parts.append(out)
                self.log.emit(f"  OK   {stem}  ({len(out)} rows)")
                n_ok += 1
            except Exception as e:
                self.log.emit(f"  FAIL {stem} - {e}")
                n_skip += 1

        result = pd.concat(parts, ignore_index=True) if parts else None
        self.log.emit(f"\n-- Done: {n_ok} bound, {n_skip} skipped.")
        return result, n_ok, n_skip


# ═════════════════════════════════════════════════════════════════════════════
class DatasetPage(QObject):
    """Binds dataset-creation behaviour to the widgets defined in main.ui."""

    status = Signal(str, int)
    # emitted whenever a dataset is created or annotated, so downstream
    # pages (Machine Learning Analysis) can consume the curated dataset
    # without re-running any sensor-processing logic
    dataset_ready = Signal(object, str)   # (DataFrame, source description)

    def __init__(self, ui, window, session_state=None):
        super().__init__(window)
        self.ui = ui
        self.window = window
        self.session_state = session_state

        self._root = None
        self._index = None
        self._thread = None
        self._result = None
        self._annotated = False
        self._feat_path = None
        self._label_path = None

        self._bind_paths = []

        self._build_figure()
        self._build_bind_training_data()
        self._configure_widgets()
        self._connect()
        self._on_session_library_changed(
            session_state.library if session_state is not None else None)

    # ── setup ────────────────────────────────────────────────────────────────
    def _build_figure(self):
        holder = QVBoxLayout(self.ui.frame_ds_figure)
        holder.setContentsMargins(0, 0, 0, 0)
        self.fig = Figure(figsize=(9.2, 3.2), dpi=100)
        self.canvas = FigureCanvas(self.fig)
        self.canvas.setMinimumHeight(240)
        holder.addWidget(self.canvas)

    def _build_bind_training_data(self):
        """Joins several ``model_features.csv`` files - one per library,
        typically - into one combined training set for Model training,
        without needing them merged into a single library first. Built in
        Python rather than in main.ui: `content_dataset`'s grid already
        has every cell filled (library/filter/console left, create/
        annotate/figure right), so this is a new row spanning both
        columns rather than a Designer restructure."""
        grp = QGroupBox("Bind training data")
        gv = QVBoxLayout(grp)
        gv.setSpacing(6)

        hint = QLabel(
            "Combine several model_features.csv files - e.g. one per "
            "library - into one training set. Rows are stacked; columns "
            "not shared by every file are kept and left blank where "
            "missing.")
        hint.setWordWrap(True)
        gv.addWidget(hint)

        self.list_bind_files = QListWidget()
        self.list_bind_files.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_bind_files.setMaximumHeight(120)
        gv.addWidget(self.list_bind_files)

        file_row = QHBoxLayout()
        self.btn_bind_add = QPushButton("Add file…")
        self.btn_bind_add.clicked.connect(self._bind_add_files)
        file_row.addWidget(self.btn_bind_add)
        self.btn_bind_remove = QPushButton("Remove selected")
        self.btn_bind_remove.clicked.connect(self._bind_remove_selected)
        file_row.addWidget(self.btn_bind_remove)
        file_row.addStretch()
        gv.addLayout(file_row)

        self.lbl_bind_status = QLabel("")
        self.lbl_bind_status.setWordWrap(True)
        gv.addWidget(self.lbl_bind_status)

        run_row = QHBoxLayout()
        run_row.addStretch()
        self.btn_bind_run = QPushButton("Bind and save…")
        self.btn_bind_run.clicked.connect(self._bind_run)
        run_row.addWidget(self.btn_bind_run)
        gv.addLayout(run_row)

        self.ui.grid_dataset.addWidget(grp, 3, 0, 1, 2)

    def _configure_widgets(self):
        u = self.ui
        # library selection is app-wide now (Home / session_state) - this
        # box just shows which one is active, rather than picking it
        u.tree_ds_library.setVisible(False)
        u.btn_ds_change_libraries.setVisible(False)
        self.lbl_library = QLabel("No library selected.")
        self.lbl_library.setStyleSheet("color:#8a95aa;")
        self.lbl_library.setWordWrap(True)
        u.grp_ds_library.layout().insertWidget(0, self.lbl_library)

        u.console_ds.setStyleSheet(
            "QPlainTextEdit{background:#1b1e23;color:#d4d4d4;"
            "border:1px solid #2c313a;border-radius:4px;}")
        u.chk_ds_select_all.setChecked(True)

    def _connect(self):
        u = self.ui
        if self.session_state is not None:
            self.session_state.library_changed.connect(
                self._on_session_library_changed)
        u.chk_ds_select_all.toggled.connect(self._set_all_checked)
        u.btn_ds_create.clicked.connect(self._run)
        u.btn_ds_save.clicked.connect(self._save)
        u.btn_ds_browse_features.clicked.connect(self._browse_features)
        u.btn_ds_browse_labels.clicked.connect(self._browse_labels)
        u.btn_ds_append.clicked.connect(self._append_annotations)
        u.btn_ds_save_annotated.clicked.connect(self._save_annotation_outputs)

    # ── library selection (session_state - see session_state.py) ────────────
    def _on_session_library_changed(self, root):
        # no status.emit here - Home already shows the one unified
        # "Library: X" message for a session-wide change (page_home.py)
        self.lbl_library.setText(
            f"Library: {root.name}" if root else "No library selected.")
        if root is None:
            self._root = None
            self._index = None
            self.ui.tree_ds_filter.clear()
            self.ui.btn_ds_create.setEnabled(False)
            return
        self._set_root(root)

    def _set_root(self, root: Path):
        self._root = root
        self.ui.tree_ds_filter.clear()
        self.ui.console_ds.clear()

        idx_path = root / _INDEX_REL
        if not idx_path.exists():
            self._log(f"Index not found:\n  {idx_path}\n")
            self._index = None
            self.ui.btn_ds_create.setEnabled(False)
            return

        try:
            self._index = di.sensor_rows(
                pd.read_csv(idx_path, low_memory=False))
        except Exception as e:
            self._log(f"Failed to load index: {e}\n")
            self._index = None
            self.ui.btn_ds_create.setEnabled(False)
            return

        self._populate_tree(self._index)
        self.ui.btn_ds_create.setEnabled(True)
        self._log(f"Library: {root.name}  ({len(self._index)} sensors)\n")

    def _populate_tree(self, df):
        """deployment_id -> treatment -> run -> file checkbox tree."""
        tree = self.ui.tree_ds_filter
        tree.blockSignals(True)
        tree.clear()

        group_cols = [c for c in ("deployment_id", "treatment", "run")
                      if c in df.columns]

        if not group_cols:
            root_item = QTreeWidgetItem(tree, ["All files"])
            _init_item(root_item, tristate=True)
            for fname in sorted(df["file"].dropna().unique()):
                _init_item(QTreeWidgetItem(root_item, [str(fname)]))
            root_item.setExpanded(True)
            tree.blockSignals(False)
            return

        level_items = {}
        for key, grp in df.groupby(group_cols, dropna=False):
            keys = key if isinstance(key, tuple) else (key,)
            parent_widget = tree.invisibleRootItem()

            for depth, val in enumerate(keys):
                path = keys[: depth + 1]
                val_str = (str(val) if val is not None
                           and not (isinstance(val, float) and pd.isna(val))
                           else "Unknown")
                if path not in level_items:
                    it = QTreeWidgetItem(parent_widget, [val_str])
                    _init_item(it, tristate=True)
                    it.setExpanded(depth == 0)
                    level_items[path] = it
                parent_widget = level_items[path]

            for fname in sorted(grp["file"].dropna().unique()):
                _init_item(QTreeWidgetItem(parent_widget, [str(fname)]))

        tree.blockSignals(False)

    def _get_selected_files(self):
        tree = self.ui.tree_ds_filter
        if tree.invisibleRootItem().childCount() == 0:
            return None
        selected = set()

        def _walk(item):
            if item.childCount() == 0:
                if item.checkState(0) == Qt.CheckState.Checked:
                    selected.add(item.text(0))
            else:
                for i in range(item.childCount()):
                    _walk(item.child(i))

        root_item = tree.invisibleRootItem()
        for i in range(root_item.childCount()):
            _walk(root_item.child(i))
        return selected

    def _set_all_checked(self, checked):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        tree = self.ui.tree_ds_filter
        tree.blockSignals(True)

        def _apply(item):
            item.setCheckState(0, state)
            for i in range(item.childCount()):
                _apply(item.child(i))

        root_item = tree.invisibleRootItem()
        for i in range(root_item.childCount()):
            _apply(root_item.child(i))
        tree.blockSignals(False)

    # ── create ───────────────────────────────────────────────────────────────
    def _run(self):
        if self._root is None:
            self.status.emit("Select a library first.", 5000)
            return

        selected = self._get_selected_files()
        if selected is not None and len(selected) == 0:
            self.status.emit("No files selected.", 4000)
            self._log("No files selected in the sensor selection tree.")
            return

        option = (OPT_UNSEGMENTED if self.ui.rb_ds_unsegmented.isChecked()
                  else OPT_SEGMENTED)
        self._result = None
        self._annotated = False
        self.ui.btn_ds_create.setEnabled(False)
        self.ui.btn_ds_save.setEnabled(False)
        self.ui.btn_ds_save_annotated.setEnabled(False)
        self.fig.clear()
        self.canvas.draw()
        self.ui.console_ds.clear()

        cfg = sensor_config.active()
        half = _WIN_SEC / 2
        label = {OPT_UNSEGMENTED: f"Unsegmented (auto nadir +/- {half:g} s)",
                 OPT_SEGMENTED: "Segmented (bind saved nadir windows)"}[option]
        n_sel = len(selected) if selected else "all"
        self._log(f"Method: {label}\nFiles selected: {n_sel}\n"
                  f"Sensor: {cfg.name} - {cfg.window_samples(_WIN_SEC)} rows "
                  f"per window at {cfg.output_rate_hz:g} Hz\n")

        self._thread = _ExtractThread(
            self._root, option, selected or set(), self._index, cfg)
        self._thread.log.connect(self._log)
        self._thread.done.connect(self._on_done)
        self._thread.start()

    def _on_done(self, n_ok, n_skip, n_rows):
        self.ui.btn_ds_create.setEnabled(True)
        self._result = self._thread.result

        if self._result is not None:
            self.ui.btn_ds_save.setEnabled(True)
            self.status.emit(
                f"Dataset created - {n_ok} files, {n_rows:,} rows.", 5000)
            self.dataset_ready.emit(
                self._result,
                "Sensor Processing - Dataset creation")
        else:
            self.status.emit("Dataset creation produced no output.", 6000)
        self._refresh_append_enabled()

    # ── annotate ─────────────────────────────────────────────────────────────
    def _browse_features(self):
        path, _ = QFileDialog.getOpenFileName(
            self.window, "Select sensor dataset CSV", str(Path.cwd()),
            "CSV files (*.csv)")
        if not path:
            return
        self._feat_path = Path(path)
        self.ui.ed_ds_features.setText(str(self._feat_path))
        self._refresh_append_enabled()

    def _browse_labels(self):
        path, _ = QFileDialog.getOpenFileName(
            self.window, "Select annotation dataset CSV", str(Path.cwd()),
            "CSV files (*.csv)")
        if not path:
            return
        self._label_path = Path(path)
        self.ui.ed_ds_labels.setText(str(self._label_path))
        self._refresh_append_enabled()

    def _refresh_append_enabled(self):
        """Append needs a features source (file or in-memory) and a label file."""
        have_feats = self._feat_path is not None or self._result is not None
        self.ui.btn_ds_append.setEnabled(
            bool(have_feats and self._label_path is not None))

    def _append_annotations(self):
        # explicit file wins over the in-memory dataset
        if self._feat_path is not None:
            try:
                feat = pd.read_csv(self._feat_path, low_memory=False)
            except Exception as e:
                self.status.emit(f"Feature load failed: {e}", 6000)
                return
        elif self._result is not None:
            feat = self._result
        else:
            self.status.emit("Select a sensor dataset first.", 5000)
            return

        if "file" not in feat.columns:
            self.status.emit("Sensor dataset has no 'file' column.", 6000)
            return

        try:
            labels = pd.read_csv(self._label_path)
        except Exception as e:
            self.status.emit(f"Label load failed: {e}", 6000)
            return

        if _LABEL_FILE_COL not in labels.columns:
            self.status.emit(
                f"Annotation CSV missing '{_LABEL_FILE_COL}' column.", 6000)
            return
        missing = [c for c in _LABEL_COLS if c not in labels.columns]
        if missing:
            self.status.emit(f"Annotation CSV missing columns: {missing}", 6000)
            return

        ann = (labels.rename(columns={_LABEL_FILE_COL: "file"})
               [["file"] + _LABEL_COLS].drop_duplicates(subset="file"))

        feat_files = set(feat["file"].unique())
        label_files = set(ann["file"].unique())
        keep = feat_files & label_files
        dropped = sorted(feat_files - label_files)

        if not keep:
            self.status.emit("No sensor files match the annotations.", 6000)
            return

        feat = feat[feat["file"].isin(keep)].copy()
        merged = feat.merge(ann, on="file", how="left")
        self._result = merged
        self._annotated = True

        self._log(
            "\n-- Append annotations --------------------------------\n"
            f"  Sensor files:       {len(feat_files)}\n"
            f"  Annotation files:   {len(label_files)}\n"
            f"  Matched (kept):     {len(keep)}\n"
            f"  Dropped (no label): {len(dropped)}\n"
            f"  Output rows:        {len(merged):,}")
        for d in dropped:
            self._log(f"    drop {d}")

        self._draw_annotation_figure()
        self.ui.btn_ds_save.setEnabled(True)
        self.ui.btn_ds_save_annotated.setEnabled(True)
        self.status.emit(
            f"Annotations appended - {len(keep)} files, "
            f"{len(dropped)} dropped, {len(merged):,} rows.", 6000)
        self.dataset_ready.emit(
            self._result,
            "Sensor Processing - Dataset creation (annotated)")

    # ── figure ───────────────────────────────────────────────────────────────
    def _bar(self, ax, labels, heights, title, ylabel, fmt, ymax=None):
        x = np.arange(len(heights))
        colors = [_BLUES[i % len(_BLUES)] for i in range(len(heights))]
        bars = ax.bar(x, heights, color=colors, edgecolor="black",
                      width=0.6, alpha=0.9)
        top = max(heights) if len(heights) else 0
        pad = top * 0.02 + 0.5
        for bar, val in zip(bars, heights):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + pad,
                    fmt(val), ha="center", va="bottom",
                    fontsize=8, fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.set_title(title, fontsize=9, fontweight="bold", color=_DARK)
        ax.set_ylim(0, ymax if ymax else top * 1.20 + 1)
        ax.set_axisbelow(True)
        ax.yaxis.grid(True, color="grey", linewidth=0.5, alpha=0.5)

    def _draw_annotation_figure(self):
        if self._result is None or "overall_passage_type" not in self._result.columns:
            return
        per_file = self._result.drop_duplicates(subset="file")
        self.fig.clear()
        ax0, ax1, ax2 = self.fig.subplots(1, 3)

        pt_order = ["leading_edge", "no_contact", "other"]
        pt_counts = per_file["overall_passage_type"].value_counts()
        self._bar(ax0, pt_order, [int(pt_counts.get(k, 0)) for k in pt_order],
                  title="Passage type", ylabel="Files (n)",
                  fmt=lambda v: f"{int(v)}")

        n_tot = len(per_file)
        n_strike = int(per_file["overall_passage_type"].isin(_STRIKE_TYPES).sum())
        rate = (n_strike / n_tot * 100) if n_tot else 0.0
        tx = (str(per_file["treatment"].iloc[0])
              if "treatment" in per_file.columns and n_tot else "all")
        self._bar(ax1, [tx], [rate],
                  title="Blade strike rate", ylabel="Blade strike rate (%)",
                  fmt=lambda v: f"{v:.1f}%", ymax=100)

        reg = pd.to_numeric(per_file["concentric_pump_region"], errors="coerce")
        reg_counts = reg.value_counts()
        self._bar(ax2, [str(k) for k in _REGION_ORDER],
                  [int(reg_counts.get(float(k), 0)) for k in _REGION_ORDER],
                  title="Concentric region", ylabel="Files (n)",
                  fmt=lambda v: f"{int(v)}")

        self.fig.tight_layout()
        self.canvas.draw()

    # ── save ─────────────────────────────────────────────────────────────────
    def _save(self):
        if self._result is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self.window, "Save dataset CSV",
            str(Path.cwd() / "model_features.csv"), "CSV files (*.csv)")
        if not path:
            return
        try:
            self._result.to_csv(path, index=False)
            self.status.emit(f"Saved: {Path(path).name}", 4000)
            self._log(f"\nSaved dataset → {path}")
        except Exception as e:
            self.status.emit(f"Save failed: {e}", 6000)

    def _save_annotation_outputs(self):
        """Save the annotated dataset CSV and the summary figure as PNG."""
        if self._result is None:
            return
        dirpath = QFileDialog.getExistingDirectory(
            self.window, "Save outputs to folder…", "")
        if not dirpath:
            return
        out = Path(dirpath)
        try:
            self._result.to_csv(out / "model_features.csv", index=False)
            self.fig.savefig(out / "annotation_summary.png",
                             dpi=300, bbox_inches="tight")
            self.status.emit(f"Saved outputs to {dirpath}", 5000)
            self._log(f"\nSaved annotated dataset + figure → {out}")
        except Exception as e:
            self.status.emit(f"Save failed: {e}", 6000)

    def _log(self, text):
        self.ui.console_ds.appendPlainText(text)
        sb = self.ui.console_ds.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ── bind training data (join several model_features.csv) ────────────────
    def _bind_add_files(self):
        start = str(self._root or settings.get_libraries_dir())
        paths, _ = QFileDialog.getOpenFileNames(
            self.window, "Add model_features.csv file(s)", start,
            "CSV files (*.csv)")
        added = 0
        for p in paths:
            path = Path(p)
            if path not in self._bind_paths:
                self._bind_paths.append(path)
                self.list_bind_files.addItem(QListWidgetItem(str(path)))
                added += 1
        if added:
            self.lbl_bind_status.setText(
                f"{len(self._bind_paths)} file(s) queued.")

    def _bind_remove_selected(self):
        for item in self.list_bind_files.selectedItems():
            row = self.list_bind_files.row(item)
            self.list_bind_files.takeItem(row)
            del self._bind_paths[row]
        self.lbl_bind_status.setText(
            f"{len(self._bind_paths)} file(s) queued." if self._bind_paths
            else "")

    def _bind_run(self):
        if len(self._bind_paths) < 2:
            self.lbl_bind_status.setText(
                "Add at least two files to bind together.")
            return

        dfs = []
        column_sets = set()
        for path in self._bind_paths:
            try:
                df = pd.read_csv(path, low_memory=False)
            except Exception as e:
                QMessageBox.critical(
                    self.window, "Could not read file", f"{path}:\n{e}")
                return
            df.insert(0, "_bind_source", path.name)
            dfs.append(df)
            column_sets.add(frozenset(df.columns) - {"_bind_source"})

        joined = pd.concat(dfs, ignore_index=True, sort=False)

        out_path, _ = QFileDialog.getSaveFileName(
            self.window, "Save bound training data",
            str(Path.cwd() / "model_features_bound.csv"), "CSV files (*.csv)")
        if not out_path:
            return
        try:
            joined.to_csv(out_path, index=False)
        except Exception as e:
            QMessageBox.critical(self.window, "Save failed", str(e))
            return

        msg = (f"Bound {len(self._bind_paths)} file(s), "
              f"{len(joined)} total rows → {out_path}")
        if len(column_sets) > 1:
            msg += (" (note: files did not all share the same columns - "
                   "missing values were left blank; check the result "
                   "before training on it)")
        self.lbl_bind_status.setText(msg)
        self.status.emit(f"Bound training data saved to {out_path}", 6000)
