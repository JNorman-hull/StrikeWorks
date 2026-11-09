# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Train tab - everything that defines and runs a training run, in four
rows:

  (dataset)          loading (or binding several) and its summary card,
                     beside a file-level preview (a draggable split).
  Labelling          Binary model - the target variable, its null (0) and
                     positive (1) values, and each of the target's values
                     coded 0, 1 or excluded | Multiclass model - the class
                     variable and its grouping | the class distributions.
  Inputs | Sequence length | Class weights | Cross-validation
                     input channels; sequence preparation; class weights;
                     validation (hold-out + stratified CV) and the
                     performance metric - the variables performance is
                     broken down by.
  Model              one box, centred: the configuration beside (1) Train
                     model (CV), (2) Evaluate performance, (3) Train final
                     model; the folds' progress and Console (the training
                     worker's output goes to the app console); one status
                     line; the out-of-fold performance of both pipeline
                     stages; the version, (4) Deploy model and Model
                     information (ml_tab_train_deploy.py).

All configuration and results live in the shared TrainingState; Evaluate
and the deployment consume them unchanged.
"""
from pathlib import Path

import pandas as pd

from PySide6.QtCore import QEvent, Qt, QElapsedTimer, QTimer
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QProgressBar,
    QPushButton, QRadioButton, QSizePolicy, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import annotation_schema as asch
from . import model_measures, recording_rate, settings
from .bind_datasets import BindTrainingData
from .cards import MetaCard, Spinner
from .layout import hsplit, scroll_area, scroll_page, Section
from .ml_tab_train_deploy import (
    ACTION_W, FIELD_W, DeploymentPanel, action_button, column,
)
from .level_grouper import LevelGrouper
from .theme import EMPTY, MUTED, PALETTE, TEXT, muted_label, style

COMBO_W = 220                    # the Labelling and settings dropdowns

# a target value's coding in the binary model
_NULL, _POSITIVE, _EXCLUDE = "null", "positive", "exclude"


class _ClassDist(QWidget):
    """Class-distribution rows: label, count, percentage and a bar."""

    ROW_H = 20
    LAB_W = 110
    NUM_W = 80

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


class AnnotationSummaryWindow(QDialog):
    """How many recordings hold each value of each annotation variable, in
    the class distributions' bars - over the recordings the preview table
    shows, so its header filters narrow it. Doesn't block, like Model
    information; re-reads the table each time it's brought up or comes back
    to the front, and goes when the tab does."""

    def __init__(self, tab, owner):
        # (the tab, without a window - the tests: never parentless)
        super().__init__(owner if owner is not None else tab)
        self.tab = tab
        self._shown_for = None
        self.setWindowTitle("Annotation summary")
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 12)
        self.lbl_source = muted_label("", wrap=True)
        v.addWidget(self.lbl_source)
        self.scroll = scroll_area(QWidget())
        v.addWidget(self.scroll, stretch=1)
        self.resize(460, 620)
        tab.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.tab and event.type() == QEvent.Type.Hide:
            self.hide()
        return super().eventFilter(obj, event)

    def event(self, event):
        if event.type() == QEvent.Type.WindowActivate:
            self.refresh()
        return super().event(event)

    def bring_up(self):
        self.refresh()
        self.show()
        self.raise_()
        self.activateWindow()

    def refresh(self):
        """Redraw for what the table shows now - unless that hasn't changed,
        so coming back to the window keeps its scroll position."""
        state = self.tab.state
        files = self.tab.shown_files()
        filters = self.tab.preview_filters()
        key = (id(state.dataset_df), tuple(files), tuple(sorted(filters.items())))
        if key == self._shown_for:
            return
        self._shown_for = key

        n_all = state.dataset_meta.get("n_files", len(files))
        text = f"{state.dataset_meta.get('name', '')} - {len(files)} recording(s)"
        if len(files) != n_all:
            text += f" of {n_all}"
        if filters:
            text += ", filtered to " + ", ".join(
                f"{k} {v or '(blank)'}" for k, v in filters.items())
        self.lbl_source.setText(text)

        body = QWidget()
        style(body, role="bare")
        bv = QVBoxLayout(body)
        bv.setContentsMargins(0, 0, 8, 0)
        counts = state.annotation_counts(files)
        sections = {}
        for var, rows in counts:
            if var.group not in sections:
                section = Section(asch.GROUP_LABELS.get(var.group, ""))
                bv.addWidget(section)
                sections[var.group] = QVBoxLayout(section)
                sections[var.group].setSpacing(4)
            sv = sections[var.group]
            sv.addWidget(muted_label(
                var.label if var.label == var.name else f"{var.label} ({var.name})"))
            dist = _ClassDist()
            dist.set_counts(rows)
            sv.addWidget(dist)
            sv.addSpacing(6)
        if not counts:
            bv.addWidget(muted_label("This dataset has no annotation columns."))
        bv.addStretch()
        self.scroll.setWidget(body)


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
        v.addWidget(hsplit((self._inputs_section(), 3),
                           (self._sequence_section(), 3),
                           (self._weights_section(), 2),
                           (self._cv_section(), 3)))
        v.addWidget(self._model_section())
        v.addStretch()

    def _dataset_section(self):
        """Loading and binding beside a file-level preview - no headings;
        the preview takes the width the left side doesn't need (drag the
        boundary to change it)."""
        grp = Section("")
        row = QHBoxLayout(grp)

        left_w = QWidget()
        left = QVBoxLayout(left_w)
        left.setContentsMargins(0, 0, 8, 0)
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
        left.addStretch()
        # several datasets stacked into one - loaded straight away; at the
        # bottom, so its buttons line up with Annotation summary's
        self.bind_widget = BindTrainingData()
        self.bind_widget.bound.connect(self._load_path)
        left.addWidget(self.bind_widget)

        self.tbl_preview = QTableWidget(0, 0)
        self.tbl_preview.setToolTip("The dataset's file-level metadata, one "
                                    "row per sensor. Click a column's "
                                    "header to sort or filter by it.")
        self.tbl_preview.verticalHeader().setVisible(False)
        self.tbl_preview.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_preview.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_preview.horizontalHeader().setStretchLastSection(True)
        self.tbl_preview.setMinimumHeight(180)

        self.annotation_summary = AnnotationSummaryWindow(self, self.main_window)
        self.btn_annotation_summary = QPushButton("Annotation summary")
        self.btn_annotation_summary.setToolTip(
            "How many recordings hold each value of each annotation - of those "
            "the table shows, so filter it first to look at a subset.")
        self.btn_annotation_summary.setEnabled(False)
        self.btn_annotation_summary.clicked.connect(self.annotation_summary.bring_up)
        right_w = QWidget()
        right = QVBoxLayout(right_w)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(8)
        right.addWidget(self.tbl_preview, stretch=1)
        summary_row = QHBoxLayout()
        summary_row.addStretch()
        summary_row.addWidget(self.btn_annotation_summary)
        right.addLayout(summary_row)
        # the left side starts as narrow as it can be; widths beyond go to
        # the preview
        row.addWidget(hsplit((left_w, 0), (right_w, 1)))
        return grp

    def shown_files(self):
        """The recordings the preview table shows - its header filters applied."""
        t = self.tbl_preview
        return [t.item(r, 0).text() for r in range(t.rowCount())
                if not t.isRowHidden(r) and t.item(r, 0) is not None]

    def preview_filters(self):
        """{column: value} the preview table's header filters hold."""
        return dict(getattr(self.tbl_preview, "_header_filters", {}))

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
        # its tooltip also says how the 0/1 variable is derived
        # (_refresh_target)
        self.ed_positive.editingFinished.connect(self._positive_changed)
        tr.addWidget(self.ed_positive, 2, 1)
        tr.setColumnStretch(2, 1)
        bv.addLayout(tr)

        # each target value coded 0, 1 or excluded, under the target
        bv.addWidget(muted_label("Classes"))
        self.values_grid = QGridLayout()
        self.values_grid.setHorizontalSpacing(12)
        self.values_grid.setVerticalSpacing(4)
        bv.addLayout(self.values_grid)
        self.lbl_population = QLabel("")
        bv.addWidget(self.lbl_population)
        bv.addStretch()
        top.addWidget(binary, stretch=3)

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

        # ── the class distributions, one above the other ───────────────────
        dist = QWidget()
        dv = QVBoxLayout(dist)
        dv.setContentsMargins(0, 0, 0, 0)
        dv.setSpacing(4)
        self.lbl_dist_bin = muted_label("Binary class distribution")
        dv.addWidget(self.lbl_dist_bin)
        self.class_dist = _ClassDist()
        dv.addWidget(self.class_dist)
        dv.addSpacing(12)
        self.lbl_dist_mc = muted_label("Multiclass class distribution")
        dv.addWidget(self.lbl_dist_mc)
        self.class_dist_mc = _ClassDist()
        dv.addWidget(self.class_dist_mc)
        dv.addStretch()
        top.addWidget(dist, stretch=3)
        tv.addLayout(top)
        return grp

    def _inputs_section(self):
        """The input channels."""
        grp = Section("Inputs")
        iv = QVBoxLayout(grp)
        iv.setSpacing(8)
        iv.addWidget(muted_label("Channels"))
        self.chan_grid = QGridLayout()
        self.chan_grid.setHorizontalSpacing(16)
        self.chan_grid.setVerticalSpacing(2)
        iv.addLayout(self.chan_grid)
        iv.addStretch()
        return grp

    def _sequence_section(self):
        """Sequence length, padding and truncation, and the input they
        make."""
        grp = Section("Sequence length")
        sv = QVBoxLayout(grp)
        sv.setSpacing(6)
        self.rb_seq_auto = QRadioButton("From the dataset")
        self.rb_seq_manual = QRadioButton("Specify")
        self.rb_seq_auto.setChecked(True)
        self.rb_seq_auto.toggled.connect(self._seq_changed)
        self.spin_seq = _spin(10, 100000, 400)
        self.spin_seq.setEnabled(False)
        self.spin_seq.valueChanged.connect(self._seq_changed)
        sv.addWidget(self.rb_seq_auto)
        seq_row = QHBoxLayout()
        seq_row.setSpacing(8)
        seq_row.addWidget(self.rb_seq_manual)
        seq_row.addWidget(self.spin_seq)
        seq_row.addStretch()
        sv.addLayout(seq_row)
        sv.addWidget(muted_label("Padding"))
        self.cmb_padding = _combo(("Repeat final observation", "repeat_last"))
        sv.addWidget(self.cmb_padding)
        sv.addWidget(muted_label("Truncation"))
        self.cmb_trunc = _combo(("Truncate to target length", "truncate"))
        sv.addWidget(self.cmb_trunc)
        self.lbl_tensor = QLabel("")
        self.lbl_tensor.setWordWrap(True)
        sv.addWidget(self.lbl_tensor)
        sv.addStretch()
        return grp

    def _weights_section(self):
        """Class weights, each class's weight and the decision threshold."""
        grp = Section("Class weights")
        wv = QVBoxLayout(grp)
        wv.setSpacing(6)
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
        wv.addLayout(w_row)
        self.lbl_weights = QLabel("")
        style(self.lbl_weights, role="muted")
        wv.addWidget(self.lbl_weights)
        t_row = QHBoxLayout()
        t_row.setSpacing(8)
        self.chk_fixed_thr = QCheckBox("Fixed decision threshold")
        self.chk_fixed_thr.setToolTip(
            "Unticked, the binary model's threshold is picked from "
            "cross-validation (Youden's J). Ticked, it's this value: "
            "cross-validation is scored at it and the model keeps it.")
        self.spin_fixed_thr = QDoubleSpinBox()
        self.spin_fixed_thr.setRange(0.01, 0.99)
        self.spin_fixed_thr.setDecimals(2)
        self.spin_fixed_thr.setSingleStep(0.05)
        self.spin_fixed_thr.setValue(0.5)
        self.spin_fixed_thr.setFixedWidth(FIELD_W)
        self.spin_fixed_thr.setEnabled(False)
        self.chk_fixed_thr.toggled.connect(self._threshold_changed)
        self.spin_fixed_thr.valueChanged.connect(self._threshold_changed)
        t_row.addWidget(self.chk_fixed_thr)
        t_row.addWidget(self.spin_fixed_thr)
        t_row.addStretch()
        wv.addLayout(t_row)
        wv.addStretch()
        return grp

    def _cv_section(self):
        """Validation, then the performance metric: the variables the
        out-of-fold performance is broken down by."""
        grp = Section("Cross-validation")
        outer = QVBoxLayout(grp)
        outer.setSpacing(8)
        vv = QGridLayout()
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
        vv.setColumnStretch(2, 1)
        outer.addLayout(vv)

        # the columns each strike's type is read from, for the performance
        # breakdown (direct, indirect, hub_0, ... - train_worker.
        # derive_strike_type): the derived variable's name, then the binary
        # and the multiclass model's own columns, three to a column; the
        # derived variables are the tooltip (_refresh_target)
        self.lbl_metric = muted_label("Performance metric")
        outer.addWidget(self.lbl_metric)
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_row.addWidget(muted_label("Variable name"))
        self.ed_breakdown_name = QLineEdit()
        self.ed_breakdown_name.setFixedWidth(FIELD_W + 60)
        self.ed_breakdown_name.setPlaceholderText("strike_type")
        self.ed_breakdown_name.setToolTip(
            "The name of the variable the performance is broken down by - "
            "Evaluate, its figure and the reports show it.")
        self.ed_breakdown_name.editingFinished.connect(
            self._breakdown_name_changed)
        name_row.addWidget(self.ed_breakdown_name)
        name_row.addStretch()
        outer.addLayout(name_row)
        self._breakdown_grids = {}
        for key, heading in (("binary", "Binary model"),
                             ("multiclass", "Multiclass model")):
            lab = muted_label(heading)
            outer.addWidget(lab)
            grid = QGridLayout()
            grid.setHorizontalSpacing(16)
            grid.setVerticalSpacing(2)
            outer.addLayout(grid)
            self._breakdown_grids[key] = (lab, grid)
        outer.addStretch()
        return grp

    def _model_section(self):
        """Configuration beside the workflow, in a box centred on the page:
        (1) Train model (CV), (2) Evaluate performance, (3) Train final
        model; the folds' progress and Console; one status line; the
        out-of-fold performance; the version, (4) Deploy model and Model
        information."""
        grp = Section("Model")
        centre = QHBoxLayout(grp)
        centre.addStretch()
        box = QFrame()
        style(box, role="box")
        centre.addWidget(box)
        centre.addStretch()
        row = QHBoxLayout(box)
        row.setContentsMargins(16, 12, 16, 12)
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
        cv.addLayout(mv)
        cv.addStretch()
        row.addWidget(config)

        # ── the workflow: train, evaluate, final model, deploy ─────────────
        train, gv = column("Train")
        # one status line for the whole box - every run and the deploy
        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        style(self.lbl_status, role="muted")
        self.deployment = DeploymentPanel(self.state, self.main_window, self,
                                          self.lbl_status)

        # three equal columns, so every button lines up: the steps, the
        # progress and Console, the status line, the OOF cards, then the
        # version, Deploy and Model information
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        self.btn_train = action_button("(1) Train model (CV)")
        self.btn_train.setEnabled(False)
        self.btn_train.clicked.connect(self.state.run_cv)
        self.btn_evaluate = action_button(
            "(2) Evaluate performance",
            "The cross-validation results in detail (Evaluate).")
        self.btn_evaluate.setEnabled(False)
        self.btn_evaluate.clicked.connect(
            lambda: self._goto_evaluate() if self._goto_evaluate else None)
        for c, btn in enumerate((self.btn_train, self.btn_evaluate,
                                 self.deployment.btn_final)):
            grid.addWidget(btn, 0, c)

        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self._progress_waiting()
        grid.addWidget(self.progress, 1, 0, 1, 2)
        # the worker's output goes to the app console (it tees print)
        self.btn_console = action_button(
            "Console", "Everything the app prints - the training run's "
            "progress included.")
        self.btn_console.clicked.connect(self._open_console)
        grid.addWidget(self.btn_console, 1, 2)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self.spinner = Spinner(size=18)
        self.spinner.setVisible(False)
        status_row.addWidget(self.spinner, alignment=Qt.AlignmentFlag.AlignTop)
        status_row.addWidget(self.lbl_status, stretch=1)
        grid.addLayout(status_row, 2, 0, 1, 3)

        cards = QHBoxLayout()
        cards.setSpacing(8)
        self.card_bin = MetaCard("Binary OOF")
        cards.addWidget(self.card_bin, stretch=1)
        self.card_mc = MetaCard("Multiclass OOF")
        self.card_mc.setToolTip(
            model_measures.AVERAGED_NOTE + " No decision threshold - the "
            "class with the highest score is the prediction.")
        cards.addWidget(self.card_mc, stretch=1)
        grid.addLayout(cards, 3, 0, 1, 3)

        # the version label and box as wide as a button
        version = QWidget()
        version.setFixedWidth(ACTION_W)
        vr = QHBoxLayout(version)
        vr.setContentsMargins(0, 0, 0, 0)
        vr.setSpacing(8)
        vr.addWidget(muted_label("Model version"))
        self.deployment.ed_version.setMinimumWidth(0)
        self.deployment.ed_version.setMaximumWidth(ACTION_W)
        vr.addWidget(self.deployment.ed_version, stretch=1)
        grid.addWidget(version, 4, 0)
        grid.addWidget(self.deployment.btn_deploy, 4, 1)
        grid.addWidget(self.deployment.btn_info, 4, 2)
        gv.addLayout(grid)
        gv.addStretch()
        row.addWidget(train)
        return grp

    def _progress_waiting(self):
        """The progress bar before a run (or after a failed one)."""
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFormat("Waiting for model run")

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
        s.final_finished.connect(self._on_final_finished)
        s.final_failed.connect(self._on_final_failed)

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
            self.btn_annotation_summary.setEnabled(s.dataset_df is not None)
            if self.annotation_summary.isVisible():
                # once the table's filters are back on
                QTimer.singleShot(0, self.annotation_summary.refresh)
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
        for key, chosen in (("binary", s.breakdown_columns),
                            ("multiclass", s.mc_breakdown_columns)):
            grid = self._breakdown_grids[key][1]
            self._clear_layout(grid)
            self._breakdown_checks[key] = {}
            for i, col in enumerate(s.breakdown_candidates()):
                chk = QCheckBox(col)
                chk.setChecked(col in chosen)
                chk.setToolTip(self.lbl_metric.toolTip())
                chk.toggled.connect(self._breakdown_changed)
                # down three, then the next column
                grid.addWidget(chk, i % 3, i // 3)
                self._breakdown_checks[key][col] = chk

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
                  + list(s.mc_breakdown_columns) + [s.region_column]):
            if c and c in df.columns and c not in cols:
                cols.append(c)
        # every sensor, one row each
        per_file = df.groupby("file").first().reset_index()[cols]
        self.tbl_preview.setColumnCount(len(cols))
        self.tbl_preview.setHorizontalHeaderLabels(cols)
        self.tbl_preview.setRowCount(len(per_file))
        for r, row in enumerate(per_file.itertuples(index=False)):
            for c, val in enumerate(row):
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
        ticked = {key: [c for c, chk in checks.items() if chk.isChecked()]
                  for key, checks in self._breakdown_checks.items()}
        self.state.update(breakdown_columns=ticked.get("binary", []),
                          mc_breakdown_columns=ticked.get("multiclass", []))
        self._fill_preview()

    def _breakdown_name_changed(self):
        if self._updating:
            return
        name = self.ed_breakdown_name.text().strip() or "strike_type"
        if name != self.state.breakdown_name:
            self.state.update(breakdown_name=name)

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

    def _threshold_changed(self):
        fixed = self.chk_fixed_thr.isChecked()
        self.spin_fixed_thr.setEnabled(fixed)
        if not self._updating:
            self.state.update(
                fixed_threshold=self.spin_fixed_thr.value() if fixed else None)

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
            ("Sensor",               recording_rate.sensor_name(
                m["identity"][recording_rate.SENSOR_COL]) if m.get("identity") else None),
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

        # how the derived 0/1 variable comes from the target - the
        # positive value's tooltip
        tip = ("The name of the derived 0/1 variable's 1 - the model's "
               "positive class.")
        if s.negative_class is not None and s.target_column:
            excluded = sorted(set(self._value_combos) - self._included())
            tip += (f"\n\n{pos} = 1 where {s.target_column} is any other "
                    f"included value, 0 where it is \"{s.negative_class}\"")
            if excluded:
                tip += f"; {', '.join(excluded)} left out"
            tip += "."
        self.ed_positive.setToolTip(tip)

        name = s.breakdown_name or "strike_type"
        if not self.ed_breakdown_name.hasFocus():
            self.ed_breakdown_name.setText(name)
        derived = [f"{pos} (0/1)"]
        for model, cols in (("binary", s.breakdown_columns),
                            ("multiclass", s.mc_breakdown_columns)):
            if cols:
                derived.append(f"{name} for the {model} model (each "
                               "strike's " + " / ".join(cols) + ")")
        tip = ("Each model's out-of-fold performance is also broken down by "
               f"{name}: a strike's first value in the variables ticked for "
               "that model.\n\nDerived variables: " + ", ".join(derived))
        self.lbl_metric.setToolTip(tip)
        for checks in self._breakdown_checks.values():
            for chk in checks.values():
                chk.setToolTip(tip)
        lab, grid = self._breakdown_grids["multiclass"]
        lab.setEnabled(s.train_multiclass)
        for chk in self._breakdown_checks.get("multiclass", {}).values():
            chk.setEnabled(s.train_multiclass)

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
        self.btn_evaluate.setEnabled(s.cv_done and not s.running)
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
        self.btn_evaluate.setEnabled(False)
        self.lbl_status.setToolTip("")
        self.card_bin.set_rows([])
        self.card_mc.set_rows([])
        self.spinner.start()
        self.progress.setFormat("%v/%m folds")
        n_models = 2 if self.state.train_multiclass else 1
        self.progress.setRange(0, max(1, self.state.n_folds * n_models))
        self.progress.setValue(0)
        self._elapsed.start()
        self._tick.start()
        style(self.lbl_status, tone="accent")
        self.lbl_status.setText("Training binary strike model")

    def _on_final_started(self):
        self.btn_evaluate.setEnabled(False)
        self.lbl_status.setToolTip("")
        self.spinner.start()
        self._elapsed.start()
        self._tick.start()
        style(self.lbl_status, tone="accent")
        self.lbl_status.setText("Training final deployment model  (0 s elapsed)")

    def _on_final_finished(self):
        self._stop_run_ui()
        style(self.lbl_status, tone="accent")
        self.lbl_status.setText("Final model saved")
        self.state.status.emit("Final deployment model(s) trained.", 5000)

    def _on_final_failed(self, msg):
        self._stop_run_ui()
        style(self.lbl_status, tone="bad")
        first = msg.strip().splitlines()[-1] if msg.strip() else "Unknown error"
        self.lbl_status.setText(f"✗ Final training failed: {first}")
        dlg = QMessageBox(self.main_window)
        dlg.setWindowTitle("Final model error")
        dlg.setIcon(QMessageBox.Icon.Critical)
        dlg.setText(f"Training the final model failed.\n\n{first}")
        dlg.setDetailedText(msg)
        dlg.exec()

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
        self.btn_train.setText("(1) Train model (CV)")
        self.btn_train.setEnabled(self.state.ready and not self.state.running)
        self.btn_evaluate.setEnabled(self.state.cv_done
                                     and not self.state.running)

    def _on_finished(self):
        self._stop_run_ui()
        self.progress.setValue(self.progress.maximum())
        s = self.state
        secs = self._elapsed.elapsed() / 1000
        style(self.lbl_status, tone="accent")
        self.lbl_status.setText(f"Cross-validation complete ({secs:.0f} s).")
        self._fill_performance()
        s.status.emit("Cross-validation complete.", 5000)

    def _on_failed(self, msg):
        self._stop_run_ui()
        self._progress_waiting()
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
        """The out-of-fold measures, by the names used everywhere
        (model_measures); the decision threshold for a binary model."""
        names = [label for label, _b, _m in model_measures.MEASURES]
        if model_measures.is_binary(metrics):
            names.append(model_measures.THRESHOLD)
        rows = [(n, model_measures.fmt(model_measures.value(metrics, n)))
                for n in names
                if model_measures.value(metrics, n) is not None]
        ho = (metrics or {}).get("holdout_performance")
        if ho:
            rows.append(("Hold-out test",
                         f"n = {ho.get('n_test')}, "
                         f"Accuracy = {ho.get('accuracy'):.3f}"))
        return rows

    def _fill_performance(self):
        s = self.state
        bin_res = s.model_results("binary")
        self.card_bin.set_rows(
            self._perf_rows(bin_res["metrics"]) if bin_res else [])
        mc_res = s.model_results("multiclass")
        # always shown - a binary-only run says so
        self.card_mc.set_rows(self._perf_rows(mc_res["metrics"]) if mc_res
                              else [("Multiclass model", "not in this run")])
