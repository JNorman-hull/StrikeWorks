# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Advanced analysis (Blade strike calculator's second tab - Calculator's
"Advanced model outputs").

  - Figures: the headline results as one 4-panel figure ((a) scaly
    collision, (b) scaly mortality, (c) eel collision, (d) eel mortality)
    and the sensitivity sweeps as another ((a)/(b) collision probability
    vs shaft speed / relative fish velocity, (c)/(d) mortality vs the
    same), one line per flow rate Q - over the ranges in Calculator's
    Advanced options (`BSMState.sweep_options`).
  - The Results table and the "Blade strike output" cards, scaly and eel.

The report is Export and report's Blade strike calculator section
(report_center.bsm_section). Follows `BSMState`, so it shows the latest
result however it was produced.
"""
from matplotlib.figure import Figure

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QSizePolicy, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from . import bsm_figures
from .bsm_model import sensitivity_sweeps
from .bsm_state import output_card_rows
from .canvas import FigureCanvas
from .cards import MetaCard
from .layout import centred, Page, scroll_page, Section, when_visible
from .tables import fit_height

_SPECIES = (("scaly", "Scaly"), ("eel", "Eel"))


class BSMAnalysisPage(Page):

    def __init__(self, main_window, bsm_state):
        super().__init__(main_window)
        self.bsm_state = bsm_state
        self.last_result = None
        # bsm_model.sensitivity_sweeps() of last_result at the current
        # sweep options - None until worked out (when the figure's shown)
        self.sweeps = None

        self._build(self)
        bsm_state.calculated.connect(self.update_from_result)
        bsm_state.calculated_all.connect(self._show_results)
        bsm_state.sweep_options_changed.connect(self._options_changed)
        self._show_results(bsm_state.results)
        self.update_from_result(bsm_state.last_result)

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, frame):
        v = scroll_page(frame)
        v.addWidget(self._figures_group())
        row = QHBoxLayout()
        row.addWidget(self._results_group(), stretch=1)
        row.addWidget(self._output_group(), stretch=1)
        v.addLayout(row)

    def _figures_group(self):
        g = Section("Figures")
        gv = QVBoxLayout(g)

        # the report's own two figures, at their report proportions
        # (12 x 12 cm and 20 x 16 cm) - the canvases still scale with the page
        w, h = bsm_figures.RESULTS_PANELS_CM
        self.fig_results = Figure(figsize=(w / 2.54, h / 2.54), dpi=100)
        w, h = bsm_figures.SWEEP_PANELS_CM
        self.fig_sweeps = Figure(figsize=(w / 2.54, h / 2.54), dpi=100)
        self.canvas_results = self._canvas(self.fig_results)
        self.canvas_sweeps = self._canvas(self.fig_sweeps)

        # one row each, centred at roughly the report figures' proportions
        # (square, and 20:16) rather than stretched across the page
        self.canvas_results.setMinimumHeight(460)
        self.canvas_results.setMaximumWidth(620)
        self.canvas_sweeps.setMinimumHeight(560)
        self.canvas_sweeps.setMaximumWidth(900)
        gv.addWidget(centred(self.canvas_results))
        gv.addWidget(centred(self.canvas_sweeps))
        return g

    @staticmethod
    def _canvas(fig):
        c = FigureCanvas(fig)
        c.setMinimumSize(220, 190)
        c.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        return c

    def _results_group(self):
        g = Section("Results")
        v = QVBoxLayout(g)
        self.results_tbl = QTableWidget(0, 6)
        self.results_tbl.setHorizontalHeaderLabels(
            ["Species", "Method", "Pco (%)", "fMR (%)", "Pm (%)", "S (%)"])
        self.results_tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        fit_height(self.results_tbl)
        v.addWidget(self.results_tbl)
        v.addStretch()
        return g

    def _output_group(self):
        g = Section("Blade strike output")
        row = QHBoxLayout(g)
        row.setSpacing(10)
        self.cards = {}
        for species, title in _SPECIES:
            self.cards[species] = MetaCard(title)
            row.addWidget(self.cards[species], stretch=1)
        return g

    # ── both species: table, cards, results figure ──────────────────────────
    # Figures are drawn when their canvas is on screen: rendering both takes
    # about a second, which would otherwise be spent at start-up.
    def _show_results(self, results):
        """Both species' results (Calculator runs scaly and eel every time
        - BSMState.calculated_all)."""
        results = results or {}
        rows = []
        for species, title in _SPECIES:
            res = results.get(species)
            self.cards[species].set_rows(output_card_rows(res) if res else [])
            if res is None:
                continue
            rows.append((title, "CEN", res["Pco_tip"], res["fMR_tip"],
                         res["Pm"], res["S"]))
            if "Pco_obs" in res:
                rows.append((title, "Observed", res["Pco_obs"], res["fMR_tip"],
                             res["Pm_obs"], res["S_obs"]))
        tbl = self.results_tbl
        tbl.setRowCount(len(rows))
        for r, (title, method, *values) in enumerate(rows):
            cells = [title, method] + [f"{v * 100:.4f}" for v in values]
            for c, text in enumerate(cells):
                tbl.setItem(r, c, QTableWidgetItem(text))
        tbl.resizeColumnsToContents()
        fit_height(tbl)

        def draw():
            bsm_figures.draw_results_panels(self.fig_results, results, dark=True)
            self.canvas_results.draw()
        when_visible(self.canvas_results, draw, key="figure")

    # ── the sweeps (scaly, the Calculator's single result) ──────────────────
    def update_from_result(self, res):
        self.last_result = res
        self.sweeps = None
        self._draw_sweeps()

    def _options_changed(self):
        self.sweeps = None
        self._draw_sweeps()

    def _draw_sweeps(self):
        """Worked out and drawn once the figure is on screen - a slider
        dragged on Calculator costs nothing until then."""
        def draw():
            res = self.last_result
            if res is not None and self.sweeps is None:
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                try:
                    self.sweeps = sensitivity_sweeps(
                        res["params"], **self.bsm_state.sweep_options)
                except Exception as e:
                    self.status.emit(f"Sensitivity sweep failed: {e}", 6000)
                finally:
                    QApplication.restoreOverrideCursor()
            title = (bsm_figures.sweep_panels_title(res["params"]["species"],
                                                    res["params"])
                     if res is not None and self.sweeps else None)
            bsm_figures.draw_sweep_panels(self.fig_sweeps, self.sweeps,
                                          dark=True, title=title)
            self.canvas_sweeps.draw()
        when_visible(self.canvas_sweeps, draw, key="figure")
