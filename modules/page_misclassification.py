"""Misclassification analysis: pick a model, list the recordings its
cross-validation got wrong (`{kind}_cv_predictions.csv`), plot the signal
and correct the labels.

Corrections go to `<dataset>_corrected.csv` beside the training dataset
(made on the first correction and read from then on, so corrections
accumulate) and to the recording's row in its library's sensor index
(`_sync_index`). The training dataset is the one in memory for a model
trained this session, else the path in its package's train_config.json.
Leaving the page after corrections loads the corrected dataset into Train
(`notify_and_load_into_training`, called by `MainWindow.navigate_to`).
"""
from datetime import datetime
from pathlib import Path

import pandas as pd
import pyqtgraph as pg

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QMessageBox, QPushButton, QSizePolicy, QSplitter,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import annotation_schema as asch
from . import deployment_index as di
from . import ml_model_library
from . import settings
from .annotation_widgets import AnnotationValueEditor, VariableListDialog
from .layout import (
    discard_widget, Page, Section, when_visible,
)
from .theme import TRACE, TRACE2, muted_label, style
from .sensor_validation import open_video
from .raw_layout import RAW_DIR, video_index
from .plot_widgets import NavViewBox
from .plot_style import (
    add_export_button, build_export_data, reserve_top_margin,
    set_right_axis_active,
)

# the model's training channels, or every channel recorded for the file
_VIEW_MODEL = "model"
_VIEW_FULL = "full"
_NON_CHANNEL_COLS = {"file", "time_s", "treatment", "deployment"}


class _VideoIndexThread(QThread):
    """raw_layout.video_index off the GUI thread: it walks every library's
    raw folder, which on OneDrive takes a second or more."""
    done = Signal(object)

    def __init__(self, lib_dir):
        super().__init__()
        self._lib_dir = lib_dir

    def run(self):
        try:
            index = video_index(self._lib_dir)
        except Exception as e:
            print(f"Could not scan {self._lib_dir} for video: {e}")
            index = {}
        self.done.emit(index)


def _resolve_column(df, var_name):
    return var_name if var_name in df.columns else None


def _misclassified_rows(entry):
    """[{file, true, pred, confidence, treatment}, ...]: the recordings the
    model's cross-validation got wrong, from its cv_predictions."""
    df = entry.cv_predictions
    if df is None or not len(df):
        return []
    rows = []
    if "error_type" in df.columns:                       # binary
        bad = df[df["error_type"] != "correct"]
        for _, r in bad.iterrows():
            rows.append({
                "file": r["file"],
                "true": "Strike" if r["y_true"] == 1 else "No strike",
                "pred": "Strike" if r["y_pred"] == 1 else "No strike",
                "confidence": float(r["probability"]),
                "treatment": r.get("treatment", "-"),
            })
    elif "true_class" in df.columns:                      # multiclass
        bad = df[~df["correct"].astype(bool)]
        for _, r in bad.iterrows():
            rows.append({
                "file": r["file"],
                "true": r["true_class"],
                "pred": r["pred_class"],
                "confidence": float(r["confidence"]),
                "treatment": r.get("treatment", "-"),
            })
    return rows


