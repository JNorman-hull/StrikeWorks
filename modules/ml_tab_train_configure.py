# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Train tab - everything that defines and runs a training run.

Dataset loading and filtering, target/label definition with live class
distributions, input-channel selection, sequence preparation, validation
(hold-out + stratified CV), class balancing and model configuration, then
the training run itself: the TRAIN MODEL control, the streaming training
console and the out-of-fold performance of both pipeline stages.

All configuration and results live in the shared TrainingState; the
Evaluate and Deploy tabs consume them unchanged.
"""
from pathlib import Path

import pandas as pd

from PySide6.QtCore import Qt, QElapsedTimer, QTimer
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QRadioButton, QScrollArea,
    QSizePolicy, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from . import settings
from .ml_train_state import GROUPING_PRESETS
from .ml_widgets import (
    ACCENT, BAD, BORDER, CARD_BG, EMPTY, MUTED, OK, PALETTE, TEXT,
    LevelGrouper, MetaCard, Spinner, Section, apply_section_defaults,
)

_PREVIEW_ROWS = 200


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


class TrainTab:
    """Builds the Train tab UI into `frame` and binds it to `state`."""

    def __init__(self, frame, state, window, goto_evaluate=None):
        self.state = state
        self.window = window
        self._goto_evaluate = goto_evaluate
        self._updating = False
        self._include_checks = {}
        self._channel_checks = {}

        self._elapsed = QElapsedTimer()
        self._tick = QTimer()
        self._tick.setInterval(500)
        self._tick.timeout.connect(self._update_elapsed)

        self._build(frame)
        self._connect_state()
        self._rebuild_dataset_widgets()
        self._refresh_all()

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, frame):
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        outer.addWidget(scroll)
        body = QWidget()
        body.setStyleSheet("background:transparent;")
        scroll.setWidget(body)
        v = QVBoxLayout(body)
        v.setContentsMargins(4, 6, 4, 6)
        v.setSpacing(10)

        # ── row 1: dataset + preview ────────────────────────────────────────
        row1 = QHBoxLayout()
        row1.setSpacing(10)

        grp_ds = Section("Training dataset")
        dv = QVBoxLayout(grp_ds)
        dv.setSpacing(8)
        btn_row = QHBoxLayout()
        self.btn_load = QPushButton("Load training dataset…")
        self.btn_load.clicked.connect(self._load_dataset)
        self.cmb_recent = QComboBox()
        self.cmb_recent.setToolTip("Recently used training datasets")
        self.cmb_recent.activated.connect(self._recent_chosen)
        btn_row.addWidget(self.btn_load)
        btn_row.addWidget(self.cmb_recent, stretch=1)
        dv.addLayout(btn_row)
        self.card_dataset = MetaCard("TRAINING DATASET")
        dv.addWidget(self.card_dataset)
        self.lbl_compat = QLabel("")
        self.lbl_compat.setStyleSheet(f"color:{OK};")
        dv.addWidget(self.lbl_compat)
        row1.addWidget(grp_ds, stretch=2)

        self.grp_preview = Section("Dataset preview (file-level metadata)")
        pv = QVBoxLayout(self.grp_preview)
        self.tbl_preview = QTableWidget(0, 0)
        self.tbl_preview.verticalHeader().setVisible(False)
        self.tbl_preview.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_preview.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_preview.horizontalHeader().setStretchLastSection(True)
        self.tbl_preview.setMinimumHeight(180)
        pv.addWidget(self.tbl_preview)

        grp_filter = Section("Dataset filtering")
        fv = QVBoxLayout(grp_filter)
        fv.setSpacing(4)
        lab = QLabel("Include records (by target value). The resulting "
                     "training population is recorded in the model provenance.")
        lab.setStyleSheet(f"color:{MUTED};")
        lab.setWordWrap(True)
        fv.addWidget(lab)
        self.include_box = QVBoxLayout()
        self.include_box.setSpacing(2)
        fv.addLayout(self.include_box)
        self.lbl_population = QLabel("")
        self.lbl_population.setStyleSheet(
            f"color:{TEXT};font-weight:bold;")
        fv.addWidget(self.lbl_population)
        fv.addStretch()
        row1.addWidget(grp_filter, stretch=1)

        grp_target = Section("Labelling")
        tv = QVBoxLayout(grp_target)
        tv.setSpacing(6)

        tr = QGridLayout()
        tr.setVerticalSpacing(6)
        tr.addWidget(self._muted("Target variable"), 0, 0)
        self.cmb_target = QComboBox()
        self.cmb_target.currentIndexChanged.connect(self._target_changed)
        tr.addWidget(self.cmb_target, 0, 1)

        tr.addWidget(self._muted("Negative class"), 1, 0)
        self.cmb_negative = QComboBox()
        self.cmb_negative.currentIndexChanged.connect(self._negative_changed)
        tr.addWidget(self.cmb_negative, 1, 1)

        tr.addWidget(self._muted("Positive class"), 2, 0)
        self.ed_positive = QLineEdit()
        self.ed_positive.setPlaceholderText("blade_strike")
        self.ed_positive.editingFinished.connect(self._positive_changed)
        tr.addWidget(self.ed_positive, 2, 1)
        tv.addLayout(tr)

        self.lbl_positive = QLabel("")
        self.lbl_positive.setStyleSheet(f"color:{MUTED};")
        self.lbl_positive.setWordWrap(True)
        tv.addWidget(self.lbl_positive)

        mc_row = QGridLayout()
        mc_row.setVerticalSpacing(4)
        self.chk_multiclass = QCheckBox(
            "Multiclass class model")
        self.chk_multiclass.toggled.connect(self._mc_toggled)
        self.lbl_class_col = self._muted("Class variable")
        self.cmb_class_col = QComboBox()
        self.cmb_class_col.currentIndexChanged.connect(self._class_col_changed)
        self.lbl_preset = self._muted("Grouping")
        self.cmb_preset = QComboBox()
        for key, spec in GROUPING_PRESETS.items():
            self.cmb_preset.addItem(spec["desc"], key)
        self.cmb_preset.currentIndexChanged.connect(self._preset_changed)
        self.chk_surface = QCheckBox("Unlabelled surface strikes -> region 1")
        self.chk_surface.toggled.connect(self._surface_changed)
        mc_row.addWidget(self.chk_multiclass, 0, 0, 1, 2)
        mc_row.addWidget(self.lbl_class_col, 1, 0)
        mc_row.addWidget(self.cmb_class_col, 1, 1)
        mc_row.addWidget(self.lbl_preset, 2, 0)
        mc_row.addWidget(self.cmb_preset, 2, 1)
        mc_row.addWidget(self.chk_surface, 3, 0, 1, 2)
        tv.addLayout(mc_row)

        # level -> class grouping, driven by the levels actually in the data
        self.grouper = LevelGrouper()
        self.grouper.changed.connect(self._groups_changed)
        tv.addWidget(self.grouper)

        self.lbl_derived = QLabel("")
        self.lbl_derived.setStyleSheet(f"color:{MUTED};")
        self.lbl_derived.setWordWrap(True)
        tv.addWidget(self.lbl_derived)

        self.lbl_dist_bin = self._muted(
            "Binary class distribution")
        tv.addWidget(self.lbl_dist_bin)
        self.class_dist = _ClassDist()
        tv.addWidget(self.class_dist)
        self.lbl_dist_mc = self._muted(
            "Multiclass class distribution")
        tv.addWidget(self.lbl_dist_mc)
        self.class_dist_mc = _ClassDist()
        tv.addWidget(self.class_dist_mc)
        tv.addStretch()
        row1.addWidget(grp_target, stretch=3)
        v.addLayout(row1)
        v.addWidget(self.grp_preview)

        # ── row 3: channels + sequence ──────────────────────────────────────
        row3 = QHBoxLayout()
        row3.setSpacing(10)

        grp_chan = Section("Model input channels")
        cv = QVBoxLayout(grp_chan)
        cv.setSpacing(4)
        self.chan_grid = QGridLayout()
        self.chan_grid.setHorizontalSpacing(16)
        self.chan_grid.setVerticalSpacing(2)
        cv.addLayout(self.chan_grid)
        self.lbl_chan_count = QLabel("")
        self.lbl_chan_count.setStyleSheet(
            f"color:{TEXT};font-weight:bold;")
        cv.addWidget(self.lbl_chan_count)
        cv.addStretch()
        row3.addWidget(grp_chan, stretch=1)

        grp_seq = Section("Sequence configuration")
        sv = QGridLayout(grp_seq)
        sv.setVerticalSpacing(6)
        self.rb_seq_auto = QRadioButton("Automatically determine from dataset")
        self.rb_seq_manual = QRadioButton("Specify manually")
        self.rb_seq_auto.setChecked(True)
        self.rb_seq_auto.toggled.connect(self._seq_changed)
        self.spin_seq = QSpinBox()
        self.spin_seq.setRange(10, 100000)
        self.spin_seq.setValue(400)
        self.spin_seq.setEnabled(False)
        self.spin_seq.valueChanged.connect(self._seq_changed)
        sv.addWidget(self.rb_seq_auto, 0, 0, 1, 2)
        sv.addWidget(self.rb_seq_manual, 1, 0)
        sv.addWidget(self.spin_seq, 1, 1)
        sv.addWidget(self._muted("Padding"), 2, 0)
        self.cmb_padding = QComboBox()
        self.cmb_padding.addItem("Repeat final observation", "repeat_last")
        sv.addWidget(self.cmb_padding, 2, 1)
        sv.addWidget(self._muted("Truncation"), 3, 0)
        self.cmb_trunc = QComboBox()
        self.cmb_trunc.addItem("Truncate to target length", "truncate")
        sv.addWidget(self.cmb_trunc, 3, 1)
        self.lbl_tensor = QLabel("")
        self.lbl_tensor.setStyleSheet(
            f"color:{TEXT};font-weight:bold;")
        sv.addWidget(self.lbl_tensor, 4, 0, 1, 2)
        row3.addWidget(grp_seq, stretch=1)
        v.addLayout(row3)

        # ── row 4: validation + balancing + model ───────────────────────────
        row4 = QHBoxLayout()
        row4.setSpacing(10)

        grp_val = Section("Validation")
        vv = QGridLayout(grp_val)
        vv.setVerticalSpacing(6)
        self.rb_cv_only = QRadioButton("Cross-validation only")
        self.rb_holdout = QRadioButton("Train / test + cross-validation")
        self.rb_cv_only.setChecked(True)
        self.rb_cv_only.toggled.connect(self._val_changed)
        vv.addWidget(self.rb_cv_only, 0, 0, 1, 2)
        vv.addWidget(self.rb_holdout, 1, 0, 1, 2)
        vv.addWidget(self._muted("Test set"), 2, 0)
        self.spin_test = QDoubleSpinBox()
        self.spin_test.setRange(0.05, 0.5)
        self.spin_test.setSingleStep(0.05)
        self.spin_test.setDecimals(2)
        self.spin_test.setValue(0.20)
        self.spin_test.setEnabled(False)
        self.spin_test.valueChanged.connect(self._val_changed)
        vv.addWidget(self.spin_test, 2, 1)
        vv.addWidget(self._muted("CV method"), 3, 0)
        cmb_cv = QComboBox()
        cmb_cv.addItem("Stratified K-Fold")
        vv.addWidget(cmb_cv, 3, 1)
        vv.addWidget(self._muted("Number of folds"), 4, 0)
        self.spin_folds = QSpinBox()
        self.spin_folds.setRange(2, 20)
        self.spin_folds.setValue(10)
        self.spin_folds.valueChanged.connect(self._val_changed)
        vv.addWidget(self.spin_folds, 4, 1)
        self.chk_shuffle = QCheckBox("Shuffle")
        self.chk_shuffle.setChecked(True)
        self.chk_shuffle.toggled.connect(self._val_changed)
        vv.addWidget(self.chk_shuffle, 5, 0)
        seed_row = QHBoxLayout()
        seed_row.addWidget(self._muted("Random seed"))
        self.spin_seed = QSpinBox()
        self.spin_seed.setRange(0, 999999)
        self.spin_seed.setValue(42)
        self.spin_seed.valueChanged.connect(self._val_changed)
        seed_row.addWidget(self.spin_seed)
        vv.addLayout(seed_row, 5, 1)
        row4.addWidget(grp_val, stretch=1)

        grp_bal = Section("Class balancing")
        bv = QVBoxLayout(grp_bal)
        bv.setSpacing(4)
        self.rb_w_none = QRadioButton("None")
        self.rb_w_balanced = QRadioButton("Balanced class weights")
        self.rb_w_balanced.setChecked(True)
        self.rb_w_balanced.toggled.connect(self._weight_changed)
        bv.addWidget(self.rb_w_none)
        bv.addWidget(self.rb_w_balanced)
        self.lbl_weights = QLabel("")
        self.lbl_weights.setStyleSheet(f"color:{TEXT};")
        bv.addWidget(self.lbl_weights)
        lab = QLabel("Minority-class observations are weighted"
                     )
        lab.setStyleSheet(f"color:{MUTED};")
        lab.setWordWrap(True)
        bv.addWidget(lab)
        bv.addStretch()
        row4.addWidget(grp_bal, stretch=1)

        grp_model = Section("Model")
        mv = QGridLayout(grp_model)
        mv.setVerticalSpacing(6)
        mv.addWidget(self._muted("Architecture"), 0, 0)
        cmb_arch = QComboBox()
        cmb_arch.addItem("MiniRocket + RidgeClassifierCV")
        mv.addWidget(cmb_arch, 0, 1, 1, 3)
        mv.addWidget(self._muted("MiniRocket seed"), 1, 0)
        self.spin_mr_seed = QSpinBox()
        self.spin_mr_seed.setRange(0, 999999)
        self.spin_mr_seed.setValue(42)
        self.spin_mr_seed.valueChanged.connect(self._model_changed)
        mv.addWidget(self.spin_mr_seed, 1, 1)
        mv.addWidget(self._muted("n_jobs"), 1, 2)
        self.spin_njobs = QSpinBox()
        self.spin_njobs.setRange(-1, 64)
        self.spin_njobs.setValue(-1)
        self.spin_njobs.valueChanged.connect(self._model_changed)
        mv.addWidget(self.spin_njobs, 1, 3)
        mv.addWidget(self._muted("Ridge alphas"), 2, 0)
        self.spin_a_min = QSpinBox()
        self.spin_a_min.setRange(-8, 0)
        self.spin_a_min.setValue(-3)
        self.spin_a_min.valueChanged.connect(self._model_changed)
        mv.addWidget(self.spin_a_min, 2, 1)
        mv.addWidget(self._muted("to"), 2, 2)
        self.spin_a_max = QSpinBox()
        self.spin_a_max.setRange(0, 8)
        self.spin_a_max.setValue(3)
        self.spin_a_max.valueChanged.connect(self._model_changed)
        mv.addWidget(self.spin_a_max, 2, 3)
        mv.addWidget(self._muted("Alpha values"), 3, 0)
        self.spin_n_alpha = QSpinBox()
        self.spin_n_alpha.setRange(5, 500)
        self.spin_n_alpha.setValue(100)
        self.spin_n_alpha.valueChanged.connect(self._model_changed)
        mv.addWidget(self.spin_n_alpha, 3, 1)
        row4.addWidget(grp_model, stretch=1)
        v.addLayout(row4)

        # ── row 5: train + console + out-of-fold performance ────────────────
        row5 = QHBoxLayout()
        row5.setSpacing(10)

        grp_run = Section("Train")
        gv = QVBoxLayout(grp_run)
        gv.setSpacing(8)
        run_row = QHBoxLayout()
        self.btn_train = QPushButton("Train model")
        self.btn_train.setMinimumHeight(38)
        self.btn_train.setEnabled(False)
        self.btn_train.clicked.connect(self.state.run_cv)
        self.spinner = Spinner(size=26)
        self.spinner.setVisible(False)
        run_row.addWidget(self.btn_train, stretch=1)
        run_row.addWidget(self.spinner)
        gv.addLayout(run_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("%v/%m folds")
        self.progress.setVisible(False)
        gv.addWidget(self.progress)

        self.lbl_status = QLabel(
            "")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet(f"color:{MUTED};")
        gv.addWidget(self.lbl_status)

        self.card_bin = MetaCard("Binary OOF")
        gv.addWidget(self.card_bin)
        self.card_mc = MetaCard("Multiclass OOF")
        self.card_mc.setVisible(False)
        gv.addWidget(self.card_mc)

        self.btn_evaluate = QPushButton("Evaluate results")
        self.btn_evaluate.setVisible(False)
        self.btn_evaluate.clicked.connect(
            lambda: self._goto_evaluate() if self._goto_evaluate else None)
        gv.addWidget(self.btn_evaluate)
        gv.addStretch()
        row5.addWidget(grp_run, stretch=2)

        grp_console = Section("Training console")
        cv = QVBoxLayout(grp_console)
        cv.setSpacing(4)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_clear = QPushButton("Clear")
        btn_clear.setFixedWidth(70)
        btn_clear.clicked.connect(lambda: self.console.clear())
        btn_row.addWidget(btn_clear)
        cv.addLayout(btn_row)
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(5000)
        self.console.setMinimumHeight(280)
        self.console.setStyleSheet(
            "QPlainTextEdit{background:#1b1e23;color:#d4d4d4;"
            "border:1px solid #2c313a;border-radius:4px;"
            "font-family:Consolas,monospace;font-size:9pt;}")
        cv.addWidget(self.console, stretch=1)
        row5.addWidget(grp_console, stretch=3)
        v.addLayout(row5)
        v.addStretch()

        apply_section_defaults(frame)

    @staticmethod
    def _muted(text):
        lab = QLabel(text)
        lab.setStyleSheet(f"color:{MUTED};")
        return lab

    # ── state wiring ─────────────────────────────────────────────────────────
    def _connect_state(self):
        s = self.state
        s.dataset_changed.connect(self._rebuild_dataset_widgets)
        s.config_changed.connect(self._refresh_all)
        s.validation_changed.connect(self._refresh_ready)
        s.cv_started.connect(self._on_started)
        s.cv_line.connect(self._on_line)
        s.cv_progress.connect(self._on_progress)
        s.cv_finished.connect(self._on_finished)
        s.cv_failed.connect(self._on_failed)
        # the final-model run streams into the same console
        s.final_started.connect(self._on_final_started)
        s.final_finished.connect(self._stop_run_ui)
        s.final_failed.connect(lambda _m: self._stop_run_ui())

    # ── dataset loading ──────────────────────────────────────────────────────
    def _load_dataset(self):
        path, _ = QFileDialog.getOpenFileName(
            self.window, "Load training dataset", str(Path.cwd()),
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
            QMessageBox.warning(self.window, "Training dataset", msg)

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
            self._rebuild_include_checks()
            self._rebuild_channel_checks()
            self._fill_preview()
        finally:
            self._updating = False
        self._refresh_all()

    def _rebuild_negative_combo(self):
        s = self.state
        self.cmb_negative.clear()
        for val in s.target_values():
            self.cmb_negative.addItem(val, val)
        if s.negative_class is not None:
            idx = self.cmb_negative.findData(str(s.negative_class))
            if idx >= 0:
                self.cmb_negative.setCurrentIndex(idx)

    def _rebuild_include_checks(self):
        s = self.state
        while self.include_box.count():
            item = self.include_box.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._include_checks = {}

        df = s.dataset_df
        if df is None or not s.target_column:
            return
        per_file = (df.groupby("file")[s.target_column].first()
                    .dropna().astype(str))
        counts = per_file.value_counts()
        included = (set(map(str, s.include_values))
                    if s.include_values is not None else set(counts.index))
        for val, n in counts.items():
            chk = QCheckBox(f"{val}   (n={int(n)})")
            chk.setChecked(val in included)
            chk.toggled.connect(self._include_changed)
            self.include_box.addWidget(chk)
            self._include_checks[val] = chk

    def _rebuild_channel_checks(self):
        s = self.state
        while self.chan_grid.count():
            item = self.chan_grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
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
        for c in ("treatment", s.target_column, s.leading_type_column(),
                  s.other_type_column(), s.region_column):
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
                text = "—" if pd.isna(val) else str(val)
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
                self._rebuild_include_checks()
                self._fill_preview()
            finally:
                self._updating = False

    def _mc_toggled(self, checked):
        if self._updating:
            return
        self.state.update(train_multiclass=checked)

    def _negative_changed(self):
        if self._updating:
            return
        val = self.cmb_negative.currentData()
        if val is not None:
            self.state.update(negative_class=val)

    def _positive_changed(self):
        if self._updating:
            return
        name = self.ed_positive.text().strip() or "blade_strike"
        if name != self.state.positive_label:
            self.state.update(positive_label=name)

    def _class_col_changed(self):
        if self._updating:
            return
        col = self.cmb_class_col.currentData()
        if col:
            self.state.update(region_column=col)

    def _preset_changed(self):
        if self._updating:
            return
        self.state.rebuild_region_groups(self.cmb_preset.currentData())
        self.state.config_changed.emit()
        self.state.validate()

    def _groups_changed(self):
        """The user edited the grouping - it is now a custom scheme."""
        if self._updating:
            return
        self.state.region_groups = self.grouper.groups()
        self.state.grouping_preset = "custom"
        self._updating = True
        try:
            idx = self.cmb_preset.findData("custom")
            if idx >= 0:
                self.cmb_preset.setCurrentIndex(idx)
        finally:
            self._updating = False
        self.state.config_changed.emit()
        self.state.validate()

    def _surface_changed(self, checked):
        if self._updating:
            return
        self.state.update(include_surface=checked)

    def _include_changed(self):
        if self._updating:
            return
        checked = {v for v, chk in self._include_checks.items()
                   if chk.isChecked()}
        all_vals = set(self._include_checks.keys())
        self.state.update(
            include_values=None if checked == all_vals else checked)

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
        self._refresh_channels()
        self._refresh_sequence()
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
        self.lbl_compat.setStyleSheet(
            f"color:{OK if ok else '#f59e0b'};")

    def _refresh_target(self):
        s = self.state
        self._updating = True
        try:
            self.ed_positive.setText(s.positive_label or "")
            self.chk_multiclass.setChecked(s.train_multiclass)
            self.chk_multiclass.setEnabled(s.region_column is not None)
            if s.region_column is None:
                self.chk_multiclass.setToolTip(
                    "No suitable class column found in the dataset")

            # class variable: any per-file column with a few levels
            cands = s.class_column_candidates()
            self.cmb_class_col.clear()
            for c in cands:
                self.cmb_class_col.addItem(c, c)
            if s.region_column:
                idx = self.cmb_class_col.findData(s.region_column)
                if idx >= 0:
                    self.cmb_class_col.setCurrentIndex(idx)

            idx = self.cmb_preset.findData(s.grouping_preset)
            if idx >= 0:
                self.cmb_preset.setCurrentIndex(idx)

            for w in (self.lbl_class_col, self.cmb_class_col,
                      self.lbl_preset, self.cmb_preset, self.chk_surface,
                      self.grouper):
                w.setEnabled(s.train_multiclass)
            self.chk_surface.setChecked(s.include_surface)
            self.grouper.set_data(s.region_levels(), s.region_groups)
        finally:
            self._updating = False

        if s.negative_class:
            pos = s.positive_label or "blade_strike"
            txt = (f"Binary: {pos} defined as "
                   f"{s.target_column} ≠ \"{s.negative_class}\".")
            if s.train_multiclass and s.region_column:
                txt += (f"Multiclass:"
                        f"classified by {s.region_column}, grouped below.")
            self.lbl_positive.setText(txt)
        else:
            self.lbl_positive.setText("")

        derived = [f"{s.positive_label or 'blade_strike'} (0/1)"]
        if s.leading_type_column() or s.other_type_column():
            derived.append("strike_type (no_contact / leading_* / other_*)")
        self.lbl_derived.setText("Derived variables: " + ", ".join(derived))

        self.class_dist.set_counts(s.binary_class_counts())
        show_mc = s.train_multiclass and s.region_column is not None
        self.lbl_dist_mc.setVisible(show_mc)
        self.class_dist_mc.setVisible(show_mc)
        self.grouper.setVisible(show_mc)
        if show_mc:
            self.class_dist_mc.set_counts(s.region_class_counts())
        n = s.population_size()
        self.lbl_population.setText(f"Training (n) = {n}")

    def _refresh_channels(self):
        s = self.state
        n = len(s.channels)
        seq = s.seq_length if not s.seq_auto \
            else s.dataset_meta.get("seq_max", "N")
        self.lbl_chan_count.setText(
            f"{n} channels selected   —   expected input: "
            f"{n} channels × {seq} time points")

    def _refresh_sequence(self):
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
        n_files = s.population_size()
        seq = s.seq_length if not s.seq_auto \
            else s.dataset_meta.get("seq_max", "?")
        self.lbl_tensor.setText(
            f"Input tensor: {n_files} samples × {len(s.channels)} channels "
            f"× {seq} time points")

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
                lines.append("— region model —")
                lines += [f"{lab}:  {total / (k * c):.2f}" if c
                          else f"{lab}:  —" for lab, c in mc_counts]
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
            self.lbl_status.setStyleSheet(f"color:{BAD};")
            self.lbl_status.setText(
                f"✗ {label}: {detail}" if detail else f"✗ {label}")
        elif not s.cv_done:
            self.lbl_status.setStyleSheet(f"color:{MUTED};")
            self.lbl_status.setText(
                "")

    # ── run lifecycle ────────────────────────────────────────────────────────
    def _on_started(self):
        self.console.clear()
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
        self.lbl_status.setStyleSheet(f"color:{ACCENT};")
        self.lbl_status.setText("Training binary strike model")

    def _on_final_started(self):
        self.console.appendPlainText("\n" + "─" * 60)
        self.spinner.start()
        self._elapsed.start()
        self._tick.start()
        self.lbl_status.setStyleSheet(f"color:{ACCENT};")
        self.lbl_status.setText("Training final deployment model")

    def _on_line(self, ln):
        self.console.appendPlainText(ln)
        sb = self.console.verticalScrollBar()
        sb.setValue(sb.maximum())

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
        self.lbl_status.setStyleSheet(f"color:{OK};")
        self.lbl_status.setText(
            f"")
        self._fill_performance()
        self.btn_evaluate.setVisible(True)
        s.status.emit("Cross-validation complete.", 5000)

    def _on_failed(self, msg):
        self._stop_run_ui()
        self.progress.setVisible(False)
        self.lbl_status.setStyleSheet(f"color:{BAD};")
        first = msg.strip().splitlines()[-1] if msg.strip() else "Unknown error"
        self.lbl_status.setText(f"✗ Training failed: {first}")
        dlg = QMessageBox(self.window)
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
