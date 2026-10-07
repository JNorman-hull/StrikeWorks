# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Model comparison (Model prediction).

Collision: each treatment's strike rate from the model against the BSM
collision probability, as a figure and a table, plus manual Video observed
and Model 1 counts shown as their own bars (Wilson 95 % CI).

Mortality: the current model's strike rate put through each species' BSM
injury model (`bsm_model.mortality_from_strike_rate`, the same formula as
the BSM's observed-counts mortality) - the model-projected mortality -
against the BSM's own mortality and any video-observed mortality, as a
figure beside the collision figure and extra table columns. The manual
Model 1 counts get no projected mortality (no BSM run behind them).

Layout: Filters (the same Deployment / Treatment / Run filters as Raw data
processing) and the three input boxes on the left, figures over the table
on the right. The filters narrow the prediction's per-recording results
and each treatment's strike rate and CI are recomputed from those.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSizePolicy, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from matplotlib.figure import Figure

from . import bsm_figures
from .bsm_model import mortality_from_strike_rate
from .canvas import FigureCanvas
from .library_widgets import LibrarySelector
from .ml_model_library import model_display_name
from .layout import apply_section_defaults, Page, scroll_area, scroll_page, Section
from .theme import muted_label, style
from .wilson_calc import wilson_interval

# the report's comparison figures: 12 x 10 cm up to three bars, 16 x 10 above
COMPARISON_SIZE_CM = ((12.0, 10.0), (16.0, 10.0))


def comparison_size_cm(n_bars):
    return COMPARISON_SIZE_CM[0] if n_bars <= 3 else COMPARISON_SIZE_CM[1]


def _pct(value):
    """A percentage for the table - two decimals below 1% (mortality is
    often that small), one above."""
    return f"{value:.2f}%" if value < 1 else f"{value:.1f}%"


def _pct_ci(value, lo, hi):
    return f"{_pct(value)} [{_pct(lo)}, {_pct(hi)}]"


def _text(value):
    if value is None:
        return ""
    s = str(value).strip()
    return "" if s.lower() == "nan" else s


def _run_text(value):
    """Run as the raw layout names it ("1"), whether the prediction
    results carry it as 1, 1.0 or "1"."""
    s = _text(value)
    try:
        f = float(s)
        return str(int(f)) if f.is_integer() else s
    except ValueError:
        return s


def _count_form():
    form = QGridLayout()
    form.setHorizontalSpacing(8)
    form.setColumnStretch(1, 1)
    return form


def _count_row(form, label, changed):
    """A count box on its own row of `form`, after its label."""
    spin = QSpinBox()
    spin.setRange(0, 1000000)
    spin.valueChanged.connect(changed)
    row = form.count() // 2
    form.addWidget(muted_label(label, wrap=True), row, 0)
    form.addWidget(spin, row, 1)
    return spin


class ModelComparisonPage(Page):

    def __init__(self, main_window, bsm_state, prediction_state=None):
        super().__init__(main_window)
        self.bsm_state = bsm_state
        self.prediction_state = prediction_state
        self.session_state = getattr(main_window, "session_state", None)
        # what the figure last drew - the report re-renders it at its
        # own fixed size from these
        self.cen_values = {}
        self.comparisons = []
        self.mortality_items = []
        self.model_name = "Model"
        self._build(self)
        bsm_state.calculated_all.connect(self._refresh_comparison)
        if prediction_state is not None:
            prediction_state.run_finished.connect(self._refresh_comparison)
        self.lib_selector.filters_changed.connect(self._refresh_comparison)
        self._refresh_comparison()

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, frame):
        v = scroll_page(frame)
        v.addWidget(self._comparison_group(), stretch=1)
        apply_section_defaults(frame)

    def _comparison_group(self):
        g = Section("Comparison")
        gv = QVBoxLayout(g)

        # the inputs scroll in their own column, so they keep their size
        # while the figures fill the height there is
        column = self._inputs_column()
        inputs = scroll_area(column)
        inputs.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # never narrower than the inputs themselves, beside their scrollbar;
        # opened wide enough for the filters' names
        inputs.setMinimumWidth(column.minimumSizeHint().width()
                               + inputs.verticalScrollBar().sizeHint().width() + 6)
        inputs.setMaximumWidth(max(480, inputs.minimumWidth()))
        names = max(c.sizeHint().width() - c.minimumSizeHint().width()
                    for c in (self.lib_selector.cmb_deployment,
                              self.lib_selector.cmb_treatment,
                              self.lib_selector.cmb_run))
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.addWidget(inputs)
        split.addWidget(self._results_column())
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([min(inputs.minimumWidth() + names,
                            inputs.maximumWidth()), 1000])
        gv.addWidget(split)
        return g

    def _inputs_column(self):
        """Filters, then Video observed / Model 1 / Blade strike model."""
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 4, 0)
        lv.setSpacing(8)

        self.lib_selector = LibrarySelector(self.session_state)
        btn_rescan = QPushButton("Rescan folders")
        btn_rescan.setToolTip("Pick up deployments, treatments or runs added "
                              "to the library's raw folders since it was "
                              "opened.")
        btn_rescan.clicked.connect(lambda: self.lib_selector.rescan())
        self.lib_selector.section_layout.addWidget(btn_rescan)
        lv.addWidget(self.lib_selector)

        lv.addWidget(self._video_observed_group())
        lv.addWidget(self._model1_group())
        lv.addWidget(self._bsm_group())
        lv.addStretch()
        return left

    def _results_column(self):
        """The collision and mortality figures side by side, half the
        width each, over the table, the figures taking two thirds of the
        height."""
        self.fig_compare = Figure(figsize=(3.5, 3.2), dpi=100)
        self.canvas_compare = FigureCanvas(self.fig_compare)
        self.fig_mortality = Figure(figsize=(3.5, 3.2), dpi=100)
        self.canvas_mortality = FigureCanvas(self.fig_mortality)
        for canvas in (self.canvas_compare, self.canvas_mortality):
            canvas.setMinimumSize(200, 240)
            canvas.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # redrawn at their real size - the bar labels' angle depends on it
        self.canvas_compare.mpl_connect(
            "resize_event", lambda _e: self._draw_compare())
        self.canvas_mortality.mpl_connect(
            "resize_event", lambda _e: self._draw_mortality())

        figs = QSplitter(Qt.Orientation.Horizontal)
        figs.setChildrenCollapsible(False)
        figs.addWidget(self.canvas_compare)
        figs.addWidget(self.canvas_mortality)
        figs.setStretchFactor(0, 1)
        figs.setStretchFactor(1, 1)
        figs.setSizes([1000, 1000])

        self.tbl_compare = QTableWidget(0, 12)
        self.tbl_compare.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_compare.setMinimumHeight(110)

        right = QSplitter(Qt.Orientation.Vertical)
        right.setChildrenCollapsible(False)
        right.addWidget(figs)
        right.addWidget(self.tbl_compare)
        right.setStretchFactor(0, 2)
        right.setStretchFactor(1, 1)
        right.setSizes([2000, 1000])
        return right

    def _video_observed_group(self):
        g = Section("Video observed")
        gv = QVBoxLayout(g)
        head = QHBoxLayout()
        self.ed_video_label = QLineEdit("Video observed")
        self.ed_video_label.setToolTip("Label shown on the table/figure.")
        self.ed_video_label.textChanged.connect(self._refresh_comparison)
        head.addWidget(self.ed_video_label, stretch=1)
        self.chk_video_plot = QCheckBox("Plot")
        self.chk_video_plot.setChecked(True)
        self.chk_video_plot.toggled.connect(self._refresh_comparison)
        head.addWidget(self.chk_video_plot)
        gv.addLayout(head)

        form = _count_form()
        self.spin_manual_total = _count_row(form, "Sensors deployed",
                                            self._refresh_comparison)
        self.spin_manual_strike = _count_row(form, "Strikes observed",
                                             self._refresh_comparison)
        self.spin_manual_mort = _count_row(form, "Mortalities observed",
                                           self._refresh_comparison)
        self.spin_manual_mort.setToolTip(
            "Fish killed, out of the sensors deployed - the observed "
            "mortality the mortality figure compares against.")
        gv.addLayout(form)
        self.lbl_manual = QLabel("")
        style(self.lbl_manual)
        self.lbl_manual.setWordWrap(True)
        gv.addWidget(self.lbl_manual)
        return g

    def _model1_group(self):
        g = Section("Model 1")
        gv = QVBoxLayout(g)
        head = QHBoxLayout()
        self.ed_model1_label = QLineEdit("Model 1")
        self.ed_model1_label.setToolTip("Label shown on the table/figure.")
        self.ed_model1_label.textChanged.connect(self._refresh_comparison)
        head.addWidget(self.ed_model1_label, stretch=1)
        self.chk_model1_plot = QCheckBox("Plot")
        self.chk_model1_plot.setChecked(True)
        self.chk_model1_plot.toggled.connect(self._refresh_comparison)
        head.addWidget(self.chk_model1_plot)
        gv.addLayout(head)

        form = _count_form()
        self.spin_model1_total = _count_row(form, "Sensors deployed",
                                            self._refresh_comparison)
        self.spin_model1_strike = _count_row(form, "Predicted strike",
                                             self._refresh_comparison)
        gv.addLayout(form)
        self.lbl_model1 = QLabel("")
        style(self.lbl_model1)
        self.lbl_model1.setWordWrap(True)
        gv.addWidget(self.lbl_model1)
        return g

    def _bsm_group(self):
        g = Section("Blade strike model")
        gv = QVBoxLayout(g)
        head = QHBoxLayout()
        self.ed_bsm_label = QLineEdit("Blade strike model")
        self.ed_bsm_label.setToolTip("Label shown on the table/figure.")
        self.ed_bsm_label.textChanged.connect(self._refresh_comparison)
        head.addWidget(self.ed_bsm_label, stretch=1)
        gv.addLayout(head)

        # each species' tick box (plot its bars) over its two values, so
        # the column stays narrow
        form = QGridLayout()
        form.setHorizontalSpacing(8)
        form.setColumnMinimumWidth(0, 12)
        form.setColumnStretch(2, 1)

        def species_rows(name, row):
            box = QCheckBox(name)
            box.setChecked(True)
            box.setToolTip(f"Plot the {name.lower()} Blade Strike Model "
                           "bars.")
            box.toggled.connect(self._refresh_comparison)
            form.addWidget(box, row, 0, 1, 3)
            values = []
            for i, what in enumerate(("Collision", "Mortality"), start=1):
                lab = QLabel("Not calculated")
                style(lab)
                lab.setWordWrap(True)
                form.addWidget(muted_label(what), row + i, 1)
                form.addWidget(lab, row + i, 2)
                values.append(lab)
            return box, values[0], values[1]

        (self.chk_scaly_show, self.lbl_scaly_value,
         self.lbl_scaly_mort) = species_rows("Scaly", 0)
        (self.chk_eel_show, self.lbl_eel_value,
         self.lbl_eel_mort) = species_rows("Eel", 3)
        gv.addLayout(form)
        note = muted_label(
            "Collision probability (Pco) and mortality (Pm) from the Blade "
            "Strike Model. The model-projected mortality puts the current "
            "model's predicted strike rate through the same injury model.", wrap=True)
        note.setWordWrap(True)
        gv.addWidget(note)
        return g

    # ── filtered per-treatment results ──────────────────────────────────────
    def _location(self, row):
        """(deployment, treatment, run) of one prediction row - where the
        library's raw folders put that recording, else the deployment/
        treatment/run the dataset itself carries."""
        loc = self.lib_selector.locations.get(_text(row.get("file")).upper())
        if loc:
            return loc[0], loc[1], loc[2]
        return (_text(row.get("deployment_id")), _text(row.get("treatment")),
                _run_text(row.get("run")))

    def _treatment_rows(self):
        """[(label, n, strike rate, ci_lo, ci_hi)] per treatment, from the
        prediction run's per-recording results narrowed to the Filters
        box's deployment/treatment/run. Falls back to the run's own
        treatment summary (unfiltered) when it has no per-recording
        results."""
        state = self.prediction_state
        if state is None:
            return []
        preds = state.predictions
        if preds is None or not len(preds):
            summary = state.summary
            if summary is None or not len(summary):
                return []
            return [(str(r["treatment"]), int(r["n"]), float(r["strike_rate"]),
                     float(r["ci_lo"]), float(r["ci_hi"]))
                    for _, r in summary.iterrows()]

        groups = {}
        for row in preds.to_dict("records"):
            dep, treat, run = self._location(row)
            if not self.lib_selector.matches_filters(dep, treat, run):
                continue
            label = _text(row.get("treatment")) or treat or "All data"
            groups.setdefault((dep, label), []).append(
                int(row.get("predicted_strike", 0) or 0))
        several_deps = len({dep for dep, _ in groups}) > 1
        out = []
        for (dep, label), strikes in groups.items():
            n = len(strikes)
            k = sum(strikes)
            lo, hi, _half = wilson_interval(k / n, n, confidence=95)
            name = f"{dep} / {label}" if several_deps and dep else label
            out.append((name, n, k / n, lo, hi))
        return sorted(out)

    # ── reactions ────────────────────────────────────────────────────────────
    def _video_observed_bar(self):
        """(label, value_pct, ci_lo, ci_hi) for the video-observed entry,
        or None if it's empty/invalid/hidden - an extra bar in the
        comparison figure, same across every selected treatment (a single
        deployment-wide count, not per treatment)."""
        total = self.spin_manual_total.value()
        strike = self.spin_manual_strike.value()
        mort = self.spin_manual_mort.value()
        if total == 0:
            self.lbl_manual.setText("")
        elif strike > total:
            self.lbl_manual.setText(
                "Strikes observed cannot exceed sensors deployed.")
        elif mort > total:
            self.lbl_manual.setText(
                "Mortalities observed cannot exceed sensors deployed.")
        else:
            lo, hi, half = wilson_interval(strike / total, total, confidence=95)
            text = (f"{strike}/{total} = {strike / total * 100:.1f}% strike "
                    f"rate, 95% CI [{lo * 100:.1f}%, {hi * 100:.1f}%], "
                    f"precision +/-{half * 100:.1f} percentage points.")
            if mort:
                m_lo, m_hi, _h = wilson_interval(mort / total, total,
                                                 confidence=95)
                text += (f"\n{mort}/{total} = {mort / total * 100:.1f}% "
                         f"mortality, 95% CI [{m_lo * 100:.1f}%, "
                         f"{m_hi * 100:.1f}%].")
            self.lbl_manual.setText(text)
        if total == 0 or strike > total or not self.chk_video_plot.isChecked():
            return None
        lo, hi, _half = wilson_interval(strike / total, total, confidence=95)
        label = self.ed_video_label.text().strip() or "Video observed"
        return (label, strike / total * 100, lo * 100, hi * 100)

    def _video_mortality_bar(self):
        """(label, value_pct, ci_lo, ci_hi) for the video-observed
        mortality, or None if none was entered / it's hidden."""
        total = self.spin_manual_total.value()
        mort = self.spin_manual_mort.value()
        if (total == 0 or mort == 0 or mort > total
                or not self.chk_video_plot.isChecked()):
            return None
        lo, hi, _half = wilson_interval(mort / total, total, confidence=95)
        label = self.ed_video_label.text().strip() or "Video observed"
        return (label, mort / total * 100, lo * 100, hi * 100)

    def _model1_bar(self):
        """(label, value_pct, ci_lo, ci_hi) for Model 1, or None if it's
        empty/invalid/hidden."""
        total = self.spin_model1_total.value()
        strike = self.spin_model1_strike.value()
        if total == 0:
            self.lbl_model1.setText("")
        elif strike > total:
            self.lbl_model1.setText(
                "Predicted strike cannot exceed sensors deployed.")
        else:
            lo, hi, half = wilson_interval(strike / total, total, confidence=95)
            self.lbl_model1.setText(
                f"{strike}/{total} = {strike / total * 100:.1f}% strike rate, "
                f"95% CI [{lo * 100:.1f}%, {hi * 100:.1f}%], "
                f"precision +/-{half * 100:.1f} percentage points.")
        if total == 0 or strike > total or not self.chk_model1_plot.isChecked():
            return None
        lo, hi, _half = wilson_interval(strike / total, total, confidence=95)
        label = self.ed_model1_label.text().strip() or "Model 1"
        return (label, strike / total * 100, lo * 100, hi * 100)

    def _run_model_name(self):
        """The model the prediction run used, named as it's deployed
        ("Model 1.1") rather than a fixed placeholder."""
        state = self.prediction_state
        if state is None:
            return "Model"
        path = (state.run_meta or {}).get("bin_model") or state.bin_model_path
        return model_display_name(path)

    def _refresh_comparison(self, *_args):
        # dual-species default: Calculator computes both scaly and eel per
        # run (BSMState.set_results()) - each species' Cen is that
        # species' own Pco_tip, an independent full BSM run, not one
        # result relabelled twice
        results = self.bsm_state.results or {}
        cen_raw = {
            sp: (results[sp]["Pco_tip"] * 100 if results.get(sp) else None)
            for sp in ("scaly", "eel")
        }
        pm_raw = {
            sp: (results[sp]["Pm"] * 100 if results.get(sp) else None)
            for sp in ("scaly", "eel")
        }
        for sp, lab_c, lab_m in (("scaly", self.lbl_scaly_value, self.lbl_scaly_mort),
                                 ("eel", self.lbl_eel_value, self.lbl_eel_mort)):
            lab_c.setText(f"{cen_raw[sp]:.1f}%" if cen_raw[sp] is not None
                          else "Not calculated")
            lab_m.setText(_pct(pm_raw[sp]) if pm_raw[sp] is not None
                          else "Not calculated")
        shown = {"scaly": self.chk_scaly_show.isChecked(),
                 "eel": self.chk_eel_show.isChecked()}
        bsm_label = self.ed_bsm_label.text().strip() or "Blade strike model"
        cen_values = {
            f"{bsm_label} - scaly": cen_raw["scaly"] if self.chk_scaly_show.isChecked() else None,
            f"{bsm_label} - eel": cen_raw["eel"] if self.chk_eel_show.isChecked() else None,
        }

        model_name = self._run_model_name()
        video_label = self.ed_video_label.text().strip() or "Video observed"
        model1_label = self.ed_model1_label.text().strip() or "Model 1"
        self.tbl_compare.setHorizontalHeaderLabels(
            ["Treatment", "N", video_label, model_name, model1_label,
             f"{bsm_label} - scaly", f"{bsm_label} - eel",
             f"{video_label} mortality",
             f"{model_name} mortality - scaly",
             f"{model_name} mortality - eel",
             f"{bsm_label} mortality - scaly",
             f"{bsm_label} mortality - eel"])

        # each also refreshes its own status label as a side effect - one
        # call each, reused below, rather than once per table row
        video = self._video_observed_bar()
        video_mort = self._video_mortality_bar()
        model1 = self._model1_bar()

        rows = self._treatment_rows()
        self.tbl_compare.setRowCount(len(rows))
        comparisons = []
        for i, (label, n, rate, lo, hi) in enumerate(rows):
            self.tbl_compare.setItem(i, 0, QTableWidgetItem(label))
            self.tbl_compare.setItem(i, 1, QTableWidgetItem(str(n)))
            self.tbl_compare.setItem(i, 2, QTableWidgetItem(
                f"{video[1]:.1f}%" if video else ""))
            self.tbl_compare.setItem(i, 3, QTableWidgetItem(
                f"{rate * 100:.1f}% [{lo * 100:.1f}%, {hi * 100:.1f}%]"))
            self.tbl_compare.setItem(i, 4, QTableWidgetItem(
                f"{model1[1]:.1f}%" if model1 else ""))
            self.tbl_compare.setItem(i, 5, QTableWidgetItem(
                f"{cen_raw['scaly']:.1f}%" if cen_raw["scaly"] is not None
                else "Not calculated"))
            self.tbl_compare.setItem(i, 6, QTableWidgetItem(
                f"{cen_raw['eel']:.1f}%" if cen_raw["eel"] is not None
                else "Not calculated"))
            self.tbl_compare.setItem(i, 7, QTableWidgetItem(
                _pct_ci(*video_mort[1:]) if video_mort else ""))
            for col, sp in ((8, "scaly"), (9, "eel")):
                res = results.get(sp)
                self.tbl_compare.setItem(i, col, QTableWidgetItem(
                    _pct_ci(*(mortality_from_strike_rate(res, v) * 100
                              for v in (rate, lo, hi)))
                    if res else "Not calculated"))
            for col, sp in ((10, "scaly"), (11, "eel")):
                self.tbl_compare.setItem(i, col, QTableWidgetItem(
                    _pct(pm_raw[sp]) if pm_raw[sp] is not None
                    else "Not calculated"))
            comparisons.append((f"{label} ({model_name})", rate * 100,
                               lo * 100, hi * 100))
        self.tbl_compare.resizeColumnsToContents()

        if video is not None:
            comparisons.append(video)
        if model1 is not None:
            comparisons.append(model1)

        # mortality: per species, the BSM's own then the current model's
        # projection for each treatment; video-observed last
        mortality = []
        for sp in ("scaly", "eel"):
            res = results.get(sp)
            if res is None or not shown[sp]:
                continue
            mortality.append((f"{bsm_label} - {sp}", pm_raw[sp], None, None, sp))
            for label, _n, rate, lo, hi in rows:
                m = [mortality_from_strike_rate(res, v) * 100
                     for v in (rate, lo, hi)]
                mortality.append((f"{label} ({model_name}) - {sp}", *m, "model"))
        if video_mort is not None:
            mortality.append((*video_mort, "observed"))

        self.cen_values, self.comparisons = cen_values, comparisons
        self.mortality_items = mortality
        self.model_name = model_name
        self._draw_figures()

    def _draw_figures(self):
        """Both figures from what `_refresh_comparison` last worked out."""
        self._draw_compare()
        self._draw_mortality()

    def _draw_compare(self):
        bsm_figures.draw_comparison_bars(
            self.fig_compare, self.cen_values, self.comparisons,
            title="Collision probability")
        self.canvas_compare.draw_idle()

    def _draw_mortality(self):
        bsm_figures.draw_mortality_bars(self.fig_mortality,
                                        self.mortality_items)
        self.canvas_mortality.draw_idle()

    def n_bars(self):
        """Bars in the comparison figure right now (picks the report
        figure's size)."""
        return (sum(1 for v in self.cen_values.values() if v is not None)
                + len(self.comparisons))