class MisclassificationPage(Page):
    """Model training > Misclassification analysis."""

    def __init__(self, main_window, training_state):
        super().__init__(main_window)
        self.training_state = training_state

        self._entries = []
        self._entry = None
        self._rows = []
        self._matches_by_file = {}
        self._cur_stem = None
        self._df_cache = {}          # id(entry) -> long-format DataFrame
        self._time = None
        self._left_key = None
        self._right_key = None
        self._editors = {}
        self._labels_for = None      # id() of the dataset the editors are for
        self._has_changes = False
        self._corrected_path = None
        self._corrections = []       # [{file, variable, old, new, when}, ...]
        self._video_index = None     # built in the background, then cached
        self._video_thread = None

        self._build(self)
        self._connect()
        # nothing loaded at startup - the model list (and the video index
        # behind its Video column) the first time the page is opened
        when_visible(self, self._reload_models,
                     key="models")

    # layout
    def _build(self, frame):
        root = QHBoxLayout(frame)
        root.setContentsMargins(4, 6, 4, 6)
        root.setSpacing(0)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        root.addWidget(split)

        split.addWidget(self._build_browser())

        # the signal plot over the Labels box, with a grab bar between them
        plot = QWidget()
        pv = QVBoxLayout(plot)
        pv.setContentsMargins(0, 0, 0, 0)
        self._build_plot_side(pv)
        labels = self._build_labels_side()
        detail = QSplitter(Qt.Orientation.Vertical)
        detail.setChildrenCollapsible(False)
        detail.setContentsMargins(5, 0, 0, 0)
        detail.addWidget(plot)
        detail.addWidget(labels)
        detail.setStretchFactor(0, 1)
        detail.setStretchFactor(1, 0)
        detail.setSizes([3000, labels.sizeHint().height()])
        split.addWidget(detail)
        split.setSizes([1, 1])


    def _build_browser(self):
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 5, 0)
        lv.setSpacing(8)

        grp = Section("Model")
        gv = QVBoxLayout(grp)
        gv.setSpacing(6)
        sel_row = QHBoxLayout()
        self.cmb_model = QComboBox()
        self.cmb_model.setSizePolicy(QSizePolicy.Policy.Expanding,
                                     QSizePolicy.Policy.Fixed)
        sel_row.addWidget(self.cmb_model, stretch=1)
        self.btn_refresh = QPushButton("Refresh")
        sel_row.addWidget(self.btn_refresh)
        gv.addLayout(sel_row)
        self.lbl_source = QLabel("")
        style(self.lbl_source, role="muted")
        self.lbl_source.setWordWrap(True)
        gv.addWidget(self.lbl_source)
        lv.addWidget(grp)

        self.tbl_misclass = QTableWidget(0, 6)
        self.tbl_misclass.setHorizontalHeaderLabels(
            ["File", "True", "Predicted", "Confidence", "Treatment", "Video"])
        self.tbl_misclass.verticalHeader().setVisible(False)
        self.tbl_misclass.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_misclass.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_misclass.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl_misclass.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive)
        lv.addWidget(self.tbl_misclass, stretch=1)
        return left

    def _build_plot_side(self, v):
        grp = Section("Signal")
        sv = QVBoxLayout(grp)
        sv.setSpacing(6)

        axis_row = QHBoxLayout()
        self.cmb_view = QComboBox()
        self.cmb_view.addItem("Model selection", _VIEW_MODEL)
        self.cmb_view.addItem("Full sensor", _VIEW_FULL)
        self.cmb_view.setToolTip(
            "Model selection: only the channels this model was trained on.\n"
            "Full sensor: every recorded channel for this file.")
        self.cmb_view.currentIndexChanged.connect(self._on_view_changed)
        axis_row.addWidget(self.cmb_view)
        self.cmb_left = QComboBox()
        self.cmb_right = QComboBox()
        axis_row.addWidget(muted_label("Left"))
        axis_row.addWidget(self.cmb_left, stretch=1)
        axis_row.addWidget(muted_label("Right"))
        axis_row.addWidget(self.cmb_right, stretch=1)
        axis_row.addStretch()
        add_export_button(axis_row, self._export_data, self.main_window,
                          file_stub="misclassification")
        sv.addLayout(axis_row)

        self._pw = pg.PlotWidget(viewBox=NavViewBox())
        pi = self._pw.plotItem
        pi.getViewBox().setMouseMode(pg.ViewBox.RectMode)
        pi.setLabel("bottom", "Time (s)")
        reserve_top_margin(pi)
        sv.addWidget(self._pw, stretch=1)

        self._vb2 = pg.ViewBox()
        pi.scene().addItem(self._vb2)
        pi.getAxis("right").linkToView(self._vb2)
        self._vb2.setXLink(pi)
        set_right_axis_active(pi, False)
        pi.vb.sigResized.connect(self._sync_vb2)

        self._curve = None
        self._right_curve = None

        self.lbl_signal_note = QLabel(
            "Select a misclassified file to view its signal.")
        style(self.lbl_signal_note, role="muted")
        self.lbl_signal_note.setWordWrap(True)
        sv.addWidget(self.lbl_signal_note)
        v.addWidget(grp, stretch=1)

    def _build_labels_side(self):
        grp = Section("Labels")
        gv = QVBoxLayout(grp)
        gv.setSpacing(6)

        self.annotation_grid = QGridLayout()
        self.annotation_grid.setVerticalSpacing(6)
        self.annotation_grid.setColumnStretch(1, 1)
        gv.addLayout(self.annotation_grid)

        self.btn_manage_vars = QPushButton("Manage variables…")
        gv.addWidget(self.btn_manage_vars)

        act = QHBoxLayout()
        self.btn_save_correction = QPushButton("Save correction")
        self.btn_save_correction.setEnabled(False)
        act.addWidget(self.btn_save_correction)
        act.addStretch()
        gv.addLayout(act)

        self.lbl_detail_status = QLabel("")
        style(self.lbl_detail_status, role="muted")
        self.lbl_detail_status.setWordWrap(True)
        gv.addWidget(self.lbl_detail_status)
        return grp

    def _connect(self):
        self.cmb_model.currentIndexChanged.connect(self._on_model_changed)
        self.btn_refresh.clicked.connect(self._refresh)
        self.tbl_misclass.itemSelectionChanged.connect(self._on_row_selected)
        self.tbl_misclass.itemDoubleClicked.connect(
            self._on_misclass_double_clicked)
        self.cmb_left.currentIndexChanged.connect(self._refresh_signal)
        self.cmb_right.currentIndexChanged.connect(self._refresh_signal)
        self.btn_manage_vars.clicked.connect(self._manage_variables)
        self.btn_save_correction.clicked.connect(self._save_correction)
        asch.notifier.changed.connect(self._rebuild_labels)
        self._rebuild_labels()

    # models
    def _refresh(self):
        """Refresh button: re-discover models and re-index videos."""
        self._video_index = None
        self._reload_models()

    def _reload_models(self):
        keep = self.cmb_model.currentText()
        self._entries = []
        if self.training_state is not None:
            self._entries += ml_model_library.session_entries(self.training_state)
        self._entries += ml_model_library.discover_models(
            settings.get_models_dir())

        self.cmb_model.blockSignals(True)
        self.cmb_model.clear()
        for e in self._entries:
            self.cmb_model.addItem(e.label)
        idx = self.cmb_model.findText(keep)
        self.cmb_model.setCurrentIndex(idx if idx >= 0 else 0)
        self.cmb_model.blockSignals(False)
        self._on_model_changed()

    def _on_model_changed(self):
        idx = self.cmb_model.currentIndex()
        self._entry = (self._entries[idx]
                       if 0 <= idx < len(self._entries) else None)
        self._populate_misclassified()

    def _populate_misclassified(self):
        self.tbl_misclass.setRowCount(0)
        self._rows = []
        self._matches_by_file = {}
        self._clear_signal()
        self._rebuild_labels()

        if self._entry is None:
            self.lbl_source.setText("No models found.")
            return

        self._rows = _misclassified_rows(self._entry)
        self.lbl_source.setText(
            f"{self._entry.label} - {len(self._rows)} misclassified "
            f"recording(s).")

        self._matches_by_file = {}
        self.tbl_misclass.setRowCount(len(self._rows))
        for r, row in enumerate(self._rows):
            item_file = QTableWidgetItem(str(row["file"]))
            item_file.setData(Qt.ItemDataRole.UserRole, row["file"])
            self.tbl_misclass.setItem(r, 0, item_file)
            self.tbl_misclass.setItem(r, 1, QTableWidgetItem(str(row["true"])))
            self.tbl_misclass.setItem(r, 2, QTableWidgetItem(str(row["pred"])))
            self.tbl_misclass.setItem(
                r, 3, QTableWidgetItem(f'{row["confidence"]:.3f}'))
            self.tbl_misclass.setItem(
                r, 4, QTableWidgetItem(str(row["treatment"])))
            video_item = QTableWidgetItem("…")
            video_item.setData(Qt.ItemDataRole.UserRole, row["file"])
            self.tbl_misclass.setItem(r, 5, video_item)
        self.tbl_misclass.resizeColumnsToContents()
        if self._video_index is None:
            self._start_video_index()
        else:
            self._fill_video_column()

    # video index (background, cached - see raw_layout.video_index)
    def _start_video_index(self):
        if self._video_thread is not None and self._video_thread.isRunning():
            return
        self._video_thread = _VideoIndexThread(settings.get_libraries_dir())
        self._video_thread.done.connect(self._on_video_index)
        self._video_thread.start()

    def _on_video_index(self, index):
        self._video_index = index
        self._fill_video_column()

    def _fill_video_column(self):
        """Video column + the double-click lookup, from the cached index -
        each row found by its own file (the table is sortable)."""
        index = self._video_index or {}
        self._matches_by_file = {}
        for r in range(self.tbl_misclass.rowCount()):
            item = self.tbl_misclass.item(r, 5)
            if item is None:
                continue
            file = str(item.data(Qt.ItemDataRole.UserRole))
            matches = index.get(file, [])
            self._matches_by_file[file] = matches
            names = list(dict.fromkeys(p.name for p in matches))
            item.setText("; ".join(names) if names else "-")
        for row in self._rows:
            row["video_matches"] = self._matches_by_file.get(str(row["file"]), [])
        self.tbl_misclass.resizeColumnToContents(5)

    def _on_misclass_double_clicked(self, item):
        if item.column() != 5:
            return
        # by file, not item.row(): the table can be sorted
        stem = item.data(Qt.ItemDataRole.UserRole)
        matches = self._matches_by_file.get(stem) or []
        message = open_video(self.main_window, stem, matches)
        if message:
            self.status.emit(message, 4000)

    # dataset access
    def _resolve_dataset_path(self, entry):
        if entry.source == "session":
            return (self.training_state.dataset_path
                    if self.training_state else None)
        if entry.model_path is None:
            return None
        pkg = ml_model_library._package_dir_for(entry.model_path)
        if pkg is None:
            return None
        cfg = ml_model_library._read_json(pkg / "train_config.json")
        if not cfg or "data" not in cfg:
            return None
        return Path(cfg["data"])

    @staticmethod
    def _corrected_path_for(path):
        return path.with_name(f"{path.stem}_corrected{path.suffix}")

    def _dataset_for_entry(self, entry):
        key = id(entry)
        if key in self._df_cache:
            return self._df_cache[key]

        base_path = self._resolve_dataset_path(entry)
        df = None
        if base_path is not None:
            corrected = self._corrected_path_for(base_path)
            if corrected.exists():
                try:
                    df = pd.read_csv(corrected, low_memory=False)
                except (OSError, ValueError) as e:
                    self.status.emit(f"Could not read {corrected.name}: {e}", 6000)
            elif entry.source == "session" and self.training_state is not None:
                df = self.training_state.dataset_df
            elif base_path.exists():
                try:
                    df = pd.read_csv(base_path, low_memory=False)
                except (OSError, ValueError) as e:
                    self.status.emit(f"Could not read {base_path.name}: {e}", 6000)
        self._df_cache[key] = df
        return df

    # selection / signal
    def _on_row_selected(self):
        items = self.tbl_misclass.selectedItems()
        if not items:
            return
        stem = self.tbl_misclass.item(items[0].row(), 0).data(
            Qt.ItemDataRole.UserRole)
        self._load_file(stem)

    def _load_file(self, stem):
        self._cur_stem = stem
        df = self._dataset_for_entry(self._entry) if self._entry else None
        if df is None or "file" not in df.columns:
            self.lbl_signal_note.setText(
                "Can't locate this model's training dataset on disk.")
            self._clear_signal()
            self._load_labels_for_current(None)
            return

        sig = df[df["file"] == stem]
        if not len(sig):
            self.lbl_signal_note.setText(
                f"{stem} not found in the training dataset.")
            self._clear_signal()
            self._load_labels_for_current(None)
            return
        sig = sig.sort_values("time_s")
        if self._labels_for != id(df):
            self._rebuild_labels()

        self._rebuild_channel_combos(sig)
        self._time = sig["time_s"].to_numpy(dtype=float)
        self._sig = sig
        self._refresh_signal()
        self.lbl_signal_note.setText("")
        self.btn_save_correction.setEnabled(True)
        self._load_labels_for_current(sig.iloc[0])

    def _on_view_changed(self, _idx):
        if hasattr(self, "_sig"):
            self._rebuild_channel_combos(self._sig)
            self._refresh_signal()

    def _rebuild_channel_combos(self, sig):
        if self.cmb_view.currentData() == _VIEW_FULL:
            chans = [c for c in sig.columns if c not in _NON_CHANNEL_COLS
                     and pd.api.types.is_numeric_dtype(sig[c])]
        else:
            chans = list(self._entry.metrics.get("channels", [])) \
                if self._entry and self._entry.metrics else []
            chans = [c for c in chans if c in sig.columns]
            derived = [c for c in sig.columns
                      if c not in chans and "_mag_" in c]
            chans = derived + chans

        for cmb, default, extra_none in (
                (self.cmb_left, "pressure_kpa", False),
                (self.cmb_right, "higacc_mag_g", True)):
            cmb.blockSignals(True)
            current = cmb.currentData()
            cmb.clear()
            if extra_none:
                cmb.addItem("None", None)
            for c in chans:
                cmb.addItem(c, c)
            idx = cmb.findData(current if current in chans else default)
            cmb.setCurrentIndex(idx if idx >= 0 else 0)
            cmb.blockSignals(False)

    def _refresh_signal(self):
        pi = self._pw.plotItem
        if self._curve is not None:
            pi.removeItem(self._curve)
            self._curve = None
        if self._right_curve is not None:
            self._vb2.removeItem(self._right_curve)
            self._right_curve = None
        if self._time is None or not hasattr(self, "_sig"):
            return

        self._left_key = self.cmb_left.currentData()
        self._right_key = self.cmb_right.currentData()
        sig = self._sig

        if self._left_key and self._left_key in sig.columns:
            y = sig[self._left_key].to_numpy(dtype=float)
            self._curve = self._pw.plot(
                self._time, y, pen=pg.mkPen(TRACE, width=1))
            self._curve.setDownsampling(auto=True, method="peak")
            self._curve.setClipToView(True)
            pi.setLabel("left", self._left_key)

        if self._right_key and self._right_key in sig.columns:
            set_right_axis_active(pi, True)
            pi.setLabel("right", self._right_key)
            self._right_curve = pg.PlotCurveItem(
                pen=pg.mkPen(TRACE2, width=1))
            self._vb2.addItem(self._right_curve)
            self._right_curve.setData(
                self._time, sig[self._right_key].to_numpy(dtype=float))
            self._sync_vb2()
            self._vb2.enableAutoRange("y", True)
        else:
            set_right_axis_active(pi, False)

        pi.enableAutoRange("x", True)
        pi.enableAutoRange("y", True)

    def _sync_vb2(self):
        pi = self._pw.plotItem
        self._vb2.setGeometry(pi.vb.sceneBoundingRect())
        self._vb2.linkedViewChanged(pi.vb, self._vb2.XAxis)

    def _clear_signal(self):
        self._cur_stem = None
        self._time = None
        if hasattr(self, "_sig"):
            del self._sig
        pi = self._pw.plotItem
        if self._curve is not None:
            pi.removeItem(self._curve)
            self._curve = None
        if self._right_curve is not None:
            self._vb2.removeItem(self._right_curve)
            self._right_curve = None
        set_right_axis_active(pi, False)
        self.btn_save_correction.setEnabled(False)
        self.lbl_signal_note.setText(
            "Select a misclassified file to view its signal.")

    def _export_data(self):
        if self._time is None or not hasattr(self, "_sig"):
            return None
        left_y = (self._sig[self._left_key].to_numpy(dtype=float)
                  if self._left_key and self._left_key in self._sig.columns
                  else None)
        right_y = (self._sig[self._right_key].to_numpy(dtype=float)
                   if self._right_key and self._right_key in self._sig.columns
                   else None)
        return build_export_data(
            self._time, self._left_key or "", left_y,
            self._right_key or "", right_y, self._pw, self._vb2)

    # labels
    def _rebuild_labels(self):
        """One editor per annotation variable the model's training dataset
        has a column for - the main ones, then the position ones under
        their own heading - so the labels are the data's, not every
        variable in the settings."""
        while self.annotation_grid.count():
            item = self.annotation_grid.takeAt(0)
            w = item.widget()
            if w is not None:
                discard_widget(w)
        self._editors = {}
        df = self._df_cache.get(id(self._entry)) if self._entry else None
        self._labels_for = id(df) if df is not None else None
        if df is None:
            self._label_note("Select a misclassified recording to see the "
                             "labels its dataset has.")
            return
        groups = [(None, [v for v in asch.all_variables(asch.MAIN_GROUP)
                          if v.name in df.columns]),
                  (asch.GROUP_LABELS[asch.POSITION_GROUP],
                   [v for v in asch.all_variables(asch.POSITION_GROUP)
                    if v.name in df.columns])]
        row = 0
        for heading, variables in groups:
            if heading and variables:
                lab = QLabel(heading)
                style(lab, role="strong")
                self.annotation_grid.addWidget(lab, row, 0, 1, 2)
                row += 1
            for var in variables:
                editor = AnnotationValueEditor(var.name)
                self.annotation_grid.addWidget(muted_label(var.label), row, 0)
                self.annotation_grid.addWidget(editor, row, 1)
                self._editors[var.name] = editor
                row += 1
        if not self._editors:
            self._label_note("This model's dataset has none of the annotation "
                             "variables (Manage variables… lists them).")
        if self._cur_stem and hasattr(self, "_sig") and len(self._sig):
            self._load_labels_for_current(self._sig.iloc[0])

    def _label_note(self, text):
        note = QLabel(text)
        note.setWordWrap(True)
        style(note, role="muted")
        self.annotation_grid.addWidget(note, 0, 0, 1, 2)

    def _load_labels_for_current(self, row):
        for name, editor in self._editors.items():
            value = ""
            if row is not None:
                col = _resolve_column(self._sig, name) if hasattr(self, "_sig") else None
                if col is not None:
                    value = row.get(col, "")
                    value = "" if pd.isna(value) else value
            editor.set_current(value)

    def _manage_variables(self):
        dlg = VariableListDialog(self.main_window)
        dlg.exec()

    # save
    def _save_correction(self):
        if self._cur_stem is None or self._entry is None:
            return
        base_path = self._resolve_dataset_path(self._entry)
        if base_path is None:
            QMessageBox.warning(
                self.main_window, "No dataset",
                "Can't locate this model's training dataset on disk.")
            return

        df = self._df_cache.get(id(self._entry))
        if df is None:
            QMessageBox.warning(self.main_window, "No dataset",
                                "Training dataset not loaded.")
            return

        mask = df["file"] == self._cur_stem
        if not mask.any():
            QMessageBox.warning(
                self.main_window, "Not found",
                f"{self._cur_stem} not found in the training dataset.")
            return

        values = {name: editor.current() for name, editor in
                  self._editors.items()}
        if not any(values.values()):
            QMessageBox.warning(
                self.main_window, "Nothing entered",
                "Enter at least one corrected value before saving.")
            return

        var_labels = {v.name: v.label for v in asch.all_variables()}
        changed = []
        for name, value in values.items():
            if not value:
                continue
            col = _resolve_column(df, name) or name
            if col not in df.columns:
                df[col] = ""
            df[col] = df[col].astype(object)
            old = df.loc[mask, col].iloc[0]
            old = "" if pd.isna(old) else str(old)
            if old != value:
                changed.append((var_labels.get(name, name), old, value))
            df.loc[mask, col] = value

        for label, old, new in changed:
            self._corrections.append({
                "file": self._cur_stem, "variable": label,
                "old": old or "(blank)", "new": new,
                "when": datetime.now().strftime("%Y-%m-%d %H:%M"),
            })

        corrected_path = self._corrected_path_for(base_path)
        try:
            df.to_csv(corrected_path, index=False)
        except Exception as e:
            QMessageBox.critical(self.main_window, "Save failed", str(e))
            return

        self._df_cache[id(self._entry)] = df
        self._sig = df[df["file"] == self._cur_stem].sort_values("time_s")
        self._has_changes = True
        self._corrected_path = corrected_path
        synced = self._sync_index(
            self._cur_stem, {k: v for k, v in values.items() if v},
            df.loc[mask].iloc[0])
        where = corrected_path.name + (
            f" and {', '.join(lib.name for lib in synced)}'s sensor index"
            if synced else "")
        self.status.emit(f"Correction saved for {self._cur_stem} to {where}",
                         5000)
        self.lbl_detail_status.setText(
            f"Saved to {corrected_path}"
            + (f"\nand the sensor index of {', '.join(str(lib) for lib in synced)}"
               if synced else "\n(no library index lists this recording)"))
        style(self.lbl_detail_status, tone="ok")

    def _index_libraries(self, stem, row):
        """The libraries whose sensor index lists `stem`: the session
        library, then any library with the recording's deployment folder
        (only those indexes are read)."""
        candidates = []
        session = self.main_window.session_state.library
        if session:
            candidates.append(Path(session))
        deployment = row.get(di.DEPLOYMENT_COL) if row is not None else None
        if deployment is not None and not pd.isna(deployment) \
                and str(deployment).strip():
            for lib in settings.list_libraries():
                if lib not in candidates and \
                        (lib / RAW_DIR / str(deployment)).is_dir():
                    candidates.append(lib)
        found = []
        for lib in candidates:
            index_df = di.read_index(lib)
            if index_df is not None and di.FILE_COL in index_df.columns and (
                    index_df[di.FILE_COL].astype(str) == str(stem)).any():
                found.append(lib)
        return found

    def _sync_index(self, stem, values, row):
        """Writes the corrected `values` (variable name -> value) onto the
        recording's row of its library's sensor index. Returns the
        libraries written to."""
        written = []
        for lib in self._index_libraries(stem, row):
            try:
                if di.set_row_values(lib, stem, values):
                    written.append(lib)
            except OSError as e:
                self.status.emit(f"Could not update {lib.name}'s sensor "
                                 f"index: {e}", 8000)
        return written

    # leaving the page (main.py's navigate_to hook)
    def has_changes(self):
        return self._has_changes

    def notify_and_load_into_training(self):
        """Called by MainWindow.navigate_to when the page is left with
        corrections made: tell the user, then load the corrected dataset into
        Model training > Train, where navigate_to goes next."""
        self._has_changes = False
        QMessageBox.information(
            self.main_window, "Retrain recommended",
            "You corrected one or more classifications. Retrain the model "
            "with the corrected dataset before its next deployment.\n\n"
            "The corrected dataset has been loaded on the Train page.")
        if self.training_state is not None and self._corrected_path is not None:
            ok, msg = self.training_state.load_dataset_csv(self._corrected_path)
            self.status.emit(msg, 6000)
