# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Train tab - everything that defines and runs a training run, in four
rows:

  Training dataset   loading (or binding several), its summary card and a
                     file-level preview.
  Labelling          the target variable, its null (0) and positive (1)
                     values - each of the target's values coded 0, 1 or
                     excluded - the multiclass class variable and its
                     grouping, the class distributions and the performance
                     breakdown.
  Inputs | Cross-validation
                     input channels and sequence preparation; validation
                     (hold-out + stratified CV) and class weights.
  Model              configuration, Train model (+ Console - the training
                     worker's output goes to the app console), the
                     out-of-fold performance of both pipeline stages, and
                     the final model and deployment
                     (ml_tab_train_deploy.py).

All configuration and results live in the shared TrainingState; Evaluate
and the deployment consume them unchanged.
"""
from pathlib import Path

import pandas as pd

from PySide6.QtCore import Qt, QElapsedTimer, QTimer
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QProgressBar,
    QPushButton, QRadioButton, QSizePolicy, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import settings
from .bind_datasets import BindTrainingData
from .cards import MetaCard, Spinner
from .layout import hsplit, scroll_page, Section
from .ml_tab_train_deploy import (
    FIELD_W, DeploymentPanel, action_button, column,
)
from .level_grouper import LevelGrouper
from .theme import EMPTY, MUTED, PALETTE, TEXT, muted_label, style

_PREVIEW_ROWS = 200
COMBO_W = 220                    # the Labelling and settings dropdowns

# a target value's coding in the binary model
_NULL, _POSITIVE, _EXCLUDE = "null", "positive", "exclude"


class _ClassDist(QWidget):
    """Class-distribution rows: label, count, percentage and a bar."""

    ROW_H = 20
    LAB_W = 170
    NUM_W = 90

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []
        self.setMinimumHeight(self.ROW_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)

    def set_counts(self, counts):
        """counts: [(label, n)]"""
        self._rows = list(counts)
        self.setFixedHeight(max(1, len(self._rows)) * self.ROW_H)
        self.update()

    def paintEvent(self, _event):
        if not self._rows:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        total = sum(n for _, n in self._rows) or 1
        bar_w = max(30, self.width() - self.LAB_W - self.NUM_W - 12)
        p.setFont(QFont("Segoe UI", 8))
        for i, (label, n) in enumerate(self._rows):
            y = i * self.ROW_H
            frac = n / total
            p.setPen(QColor(TEXT))
            p.drawText(0, y, self.LAB_W, self.ROW_H,
                       Qt.AlignmentFlag.AlignVCenter, str(label))
            p.setPen(QColor(MUTED))
            p.drawText(self.LAB_W, y, self.NUM_W, self.ROW_H,
                       Qt.AlignmentFlag.AlignVCenter,
                       f"{n}   {frac * 100:.1f}%")
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(EMPTY))
            p.drawRoundedRect(self.LAB_W + self.NUM_W, y + 5, bar_w,
                              self.ROW_H - 10, 3, 3)
            fill = int(bar_w * frac)
            if fill > 0:
                p.setBrush(QColor(PALETTE[i % len(PALETTE)]))
                p.drawRoundedRect(self.LAB_W + self.NUM_W, y + 5, fill,
                                  self.ROW_H - 10, 3, 3)
        p.end()


def _spin(lo, hi, value, step=None):
    box = QSpinBox()
    box.setRange(lo, hi)
    box.setValue(value)
    if step:
        box.setSingleStep(step)
    box.setFixedWidth(FIELD_W)
    return box


def _combo(*items):
    """A fixed-width dropdown of (text, data) or plain-text items."""
    box = QComboBox()
    box.setFixedWidth(COMBO_W)
    for item in items:
        text, data = item if isinstance(item, tuple) else (item, None)
        box.addItem(text, data)
    return box


class TrainTab(QWidget):
    """The Train tab, bound to `state`."""

    def __init__(self, state, main_window, goto_evaluate=None):
        super().__init__()
        self.state = state
        self.main_window = main_window
        self._goto_evaluate = goto_evaluate
        self._updating = False
        self._value_combos = {}          # target value -> its coding combo
        self._channel_checks = {}
        self._breakdown_checks = {}

        self._elapsed = QElapsedTimer()
        self._tick = QTimer()
        self._tick.setInterval(500)
        self._tick.timeout.connect(self._update_elapsed)

        self._build(self)
        self._connect_state()
        self._rebuild_dataset_widgets()
        self._refresh_all()

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, frame):
        v = scroll_page(frame)
        v.addWidget(self._dataset_section())
        v.addWidget(self._labelling_section())
        v.addWidget(hsplit(self._inputs_section(), self._cv_section()))
        v.addWidget(self._model_section())
        v.addStretch()

    def _dataset_section(self):
        """Loading and binding beside a file-level preview."""
        grp = Section("Training dataset")
        row = QHBoxLayout(grp)
        row.setSpacing(16)

        left = QVBoxLayout()
        left.setSpacing(8)
        btn_row = QHBoxLayout()
        self.btn_load = QPushButton("Load training dataset…")
        self.btn_load.clicked.connect(self._load_dataset)
        self.cmb_recent = QComboBox()
        self.cmb_recent.setToolTip("Recently used training datasets")
        self.cmb_recent.activated.connect(self._recent_chosen)
        btn_row.addWidget(self.btn_load)
        btn_row.addWidget(self.cmb_recent, stretch=1)
        left.addLayout(btn_row)
        self.card_dataset = MetaCard("Training dataset")
        left.addWidget(self.card_dataset)
        self.lbl_compat = QLabel("")
        style(self.lbl_compat, tone="ok")
        left.addWidget(self.lbl_compat)
        # several datasets stacked into one - loaded straight away
        self.bind_widget = BindTrainingData()
        self.bind_widget.bound.connect(self._load_path)
        left.addWidget(self.bind_widget)
        left.addStretch()
        row.addLayout(left, stretch=2)

        right = QVBoxLayout()
        right.setSpacing(4)
        right.addWidget(muted_label("Preview (file-level metadata)"))
        self.tbl_preview = QTableWidget(0, 0)
        self.tbl_preview.verticalHeader().setVisible(False)
        self.tbl_preview.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_preview.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_preview.horizontalHeader().setStretchLastSection(True)
        self.tbl_preview.setMinimumHeight(180)
        right.addWidget(self.tbl_preview, stretch=1)
        row.addLayout(right, stretch=3)
        return grp

    def _labelling_section(self):
        """The binary target and its values' coding, the multiclass class
        variable and grouping, then the class distributions and the
        performance breakdown."""
        grp = Section("Labelling")
        tv = QVBoxLayout(grp)
        tv.setSpacing(10)
        top = QHBoxLayout()
        top.setSpacing(24)

        # ── binary: target, null (0) and positive (1) ──────────────────────
        binary, bv = column("Binary model")
        tr = QGridLayout()
        tr.setVerticalSpacing(6)
        tr.setHorizontalSpacing(10)
        tr.addWidget(muted_label("Target variable"), 0, 0)
        self.cmb_target = _combo()
        self.cmb_target.currentIndexChanged.connect(self._target_changed)
        tr.addWidget(self.cmb_target, 0, 1)
        tr.addWidget(muted_label("Null value (0)"), 1, 0)
        self.cmb_negative = _combo()
        self.cmb_negative.setToolTip(
            "The target value coded 0 - every other included value is 1.")
        self.cmb_negative.currentIndexChanged.connect(self._negative_changed)
        tr.addWidget(self.cmb_negative, 1, 1)
        tr.addWidget(muted_label("Positive value (1)"), 2, 0)
        self.ed_positive = QLineEdit()
        self.ed_positive.setFixedWidth(COMBO_W)
        self.ed_positive.setPlaceholderText("blade_strike")
        self.ed_positive.setToolTip(
            "The name of the derived 0/1 variable's 1 - the model's "
            "positive class.")
        self.ed_positive.editingFinished.connect(self._positive_changed)
        tr.addWidget(self.ed_positive, 2, 1)
        tr.setColumnStretch(2, 1)
        bv.addLayout(tr)
        self.lbl_positive = QLabel("")
        style(self.lbl_positive, role="muted")
        self.lbl_positive.setWordWrap(True)
        bv.addWidget(self.lbl_positive)
        bv.addStretch()
        top.addWidget(binary, stretch=3)

        # ── each target value coded 0, 1 or excluded ───────────────────────
        values, vv = column("Values")
        self.lbl_values = vv.itemAt(0).widget()
        self.values_grid = QGridLayout()
        self.values_grid.setHorizontalSpacing(12)
        self.values_grid.setVerticalSpacing(4)
        vv.addLayout(self.values_grid)
        self.lbl_population = QLabel("")
        vv.addWidget(self.lbl_population)
        vv.addStretch()
        top.addWidget(values, stretch=3)

        # ── multiclass: class variable and its grouping ────────────────────
        multi, mv = column("Multiclass model")
        self.chk_multiclass = QCheckBox("Train a multiclass model")
        self.chk_multiclass.toggled.connect(self._mc_toggled)
        mv.addWidget(self.chk_multiclass)
        cls_row = QHBoxLayout()
        cls_row.setSpacing(10)
        self.lbl_class_col = muted_label("Class variable")
        self.cmb_class_col = _combo()
        self.cmb_class_col.currentIndexChanged.connect(self._class_col_changed)
        cls_row.addWidget(self.lbl_class_col)
        cls_row.addWidget(self.cmb_class_col)
        cls_row.addStretch()
        mv.addLayout(cls_row)
        # level -> class grouping, driven by the levels actually in the
        # data: each level starts as its own class, the user groups and
        # names them
        self.grouper = LevelGrouper()
        self.grouper.changed.connect(self._groups_changed)
        mv.addWidget(self.grouper)
        mv.addStretch()
        top.addWidget(multi, stretch=4)
        tv.addLayout(top)

        # ── class distributions, side by side ──────────────────────────────
        dist = QHBoxLayout()
        dist.setSpacing(24)
        bin_dist = QVBoxLayout()
        bin_dist.setSpacing(4)
        self.lbl_dist_bin = muted_label("Binary class distribution")
        bin_dist.addWidget(self.lbl_dist_bin)
        self.class_dist = _ClassDist()
        bin_dist.addWidget(self.class_dist)
        bin_dist.addStretch()
        dist.addLayout(bin_dist, stretch=1)
        mc_dist = QVBoxLayout()
        mc_dist.setSpacing(4)
        self.lbl_dist_mc = muted_label("Multiclass class distribution")
        mc_dist.addWidget(self.lbl_dist_mc)
        self.class_dist_mc = _ClassDist()
        mc_dist.addWidget(self.class_dist_mc)
        mc_dist.addStretch()
        dist.addLayout(mc_dist, stretch=1)
        tv.addLayout(dist)

        # the columns each strike's type is read from, for the performance
        # breakdown (direct, indirect, hub_0, ... - train_worker.
        # derive_strike_type)
        tv.addWidget(muted_label("Break down performance by"))
        self.breakdown_box = QHBoxLayout()
        self.breakdown_box.setSpacing(12)
        tv.addLayout(self.breakdown_box)
        self.lbl_derived = QLabel("")
        style(self.lbl_derived, role="muted")
        self.lbl_derived.setWordWrap(True)
        tv.addWidget(self.lbl_derived)
        return grp

    def _inputs_section(self):
        """Input channels and sequence preparation."""
        grp = Section("Inputs")
        iv = QVBoxLayout(grp)
        iv.setSpacing(8)
        iv.addWidget(muted_label("Channels"))
        self.chan_grid = QGridLayout()
        self.chan_grid.setHorizontalSpacing(16)
        self.chan_grid.setVerticalSpacing(2)
        iv.addLayout(self.chan_grid)

        sv = QGridLayout()
        sv.setVerticalSpacing(6)
        sv.setHorizontalSpacing(10)
        sv.addWidget(muted_label("Sequence length"), 0, 0)
        self.rb_seq_auto = QRadioButton("From the dataset")
        self.rb_seq_manual = QRadioButton("Specify")
        self.rb_seq_auto.setChecked(True)
        self.rb_seq_auto.toggled.connect(self._seq_changed)
        self.spin_seq = _spin(10, 100000, 400)
        self.spin_seq.setEnabled(False)
        self.spin_seq.valueChanged.connect(self._seq_changed)
        sv.addWidget(self.rb_seq_auto, 0, 1)
        seq_row = QHBoxLayout()
        seq_row.setSpacing(8)
        seq_row.addWidget(self.rb_seq_manual)
        seq_row.addWidget(self.spin_seq)
        seq_row.addStretch()
        sv.addLayout(seq_row, 1, 1)
        sv.addWidget(muted_label("Padding"), 2, 0)
        self.cmb_padding = _combo(("Repeat final observation", "repeat_last"))
        sv.addWidget(self.cmb_padding, 2, 1)
        sv.addWidget(muted_label("Truncation"), 3, 0)
        self.cmb_trunc = _combo(("Truncate to target length", "truncate"))
        sv.addWidget(self.cmb_trunc, 3, 1)
        sv.setColumnStretch(2, 1)
        iv.addLayout(sv)
        self.lbl_tensor = QLabel("")
        iv.addWidget(self.lbl_tensor)
        iv.addStretch()
        return grp

    def _cv_section(self):
        """Validation and class weights."""
        grp = Section("Cross-validation")
        vv = QGridLayout(grp)
        vv.setVerticalSpacing(6)
        vv.setHorizontalSpacing(10)
        self.rb_cv_only = QRadioButton("Cross-validation only")
        self.rb_holdout = QRadioButton("Train / test + cross-validation")
        self.rb_cv_only.setChecked(True)
        self.rb_cv_only.toggled.connect(self._val_changed)
        vv.addWidget(self.rb_cv_only, 0, 0, 1, 2)
        vv.addWidget(self.rb_holdout, 1, 0, 1, 2)
        vv.addWidget(muted_label("Test set"), 2, 0)
        self.spin_test = QDoubleSpinBox()
        self.spin_test.setRange(0.05, 0.5)
        self.spin_test.setSingleStep(0.05)
        self.spin_test.setDecimals(2)
        self.spin_test.setValue(0.20)
        self.spin_test.setFixedWidth(FIELD_W)
        self.spin_test.setEnabled(False)
        self.spin_test.valueChanged.connect(self._val_changed)
        vv.addWidget(self.spin_test, 2, 1)
        vv.addWidget(muted_label("CV method"), 3, 0)
        vv.addWidget(_combo("Stratified K-Fold"), 3, 1)
        vv.addWidget(muted_label("Number of folds"), 4, 0)
        self.spin_folds = _spin(2, 20, 10)
        self.spin_folds.valueChanged.connect(self._val_changed)
        vv.addWidget(self.spin_folds, 4, 1)
        self.chk_shuffle = QCheckBox("Shuffle")
        self.chk_shuffle.setChecked(True)
        self.chk_shuffle.toggled.connect(self._val_changed)
        vv.addWidget(self.chk_shuffle, 5, 0)
        seed_row = QHBoxLayout()
        seed_row.setSpacing(8)
        seed_row.addWidget(muted_label("Random seed"))
        self.spin_seed = _spin(0, 999999, 42)
        self.spin_seed.valueChanged.connect(self._val_changed)
        seed_row.addWidget(self.spin_seed)
        seed_row.addStretch()
        vv.addLayout(seed_row, 5, 1)

        vv.addWidget(muted_label("Class weights"), 6, 0)
        self.rb_w_none = QRadioButton("None")
        self.rb_w_balanced = QRadioButton("Balanced")
        self.rb_w_balanced.setToolTip("Minority-class observations are "
                                      "weighted up.")
        self.rb_w_balanced.setChecked(True)
        self.rb_w_balanced.toggled.connect(self._weight_changed)
        w_row = QHBoxLayout()
        w_row.setSpacing(12)
        w_row.addWidget(self.rb_w_balanced)
        w_row.addWidget(self.rb_w_none)
        w_row.addStretch()
        vv.addLayout(w_row, 6, 1)
        self.lbl_weights = QLabel("")
        style(self.lbl_weights, role="muted")
        vv.addWidget(self.lbl_weights, 7, 1)
        vv.setColumnStretch(2, 1)
        vv.setRowStretch(8, 1)
        return grp

    def _model_section(self):
        """Configuration, then the workflow left to right: train
        (cross-validation), final model, deploy."""
        grp = Section("Model")
        row = QHBoxLayout(grp)
        row.setSpacing(24)

        # ── configuration ──────────────────────────────────────────────────
        config, cv = column("Configuration")
        mv = QGridLayout()
        mv.setVerticalSpacing(6)
        mv.setHorizontalSpacing(10)
        mv.addWidget(muted_label("Architecture"), 0, 0)
        arch = QComboBox()
        arch.addItem("MiniRocket + RidgeClassifierCV")
        arch.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        mv.addWidget(arch, 0, 1, 1, 3)
        mv.addWidget(muted_label("MiniRocket seed"), 1, 0)
        self.spin_mr_seed = _spin(0, 999999, 42)
        self.spin_mr_seed.valueChanged.connect(self._model_changed)
        mv.addWidget(self.spin_mr_seed, 1, 1)
        mv.addWidget(muted_label("n_jobs"), 2, 0)
        self.spin_njobs = _spin(-1, 64, -1)
        self.spin_njobs.valueChanged.connect(self._model_changed)
        mv.addWidget(self.spin_njobs, 2, 1)
        mv.addWidget(muted_label("Ridge alphas 10^"), 3, 0)
        self.spin_a_min = _spin(-8, 0, -3)
        self.spin_a_min.valueChanged.connect(self._model_changed)
        mv.addWidget(self.spin_a_min, 3, 1)
        mv.addWidget(muted_label("to"), 3, 2)
        self.spin_a_max = _spin(0, 8, 3)
        self.spin_a_max.valueChanged.connect(self._model_changed)
        mv.addWidget(self.spin_a_max, 3, 3)
        mv.addWidget(muted_label("Alpha values"), 4, 0)
        self.spin_n_alpha = _spin(5, 500, 100)
        self.spin_n_alpha.valueChanged.connect(self._model_changed)
        mv.addWidget(self.spin_n_alpha, 4, 1)
        mv.setColumnStretch(4, 1)
        cv.addLayout(mv)
        cv.addStretch()
        row.addWidget(config, stretch=1)

        # ── train: cross-validation, its progress and results ──────────────
        train, gv = column("Train")
        run_row = QHBoxLayout()
        run_row.setSpacing(8)
        self.btn_train = action_button("Train model")
        self.btn_train.setEnabled(False)
        self.btn_train.clicked.connect(self.state.run_cv)
        # the worker's output goes to the app console (it tees print)
        self.btn_console = action_button(
            "Console", "Everything the app prints - the training run's "
            "progress included.")
        self.btn_console.clicked.connect(self._open_console)
        self.spinner = Spinner(size=24)
        self.spinner.setVisible(False)
        run_row.addWidget(self.btn_train)
        run_row.addWidget(self.btn_console)
        run_row.addWidget(self.spinner)
        run_row.addStretch()
        gv.addLayout(run_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("%v/%m folds")
        self.progress.setVisible(False)
        gv.addWidget(self.progress)

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        style(self.lbl_status, role="muted")
        gv.addWidget(self.lbl_status)

        self.card_bin = MetaCard("Binary OOF")
        gv.addWidget(self.card_bin)
        self.card_mc = MetaCard("Multiclass OOF")
        self.card_mc.setVisible(False)
        gv.addWidget(self.card_mc)

        self.btn_evaluate = action_button("Evaluate results")
        self.btn_evaluate.setVisible(False)
        self.btn_evaluate.clicked.connect(
            lambda: self._goto_evaluate() if self._goto_evaluate else None)
        gv.addWidget(self.btn_evaluate)
        gv.addStretch()
        row.addWidget(train, stretch=1)

        # accept the run: train the final model and deploy it
        self.deployment = DeploymentPanel(self.state, self.main_window)
        row.addWidget(self.deployment, stretch=2)
        return grp

    def _open_console(self):
        console = getattr(self.main_window, "dev_console", None)
        if console is not None:
            console.bring_up()

    # ── state wiring ─────────────────────────────────────────────────────────
    def _connect_state(self):
        s = self.state
        s.dataset_changed.connect(self._rebuild_dataset_widgets)
        s.config_changed.connect(self._refresh_all)
        s.validation_changed.connect(self._refresh_ready)
        s.cv_started.connect(self._on_started)
        s.cv_progress.connect(self._on_progress)
        s.cv_finished.connect(self._on_finished)
        s.cv_failed.connect(self._on_failed)
        s.final_started.connect(self._on_final_started)
        s.final_finished.connect(self._stop_run_ui)
        s.final_failed.connect(lambda _m: self._stop_run_ui())

    # ── dataset loading ──────────────────────────────────────────────────────
    def _load_dataset(self):
        path, _ = QFileDialog.getOpenFileName(
            self.main_window, "Load training dataset",
            str(settings.get_input_data_dir()),
            "CSV files (*.csv)")
        if path:
            self._load_path(path)

    def _recent_chosen(self, idx):
        path = self.cmb_recent.itemData(idx)
        if path:
            self._load_path(path)

    def _load_path(self, path):
        ok, msg = self.state.load_dataset_csv(path)
        self.state.status.emit(msg, 6000)
        if not ok:
            QMessageBox.warning(self.main_window, "Training dataset", msg)

    # ── dynamic widget sets (rebuilt on dataset change) ──────────────────────
    def _rebuild_dataset_widgets(self):
        s = self.state
        self._updating = True
        try:
            self.cmb_recent.clear()
            self.cmb_recent.addItem("Recently used…", None)
            for p in settings.get_recent_training_datasets():
                self.cmb_recent.addItem(Path(p).name, p)

            self.cmb_target.clear()
            for c in s.target_candidates():
                self.cmb_target.addItem(c, c)
            if s.target_column:
                idx = self.cmb_target.findData(s.target_column)
                if idx >= 0:
                    self.cmb_target.setCurrentIndex(idx)

            self._rebuild_negative_combo()
            self._rebuild_value_rows()
            self._rebuild_breakdown_checks()
            self._rebuild_channel_checks()
            self._fill_preview()
        finally:
            self._updating = False
        self._refresh_all()

    def _rebuild_negative_combo(self):
        s = self.state
        self.cmb_negative.clear()
        # nothing chosen until the user (or the settings' default) picks one
        self.cmb_negative.addItem("Choose…", None)
        for val in s.target_values():
            self.cmb_negative.addItem(val, val)
        if s.negative_class is not None:
            idx = self.cmb_negative.findData(str(s.negative_class))
            if idx >= 0:
                self.cmb_negative.setCurrentIndex(idx)

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.deleteLater()

    def _rebuild_breakdown_checks(self):
        s = self.state
        self._clear_layout(self.breakdown_box)
        self._breakdown_checks = {}
        for col in s.breakdown_candidates():
            chk = QCheckBox(col)
            chk.setChecked(col in s.breakdown_columns)
            chk.toggled.connect(self._breakdown_changed)
            self.breakdown_box.addWidget(chk)
            self._breakdown_checks[col] = chk
        self.breakdown_box.addStretch()

    def _rebuild_value_rows(self):
        """One row per value of the target: the value, its recordings and
        its coding - 0 (null), 1 (positive) or excluded from training -
        which is how the derived 0/1 variable is built from the target.
        Rows only change with the target; `_sync_value_rows` keeps their
        codings in step with the state."""
        s = self.state
        self._clear_layout(self.values_grid)
        self._value_combos = {}
        df = s.dataset_df
        self.lbl_values.setText(f"Values of {s.target_column}"
                                if s.target_column else "Values")
        if df is None or not s.target_column:
            return
        counts = (df.groupby("file")[s.target_column].first()
                  .dropna().astype(str).value_counts())
        for r, (val, n) in enumerate(counts.items()):
            self.values_grid.addWidget(QLabel(val), r, 0)
            self.values_grid.addWidget(muted_label(f"n = {int(n)}"), r, 1)
            cmb = QComboBox()
            cmb.addItem("0  (null)", _NULL)
            cmb.addItem("1", _POSITIVE)
            cmb.addItem("Exclude", _EXCLUDE)
            cmb.setFixedWidth(COMBO_W - 40)
            cmb.currentIndexChanged.connect(
                lambda _i, value=val: self._value_coding_changed(value))
            self.values_grid.addWidget(cmb, r, 2)
            self._value_combos[val] = cmb
        self.values_grid.setColumnStretch(3, 1)

    def _sync_value_rows(self):
        s = self.state
        pos = s.positive_label or "blade_strike"
        included = (None if s.include_values is None
                    else {str(v) for v in s.include_values})
        neg = None if s.negative_class is None else str(s.negative_class)
        for value, cmb in self._value_combos.items():
            if included is not None and value not in included:
                coding = _EXCLUDE
            elif value == neg:
                coding = _NULL
            else:
                coding = _POSITIVE
            cmb.blockSignals(True)
            cmb.setItemText(1, f"1  ({pos})")
            cmb.setCurrentIndex(cmb.findData(coding))
            cmb.blockSignals(False)

    def _rebuild_channel_checks(self):
        s = self.state
        self._clear_layout(self.chan_grid)
        self._channel_checks = {}
        for i, chan in enumerate(s.channel_candidates()):
            chk = QCheckBox(chan)
            chk.setChecked(chan in s.channels)
            chk.toggled.connect(self._channels_changed)
            self.chan_grid.addWidget(chk, i // 2, i % 2)
            self._channel_checks[chan] = chk

    def _fill_preview(self):
        s = self.state
        df = s.dataset_df
        self.tbl_preview.setRowCount(0)
        self.tbl_preview.setColumnCount(0)
        if df is None:
            return
        cols = ["file"]
        for c in (["treatment", s.target_column] + list(s.breakdown_columns)
                  + [s.region_column]):
            if c and c in df.columns and c not in cols:
                cols.append(c)
        per_file = df.groupby("file").first().reset_index()
        per_file = per_file[cols].head(_PREVIEW_ROWS)
        self.tbl_preview.setColumnCount(len(cols))
        self.tbl_preview.setHorizontalHeaderLabels(cols)
        self.tbl_preview.setRowCount(len(per_file))
        for r, (_, row) in enumerate(per_file.iterrows()):
            for c, col in enumerate(cols):
                val = row[col]
                text = "-" if pd.isna(val) else str(val)
                self.tbl_preview.setItem(r, c, QTableWidgetItem(text))

    # ── widget -> state ──────────────────────────────────────────────────────
    def _target_changed(self):
        if self._updating:
            return
        col = self.cmb_target.currentData()
        if col:
            self.state.update(target_column=col)
            self._updating = True
            try:
                self._rebuild_negative_combo()
                self._rebuild_value_rows()
                self._rebuild_breakdown_checks()
                self._fill_preview()
            finally:
                self._updating = False
            self._refresh_all()

    def _mc_toggled(self, checked):
        if self._updating:
            return
        self.state.update(train_multiclass=checked)

    def _included(self):
        """The included target values, as a set (every value when the
        state's filter is None)."""
        s = self.state
        return (set(self._value_combos) if s.include_values is None
                else {str(v) for v in s.include_values})

    def _include_kw(self, included):
        return {"include_values": None if included == set(self._value_combos)
                else included}

    def _negative_changed(self):
        if self._updating:
            return
        value = self.cmb_negative.currentData()
        kw = {"negative_class": value}
        if value is not None and value not in self._included():
            # the null value is always part of the training population
            kw.update(self._include_kw(self._included() | {value}))
        self.state.update(**kw)

    def _value_coding_changed(self, value):
        """A value's row was set to 0, 1 or Exclude: the null value and the
        included values follow."""
        if self._updating:
            return
        coding = self._value_combos[value].currentData()
        s = self.state
        neg = None if s.negative_class is None else str(s.negative_class)
        included = self._included()
        kw = {}
        if coding == _EXCLUDE:
            included.discard(value)
        else:
            included.add(value)
        if coding == _NULL:
            kw["negative_class"] = value
        elif value == neg:
            kw["negative_class"] = None          # no null value until one is chosen
        kw.update(self._include_kw(included))
        s.update(**kw)

    def _positive_changed(self):
        if self._updating:
            return
        name = self.ed_positive.text().strip() or "blade_strike"
        if name != self.state.positive_label:
            self.state.update(positive_label=name)

    def _class_col_changed(self):
        if self._updating:
            return
        self.state.update(region_column=self.cmb_class_col.currentData())

    def _groups_changed(self):
        """The user edited the grouping."""
        if self._updating:
            return
        self.state.region_groups = self.grouper.groups()
        self.state.config_changed.emit()
        self.state.validate()

    def _breakdown_changed(self):
        if self._updating:
            return
        self.state.update(breakdown_columns=[
            c for c, chk in self._breakdown_checks.items() if chk.isChecked()])
        self._fill_preview()

    def _channels_changed(self):
        if self._updating:
            return
        chans = [c for c, chk in self._channel_checks.items()
                 if chk.isChecked()]
        self.state.update(channels=chans)

    def _seq_changed(self):
        if self._updating:
            return
        self.spin_seq.setEnabled(self.rb_seq_manual.isChecked())
        self.state.update(seq_auto=self.rb_seq_auto.isChecked(),
                          seq_length=self.spin_seq.value())

    def _val_changed(self):
        if self._updating:
            return
        self.spin_test.setEnabled(self.rb_holdout.isChecked())
        self.state.update(
            split_mode="holdout_cv" if self.rb_holdout.isChecked()
            else "cv_only",
            test_size=self.spin_test.value(),
            n_folds=self.spin_folds.value(),
            shuffle=self.chk_shuffle.isChecked(),
            random_seed=self.spin_seed.value())

    def _weight_changed(self):
        if self._updating:
            return
        self.state.update(
            class_weighting="balanced" if self.rb_w_balanced.isChecked()
            else "none")

    def _model_changed(self):
        if self._updating:
            return
        self.state.update(
            mr_seed=self.spin_mr_seed.value(),
            mr_n_jobs=self.spin_njobs.value(),
            alpha_min_exp=self.spin_a_min.value(),
            alpha_max_exp=self.spin_a_max.value(),
            n_alphas=self.spin_n_alpha.value())

    # ── state -> widgets ─────────────────────────────────────────────────────
    def _refresh_all(self):
        if self._updating:
            return
        self._refresh_dataset_card()
        self._refresh_target()
        self._refresh_inputs()
        self._refresh_weights()
        self._refresh_ready()

    def _refresh_dataset_card(self):
        s = self.state
        m = s.dataset_meta
        if not m:
            self.card_dataset.set_rows([("Dataset", "No dataset loaded")])
            self.lbl_compat.setText("")
            return
        seq = (f"{m['seq_min']}–{m['seq_max']}"
               if m.get("seq_min") != m.get("seq_max")
               else str(m.get("seq_max")))
        self.card_dataset.set_rows([
            ("Dataset",              m.get("name")),
            ("Files", m.get("n_files")),
            ("Unique sensors",       m.get("n_files")),
            ("Channels",             m.get("n_channel_candidates")),
            ("Treatments",           len(m.get("treatments", []))
                                     if m.get("treatments") else None),
            ("Sampling rate",        f"{m['sampling_rate_hz']:,} Hz"
                                     if m.get("sampling_rate_hz") else None),
            ("Sequence range",       seq),
            ("Missing values",       m.get("missing_in_channels")),
        ])
        ok = m.get("missing_in_channels", 0) == 0 and s.target_column
        self.lbl_compat.setText(
            "Dataset ok" if ok
            else "Dataset incorrect")
        style(self.lbl_compat, tone="ok" if ok else "warn")

    def _refresh_target(self):
        s = self.state
        pos = s.positive_label or "blade_strike"
        self._updating = True
        try:
            if not self.ed_positive.hasFocus():
                self.ed_positive.setText(s.positive_label or "")
            idx = (self.cmb_negative.findData(str(s.negative_class))
                   if s.negative_class is not None else 0)
            self.cmb_negative.setCurrentIndex(max(idx, 0))
            self._sync_value_rows()
            # class variable: any per-file column with a few levels
            cands = s.class_column_candidates()
            self.chk_multiclass.setChecked(s.train_multiclass)
            self.chk_multiclass.setEnabled(bool(cands))
            self.chk_multiclass.setToolTip(
                "" if cands else "No column with a few levels to classify by")
            self.cmb_class_col.clear()
            self.cmb_class_col.addItem("Choose…", None)
            for c in cands:
                self.cmb_class_col.addItem(c, c)
            if s.region_column:
                idx = self.cmb_class_col.findData(s.region_column)
                if idx >= 0:
                    self.cmb_class_col.setCurrentIndex(idx)

            for w in (self.lbl_class_col, self.cmb_class_col, self.grouper):
                w.setEnabled(s.train_multiclass)
            self.grouper.set_data(s.region_levels(), s.region_groups)
        finally:
            self._updating = False

        # how the derived 0/1 variable comes from the target
        if s.negative_class is not None and s.target_column:
            excluded = sorted(set(self._value_combos) - self._included())
            txt = (f"{pos} = 1 where {s.target_column} is any other "
                   f"included value, 0 where it is \"{s.negative_class}\"")
            if excluded:
                txt += f"; {', '.join(excluded)} left out"
            self.lbl_positive.setText(txt + ".")
        else:
            self.lbl_positive.setText("")

        derived = [f"{pos} (0/1)"]
        if s.breakdown_columns:
            derived.append("strike_type (each strike's "
                           + " / ".join(s.breakdown_columns) + ")")
        self.lbl_derived.setText("Derived variables: " + ", ".join(derived))

        self.class_dist.set_counts(s.binary_class_counts())
        show_mc = s.train_multiclass and s.region_column is not None
        self.lbl_dist_mc.setVisible(show_mc)
        self.class_dist_mc.setVisible(show_mc)
        self.grouper.setVisible(show_mc)
        if show_mc:
            self.class_dist_mc.set_counts(s.region_class_counts())
        self.lbl_population.setText(f"Training (n) = {s.population_size()}")

    def _refresh_inputs(self):
        s = self.state
        self._updating = True
        try:
            self.rb_seq_auto.setChecked(s.seq_auto)
            self.rb_seq_manual.setChecked(not s.seq_auto)
            self.spin_seq.setEnabled(not s.seq_auto)
            if s.dataset_meta.get("seq_max") and s.seq_auto:
                self.spin_seq.setValue(s.dataset_meta["seq_max"])
        finally:
            self._updating = False
        seq = s.seq_length if not s.seq_auto \
            else s.dataset_meta.get("seq_max", "?")
        self.lbl_tensor.setText(
            f"Input: {s.population_size()} samples × {len(s.channels)} "
            f"channels × {seq} time points")

    def _refresh_weights(self):
        s = self.state
        counts = s.binary_class_counts()
        if not counts:
            self.lbl_weights.setText("")
            return
        if s.class_weighting == "none":
            self.lbl_weights.setText(
                "\n".join(f"{lab}:  1.00" for lab, _ in counts))
            return
        lines = []
        if len(counts) == 2:
            n_neg, n_pos = counts[0][1], counts[1][1]
            w = n_neg / n_pos if n_pos else 1.0
            lines += [f"{counts[0][0]}:  1.00",
                      f"{counts[1][0]}:  {w:.2f}"]
        if s.train_multiclass:
            mc_counts = s.region_class_counts()
            nonzero = [c for _, c in mc_counts if c > 0]
            if nonzero:
                total = sum(nonzero)
                k = len(nonzero)
                lines.append("- region model -")
                lines += [f"{lab}:  {total / (k * c):.2f}" if c
                          else f"{lab}:  -" for lab, c in mc_counts]
        self.lbl_weights.setText("\n".join(lines))

    def _refresh_ready(self):
        """Gate the train button, and surface any blocking problem inline."""
        s = self.state
        self.btn_train.setEnabled(s.ready and not s.running)
        if s.running:
            return
        blockers = [c for c in s.checks if c[0] == "fail"]
        if blockers:
            state, label, detail = blockers[0]
            style(self.lbl_status, tone="bad")
            self.lbl_status.setText(
                f"✗ {label}: {detail}" if detail else f"✗ {label}")
        elif not s.cv_done:
            style(self.lbl_status, role="muted")
            self.lbl_status.setText("")

    # ── run lifecycle ────────────────────────────────────────────────────────
    def _on_started(self):
        self.btn_train.setEnabled(False)
        self.btn_train.setText("Training…")
        self.btn_evaluate.setVisible(False)
        self.card_bin.set_rows([])
        self.card_mc.set_rows([])
        self.card_mc.setVisible(False)
        self.spinner.start()
        self.progress.setVisible(True)
        n_models = 2 if self.state.train_multiclass else 1
        self.progress.setRange(0, max(1, self.state.n_folds * n_models))
        self.progress.setValue(0)
        self._elapsed.start()
        self._tick.start()
        style(self.lbl_status, tone="accent")
        self.lbl_status.setText("Training binary strike model")

    def _on_final_started(self):
        self._elapsed.start()
        self._tick.start()
        style(self.lbl_status, tone="accent")
        self.lbl_status.setText("Training final deployment model")

    def _on_progress(self, fold, total, model):
        n_models = 2 if self.state.train_multiclass else 1
        offset = total if model == "multiclass" else 0
        self.progress.setRange(0, total * n_models)
        self.progress.setValue(offset + fold)
        name = ("multiclass region" if model == "multiclass"
                else "binary strike")
        self.lbl_status.setText(
            f"Training {name} model…  fold {fold}/{total}  "
            f"({self._elapsed.elapsed() // 1000} s elapsed)")

    def _update_elapsed(self):
        if not self.state.running:
            return
        secs = self._elapsed.elapsed() // 1000
        self.lbl_status.setText(
            self.lbl_status.text().split("(")[0].strip()
            + f"  ({secs} s elapsed)")

    def _stop_run_ui(self):
        self._tick.stop()
        self.spinner.stop()
        self.btn_train.setText("Train model")
        self.btn_train.setEnabled(self.state.ready and not self.state.running)

    def _on_finished(self):
        self._stop_run_ui()
        self.progress.setValue(self.progress.maximum())
        s = self.state
        secs = self._elapsed.elapsed() / 1000
        style(self.lbl_status, tone="ok")
        self.lbl_status.setText(f"Cross-validation complete ({secs:.0f} s).")
        self._fill_performance()
        self.btn_evaluate.setVisible(True)
        s.status.emit("Cross-validation complete.", 5000)

    def _on_failed(self, msg):
        self._stop_run_ui()
        self.progress.setVisible(False)
        style(self.lbl_status, tone="bad")
        first = msg.strip().splitlines()[-1] if msg.strip() else "Unknown error"
        self.lbl_status.setText(f"✗ Training failed: {first}")
        dlg = QMessageBox(self.main_window)
        dlg.setWindowTitle("Training error")
        dlg.setIcon(QMessageBox.Icon.Critical)
        dlg.setText("The training worker failed.\n\n"
                    f"{first}\n\nFull details below.")
        dlg.setDetailedText(msg)
        dlg.exec()

    @staticmethod
    def _perf_rows(metrics):
        perf = (metrics or {}).get("out_of_fold_performance", {})
        rows = []
        for key, label in (("roc_auc", "AUC"), ("pr_auc", "PR-AUC"),
                           ("overall_accuracy", "Accuracy"),
                           ("sensitivity", "Sensitivity"),
                           ("specificity", "Specificity"),
                           ("precision", "Precision"),
                           ("macro_precision", "Macro precision"),
                           ("macro_recall", "Macro recall"),
                           ("f1_score", "F1-Score"),
                           ("macro_f1", "Macro F1"),
                           ("mcc", "MCC"),
                           ("optimal_threshold", "Optimal threshold")):
            if key in perf:
                rows.append((label, f"{perf[key]:.3f}"))
        ho = (metrics or {}).get("holdout_performance")
        if ho:
            rows.append(("Hold-out test",
                         f"n={ho.get('n_test')}, "
                         f"accuracy={ho.get('accuracy'):.3f}"))
        return rows

    def _fill_performance(self):
        s = self.state
        bin_res = s.model_results("binary")
        self.card_bin.set_rows(
            self._perf_rows(bin_res["metrics"]) if bin_res else [])
        mc_res = s.model_results("multiclass")
        self.card_mc.setVisible(mc_res is not None)
        if mc_res:
            self.card_mc.set_rows(self._perf_rows(mc_res["metrics"]))
