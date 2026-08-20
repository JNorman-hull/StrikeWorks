# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Configure tab - everything that defines a training run.

Dataset loading and filtering, target/label definition with live class
distribution, input-channel selection, sequence preparation, validation
(hold-out + stratified CV), class balancing, model configuration and the
pre-training readiness checklist. All configuration lives in the shared
TrainingState; the Cross-validate tab consumes it unchanged.
"""
from pathlib import Path

import pandas as pd

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QGridLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton, QRadioButton,
    QScrollArea, QSizePolicy, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from . import settings
from .ml_train_state import COLLAPSE_SCHEMES
from .ml_widgets import (
    BORDER, CARD_BG, EMPTY, MUTED, OK, PALETTE, TEXT, CheckList, MetaCard,
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


class ConfigureTab:
    """Builds the Configure tab UI into `frame` and binds it to `state`."""

    def __init__(self, frame, state, window, goto_cv=None):
        self.state = state
        self.window = window
        self._goto_cv = goto_cv
        self._updating = False
        self._include_checks = {}
        self._channel_checks = {}

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

        grp_ds = QGroupBox("Training dataset")
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
        self.lbl_compat.setStyleSheet(f"color:{OK};font-size:10px;")
        dv.addWidget(self.lbl_compat)
        row1.addWidget(grp_ds, stretch=2)

        self.grp_preview = QGroupBox("Dataset preview (file-level metadata)")
        self.grp_preview.setCheckable(True)
        self.grp_preview.setChecked(False)
        pv = QVBoxLayout(self.grp_preview)
        self.tbl_preview = QTableWidget(0, 0)
        self.tbl_preview.verticalHeader().setVisible(False)
        self.tbl_preview.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_preview.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_preview.horizontalHeader().setStretchLastSection(True)
        self.tbl_preview.setMinimumHeight(180)
        self.tbl_preview.setVisible(False)
        pv.addWidget(self.tbl_preview)
        self.grp_preview.toggled.connect(self._toggle_preview)
        row1.addWidget(self.grp_preview, stretch=3)
        v.addLayout(row1)

        # ── row 2: filtering + labels ───────────────────────────────────────
        row2 = QHBoxLayout()
        row2.setSpacing(10)

        grp_filter = QGroupBox("Dataset filtering")
        fv = QVBoxLayout(grp_filter)
        fv.setSpacing(4)
        lab = QLabel("Include records (by target value). The resulting "
                     "training population is recorded in the model provenance.")
        lab.setStyleSheet(f"color:{MUTED};font-size:9px;")
        lab.setWordWrap(True)
        fv.addWidget(lab)
        self.include_box = QVBoxLayout()
        self.include_box.setSpacing(2)
        fv.addLayout(self.include_box)
        self.lbl_population = QLabel("")
        self.lbl_population.setStyleSheet(
            f"color:{TEXT};font-size:10px;font-weight:bold;")
        fv.addWidget(self.lbl_population)
        fv.addStretch()
        row2.addWidget(grp_filter, stretch=1)

        grp_target = QGroupBox("Labels / target — two-stage pipeline")
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
        tv.addLayout(tr)

        self.lbl_positive = QLabel("")
        self.lbl_positive.setStyleSheet(f"color:{MUTED};font-size:9px;")
        self.lbl_positive.setWordWrap(True)
        tv.addWidget(self.lbl_positive)

        mc_row = QGridLayout()
        mc_row.setVerticalSpacing(4)
        self.chk_multiclass = QCheckBox(
            "Stage 2 — train the multiclass region model")
        self.chk_multiclass.toggled.connect(self._mc_toggled)
        self.lbl_scheme = self._muted("Region collapse")
        self.cmb_scheme = QComboBox()
        for key, sch in COLLAPSE_SCHEMES.items():
            self.cmb_scheme.addItem(f"{key}: {sch['desc']}", key)
        self.cmb_scheme.currentIndexChanged.connect(self._scheme_changed)
        self.chk_surface = QCheckBox(
            "Treat unlabelled impeller-surface strikes as region 1")
        self.chk_surface.toggled.connect(self._surface_changed)
        mc_row.addWidget(self.chk_multiclass, 0, 0, 1, 2)
        mc_row.addWidget(self.lbl_scheme, 1, 0)
        mc_row.addWidget(self.cmb_scheme, 1, 1)
        mc_row.addWidget(self.chk_surface, 2, 0, 1, 2)
        tv.addLayout(mc_row)

        self.lbl_derived = QLabel("")
        self.lbl_derived.setStyleSheet(f"color:{MUTED};font-size:9px;")
        self.lbl_derived.setWordWrap(True)
        tv.addWidget(self.lbl_derived)

        self.lbl_dist_bin = self._muted(
            "CLASS DISTRIBUTION — stage 1 (strike vs no contact)")
        tv.addWidget(self.lbl_dist_bin)
        self.class_dist = _ClassDist()
        tv.addWidget(self.class_dist)
        self.lbl_dist_mc = self._muted(
            "CLASS DISTRIBUTION — stage 2 (region of ground-truth strikes)")
        tv.addWidget(self.lbl_dist_mc)
        self.class_dist_mc = _ClassDist()
        tv.addWidget(self.class_dist_mc)
        tv.addStretch()
        row2.addWidget(grp_target, stretch=2)
        v.addLayout(row2)

        # ── row 3: channels + sequence ──────────────────────────────────────
        row3 = QHBoxLayout()
        row3.setSpacing(10)

        grp_chan = QGroupBox("Model input channels")
        cv = QVBoxLayout(grp_chan)
        cv.setSpacing(4)
        self.chan_grid = QGridLayout()
        self.chan_grid.setHorizontalSpacing(16)
        self.chan_grid.setVerticalSpacing(2)
        cv.addLayout(self.chan_grid)
        self.lbl_chan_count = QLabel("")
        self.lbl_chan_count.setStyleSheet(
            f"color:{TEXT};font-size:10px;font-weight:bold;")
        cv.addWidget(self.lbl_chan_count)
        cv.addStretch()
        row3.addWidget(grp_chan, stretch=1)

        grp_seq = QGroupBox("Sequence configuration")
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
            f"color:{TEXT};font-size:10px;font-weight:bold;")
        sv.addWidget(self.lbl_tensor, 4, 0, 1, 2)
        row3.addWidget(grp_seq, stretch=1)
        v.addLayout(row3)

        # ── row 4: validation + balancing + model ───────────────────────────
        row4 = QHBoxLayout()
        row4.setSpacing(10)

        grp_val = QGroupBox("Validation")
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

        grp_bal = QGroupBox("Class balancing")
        bv = QVBoxLayout(grp_bal)
        bv.setSpacing(4)
        self.rb_w_none = QRadioButton("None")
        self.rb_w_balanced = QRadioButton("Balanced class weights")
        self.rb_w_balanced.setChecked(True)
        self.rb_w_balanced.toggled.connect(self._weight_changed)
        bv.addWidget(self.rb_w_none)
        bv.addWidget(self.rb_w_balanced)
        self.lbl_weights = QLabel("")
        self.lbl_weights.setStyleSheet(f"color:{TEXT};font-size:10px;")
        bv.addWidget(self.lbl_weights)
        lab = QLabel("Minority-class observations are weighted during "
                     "training to compensate for class imbalance.")
        lab.setStyleSheet(f"color:{MUTED};font-size:9px;")
        lab.setWordWrap(True)
        bv.addWidget(lab)
        bv.addStretch()
        row4.addWidget(grp_bal, stretch=1)

        grp_model = QGroupBox("Model")
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
        mv.addWidget(self._muted("Ridge alphas 10^"), 2, 0)
        self.spin_a_min = QSpinBox()
        self.spin_a_min.setRange(-8, 0)
        self.spin_a_min.setValue(-3)
        self.spin_a_min.valueChanged.connect(self._model_changed)
        mv.addWidget(self.spin_a_min, 2, 1)
        mv.addWidget(self._muted("… to 10^"), 2, 2)
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

        # ── row 5: readiness ────────────────────────────────────────────────
        grp_ready = QGroupBox("Ready to train")
        rv = QHBoxLayout(grp_ready)
        self.checklist = CheckList()
        rv.addWidget(self.checklist, stretch=1)
        side = QVBoxLayout()
        self.btn_go_cv = QPushButton("Go to Cross-validate →")
        self.btn_go_cv.setMinimumHeight(34)
        self.btn_go_cv.clicked.connect(
            lambda: self._goto_cv() if self._goto_cv else None)
        side.addWidget(self.btn_go_cv)
        side.addStretch()
        rv.addLayout(side)
        v.addWidget(grp_ready)
        v.addStretch()

    @staticmethod
    def _muted(text):
        lab = QLabel(text)
        lab.setStyleSheet(f"color:{MUTED};font-size:10px;")
        return lab

    # ── state wiring ─────────────────────────────────────────────────────────
    def _connect_state(self):
        s = self.state
        s.dataset_changed.connect(self._rebuild_dataset_widgets)
        s.config_changed.connect(self._refresh_all)
        s.validation_changed.connect(self._refresh_checklist)

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

    def _toggle_preview(self, checked):
        self.tbl_preview.setVisible(checked)

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

    def _scheme_changed(self):
        if self._updating:
            return
        self.state.update(collapse_scheme=self.cmb_scheme.currentData())

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
        self._refresh_checklist()

    def _refresh_dataset_card(self):
        s = self.state
        m = s.dataset_meta
        if not m:
            self.card_dataset.set_rows([
                ("Dataset", "No training dataset loaded"),
                ("Hint", "Load a model_features CSV produced by Sensor "
                         "Processing (with annotation labels appended)."),
            ])
            self.lbl_compat.setText("")
            return
        seq = (f"{m['seq_min']}–{m['seq_max']}"
               if m.get("seq_min") != m.get("seq_max")
               else str(m.get("seq_max")))
        self.card_dataset.set_rows([
            ("Dataset",              m.get("name")),
            ("Files / observations", m.get("n_files")),
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
            "✓ Dataset compatible with training pipeline" if ok
            else "⚠ Dataset needs attention - see the checklist below")
        self.lbl_compat.setStyleSheet(
            f"color:{OK if ok else '#f59e0b'};font-size:10px;")

    def _refresh_target(self):
        s = self.state
        self._updating = True
        try:
            self.chk_multiclass.setChecked(s.train_multiclass)
            self.chk_multiclass.setEnabled(s.region_column is not None)
            if s.region_column is None:
                self.chk_multiclass.setToolTip(
                    "No pump-region column in dataset")
            for w in (self.lbl_scheme, self.cmb_scheme, self.chk_surface):
                w.setEnabled(s.train_multiclass)
            self.chk_surface.setChecked(s.include_surface)
            idx = self.cmb_scheme.findData(s.collapse_scheme)
            if idx >= 0:
                self.cmb_scheme.setCurrentIndex(idx)
        finally:
            self._updating = False

        if s.negative_class:
            txt = (f"Stage 1 — binary: blade_strike defined as "
                   f"{s.target_column} ≠ \"{s.negative_class}\".")
            if s.train_multiclass and s.region_column:
                txt += (f"   Stage 2 — multiclass: ground-truth strikes "
                        f"classified by collapsed {s.region_column}.")
            self.lbl_positive.setText(txt)
        else:
            self.lbl_positive.setText("")

        derived = ["blade_strike (0/1)"]
        if s.leading_type_column() or s.other_type_column():
            derived.append("strike_type (no_contact / leading_* / other_*)")
        self.lbl_derived.setText("Derived variables: " + ", ".join(derived))

        self.class_dist.set_counts(s.binary_class_counts())
        show_mc = s.train_multiclass and s.region_column is not None
        self.lbl_dist_mc.setVisible(show_mc)
        self.class_dist_mc.setVisible(show_mc)
        if show_mc:
            self.class_dist_mc.set_counts(s.region_class_counts())
        n = s.population_size()
        self.lbl_population.setText(f"Training population: {n} recordings")

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

    def _refresh_checklist(self):
        s = self.state
        self.checklist.set_checks(s.checks, s.ready,
                                  ready_text="READY TO TRAIN",
                                  blocked_text="TRAINING UNAVAILABLE")
