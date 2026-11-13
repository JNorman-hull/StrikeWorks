"""Evaluate: the cross-validated performance of a model trained this
session or of any model in the models folder (ml_model_library) - the
performance table, performance by class and by treatment, and the
evaluation figures.
"""
from pathlib import Path

from matplotlib.figure import Figure

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QPushButton, QSizePolicy,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import ml_model_library, ml_train_figures, model_measures, settings
from .canvas import FigureCanvas
from .layout import scroll_page, Section, when_visible
from .tables import fill_table_width, fit_height
from .theme import muted_label

# as wide as Model training's dataset row (Load training dataset… and
# Recently used…)
SELECTOR_W = 303
FIG_MIN_W = 240
FIG_H = 300                      # 20% taller than the 250 they were

# the figures' rows, each figure with its share of the row: a binary
# model's in thirds, a multiclass model's in halves, its last two thirds
# wide (None: the gap beside it)
_FIGURE_ROWS = {
    True: ((("roc", 1), ("pr", 1), ("confusion", 1)),
           (("probability", 1), ("by_type", 2))),
    False: ((("roc", 1), ("confusion", 1)),
            (("by_class", 1), ("probability", 1)),
            (("by_type", 2), (None, 1))),
}


class EvaluateTab(QWidget):
    """The Evaluate tab, bound to `state`."""

    def __init__(self, state, main_window, models_dir=None):
        super().__init__()
        self.state = state
        self.main_window = main_window
        self.models_dir = Path(models_dir or settings.get_models_dir())
        self._entries = []
        self._entry = None
        self._grid_binary = None         # the figure layout shown

        self.figures = {}
        self.canvases = {}
        for role in ("roc", "pr", "confusion", "probability", "by_class",
                     "by_type"):
            fig = Figure(figsize=(4.2, 3.0), dpi=100)
            canvas = FigureCanvas(fig)
            canvas.setMinimumWidth(FIG_MIN_W)
            canvas.setFixedHeight(FIG_H)
            # widths from the grid's equal columns alone, not the figures'
            # own preferred sizes
            canvas.setSizePolicy(QSizePolicy.Policy.Ignored,
                                 QSizePolicy.Policy.Fixed)
            self.figures[role] = fig
            self.canvases[role] = canvas

        self._build(self)
        if state is not None:
            state.cv_finished.connect(self.reload_sources)
        self.reload_sources()

    # layout
    def _build(self, frame):
        v = scroll_page(frame)

        # the model (where it's from: the list's tooltip)
        sel_row = QHBoxLayout()
        sel_row.addWidget(muted_label("Model"))
        self.cmb_model = QComboBox()
        self.cmb_model.setFixedWidth(SELECTOR_W)
        self.cmb_model.currentIndexChanged.connect(self._on_model_changed)
        sel_row.addWidget(self.cmb_model)
        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self.reload_sources)
        sel_row.addWidget(btn_refresh)
        sel_row.addStretch()
        v.addLayout(sel_row)

        # one table: out-of-fold, cross-validation, hold-out
        grp_perf = Section("Performance")
        pv = QVBoxLayout(grp_perf)
        pv.setSpacing(4)
        self.tbl_summary = QTableWidget(0, 0)
        self.tbl_summary.setProperty("noRowNumbers", True)  # its own header rows
        self.tbl_summary.horizontalHeader().setVisible(False)
        self.tbl_summary.verticalHeader().setVisible(False)
        self.tbl_summary.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        pv.addWidget(self.tbl_summary)
        self.lbl_averaged = muted_label(model_measures.AVERAGED_NOTE)
        self.lbl_averaged.setWordWrap(True)
        pv.addWidget(self.lbl_averaged)
        v.addWidget(grp_perf)

        # by class | by treatment
        grp_class = Section("Performance by class")
        cv = QHBoxLayout(grp_class)
        cv.setSpacing(10)
        self.tbl_class = self._make_table(model_measures.CLASS_HEADERS)
        self.tbl_tx = self._make_table(["Treatment", "n", "Accuracy"])
        for tbl in (self.tbl_class, self.tbl_tx):
            cv.addWidget(tbl, stretch=1)
        v.addWidget(grp_class)

        # figures (_layout_figures places them for the model)
        grp_figs = Section("Evaluation figures")
        self.fig_rows = QVBoxLayout(grp_figs)
        self.fig_rows.setSpacing(8)
        v.addWidget(grp_figs)
        v.addStretch()

        self._layout_figures(True)
        ml_train_figures.draw_all(self.figures, None, None, None, dark=True)

    def _layout_figures(self, binary):
        if binary == self._grid_binary:
            return
        self._grid_binary = binary
        while self.fig_rows.count():
            row = self.fig_rows.takeAt(0).layout()
            while row.count():
                row.takeAt(0)
        for canvas in self.canvases.values():
            canvas.setVisible(False)
        for figures in _FIGURE_ROWS[binary]:
            row = QHBoxLayout()
            row.setSpacing(8)
            for role, share in figures:
                if role is None:
                    row.addStretch(share)
                else:
                    row.addWidget(self.canvases[role], stretch=share)
                    self.canvases[role].setVisible(True)
            self.fig_rows.addLayout(row)

    @staticmethod
    def _make_table(headers):
        tbl = QTableWidget(0, len(headers))
        tbl.setProperty("noRowNumbers", True)
        tbl.setHorizontalHeaderLabels(headers)
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        # as big as its rows and columns - no scrolling
        tbl.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return tbl

    @staticmethod
    def _fill(tbl, headers, rows):
        """Rows of text, in the model's own order; the table as big as
        its rows and columns need, then filling its share of the width."""
        tbl.clear()
        tbl.setColumnCount(len(headers))
        tbl.setHorizontalHeaderLabels(headers)
        tbl.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, text in enumerate(row):
                tbl.setItem(r, c, QTableWidgetItem(str(text)))
        tbl.resizeColumnsToContents()
        tbl.setMinimumWidth(tbl.horizontalHeader().length()
                            + 2 * tbl.frameWidth())
        fit_height(tbl)
        fill_table_width(tbl)

    def _fill_summary(self, metrics):
        """model_measures.summary_table in the HIG peak analysis table's
        layout: a heading row over each group of measures, then a row per
        source (out-of-fold, cross-validation, hold-out)."""
        columns, rows = model_measures.summary_table(metrics)
        tbl = self.tbl_summary
        tbl.clearSpans()
        tbl.clear()
        tbl.setColumnCount(1 + len(columns))
        tbl.setRowCount(2 + len(rows))

        def put(r, c, text):
            tbl.setItem(r, c, QTableWidgetItem(text))

        put(0, 0, "")
        tbl.setSpan(0, 0, 2, 1)
        i = 0
        while i < len(columns):
            group = columns[i][0]
            span = 1
            while group and i + span < len(columns) \
                    and columns[i + span][0] == group:
                span += 1
            if group:
                put(0, 1 + i, group)
                if span > 1:
                    tbl.setSpan(0, 1 + i, 1, span)
                for k in range(span):
                    put(1, 1 + i + k, columns[i + k][1])
            else:
                put(0, 1 + i, columns[i][1])
                tbl.setSpan(0, 1 + i, 2, 1)
            i += span
        for r, (label, cells) in enumerate(rows, start=2):
            put(r, 0, label)
            for c, text in enumerate(cells, start=1):
                put(r, c, text)
        tbl.resizeColumnsToContents()
        fill_table_width(tbl)
        fit_height(tbl)

    # model sources
    def follow_default_models_dir(self):
        """Settings' models folder changed - follow it."""
        new = Path(settings.get_models_dir())
        if new != self.models_dir:
            self.models_dir = new
            self.reload_sources()

    def reload_sources(self):
        """Re-list the models: now if the tab is on screen, otherwise when
        it's next opened (reading every deployed model and drawing its
        figures takes a second or more)."""
        when_visible(self, self._reload_sources, key="sources")

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
        self._refresh()

    # refresh
    def _refresh(self):
        entry = self._entry
        m = entry.metrics if entry else {}
        cv_predictions = entry.cv_predictions if entry else None
        curves = entry.curves if entry else None
        binary = model_measures.is_binary(m) or not m

        # where the model is from: the list's tooltip
        if entry is None:
            tip = (f"No models found in {self.models_dir}. Train a model, or "
                   "choose another models folder in Settings.")
        elif entry.source == "deployed":
            tip = f"Deployed model: {entry.model_path}"
            if entry.cv_predictions is None:
                tip += ("\nCross-validation predictions are not available "
                        "for this model, so the per-recording figures are "
                        "omitted.")
        else:
            tip = ("Cross-validation results from the model trained in this "
                   "session.")
        self.cmb_model.setToolTip(tip)

        self._fill_summary(m)
        self.lbl_averaged.setVisible(not binary)
        self._fill(self.tbl_class, model_measures.CLASS_HEADERS,
                   model_measures.class_table(m))
        self._fill_treatments(binary, cv_predictions)

        self._layout_figures(binary)
        ml_train_figures.draw_all(self.figures, m or None, cv_predictions,
                                  curves, dark=True)
        for figures in _FIGURE_ROWS[binary]:
            for role, _share in figures:
                if role is not None:
                    self.canvases[role].draw()

    def _fill_treatments(self, binary, df):
        rows = []
        if df is not None and "treatment" in df.columns:
            for tx, grp in df.groupby("treatment"):
                row = [str(tx), len(grp), f"{grp['correct'].mean():.3f}"]
                if binary:
                    row += [f"{grp['y_true'].mean() * 100:.1f}%",
                            f"{grp['y_pred'].mean() * 100:.1f}%"]
                rows.append(row)
        headers = (["Treatment", "n", "Accuracy"]
                   + (["True strike rate", "Predicted strike rate"]
                      if binary else []))
        self._fill(self.tbl_tx, headers, rows)
