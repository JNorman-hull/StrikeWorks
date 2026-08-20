# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Cross-validate tab - run the training worker and watch it live.

The console keeps the pipeline scripts' full output (fold metrics, class
distributions, confusion matrices) exactly as a script run would print
them; the progress bar and summary panel sit on top of it, they do not
replace it.
"""
from PySide6.QtCore import QElapsedTimer, Qt, QTimer
from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from .ml_widgets import (
    ACCENT, BAD, MUTED, OK, TEXT, CheckList, MetaCard, Spinner,
)


class CrossValidateTab:
    """Builds the Cross-validate tab UI into `frame`, bound to `state`."""

    def __init__(self, frame, state, window, goto_evaluate=None):
        self.state = state
        self.window = window
        self._goto_evaluate = goto_evaluate

        self._elapsed = QElapsedTimer()
        self._tick = QTimer()
        self._tick.setInterval(500)
        self._tick.timeout.connect(self._update_elapsed)

        self._build(frame)
        self._connect_state()
        self._refresh_ready()

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, frame):
        root = QHBoxLayout(frame)
        root.setContentsMargins(4, 6, 4, 6)
        root.setSpacing(10)

        # left column: readiness + run control + summary (scrollable so the
        # two per-model summary cards never get compressed)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFixedWidth(450)
        left_scroll.setStyleSheet(
            "QScrollArea{border:none;background:transparent;}")
        left = QWidget()
        left.setStyleSheet("background:transparent;")
        left_scroll.setWidget(left)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 8, 0)
        lv.setSpacing(8)

        grp_ready = QGroupBox("Configuration")
        rv = QVBoxLayout(grp_ready)
        self.checklist = CheckList()
        rv.addWidget(self.checklist)
        lv.addWidget(grp_ready)

        grp_run = QGroupBox("Cross-validation")
        gv = QVBoxLayout(grp_run)
        gv.setSpacing(8)
        run_row = QHBoxLayout()
        self.btn_train = QPushButton("TRAIN MODEL")
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

        self.lbl_status = QLabel("Configure the run, then train. "
                                 "Cross-validation estimates performance "
                                 "before any deployment model is built.")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet(f"color:{MUTED};font-size:10px;")
        gv.addWidget(self.lbl_status)
        lv.addWidget(grp_run)

        grp_sum = QGroupBox("Out-of-fold performance")
        sv = QVBoxLayout(grp_sum)
        self.card_bin = MetaCard("Binary strike model")
        sv.addWidget(self.card_bin)
        self.card_mc = MetaCard("Multiclass region model")
        self.card_mc.setVisible(False)
        sv.addWidget(self.card_mc)
        self.btn_evaluate = QPushButton("Evaluate results →")
        self.btn_evaluate.setVisible(False)
        self.btn_evaluate.clicked.connect(
            lambda: self._goto_evaluate() if self._goto_evaluate else None)
        sv.addWidget(self.btn_evaluate)
        lv.addWidget(grp_sum)
        lv.addStretch()
        root.addWidget(left_scroll)

        # right: training console
        grp_console = QGroupBox("Training console")
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
        self.console.setStyleSheet(
            "QPlainTextEdit{background:#1b1e23;color:#d4d4d4;"
            "border:1px solid #2c313a;border-radius:4px;"
            "font-family:Consolas,monospace;font-size:9pt;}")
        cv.addWidget(self.console, stretch=1)
        root.addWidget(grp_console, stretch=1)

    # ── state wiring ─────────────────────────────────────────────────────────
    def _connect_state(self):
        s = self.state
        s.validation_changed.connect(self._refresh_ready)
        s.cv_started.connect(self._on_started)
        s.cv_line.connect(self._on_line)
        s.cv_progress.connect(self._on_progress)
        s.cv_finished.connect(self._on_finished)
        s.cv_failed.connect(self._on_failed)
        # final-model output also streams into this console
        s.final_started.connect(self._on_final_started)
        s.final_finished.connect(self._stop_run_ui)
        s.final_failed.connect(lambda _m: self._stop_run_ui())

    def _refresh_ready(self):
        s = self.state
        self.checklist.set_checks(s.checks, s.ready,
                                  ready_text="READY TO TRAIN",
                                  blocked_text="TRAINING UNAVAILABLE")
        self.btn_train.setEnabled(s.ready and not s.running)

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
        self.lbl_status.setStyleSheet(f"color:{ACCENT};font-size:10px;")
        self.lbl_status.setText("Training binary strike model…")

    def _on_final_started(self):
        self.console.appendPlainText("\n" + "─" * 60)
        self.spinner.start()
        self._elapsed.start()
        self._tick.start()
        self.lbl_status.setStyleSheet(f"color:{ACCENT};font-size:10px;")
        self.lbl_status.setText("Training final deployment model…")

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
        secs = self._elapsed.elapsed() // 1000
        if self.state.running:
            self.lbl_status.setText(
                self.lbl_status.text().split("(")[0].strip()
                + f"  ({secs} s elapsed)")

    def _stop_run_ui(self):
        self._tick.stop()
        self.spinner.stop()
        self.btn_train.setText("TRAIN MODEL")
        self.btn_train.setEnabled(self.state.ready and not self.state.running)

    def _on_finished(self):
        self._stop_run_ui()
        self.progress.setValue(self.progress.maximum())
        s = self.state
        secs = self._elapsed.elapsed() / 1000
        self.lbl_status.setStyleSheet(f"color:{OK};font-size:10px;")
        self.lbl_status.setText(
            f"✓ Cross-validation complete ({secs:.1f} s). Review the "
            "performance, then accept it on the Deploy tab to train the "
            "final model.")
        self._fill_summary()
        self.btn_evaluate.setVisible(True)
        s.status.emit("Cross-validation complete.", 5000)

    def _on_failed(self, msg):
        self._stop_run_ui()
        self.progress.setVisible(False)
        self.lbl_status.setStyleSheet(f"color:{BAD};font-size:10px;")
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

    def _fill_summary(self):
        s = self.state
        bin_res = s.model_results("binary")
        self.card_bin.set_rows(
            self._perf_rows(bin_res["metrics"]) if bin_res else [])
        mc_res = s.model_results("multiclass")
        self.card_mc.setVisible(mc_res is not None)
        if mc_res:
            self.card_mc.set_rows(self._perf_rows(mc_res["metrics"]))
