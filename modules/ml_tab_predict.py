# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Predict tab - the primary operational screen of Model Prediction.

Presents the loaded model and dataset side by side, a real compatibility
check, the prediction configuration, the asynchronous run control and the
treatment-level results (cards, table, figures). All data comes from the
shared PredictionState - this module never loads models or datasets itself.
"""
import re
from pathlib import Path

from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from PySide6.QtCore import Qt, QElapsedTimer, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QPushButton, QScrollArea, QSizePolicy,
    QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import ml_figures
from .ml_widgets import (
    ACCENT, BAD, MUTED, OK, PALETTE, PINK, TEXT, WARN,
    CARD_W2, CARD_H2, MetaCard, RingCard, Spinner, Section, apply_section_defaults,
)

FIG_MIN_W, FIG_MIN_H = 320, 300


class _NumItem(QTableWidgetItem):
    """Table item that sorts by a numeric key rather than its display text."""

    def __init__(self, text, key):
        super().__init__(text)
        self._key = key

    def __lt__(self, other):
        if isinstance(other, _NumItem):
            return self._key < other._key
        return super().__lt__(other)


def _model_version(path):
    """Version implied by the model filename, e.g. binary1_1 -> 1.1."""
    if not path:
        return None
    m = re.search(r"(\d+(?:_\d+)*)$", Path(path).stem)
    return m.group(1).replace("_", ".") if m else None


# ═════════════════════════════════════════════════════════════════════════════
class PredictTab:
    """Builds the Predict tab UI into `frame` and binds it to `state`."""

    def __init__(self, frame, state, window, goto_inspect=None):
        self.state = state
        self.window = window
        self._goto_inspect = goto_inspect

        self._elapsed = QElapsedTimer()
        self._tick = QTimer()
        self._tick.setInterval(500)
        self._tick.timeout.connect(self._update_elapsed)

        self.fig_bin = Figure(figsize=(4.3, 3.4), dpi=100)
        self.canvas_bin = FigureCanvas(self.fig_bin)
        self.fig_mc = Figure(figsize=(4.3, 3.4), dpi=100)
        self.canvas_mc = FigureCanvas(self.fig_mc)
        for c in (self.canvas_bin, self.canvas_mc):
            c.setMinimumSize(FIG_MIN_W, FIG_MIN_H)
            c.setSizePolicy(QSizePolicy.Policy.Expanding,
                            QSizePolicy.Policy.Expanding)

        self._build(frame)
        self._connect_state()
        self._refresh_model()
        self._refresh_dataset()
        self._refresh_config()
        self._refresh_validation()

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, frame):
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea{border:none;background:transparent;}")
        outer.addWidget(scroll)

        body = QWidget()
        body.setStyleSheet("background:transparent;")
        scroll.setWidget(body)
        v = QVBoxLayout(body)
        v.setContentsMargins(4, 6, 4, 6)
        v.setSpacing(10)

        # ── row 1: model + dataset cards ────────────────────────────────────
        row1 = QHBoxLayout()
        row1.setSpacing(10)

        grp_model = Section("Model")
        mv = QVBoxLayout(grp_model)
        mv.setSpacing(8)
        self.card_model = MetaCard("Deployed model")
        mv.addWidget(self.card_model)

        perf_row = QHBoxLayout()
        perf_row.setSpacing(6)
        self.ring_acc  = RingCard("Accuracy",    w=CARD_W2, h=CARD_H2)
        self.ring_sens = RingCard("Sensitivity", w=CARD_W2, h=CARD_H2)
        self.ring_spec = RingCard("Specificity", w=CARD_W2, h=CARD_H2)
        self.ring_auc  = RingCard("ROC AUC",     w=CARD_W2, h=CARD_H2)
        for r in (self.ring_acc, self.ring_sens, self.ring_spec, self.ring_auc):
            perf_row.addWidget(r)
        perf_row.addStretch()
        mv.addLayout(perf_row)

        sel_row = QHBoxLayout()
        lab_bin_sel = QLabel("Binary")
        lab_bin_sel.setStyleSheet(f"color:{MUTED};")
        self.cmb_bin_model = QComboBox()
        self.cmb_bin_model.currentIndexChanged.connect(self._on_bin_model_picked)
        sel_row.addWidget(lab_bin_sel)
        sel_row.addWidget(self.cmb_bin_model, stretch=1)
        lab_mc_sel = QLabel("Multiclass")
        lab_mc_sel.setStyleSheet(f"color:{MUTED};")
        self.cmb_mc_model = QComboBox()
        self.cmb_mc_model.currentIndexChanged.connect(self._on_mc_model_picked)
        sel_row.addWidget(lab_mc_sel)
        sel_row.addWidget(self.cmb_mc_model, stretch=1)
        mv.addLayout(sel_row)

        mdl_btn_row = QHBoxLayout()
        self.btn_models = QPushButton("Change models folder…")
        self.btn_models.clicked.connect(self._change_models_folder)
        self.lbl_models_dir = QLabel("")
        self.lbl_models_dir.setStyleSheet(f"color:{MUTED};")
        self.lbl_models_dir.setWordWrap(True)
        mdl_btn_row.addWidget(self.btn_models)
        mdl_btn_row.addWidget(self.lbl_models_dir, stretch=1)
        mv.addLayout(mdl_btn_row)
        row1.addWidget(grp_model, stretch=1)

        grp_data = Section("Dataset")
        dv = QVBoxLayout(grp_data)
        dv.setSpacing(8)
        self.card_dataset = MetaCard("Curated sensor dataset")
        dv.addWidget(self.card_dataset)

        ds_btn_row = QHBoxLayout()
        self.btn_load_csv = QPushButton("Load dataset CSV…")
        self.btn_load_csv.clicked.connect(self._load_csv)
        ds_btn_row.addWidget(self.btn_load_csv)
        ds_btn_row.addStretch()
        dv.addLayout(ds_btn_row)
        row1.addWidget(grp_data, stretch=1)
        v.addLayout(row1)

        # ── row 2: configuration + run ──────────────────────────────────────
        row2 = QHBoxLayout()
        row2.setSpacing(10)

        grp_cfg = Section("Prediction configuration")
        gv = QVBoxLayout(grp_cfg)
        gv.setSpacing(8)

        mode_row = QHBoxLayout()
        lab_mode = QLabel("Model mode")
        lab_mode.setStyleSheet(f"color:{MUTED};")
        self.cmb_mode = QComboBox()
        self.cmb_mode.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(lab_mode)
        mode_row.addWidget(self.cmb_mode, stretch=1)
        gv.addLayout(mode_row)

        self.lbl_thresh = QLabel("Decision threshold: —")
        self.lbl_thresh.setStyleSheet(f"color:{TEXT};")
        gv.addWidget(self.lbl_thresh)

        th_row = QHBoxLayout()
        self.chk_override = QCheckBox("Override deployed threshold")
        self.chk_override.toggled.connect(self._on_override_toggled)
        self.spin_thresh = QDoubleSpinBox()
        self.spin_thresh.setRange(0.0, 1.0)
        self.spin_thresh.setDecimals(3)
        self.spin_thresh.setSingleStep(0.01)
        self.spin_thresh.setEnabled(False)
        self.spin_thresh.valueChanged.connect(self._on_threshold_edited)
        th_row.addWidget(self.chk_override)
        th_row.addWidget(self.spin_thresh)
        th_row.addStretch()
        gv.addLayout(th_row)

        self.lbl_override_note = QLabel(
            "⚠ You are overriding the deployed model threshold.")
        self.lbl_override_note.setStyleSheet(f"color:{WARN};")
        self.lbl_override_note.setVisible(False)
        gv.addWidget(self.lbl_override_note)

        gv.addStretch()
        row2.addWidget(grp_cfg, stretch=1)

        grp_run = Section("Run")
        rv = QVBoxLayout(grp_run)
        rv.setSpacing(8)
        run_row = QHBoxLayout()
        self.btn_run = QPushButton("Run prediction")
        self.btn_run.setMinimumHeight(36)
        self.btn_run.setEnabled(False)
        self.btn_run.clicked.connect(self.state.run_prediction)
        self.spinner = Spinner(size=26)
        self.spinner.setVisible(False)
        run_row.addWidget(self.btn_run, stretch=1)
        run_row.addWidget(self.spinner)
        rv.addLayout(run_row)

        self.lbl_run_status = QLabel("")
        self.lbl_run_status.setWordWrap(True)
        self.lbl_run_status.setStyleSheet(f"color:{MUTED};")
        self.lbl_run_status.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        rv.addWidget(self.lbl_run_status)

        self.btn_low_conf = QPushButton("Inspect low-confidence predictions →")
        self.btn_low_conf.setVisible(False)
        self.btn_low_conf.clicked.connect(self._inspect_low_conf)
        rv.addWidget(self.btn_low_conf)
        rv.addStretch()
        row2.addWidget(grp_run, stretch=1)
        v.addLayout(row2)

        # ── row 3: prediction summary cards ─────────────────────────────────
        grp_sum = Section("Prediction summary")
        sv = QHBoxLayout(grp_sum)
        sv.setSpacing(8)
        self.card_recordings = RingCard("Recordings (by treatment)")
        self.card_strikes    = RingCard("Predicted strikes")
        self.card_rate       = RingCard("Strike rate")
        self.card_conf       = RingCard("Mean confidence")
        self.card_regions    = RingCard("Strike classes")
        for c in (self.card_recordings, self.card_strikes, self.card_rate,
                  self.card_conf, self.card_regions):
            sv.addWidget(c)
        sv.addStretch()
        v.addWidget(grp_sum)

        # ── row 4: results table ────────────────────────────────────────────
        grp_tbl = Section("Results by treatment")
        tv = QVBoxLayout(grp_tbl)
        self.tbl = QTableWidget(0, 0)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tbl.setSortingEnabled(True)
        self.tbl.setMinimumHeight(160)
        self.tbl.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.itemSelectionChanged.connect(self._on_treatment_selected)
        tv.addWidget(self.tbl)
        v.addWidget(grp_tbl)

        # ── row 5: figures ──────────────────────────────────────────────────
        grp_figs = Section("Prediction figures")
        fv = QVBoxLayout(grp_figs)
        figs_split = QSplitter(Qt.Orientation.Horizontal)
        figs_split.setChildrenCollapsible(False)
        figs_split.addWidget(self.canvas_bin)
        figs_split.addWidget(self.canvas_mc)
        figs_split.setSizes([1, 1])
        fv.addWidget(figs_split)
        v.addWidget(grp_figs)

        v.addStretch()

        ml_figures.draw_strike_rate(self.fig_bin, None, dark=True)
        ml_figures.draw_region(self.fig_mc, None, [], dark=True)

        apply_section_defaults(frame)

    # ── state wiring ─────────────────────────────────────────────────────────
    def _connect_state(self):
        s = self.state
        s.models_changed.connect(self._refresh_model)
        s.dataset_changed.connect(self._refresh_dataset)
        s.validation_changed.connect(self._refresh_validation)
        s.config_changed.connect(self._refresh_config)
        s.run_started.connect(self._on_run_started)
        s.run_finished.connect(self._on_run_finished)
        s.run_failed.connect(self._on_run_failed)

    # ── model card ───────────────────────────────────────────────────────────
    def _refresh_model(self):
        s = self.state
        bm = s.bin_metrics or {}
        perf = bm.get("out_of_fold_performance", {})

        rows = [
            ("Binary model",     s.bin_model_path.name if s.bin_model_path else None),
            ("Model type",       bm.get("model")),
            ("Version",          _model_version(s.bin_model_path)),
            ("Mode",             "Binary + multiclass" if s.mc_model_path
                                 else ("Binary only" if s.bin_model_path else None)),
            ("Channels",         f"{bm.get('n_channels')} "
                                 f"({', '.join(bm.get('channels', [])[:3])}…)"
                                 if bm.get("channels") else None),
            ("Input window",     f"{bm.get('max_sequence_length')} samples"
                                 if bm.get("max_sequence_length") else None),
            ("Training samples", bm.get("n_samples")),
            ("Deployed threshold",
                                 f"{s.deployed_threshold:.4f}"
                                 if s.deployed_threshold is not None else None),
        ]
        if s.mc_model_path:
            mm = s.mc_metrics or {}
            rows += [
                ("Multiclass model", s.mc_model_path.name),
                ("Classes",          s.class_names),
                ("Multiclass accuracy",
                 f"{mm.get('out_of_fold_performance', {}).get('overall_accuracy'):.3f}"
                 if mm.get("out_of_fold_performance", {}).get("overall_accuracy")
                 is not None else None),
            ]
        elif s.bin_model_path:
            rows.append(("Multiclass model", "not found (binary-only mode)"))
        self.card_model.set_rows(rows)

        if s.bin_model_path and bm.get("channels"):
            tip = "Model channels:\n" + "\n".join(bm["channels"])
            self.card_model.setToolTip(tip)

        for ring, key in ((self.ring_acc, "overall_accuracy"),
                          (self.ring_sens, "sensitivity"),
                          (self.ring_spec, "specificity"),
                          (self.ring_auc, "roc_auc")):
            val = perf.get(key)
            if val is None:
                ring.clear()
            else:
                ring.set_value(float(val))

        self.lbl_models_dir.setText(str(s.models_dir))

        self.cmb_bin_model.blockSignals(True)
        self.cmb_bin_model.clear()
        for p in s.bin_candidates:
            self.cmb_bin_model.addItem(p.name, str(p))
        idx = self.cmb_bin_model.findData(
            str(s.bin_model_path) if s.bin_model_path else None)
        if idx >= 0:
            self.cmb_bin_model.setCurrentIndex(idx)
        self.cmb_bin_model.setEnabled(self.cmb_bin_model.count() > 1)
        self.cmb_bin_model.blockSignals(False)

        self.cmb_mc_model.blockSignals(True)
        self.cmb_mc_model.clear()
        self.cmb_mc_model.addItem("(none - binary only)", None)
        for p in s.mc_candidates:
            self.cmb_mc_model.addItem(p.name, str(p))
        idx = self.cmb_mc_model.findData(
            str(s.mc_model_path) if s.mc_model_path else None)
        self.cmb_mc_model.setCurrentIndex(idx if idx >= 0 else 0)
        self.cmb_mc_model.setEnabled(len(s.mc_candidates) > 0)
        self.cmb_mc_model.blockSignals(False)

    # ── dataset card ─────────────────────────────────────────────────────────
    def _refresh_dataset(self):
        s = self.state
        m = s.dataset_meta
        if not m:
            self.card_dataset.set_rows([("Dataset", "No dataset loaded")])
            return

        sr = m.get("sampling_rate_hz")
        seq = None
        if m.get("seq_len_min") is not None:
            if m["seq_len_min"] == m["seq_len_max"]:
                seq = f"{m['seq_len_max']} samples"
                if sr:
                    seq += f" ({m['seq_len_max'] / sr * 1000:.0f} ms)"
            else:
                seq = f"{m['seq_len_min']}–{m['seq_len_max']} samples (varying)"

        req = set(s.required_channels())
        n_chan_present = (len([c for c in m.get("columns", []) if c in req])
                          if req else None)

        self.card_dataset.set_rows([
            ("Dataset",       m.get("name")),
            ("Source",        s.dataset_source),
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

    # ── validation ───────────────────────────────────────────────────────────
    def _refresh_validation(self):
        # no persistent compatibility panel - Run itself triggers validate()
        # and surfaces any failure (see PredictionState.run_prediction);
        # this only needs to keep the button from being double-clicked
        # mid-run, not pre-emptively gate on readiness.
        self.btn_run.setEnabled(not self.state.running)

    # ── configuration ────────────────────────────────────────────────────────
    def _refresh_config(self):
        s = self.state
        labels = {"binary": "Binary (strike / no strike)",
                  "multiclass": "Multiclass (strike → region class)"}

        self.cmb_mode.blockSignals(True)
        self.cmb_mode.clear()
        for m in s.available_modes:
            self.cmb_mode.addItem(labels[m], m)
        idx = self.cmb_mode.findData(s.mode)
        if idx >= 0:
            self.cmb_mode.setCurrentIndex(idx)
        self.cmb_mode.setEnabled(self.cmb_mode.count() > 1)
        self.cmb_mode.blockSignals(False)

        dep = s.deployed_threshold
        if s.threshold_overridden:
            self.lbl_thresh.setText(
                f"Decision threshold: {s.threshold_override:.3f} "
                f"(deployed: {dep:.4f})" if dep is not None else
                f"Decision threshold: {s.threshold_override:.3f}")
        else:
            self.lbl_thresh.setText(
                f"Decision threshold: {dep:.4f} (deployed)"
                if dep is not None else "Decision threshold: —")

        self.chk_override.blockSignals(True)
        self.chk_override.setChecked(s.threshold_overridden)
        self.chk_override.setEnabled(s.bin_model_path is not None)
        self.chk_override.blockSignals(False)

        self.spin_thresh.blockSignals(True)
        self.spin_thresh.setEnabled(s.threshold_overridden)
        self.spin_thresh.setValue(
            s.threshold_override if s.threshold_overridden
            else (dep if dep is not None else 0.5))
        self.spin_thresh.blockSignals(False)
        self.lbl_override_note.setVisible(s.threshold_overridden)

    def _on_mode_changed(self):
        mode = self.cmb_mode.currentData()
        if mode:
            self.state.set_mode(mode)

    def _on_bin_model_picked(self):
        path = self.cmb_bin_model.currentData()
        if not path:
            return
        ok, msg = self.state.select_bin_model(path)
        if not ok:
            self.state.status.emit(f"Could not switch binary model: {msg}", 6000)

    def _on_mc_model_picked(self):
        path = self.cmb_mc_model.currentData()
        ok, msg = self.state.select_mc_model(path)
        if not ok:
            self.state.status.emit(f"Could not switch multiclass model: {msg}", 6000)

    def _on_override_toggled(self, checked):
        # the spinbox shows the deployed threshold while unchecked, so
        # enabling the override starts from the deployed value
        value = self.spin_thresh.value() if checked else None
        self.state.set_threshold_override(checked, value)

    def _on_threshold_edited(self, value):
        if self.chk_override.isChecked():
            self.state.set_threshold_override(True, value)

    # ── model / dataset pickers ──────────────────────────────────────────────
    def _change_models_folder(self):
        s = self.state
        start = str(s.models_dir if Path(s.models_dir).exists() else Path.cwd())
        path = QFileDialog.getExistingDirectory(
            self.window, "Select models folder", start)
        if not path:
            return
        ok, msg = s.load_models_from_dir(path)
        s.status.emit(msg, 6000)
        if not ok:
            QMessageBox.warning(self.window, "Model loading", msg)

    def _load_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self.window, "Load dataset CSV", str(Path.cwd()),
            "CSV files (*.csv)")
        if not path:
            return
        ok, msg = self.state.load_dataset_csv(path)
        self.state.status.emit(msg, 6000)
        if not ok:
            QMessageBox.warning(self.window, "Dataset loading", msg)

    # ── run lifecycle ────────────────────────────────────────────────────────
    def _on_run_started(self):
        n = self.state.dataset_meta.get("n_files", "?")
        self.btn_run.setEnabled(False)
        self.btn_run.setText("Running…")
        self.btn_low_conf.setVisible(False)
        self.spinner.start()
        self._elapsed.start()
        self._tick.start()
        self.lbl_run_status.setStyleSheet(f"color:{ACCENT};")
        self.lbl_run_status.setText(f"Predicting {n} recordings…")

    def _update_elapsed(self):
        secs = self._elapsed.elapsed() // 1000
        n = self.state.dataset_meta.get("n_files", "?")
        self.lbl_run_status.setText(
            f"Predicting {n} recordings…  {secs} s elapsed")

    def _stop_run_ui(self):
        self._tick.stop()
        self.spinner.stop()
        self.btn_run.setText("Run prediction")
        self.btn_run.setEnabled(True)

    def _on_run_finished(self):
        self._stop_run_ui()
        s = self.state
        meta = s.run_meta
        n = meta.get("n_files", 0)
        k = meta.get("n_strike", 0)
        rate = meta.get("strike_rate", 0.0) * 100
        secs = self._elapsed.elapsed() / 1000
        self.lbl_run_status.setStyleSheet(f"color:{OK};")
        self.lbl_run_status.setText(
            f"Prediction complete ({secs:.1f} s)\n"
            f"{n} recordings processed\n"
            f"{k} strikes detected\n"
            f"{rate:.1f}% predicted strike rate")

        # low-confidence shortcut into Inspect
        if s.predictions is not None and "confidence" in s.predictions.columns:
            n_low = int((s.predictions["confidence"]
                         < s.low_conf_threshold).sum())
            if n_low and self._goto_inspect:
                self.btn_low_conf.setText(f"Inspect low confidence ({n_low}) →")
                self.btn_low_conf.setToolTip(
                    f"{n_low} prediction(s) below confidence "
                    f"{s.low_conf_threshold:.2f} - open them in Inspect")
                self.btn_low_conf.setVisible(True)

        self._populate_summary_cards()
        self._populate_table()
        ml_figures.draw_strike_rate(self.fig_bin, s.summary, dark=True)
        self.canvas_bin.draw()
        mc_run = s.run_meta.get("mode") == "multiclass"
        ml_figures.draw_region(self.fig_mc, s.summary,
                               s.class_names if mc_run else [], dark=True)
        self.canvas_mc.draw()
        s.status.emit(f"Prediction complete — {k} strikes in {n} recordings.",
                      6000)

    def _on_run_failed(self, msg):
        self._stop_run_ui()
        self.lbl_run_status.setStyleSheet(f"color:{BAD};")
        msg = msg.strip() or "Unknown error"
        if msg.startswith("Prediction is not ready"):
            # a pre-flight compatibility failure - short, already itemised
            # by validate(), and expected (missing dataset, wrong mode) -
            # the status line is enough, no need to interrupt with a modal
            self.lbl_run_status.setText(f"✗ {msg}")
            return
        first = msg.splitlines()[-1]
        self.lbl_run_status.setText(f"✗ Prediction failed: {first}")
        dlg = QMessageBox(self.window)
        dlg.setWindowTitle("Prediction error")
        dlg.setIcon(QMessageBox.Icon.Critical)
        dlg.setText("The prediction worker failed.\n\n"
                    f"{first}\n\nFull details below.")
        dlg.setDetailedText(msg)
        dlg.exec()

    # ── summary cards ────────────────────────────────────────────────────────
    def _populate_summary_cards(self):
        s = self.state
        df = s.summary
        if df is None or not len(df):
            for c in (self.card_recordings, self.card_strikes, self.card_rate,
                      self.card_conf, self.card_regions):
                c.clear()
            return

        n_total  = int(df["n"].sum())
        n_strike = int(df["n_strike"].sum())

        self.card_recordings.set_segments([
            (str(r["treatment"]), int(r["n"]), PALETTE[i % len(PALETTE)])
            for i, (_, r) in enumerate(df.iterrows())
        ])
        self.card_strikes.set_segments([
            ("Strike",    n_strike,           PINK),
            ("No strike", n_total - n_strike, PALETTE[0]),
        ])
        rate = n_strike / n_total if n_total else 0.0
        self.card_rate.set_value(rate, f"{rate * 100:.1f}%")

        if s.predictions is not None and "confidence" in s.predictions.columns:
            conf = float(s.predictions["confidence"].mean())
            self.card_conf.set_value(conf, f"{conf:.3f}")
        else:
            self.card_conf.clear()

        mc_run = s.run_meta.get("mode") == "multiclass"
        have = mc_run and s.class_names and all(
            f"n_{cn}" in df.columns for cn in s.class_names)
        self.card_regions.setVisible(bool(have))
        if have:
            self.card_regions.set_segments([
                (cn, int(df[f"n_{cn}"].sum()), PALETTE[i % len(PALETTE)])
                for i, cn in enumerate(s.class_names)
            ])
        else:
            self.card_regions.clear()

    # ── results table ────────────────────────────────────────────────────────
    def _populate_table(self):
        s = self.state
        df = s.summary
        mc_run = s.run_meta.get("mode") == "multiclass"
        class_names = s.class_names if (mc_run and s.class_names and df is not None
                                        and all(f"n_{cn}" in df.columns
                                                for cn in s.class_names)) else []

        headers = (["Treatment", "N", "Strikes", "No strike", "Strike rate",
                    "95% CI", "Mean prob", "Mean conf"]
                   + list(class_names))

        self.tbl.setSortingEnabled(False)
        self.tbl.clear()
        self.tbl.setColumnCount(len(headers))
        self.tbl.setHorizontalHeaderLabels(headers)
        self.tbl.setRowCount(0 if df is None else len(df))
        if df is None:
            self.tbl.setSortingEnabled(True)
            return

        for row, (_, r) in enumerate(df.iterrows()):
            n_strike = int(r["n_strike"])
            items = [
                QTableWidgetItem(str(r["treatment"])),
                _NumItem(str(int(r["n"])), int(r["n"])),
                _NumItem(str(n_strike), n_strike),
                _NumItem(str(int(r["n_no_strike"])), int(r["n_no_strike"])),
                _NumItem(f"{r['strike_rate'] * 100:.1f}%", float(r["strike_rate"])),
                _NumItem(f"{r['ci_lo'] * 100:.1f}% – {r['ci_hi'] * 100:.1f}%",
                         float(r["ci_lo"])),
                _NumItem(f"{r['mean_prob']:.3f}", float(r["mean_prob"])),
                _NumItem(f"{r['mean_conf']:.3f}", float(r["mean_conf"])),
            ]
            for cn in class_names:
                nc = int(r[f"n_{cn}"])
                pct = nc / n_strike * 100 if n_strike else 0
                items.append(_NumItem(f"{nc} ({pct:.0f}%)", nc))

            for col, item in enumerate(items):
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tbl.setItem(row, col, item)
        self.tbl.setSortingEnabled(True)

    def _on_treatment_selected(self):
        items = self.tbl.selectedItems()
        if items:
            self.state.select_treatment(self.tbl.item(items[0].row(), 0).text())

    # ── navigation ───────────────────────────────────────────────────────────
    def _inspect_low_conf(self):
        if self._goto_inspect:
            self._goto_inspect("low_conf")
