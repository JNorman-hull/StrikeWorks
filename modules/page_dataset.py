# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Dataset creation (hidden for now - see ROADMAP.md, "Hidden for now";
Annotate's "Save and export" builds the dataset instead).

  Create from unsegmented (auto)
      Takes ``pres_min.time.`` from the global index, slices half the
      analysis window either side of the nadir out of the full sensor CSV
      and standardises it to the window's row count.

  Create from segmented
      Binds the saved window files in ``processed_sens_data/nadir_window``,
      keeping only sensors in the index with ``bad_sens == N``.

The window is 200 ms; its row count follows the selected sensor's output
rate (400 rows for RAPID at 2000 Hz).
"""
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton, QRadioButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)

from . import deployment_index as di
from . import sensor_config, settings
from .bind_datasets import BindTrainingData
from .dataset_build import (
    INDEX_REL, OPT_SEGMENTED, OPT_UNSEGMENTED, WIN_SEC, ExtractThread,
)
from .layout import Page, group_box
from .theme import style

# ── annotation join (model_labels.csv) ──────────────────────────────────────
_LABEL_FILE_COL = "sens_file"          # joins to feature 'file'
_LABEL_COLS = ["overall_passage_type", "leading_edge_type",
               "other_type", "concentric_pump_region"]
_STRIKE_TYPES = {"leading_edge", "other"}
_REGION_ORDER = [1, 2, 3, 4, 5]

_BLUES = ["#1e3a5f", "#2e5d9f", "#4a86c8", "#6fa8dc", "#9fc5e8"]
_DARK = "#1e3a5f"


def _init_item(item, tristate=False):
    flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
    if tristate:
        flags |= Qt.ItemFlag.ItemIsAutoTristate
    item.setFlags(flags)
    item.setCheckState(0, Qt.CheckState.Checked)


# ═════════════════════════════════════════════════════════════════════════════
class DatasetPage(Page):
    """Advanced dataset options: dataset creation and Bind training data."""

    # emitted whenever a dataset is created or annotated, so downstream
    # pages (Machine Learning Analysis) can consume the curated dataset
    # without re-running any sensor-processing logic
    dataset_ready = Signal(object, str)   # (DataFrame, source description)

    def __init__(self, main_window, session_state=None):
        super().__init__(main_window)
        self.session_state = session_state

        self._root = None
        self._index = None
        self._thread = None
        self._result = None
        self._annotated = False
        self._feat_path = None
        self._label_path = None

        self._build_ui()
        self._build_figure()
        self._build_bind_training_data()
        self._configure_widgets()
        self._connect()
        self._on_session_library_changed(
            session_state.library if session_state is not None else None)

    # ── setup ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        """Library, Sensor selection and Console output on the left; Create
        dataset, Annotate dataset and Annotation summary on the right."""
        grid = self.grid_dataset = QGridLayout(self)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setSpacing(8)

        self.grp_ds_library, _ = group_box("Library")
        grid.addWidget(self.grp_ds_library, 0, 0)

        self.grp_ds_filter, fv = group_box("Sensor selection")
        self.tree_ds_filter = QTreeWidget()
        self.tree_ds_filter.setHeaderHidden(True)
        fv.addWidget(self.tree_ds_filter)
        self.chk_ds_select_all = QCheckBox("Select / unselect all")
        fv.addWidget(self.chk_ds_select_all)
        grid.addWidget(self.grp_ds_filter, 1, 0)

        self.grp_ds_console, cv = group_box("Console output")
        self.console_ds = QPlainTextEdit()
        self.console_ds.setReadOnly(True)
        cv.addWidget(self.console_ds)
        grid.addWidget(self.grp_ds_console, 2, 0)

        self.grp_ds_create, rv = group_box("Create dataset")
        self.rb_ds_unsegmented = QRadioButton(
            "Create from unsegmented (auto nadir, 200 ms window)")
        self.rb_ds_unsegmented.setChecked(True)
        self.rb_ds_segmented = QRadioButton(
            "Create from segmented (bind saved nadir windows)")
        rv.addWidget(self.rb_ds_unsegmented)
        rv.addWidget(self.rb_ds_segmented)
        self.btn_ds_create = QPushButton("Create dataset")
        self.btn_ds_save = QPushButton("Save dataset")
        rv.addLayout(self._button_row(self.btn_ds_create, self.btn_ds_save))
        grid.addWidget(self.grp_ds_create, 0, 1)

        self.grp_ds_annotate, av = group_box("Annotate dataset")
        self.ed_ds_features, self.btn_ds_browse_features = self._file_row(
            av, "Sensor dataset:")
        self.ed_ds_labels, self.btn_ds_browse_labels = self._file_row(
            av, "Annotation dataset:")
        self.btn_ds_append = QPushButton("Append features")
        self.btn_ds_save_annotated = QPushButton("Save annotated dataset")
        av.addLayout(self._button_row(self.btn_ds_append,
                                      self.btn_ds_save_annotated))
        grid.addWidget(self.grp_ds_annotate, 1, 1)

        self.grp_ds_figure, gv = group_box("Annotation summary")
        self.frame_ds_figure = QFrame()
        gv.addWidget(self.frame_ds_figure)
        grid.addWidget(self.grp_ds_figure, 2, 1)

    @staticmethod
    def _button_row(*buttons):
        row = QHBoxLayout()
        for b in buttons:
            b.setEnabled(False)
            row.addWidget(b)
        row.addStretch()
        return row

    @staticmethod
    def _file_row(layout, label):
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        edit = QLineEdit()
        edit.setPlaceholderText("no file selected")
        edit.setReadOnly(True)
        row.addWidget(edit, stretch=1)
        browse = QPushButton("Browse…")
        row.addWidget(browse)
        layout.addLayout(row)
        return edit, browse

    def _build_figure(self):
        holder = QVBoxLayout(self.frame_ds_figure)
        holder.setContentsMargins(0, 0, 0, 0)
        self.fig = Figure(figsize=(9.2, 3.2), dpi=100)
        self.canvas = FigureCanvas(self.fig)
        self.canvas.setMinimumHeight(240)
        holder.addWidget(self.canvas)

    def _build_bind_training_data(self):
        """Joins several ``model_features.csv`` files - one per library,
        typically - into one combined training set for Model training,
        without needing them merged into a single library first: a row
        under the grid's six boxes, spanning both columns."""
        grp = QGroupBox("Bind training data")
        gv = QVBoxLayout(grp)
        gv.addWidget(BindTrainingData(start_dir=lambda: self._root
                                      or settings.get_libraries_dir()))

        # only Bind training data is offered: building a dataset is
        # Annotate's Save and export, so the other boxes are hidden
        grid = self.grid_dataset
        for w in (self.grp_ds_library, self.grp_ds_filter,
                  self.grp_ds_console, self.grp_ds_create,
                  self.grp_ds_annotate, self.grp_ds_figure):
            w.setVisible(False)
        for row in range(3):
            grid.setRowStretch(row, 0)
        grid.addWidget(grp, 3, 0, 1, 2)
        grid.setRowStretch(3, 0)
        grid.setRowStretch(4, 1)

    def _configure_widgets(self):
        # the library is chosen on Home; this box only shows it
        self.lbl_library = QLabel("No library selected.")
        style(self.lbl_library, role="muted")
        self.lbl_library.setWordWrap(True)
        self.grp_ds_library.layout().insertWidget(0, self.lbl_library)

        style(self.console_ds, role="console")
        self.chk_ds_select_all.setChecked(True)

    def _connect(self):
        if self.session_state is not None:
            self.session_state.library_changed.connect(
                self._on_session_library_changed)
        self.chk_ds_select_all.toggled.connect(self._set_all_checked)
        self.btn_ds_create.clicked.connect(self._run)
        self.btn_ds_save.clicked.connect(self._save)
        self.btn_ds_browse_features.clicked.connect(self._browse_features)
        self.btn_ds_browse_labels.clicked.connect(self._browse_labels)
        self.btn_ds_append.clicked.connect(self._append_annotations)
        self.btn_ds_save_annotated.clicked.connect(self._save_annotation_outputs)

    # ── library selection (session_state - see session_state.py) ────────────
    def _on_session_library_changed(self, root):
        # no status.emit here - Home already shows the one unified
        # "Library: X" message for a session-wide change (page_home.py)
        self.lbl_library.setText(
            f"Library: {root.name}" if root else "No library selected.")
        if root is None:
            self._root = None
            self._index = None
            self.tree_ds_filter.clear()
            self.btn_ds_create.setEnabled(False)
            return
        self._set_root(root)

    def _set_root(self, root: Path):
        self._root = root
        self.tree_ds_filter.clear()
        self.console_ds.clear()

        idx_path = root / INDEX_REL
        if not idx_path.exists():
            self._log(f"Index not found:\n  {idx_path}\n")
            self._index = None
            self.btn_ds_create.setEnabled(False)
            return

        try:
            self._index = di.sensor_rows(
                pd.read_csv(idx_path, low_memory=False))
        except Exception as e:
            self._log(f"Failed to load index: {e}\n")
            self._index = None
            self.btn_ds_create.setEnabled(False)
            return

        self._populate_tree(self._index)
        self.btn_ds_create.setEnabled(True)
        self._log(f"Library: {root.name}  ({len(self._index)} sensors)\n")

    def _populate_tree(self, df):
        """deployment_id -> treatment -> run -> file checkbox tree."""
        tree = self.tree_ds_filter
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
        tree = self.tree_ds_filter
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
        tree = self.tree_ds_filter
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

        option = (OPT_UNSEGMENTED if self.rb_ds_unsegmented.isChecked()
                  else OPT_SEGMENTED)
        self._result = None
        self._annotated = False
        self.btn_ds_create.setEnabled(False)
        self.btn_ds_save.setEnabled(False)
        self.btn_ds_save_annotated.setEnabled(False)
        self.fig.clear()
        self.canvas.draw()
        self.console_ds.clear()

        cfg = sensor_config.active()
        half = WIN_SEC / 2
        label = {OPT_UNSEGMENTED: f"Unsegmented (auto nadir +/- {half:g} s)",
                 OPT_SEGMENTED: "Segmented (bind saved nadir windows)"}[option]
        n_sel = len(selected) if selected else "all"
        self._log(f"Method: {label}\nFiles selected: {n_sel}\n"
                  f"Sensor: {cfg.name} - {cfg.window_samples(WIN_SEC)} rows "
                  f"per window at {cfg.output_rate_hz:g} Hz\n")

        self._thread = ExtractThread(
            self._root, option, selected or set(), self._index, cfg)
        self._thread.log.connect(self._log)
        self._thread.done.connect(self._on_done)
        self._thread.start()

    def _on_done(self, n_ok, n_skip, n_rows):
        self.btn_ds_create.setEnabled(True)
        self._result = self._thread.result

        if self._result is not None:
            self.btn_ds_save.setEnabled(True)
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
            self.main_window, "Select sensor dataset CSV",
            str(settings.get_input_data_dir()),
            "CSV files (*.csv)")
        if not path:
            return
        self._feat_path = Path(path)
        self.ed_ds_features.setText(str(self._feat_path))
        self._refresh_append_enabled()

    def _browse_labels(self):
        path, _ = QFileDialog.getOpenFileName(
            self.main_window, "Select annotation dataset CSV",
            str(settings.get_input_data_dir()),
            "CSV files (*.csv)")
        if not path:
            return
        self._label_path = Path(path)
        self.ed_ds_labels.setText(str(self._label_path))
        self._refresh_append_enabled()

    def _refresh_append_enabled(self):
        """Append needs a features source (file or in-memory) and a label file."""
        have_feats = self._feat_path is not None or self._result is not None
        self.btn_ds_append.setEnabled(
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
        self.btn_ds_save.setEnabled(True)
        self.btn_ds_save_annotated.setEnabled(True)
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
            self.main_window, "Save dataset CSV",
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
            self.main_window, "Save outputs to folder…", "")
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
        self.console_ds.appendPlainText(text)
        sb = self.console_ds.verticalScrollBar()
        sb.setValue(sb.maximum())

