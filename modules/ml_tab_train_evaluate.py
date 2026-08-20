# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Evaluate tab - interrogate the cross-validated performance.

Performance cards, the CV mean±SD table, the evaluation figures ported from
the pipeline scripts, the misclassification (error-analysis) table and the
performance stratification by strike type and treatment. Everything reads
from the shared TrainingState results; nothing is recomputed by the model
stack.
"""
import pandas as pd

from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QScrollArea, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from . import ml_train_figures
from .ml_tab_predict import _NumItem
from .ml_widgets import (
    BAD, MUTED, OK, TEXT, WARN, CARD_W2, CARD_H2, MetaCard, RingCard,
)

FIG_MIN_W, FIG_MIN_H = 300, 260


class EvaluateTab:
    """Builds the Evaluate tab UI into `frame`, bound to `state`."""

    def __init__(self, frame, state, window):
        self.state = state
        self.window = window

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
        state.cv_finished.connect(self._refresh)
        self._refresh()

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

        # ── model selector (the pipeline trains two models) ─────────────────
        sel_row = QHBoxLayout()
        lab_sel = QLabel("Model")
        lab_sel.setStyleSheet(f"color:{MUTED};font-size:10px;")
        self.cmb_model = QComboBox()
        self.cmb_model.addItem("Binary — strike / no contact", "binary")
        self.cmb_model.addItem("Multiclass — strike region", "multiclass")
        self.cmb_model.currentIndexChanged.connect(self._refresh)
        sel_row.addWidget(lab_sel)
        sel_row.addWidget(self.cmb_model)
        sel_row.addStretch()
        v.addLayout(sel_row)

        # ── performance cards ───────────────────────────────────────────────
        grp_perf = QGroupBox("Performance (out-of-fold)")
        pv = QHBoxLayout(grp_perf)
        pv.setSpacing(8)
        self.rings = []
        for _ in range(5):
            ring = RingCard("", w=CARD_W2, h=CARD_H2)
            self.rings.append(ring)
            pv.addWidget(ring)
        self.card_detail = MetaCard("Details")
        pv.addWidget(self.card_detail, stretch=1)
        v.addWidget(grp_perf)

        # ── CV summary table ────────────────────────────────────────────────
        row2 = QHBoxLayout()
        row2.setSpacing(10)
        grp_cv = QGroupBox("Cross-validation (mean ± SD across folds)")
        cv = QVBoxLayout(grp_cv)
        self.tbl_cv = self._make_table(["Metric", "Mean", "SD"])
        self.tbl_cv.setMinimumHeight(180)
        cv.addWidget(self.tbl_cv)
        row2.addWidget(grp_cv, stretch=1)

        grp_err = QGroupBox("Error analysis")
        ev = QVBoxLayout(grp_err)
        self.lbl_mis = QLabel("No cross-validation run.")
        self.lbl_mis.setStyleSheet(f"color:{TEXT};font-size:10px;")
        ev.addWidget(self.lbl_mis)
        self.tbl_err = self._make_table([])
        self.tbl_err.setMinimumHeight(180)
        ev.addWidget(self.tbl_err)
        lab = QLabel("Misclassified recordings can be reviewed against their "
                     "sensor signals via Model Prediction → Inspect once the "
                     "model is deployed.")
        lab.setStyleSheet(f"color:{MUTED};font-size:9px;")
        lab.setWordWrap(True)
        ev.addWidget(lab)
        row2.addWidget(grp_err, stretch=2)
        v.addLayout(row2)

        # ── figures ─────────────────────────────────────────────────────────
        grp_figs = QGroupBox("Evaluation figures")
        fg = QGridLayout(grp_figs)
        fg.setSpacing(8)
        fg.addWidget(self.canvases["fig1"], 0, 0)
        fg.addWidget(self.canvases["fig2"], 0, 1)
        fg.addWidget(self.canvases["fig3"], 0, 2)
        fg.addWidget(self.canvases["fig4"], 1, 0)
        fg.addWidget(self.canvases["fig5"], 1, 1, 1, 2)
        v.addWidget(grp_figs)

        # ── stratification ──────────────────────────────────────────────────
        row4 = QHBoxLayout()
        row4.setSpacing(10)
        grp_type = QGroupBox("Performance by strike type")
        tv = QVBoxLayout(grp_type)
        self.tbl_type = self._make_table(["Strike type", "N", "Accuracy"])
        self.tbl_type.setMinimumHeight(150)
        tv.addWidget(self.tbl_type)
        row4.addWidget(grp_type, stretch=1)

        grp_tx = QGroupBox("Performance by treatment")
        xv = QVBoxLayout(grp_tx)
        self.tbl_tx = self._make_table([])
        self.tbl_tx.setMinimumHeight(150)
        xv.addWidget(self.tbl_tx)
        row4.addWidget(grp_tx, stretch=2)
        v.addLayout(row4)
        v.addStretch()

        ml_train_figures.draw_all(self.figures, None, None, None)

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

    # ── refresh ──────────────────────────────────────────────────────────────
    def _refresh(self):
        s = self.state
        trained = s.trained_kinds()
        self.cmb_model.setVisible(len(trained) > 1)
        kind = self.cmb_model.currentData() or "binary"
        if trained and kind not in trained:
            kind = trained[0]
        res = s.model_results(kind)
        m = res["metrics"] if res else {}
        cv_predictions = res["cv_predictions"] if res else None
        curves = res["curves"] if res else None

        perf = m.get("out_of_fold_performance", {})
        binary = "roc_auc" in perf or not m

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
        self.card_detail.set_rows(rows)

        # CV table
        cv = m.get("cross_validation", {})
        cv_rows = []
        for key in sorted(k[5:] for k in cv if k.startswith("mean_")):
            mean, std = cv.get(f"mean_{key}"), cv.get(f"std_{key}")
            cv_rows.append([key, (f"{mean:.3f}", mean), (f"{std:.3f}", std)])
        if "n_folds" in cv:
            cv_rows.insert(0, ["n_folds", (str(cv["n_folds"]),
                                           cv["n_folds"]), ("—", 0)])
        self._fill(self.tbl_cv, ["Metric", "Mean", "SD"], cv_rows)

        # figures
        ml_train_figures.draw_all(self.figures, m or None, cv_predictions,
                                  curves)
        for canvas in self.canvases.values():
            canvas.draw()

        self._refresh_errors(binary, m, cv_predictions)
        self._refresh_stratification(binary, m, cv_predictions)

    def _refresh_errors(self, binary, metrics, df):
        if df is None:
            self.lbl_mis.setText("No cross-validation run.")
            self._fill(self.tbl_err, [], [])
            return
        m = metrics.get("misclassified", {})
        if binary:
            self.lbl_mis.setText(
                f"MISCLASSIFICATION   total: {m.get('total', 0)}    "
                f"false positives: {m.get('false_positives', 0)}    "
                f"false negatives: {m.get('false_negatives', 0)}")
        else:
            self.lbl_mis.setText(
                f"MISCLASSIFICATION   total: {m.get('total', 0)} of "
                f"{len(df)}")

        rows = []
        if binary and "error_type" in df.columns:
            bad = df[df["error_type"] != "correct"]
            for _, r in bad.iterrows():
                err = "FP" if r["error_type"] == "false_positive" else "FN"
                rows.append([
                    str(r["file"]),
                    "Strike" if r["y_true"] == 1 else "No strike",
                    "Strike" if r["y_pred"] == 1 else "No strike",
                    (f"{r['probability']:.3f}", float(r["probability"])),
                    str(r.get("treatment", "—")),
                    err,
                ])
            headers = ["File", "True", "Predicted", "Probability",
                       "Treatment", "Error"]
        elif "true_class" in df.columns:
            bad = df[~df["correct"]]
            for _, r in bad.iterrows():
                rows.append([
                    str(r["file"]), str(r["true_class"]),
                    str(r["pred_class"]),
                    (f"{r['confidence']:.3f}", float(r["confidence"])),
                    str(r.get("treatment", "—")),
                ])
            headers = ["File", "True class", "Predicted class",
                       "Confidence", "Treatment"]
        else:
            headers = []
        self._fill(self.tbl_err, headers, rows)

    def _refresh_stratification(self, binary, metrics, df):
        m = metrics or {}

        by_type = m.get("performance_by_strike_type", {})
        type_rows = [[st, (str(d["n_files"]), d["n_files"]),
                      (f"{d['accuracy']:.3f}", d["accuracy"])]
                     for st, d in by_type.items()]
        if not type_rows and df is not None \
                and "true_class" in df.columns:
            for cn, grp in df.groupby("true_class"):
                type_rows.append([cn, (str(len(grp)), len(grp)),
                                  (f"{grp['correct'].mean():.3f}",
                                   grp["correct"].mean())])
        self._fill(self.tbl_type, ["Strike type / class", "N", "Accuracy"],
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
