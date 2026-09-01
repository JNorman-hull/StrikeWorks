# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Evaluate tab - interrogate any model's cross-validated performance.

Evaluates either a model trained in this session or any model already
deployed in the models folder (discovered by ``ml_model_library``), so a
previously deployed model can be reviewed without retraining it.

Shows performance cards, the CV mean±SD table, the evaluation figures
ported from the pipeline scripts, the misclassification (error-analysis)
table and performance stratification, and exports a complete model report.
"""
from pathlib import Path

from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSplitter,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import ml_model_library, ml_train_figures, settings
from .ml_tab_predict import _NumItem
from .ml_widgets import (
    BAD, MUTED, OK, TEXT, WARN, CARD_W2, CARD_H2, MetaCard, RingCard, Section,
    apply_section_defaults,
)

FIG_MIN_W, FIG_MIN_H = 300, 250


class EvaluateTab:
    """Builds the Evaluate tab UI into `frame`, bound to `state`."""

    def __init__(self, frame, state, window, models_dir=None):
        self.state = state
        self.window = window
        self.models_dir = Path(models_dir or settings.get_models_dir())
        self._entries = []
        self._entry = None

        self.figures = {}
        self.canvases = {}
        for name in ("fig1", "fig2", "fig3", "fig4", "fig5"):
            fig = Figure(figsize=(4.2, 3.4), dpi=100)
            canvas = FigureCanvas(fig)
            canvas.setMinimumSize(FIG_MIN_W, FIG_MIN_H)
            canvas.setSizePolicy(QSizePolicy.Policy.Expanding,
                                 QSizePolicy.Policy.Expanding)
            self.figures[name] = fig
            self.canvases[name] = canvas

        self._build(frame)
        if state is not None:
            state.cv_finished.connect(self._reload_sources)
        self._reload_sources()

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

        # ── model source ────────────────────────────────────────────────────
        sel_row = QHBoxLayout()
        lab_sel = QLabel("Model")
        lab_sel.setStyleSheet(f"color:{MUTED};")
        self.cmb_model = QComboBox()
        self.cmb_model.setSizePolicy(QSizePolicy.Policy.Expanding,
                                     QSizePolicy.Policy.Fixed)
        self.cmb_model.currentIndexChanged.connect(self._on_model_changed)
        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self._reload_sources)
        btn_folder = QPushButton("Models folder…")
        btn_folder.clicked.connect(self._change_models_dir)
        self.btn_report = QPushButton("Export model report…")
        self.btn_report.clicked.connect(self._export_report)
        sel_row.addWidget(lab_sel)
        sel_row.addWidget(self.cmb_model, stretch=1)
        sel_row.addWidget(btn_refresh)
        sel_row.addWidget(btn_folder)
        sel_row.addWidget(self.btn_report)
        v.addLayout(sel_row)

        self.lbl_source = QLabel("")
        self.lbl_source.setStyleSheet(f"color:{MUTED};")
        self.lbl_source.setWordWrap(True)
        v.addWidget(self.lbl_source)

        # ── performance cards ───────────────────────────────────────────────
        grp_perf = Section("Performance (out-of-fold)")
        pv = QHBoxLayout(grp_perf)
        pv.setSpacing(8)
        self.rings = []
        for _ in range(5):
            ring = RingCard("", w=CARD_W2 + 30, h=CARD_H2)
            ring.setMaximumWidth(CARD_W2 + 90)
            self.rings.append(ring)
            pv.addWidget(ring)
        self.card_detail = MetaCard("Details")
        pv.addWidget(self.card_detail, stretch=1)
        v.addWidget(grp_perf)

        # ── CV summary + error analysis ─────────────────────────────────────
        split2 = QSplitter(Qt.Orientation.Horizontal)
        split2.setChildrenCollapsible(False)
        grp_cv = Section("Cross-validation (mean ± SD across folds)")
        cv = QVBoxLayout(grp_cv)
        self.tbl_cv = self._make_table(["Metric", "Mean", "SD"])
        self.tbl_cv.setMinimumHeight(190)
        cv.addWidget(self.tbl_cv)
        split2.addWidget(grp_cv)

        grp_err = Section("Error analysis")
        ev = QVBoxLayout(grp_err)
        self.lbl_mis = QLabel("No model selected.")
        self.lbl_mis.setStyleSheet(f"color:{TEXT};")
        ev.addWidget(self.lbl_mis)
        self.lbl_err_note = QLabel("")
        self.lbl_err_note.setStyleSheet(f"color:{MUTED};")
        self.lbl_err_note.setWordWrap(True)
        ev.addWidget(self.lbl_err_note)
        ev.addStretch()
        split2.addWidget(grp_err)
        split2.setStretchFactor(0, 1)
        split2.setStretchFactor(1, 2)
        v.addWidget(split2)

        # ── figures ─────────────────────────────────────────────────────────
        grp_figs = Section("Evaluation figures")
        fg = QVBoxLayout(grp_figs)
        row1 = QSplitter(Qt.Orientation.Horizontal)
        row1.setChildrenCollapsible(False)
        for key in ("fig1", "fig2", "fig3"):
            row1.addWidget(self.canvases[key])
        row1.setSizes([1, 1, 1])
        row2 = QSplitter(Qt.Orientation.Horizontal)
        row2.setChildrenCollapsible(False)
        row2.addWidget(self.canvases["fig4"])
        row2.addWidget(self.canvases["fig5"])
        row2.setSizes([1, 2])
        figs_split = QSplitter(Qt.Orientation.Vertical)
        figs_split.setChildrenCollapsible(False)
        figs_split.addWidget(row1)
        figs_split.addWidget(row2)
        figs_split.setSizes([1, 1])
        fg.addWidget(figs_split)
        v.addWidget(grp_figs)

        # ── stratification ──────────────────────────────────────────────────
        split3 = QSplitter(Qt.Orientation.Horizontal)
        split3.setChildrenCollapsible(False)
        grp_type = Section("Performance by strike type / class")
        tv = QVBoxLayout(grp_type)
        self.tbl_type = self._make_table(["Strike type", "N", "Accuracy"])
        self.tbl_type.setMinimumHeight(160)
        tv.addWidget(self.tbl_type)
        split3.addWidget(grp_type)

        grp_tx = Section("Performance by treatment")
        xv = QVBoxLayout(grp_tx)
        self.tbl_tx = self._make_table([])
        self.tbl_tx.setMinimumHeight(160)
        xv.addWidget(self.tbl_tx)
        split3.addWidget(grp_tx)

        grp_report = Section("Model report")
        rv = QVBoxLayout(grp_report)
        self.btn_report2 = QPushButton("Generate model report")
        self.btn_report2.setMinimumHeight(36)
        self.btn_report2.clicked.connect(self._export_report)
        rv.addWidget(self.btn_report2)
        rv.addStretch()
        split3.addWidget(grp_report)

        split3.setStretchFactor(0, 1)
        split3.setStretchFactor(1, 1)
        split3.setStretchFactor(2, 1)
        v.addWidget(split3)
        v.addStretch()

        ml_train_figures.draw_all(self.figures, None, None, None, dark=True)

        apply_section_defaults(frame)

    @staticmethod
    def _make_table(headers):
        tbl = QTableWidget(0, len(headers))
        if headers:
            tbl.setHorizontalHeaderLabels(headers)
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.setSortingEnabled(True)
        tbl.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        tbl.horizontalHeader().setStretchLastSection(True)
        return tbl

    @staticmethod
    def _fill(tbl, headers, rows):
        tbl.setSortingEnabled(False)
        tbl.clear()
        tbl.setColumnCount(len(headers))
        tbl.setHorizontalHeaderLabels(headers)
        tbl.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, cell in enumerate(row):
                if isinstance(cell, tuple):
                    item = _NumItem(cell[0], cell[1])
                else:
                    item = QTableWidgetItem(str(cell))
                if c >= 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                tbl.setItem(r, c, item)
        tbl.setSortingEnabled(True)

    # ── model sources ────────────────────────────────────────────────────────
    def _change_models_dir(self):
        path = QFileDialog.getExistingDirectory(
            self.window, "Select models folder", str(self.models_dir))
        if path:
            self.models_dir = Path(path)
            self._reload_sources()

    def _reload_sources(self):
        """Session results first, then every deployed model on disk."""
        keep = self.cmb_model.currentText()
        self._entries = []
        if self.state is not None:
            self._entries += ml_model_library.session_entries(self.state)
        self._entries += ml_model_library.discover_models(self.models_dir)

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
        self.btn_report.setEnabled(self._entry is not None)
        self.btn_report2.setEnabled(self._entry is not None)
        self._refresh()

    # ── refresh ──────────────────────────────────────────────────────────────
    def _refresh(self):
        entry = self._entry
        m = entry.metrics if entry else {}
        cv_predictions = entry.cv_predictions if entry else None
        curves = entry.curves if entry else None
        perf = m.get("out_of_fold_performance", {})
        binary = "roc_auc" in perf or not m

        if entry is None:
            self.lbl_source.setText(
                f"No models found in {self.models_dir}. Train a model, or "
                "point at a different models folder.")
        elif entry.source == "deployed":
            extra = ("" if entry.cv_predictions is not None else
                     "  Cross-validation predictions are not available for "
                     "this model, so error analysis and per-recording "
                     "figures are omitted.")
            self.lbl_source.setText(
                f"Deployed model: {entry.model_path}{extra}")
        else:
            self.lbl_source.setText(
                "Cross-validation results from the model trained in this "
                "session.")

        # rings
        if binary:
            specs = [("ROC-AUC", "roc_auc"), ("PR-AUC", "pr_auc"),
                     ("Accuracy", "overall_accuracy"),
                     ("Sensitivity", "sensitivity"),
                     ("Specificity", "specificity")]
        else:
            specs = [("Accuracy", "overall_accuracy"),
                     ("Macro precision", "macro_precision"),
                     ("Macro recall", "macro_recall"),
                     ("Macro F1", "macro_f1"), ("", None)]
        for ring, (title, key) in zip(self.rings, specs):
            ring.set_title(title)
            val = perf.get(key) if key else None
            if val is None:
                ring.clear()
            else:
                ring.set_value(float(val))

        # detail card
        rows = []
        if binary:
            for key, label in (("precision", "Precision"),
                               ("f1_score", "F1-Score"), ("mcc", "MCC"),
                               ("FNR", "FNR"), ("FPR", "FPR"),
                               ("optimal_threshold", "Optimal threshold")):
                if key in perf:
                    rows.append((label, f"{perf[key]:.3f}"))
        else:
            for cn, pm in perf.get("per_class_metrics", {}).items():
                rows.append((cn, f"P={pm['precision']:.2f} "
                                 f"R={pm['recall']:.2f} "
                                 f"F1={pm['f1_score']:.2f} "
                                 f"(n={pm['support']})"))
        ho = m.get("holdout_performance")
        if ho:
            txt = f"n={ho.get('n_test')}, accuracy={ho.get('accuracy'):.3f}"
            if "roc_auc" in ho:
                txt += f", AUC={ho['roc_auc']:.3f}"
            if "macro_f1" in ho:
                txt += f", macro-F1={ho['macro_f1']:.3f}"
            rows.append(("Hold-out test set", txt))
        if m.get("n_samples"):
            rows.append(("Training observations", m["n_samples"]))
        self.card_detail.set_rows(rows)

        # CV table
        cv = m.get("cross_validation", {})
        cv_rows = []
        for key in sorted(k[5:] for k in cv if k.startswith("mean_")):
            mean, std = cv.get(f"mean_{key}"), cv.get(f"std_{key}")
            cv_rows.append([key, (f"{mean:.3f}", mean), (f"{std:.3f}", std)])
        if "n_folds" in cv:
            cv_rows.insert(0, ["n_folds", (str(cv["n_folds"]),
                                           cv["n_folds"]), ("-", 0)])
        self._fill(self.tbl_cv, ["Metric", "Mean", "SD"], cv_rows)

        # figures
        ml_train_figures.draw_all(self.figures, m or None, cv_predictions,
                                  curves, dark=True)
        for canvas in self.canvases.values():
            canvas.draw()

        self._refresh_errors(binary, m, cv_predictions)
        self._refresh_stratification(binary, m, cv_predictions)

    def _refresh_errors(self, binary, metrics, df):
        mis = (metrics or {}).get("misclassified", {})
        if binary:
            self.lbl_mis.setText(
                f"MISCLASSIFICATION   total: {mis.get('total', 0)}    "
                f"false positives: {mis.get('false_positives', 0)}    "
                f"false negatives: {mis.get('false_negatives', 0)}"
                if mis else "No model selected.")
        else:
            self.lbl_mis.setText(
                f"MISCLASSIFICATION   total: {mis.get('total', 0)}"
                + (f" of {len(df)}" if df is not None else "")
                if mis else "No model selected.")

        if df is None:
            self.lbl_err_note.setText(
                "Per-recording cross-validation predictions were not saved "
                "with this model, so the individual misclassifications "
                "cannot be listed. Models trained and deployed from this "
                "page keep them in their deployment package.")
            return
        self.lbl_err_note.setText(
            "The per-recording list moved to Model training > "
            "Misclassification analysis, where it can be reviewed against "
            "each sensor's signal and corrected.")

    def _refresh_stratification(self, binary, metrics, df):
        m = metrics or {}

        by_type = m.get("performance_by_strike_type", {})
        type_rows = [[st, (str(d["n_files"]), d["n_files"]),
                      (f"{d['accuracy']:.3f}", d["accuracy"])]
                     for st, d in by_type.items()]
        if not type_rows and df is not None and "true_class" in df.columns:
            for cn, grp in df.groupby("true_class"):
                type_rows.append([cn, (str(len(grp)), len(grp)),
                                  (f"{grp['correct'].mean():.3f}",
                                   grp["correct"].mean())])
        if not type_rows:
            per_class = m.get("out_of_fold_performance", {}).get(
                "per_class_metrics", {})
            type_rows = [[cn, (str(d["support"]), d["support"]),
                          (f"{d['recall']:.3f}", d["recall"])]
                         for cn, d in per_class.items()]
        self._fill(self.tbl_type,
                   ["Strike type / class", "N", "Accuracy / recall"],
                   type_rows)

        tx_rows = []
        if df is not None and "treatment" in df.columns:
            for tx, grp in df.groupby("treatment"):
                n = len(grp)
                acc = float(grp["correct"].mean())
                if binary:
                    tx_rows.append([
                        str(tx), (str(n), n),
                        (f"{acc:.3f}", acc),
                        (f"{grp['y_true'].mean() * 100:.1f}%",
                         float(grp["y_true"].mean())),
                        (f"{grp['y_pred'].mean() * 100:.1f}%",
                         float(grp["y_pred"].mean())),
                    ])
                else:
                    tx_rows.append([str(tx), (str(n), n), (f"{acc:.3f}", acc)])
        headers = (["Treatment", "N", "Accuracy", "True strike rate",
                    "Predicted strike rate"] if binary
                   else ["Treatment", "N strikes", "Accuracy"])
        self._fill(self.tbl_tx, headers, tx_rows)

    # ── report ───────────────────────────────────────────────────────────────
    def _export_report(self):
        if self._entry is None:
            return
        dirpath = QFileDialog.getExistingDirectory(
            self.window, "Export model report to folder…", "")
        if not dirpath:
            return
        app_version = getattr(self.state, "app_version", "") if self.state \
            else ""
        try:
            out = ml_model_library.export_model_report(
                self._entry, dirpath, app_version=app_version)
        except Exception as e:
            QMessageBox.critical(self.window, "Export failed", str(e))
            return
        if self.state is not None:
            self.state.status.emit(f"Model report exported to {out}", 6000)
        QMessageBox.information(
            self.window, "Model report",
            f"Report written to:\n\n{out}\n\n"
            + "\n".join(f"  • {p.name}" for p in sorted(out.glob('*'))))
