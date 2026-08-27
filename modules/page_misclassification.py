# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Controller for Misclassification analysis (Model training).

Inspect used as the base again: a model picker, a list of the files its
cross-validation got wrong (from the deployment package's
`{kind}_cv_predictions.csv` - `ml_model_library.discover_models()` already
loads these, the same data Evaluate's error-analysis table reads), a signal
plot, and a Labels box reusing `AnnotationValueEditor`/`VariableListDialog`
verbatim from Annotate - the same "pick or add one value for one recording"
shape, not a second implementation.

A correction is written to a `_corrected` copy of the training dataset
sitting beside the original (`<name>_corrected.csv`, first correction
copies the original there) - all of a file's rows in the long-format
dataset share one annotation value per variable, so the write is a masked
update exactly like `deployment_index.set_row_values`. The corrected CSV,
once it exists, is what gets read back on every subsequent visit, so
corrections accumulate across files and sessions.

The training dataset itself isn't shipped with a deployed model - for a
session-trained model it's already in memory (`TrainingState.dataset_df`);
for a deployed one, `train_config.json` in its `BladeStrikeModel_v<v>/`
package records the exact path it was trained from (`ml_train_state.py`'s
`build_config()` writes it, `ml_model_library.export_model_report()`
already copies it into every deployment package).

Leaving the page after making at least one correction (`MainWindow.
navigate_to`, whichever button was actually clicked) is redirected to
Model training > Train with the corrected dataset loaded, after a
notice that the model should be retrained before its next deployment -
`notify_and_load_into_training()` is main.py's hook for this.
"""
from pathlib import Path

import pandas as pd
import pyqtgraph as pg

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QMessageBox, QPushButton, QSizePolicy, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import annotation_schema as asch
from . import ml_model_library
from .annotation_widgets import AnnotationValueEditor, VariableListDialog
from .ml_train_state import DEFAULT_MODELS_DIR
from .ml_widgets import BAD, MUTED, OK, Section, apply_section_defaults
from .page_validate import _NavViewBox
from .plot_style import (
    add_export_button, build_export_data, reserve_top_margin,
    set_right_axis_active,
)

pg.setConfigOptions(antialias=True, background="#21252b",
                    foreground="#c8cdd6")

# StrikeWorks' own annotation_schema names vs. the MVP-legacy names the
# training pipeline still recognises (ml_state.ANNOTATION_COLUMNS,
# ml_train_state.leading_type_column()) - a dataset built either way is
# readable here.
_LEGACY_ALIASES = {
    "overall_passage_type": "passage_type",
    "leading_edge_type": "leading_type",
}


def _resolve_column(df, var_name):
    if var_name in df.columns:
        return var_name
    alias = _LEGACY_ALIASES.get(var_name)
    return alias if alias and alias in df.columns else None


def _misclassified_rows(entry):
    """[{file, true, pred, confidence, treatment}, ...] - mirrors
    ml_model_library.build_model_report_html's exact same read of
    cv_predictions, so the list matches what the report already shows."""
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
                "treatment": r.get("treatment", "—"),
            })
    elif "true_class" in df.columns:                      # multiclass
        bad = df[~df["correct"].astype(bool)]
        for _, r in bad.iterrows():
            rows.append({
                "file": r["file"],
                "true": r["true_class"],
                "pred": r["pred_class"],
                "confidence": float(r["confidence"]),
                "treatment": r.get("treatment", "—"),
            })
    return rows


class MisclassificationPage(QObject):
    """Binds Misclassification analysis to `ui.content_misclassification`."""

    status = Signal(str, int)

    def __init__(self, ui, window, training_state):
        super().__init__(window)
        self.ui = ui
        self.window = window
        self.training_state = training_state

        self._entries = []
        self._entry = None
        self._rows = []
        self._cur_stem = None
        self._df_cache = {}          # id(entry) -> long-format DataFrame
        self._time = None
        self._left_key = None
        self._right_key = None
        self._editors = {}
        self._has_changes = False
        self._corrected_path = None

        self._build(ui.content_misclassification)
        self._connect()
        self._reload_models()

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, frame):
        root = QHBoxLayout(frame)
        root.setContentsMargins(4, 6, 4, 6)
        root.setSpacing(0)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        root.addWidget(split)

        split.addWidget(self._build_browser())

        detail = QWidget()
        dv = QVBoxLayout(detail)
        dv.setContentsMargins(5, 0, 0, 0)
        dv.setSpacing(8)
        self._build_plot_side(dv)
        dv.addWidget(self._build_labels_side())
        split.addWidget(detail)
        split.setSizes([1, 3])

        apply_section_defaults(frame)

    def _build_browser(self):
        left = QWidget()
        left.setMinimumWidth(380)
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
        self.lbl_source.setStyleSheet(f"color:{MUTED};")
        self.lbl_source.setWordWrap(True)
        gv.addWidget(self.lbl_source)
        lv.addWidget(grp)

        self.tbl_misclass = QTableWidget(0, 4)
        self.tbl_misclass.setHorizontalHeaderLabels(
            ["File", "True -> Predicted", "Confidence", "Treatment"])
        self.tbl_misclass.verticalHeader().setVisible(False)
        self.tbl_misclass.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_misclass.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_misclass.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl_misclass.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive)
        self.tbl_misclass.setSortingEnabled(True)
        lv.addWidget(self.tbl_misclass, stretch=1)
        return left

    def _build_plot_side(self, v):
        grp = Section("Signal")
        sv = QVBoxLayout(grp)
        sv.setSpacing(6)

        axis_row = QHBoxLayout()
        self.cmb_left = QComboBox()
        self.cmb_right = QComboBox()
        axis_row.addWidget(self._muted("Left"))
        axis_row.addWidget(self.cmb_left, stretch=1)
        axis_row.addWidget(self._muted("Right"))
        axis_row.addWidget(self.cmb_right, stretch=1)
        axis_row.addStretch()
        add_export_button(axis_row, self._export_data, self.window,
                          file_stub="misclassification")
        sv.addLayout(axis_row)

        self._pw = pg.PlotWidget(viewBox=_NavViewBox())
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
        self.lbl_signal_note.setStyleSheet(f"color:{MUTED};")
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
        self.lbl_detail_status.setStyleSheet(f"color:{MUTED};")
        self.lbl_detail_status.setWordWrap(True)
        gv.addWidget(self.lbl_detail_status)
        return grp

    @staticmethod
    def _muted(text):
        lab = QLabel(text)
        lab.setStyleSheet(f"color:{MUTED};")
        return lab

    def _connect(self):
        self.cmb_model.currentIndexChanged.connect(self._on_model_changed)
        self.btn_refresh.clicked.connect(self._reload_models)
        self.tbl_misclass.itemSelectionChanged.connect(self._on_row_selected)
        self.cmb_left.currentIndexChanged.connect(self._refresh_signal)
        self.cmb_right.currentIndexChanged.connect(self._refresh_signal)
        self.btn_manage_vars.clicked.connect(self._manage_variables)
        self.btn_save_correction.clicked.connect(self._save_correction)
        asch.notifier.changed.connect(self._rebuild_labels)
        self._rebuild_labels()

    # ── models ───────────────────────────────────────────────────────────────
    def _reload_models(self):
        keep = self.cmb_model.currentText()
        self._entries = []
        if self.training_state is not None:
            self._entries += ml_model_library.session_entries(self.training_state)
        self._entries += ml_model_library.discover_models(DEFAULT_MODELS_DIR)

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
        self.tbl_misclass.setSortingEnabled(False)
        self.tbl_misclass.setRowCount(0)
        self._rows = []
        self._clear_signal()

        if self._entry is None:
            self.lbl_source.setText(f"No models found.")
            self.tbl_misclass.setSortingEnabled(True)
            return

        self._rows = _misclassified_rows(self._entry)
        self.lbl_source.setText(
            f"{self._entry.label} - {len(self._rows)} misclassified "
            f"recording(s).")

        self.tbl_misclass.setRowCount(len(self._rows))
        for r, row in enumerate(self._rows):
            item_file = QTableWidgetItem(str(row["file"]))
            item_file.setData(Qt.ItemDataRole.UserRole, row["file"])
            self.tbl_misclass.setItem(r, 0, item_file)
            self.tbl_misclass.setItem(
                r, 1, QTableWidgetItem(f'{row["true"]} -> {row["pred"]}'))
            conf_item = QTableWidgetItem(f'{row["confidence"]:.3f}')
            conf_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tbl_misclass.setItem(r, 2, conf_item)
            self.tbl_misclass.setItem(
                r, 3, QTableWidgetItem(str(row["treatment"])))
        self.tbl_misclass.resizeColumnsToContents()
        self.tbl_misclass.setSortingEnabled(True)

    # ── dataset access ───────────────────────────────────────────────────────
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
                except Exception:
                    df = None
            elif entry.source == "session" and self.training_state is not None:
                df = self.training_state.dataset_df
            elif base_path.exists():
                try:
                    df = pd.read_csv(base_path, low_memory=False)
                except Exception:
                    df = None
        self._df_cache[key] = df
        return df

    # ── selection / signal ──────────────────────────────────────────────────
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

        self._rebuild_channel_combos(sig)
        self._time = sig["time_s"].to_numpy(dtype=float)
        self._sig = sig
        self._refresh_signal()
        self.lbl_signal_note.setText(
            "Drag to box-zoom, wheel to pan, Shift+wheel to pan vertically.")
        self.btn_save_correction.setEnabled(True)
        self._load_labels_for_current(sig.iloc[0])

    def _rebuild_channel_combos(self, sig):
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
                self._time, y, pen=pg.mkPen("#dddddd", width=1))
            self._curve.setDownsampling(auto=True, method="peak")
            self._curve.setClipToView(True)
            pi.setLabel("left", self._left_key)

        if self._right_key and self._right_key in sig.columns:
            set_right_axis_active(pi, True)
            pi.setLabel("right", self._right_key)
            self._right_curve = pg.PlotCurveItem(
                pen=pg.mkPen("#ff5555", width=1))
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
        (x0, x1), _ = self._pw.plotItem.vb.viewRange()
        left_y = (self._sig[self._left_key].to_numpy(dtype=float)
                  if self._left_key and self._left_key in self._sig.columns
                  else None)
        right_y = (self._sig[self._right_key].to_numpy(dtype=float)
                   if self._right_key and self._right_key in self._sig.columns
                   else None)
        return build_export_data(
            self._time, self._left_key or "", left_y,
            self._right_key or "", right_y, (x0, x1))

    # ── labels ───────────────────────────────────────────────────────────────
    def _rebuild_labels(self):
        while self.annotation_grid.count():
            item = self.annotation_grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._editors = {}
        for row, var in enumerate(asch.all_variables()):
            lab = self._muted(var.label)
            editor = AnnotationValueEditor(var.name)
            self.annotation_grid.addWidget(lab, row, 0)
            self.annotation_grid.addWidget(editor, row, 1)
            self._editors[var.name] = editor
        if self._cur_stem and hasattr(self, "_sig") and len(self._sig):
            self._load_labels_for_current(self._sig.iloc[0])

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
        dlg = VariableListDialog(self.window)
        dlg.exec()

    # ── save ─────────────────────────────────────────────────────────────────
    def _save_correction(self):
        if self._cur_stem is None or self._entry is None:
            return
        base_path = self._resolve_dataset_path(self._entry)
        if base_path is None:
            QMessageBox.warning(
                self.window, "No dataset",
                "Can't locate this model's training dataset on disk.")
            return

        df = self._df_cache.get(id(self._entry))
        if df is None:
            QMessageBox.warning(self.window, "No dataset",
                                "Training dataset not loaded.")
            return

        mask = df["file"] == self._cur_stem
        if not mask.any():
            QMessageBox.warning(
                self.window, "Not found",
                f"{self._cur_stem} not found in the training dataset.")
            return

        values = {name: editor.current() for name, editor in
                  self._editors.items()}
        if not any(values.values()):
            QMessageBox.warning(
                self.window, "Nothing entered",
                "Enter at least one corrected value before saving.")
            return

        for name, value in values.items():
            if not value:
                continue
            col = _resolve_column(df, name) or name
            if col not in df.columns:
                df[col] = ""
            df[col] = df[col].astype(object)
            df.loc[mask, col] = value

        corrected_path = self._corrected_path_for(base_path)
        try:
            df.to_csv(corrected_path, index=False)
        except Exception as e:
            QMessageBox.critical(self.window, "Save failed", str(e))
            return

        self._df_cache[id(self._entry)] = df
        self._sig = df[df["file"] == self._cur_stem].sort_values("time_s")
        self._has_changes = True
        self._corrected_path = corrected_path
        self.status.emit(
            f"Correction saved for {self._cur_stem} to "
            f"{corrected_path.name}", 5000)
        self.lbl_detail_status.setText(f"Saved to {corrected_path}")
        self.lbl_detail_status.setStyleSheet(f"color:{OK};")

    # ── leaving the page (main.py's navigate_to hook) ───────────────────────
    def has_changes(self):
        return self._has_changes

    def notify_and_load_into_training(self):
        """Called by MainWindow.navigate_to when the user leaves this page
        having made at least one correction: notify, then load the
        corrected dataset into Model training > Train so the redirect
        `navigate_to` performs next lands on it already in place."""
        self._has_changes = False
        QMessageBox.information(
            self.window, "Retrain recommended",
            "You corrected one or more classifications. Retrain the model "
            "with the corrected dataset before its next deployment.\n\n"
            "The corrected dataset has been loaded on the Train page.")
        if self.training_state is not None and self._corrected_path is not None:
            ok, msg = self.training_state.load_dataset_csv(self._corrected_path)
            self.status.emit(msg, 6000)
