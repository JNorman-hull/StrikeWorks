# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""The Predict and Results pages - one of each, shared by StrikeWorks (its
Predict and Report steps) and the Development toolkit (Model prediction >
Predict, as its two tabs - PredictTab):

  PredictPanel   - the Dataset and Model cards side by side; Load dataset,
                   Run prediction and Advanced features; a spinner and the
                   time elapsed while it runs, one line when it's done; and
                   the Predicted strikes (strike rate in the centre), Strike
                   classes and Collisions (collision rate) rings.
  AdvancedFeaturesWindow - Model mode, the decision threshold and its
                   override, HIG peak analysis and the blade strike
                   mortality inputs, in a window that doesn't block (like
                   Annotations and notes) and closes with its page.
  ResultsPanel   - the results by treatment, the HIG peak analysis table,
                   the strike rate, strike class and HIG peak figures, the
                   acceleration centred on the peak and on the nadir, and -
                   once a blade strike model has been calculated this
                   session - the mortality sweep.

All data comes from the shared PredictionState (BSMState for mortality),
so both apps' pages show the same run. The models are Settings' defaults
(PredictionState.use_default_models) - no pickers here.
"""
import re
from pathlib import Path

import numpy as np
from matplotlib.figure import Figure

from PySide6.QtCore import QElapsedTimer, QEvent, Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSizePolicy, QTabWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import (
    bsm_figures, hig_peaks, ml_figures, model_measures, recording_rate, settings,
    severity,
)
from .bsm_model import (
    default_vcrit, recompute_mortality, recompute_mortality_at_vcrit,
)
from .canvas import FigureCanvas
from .cards import MetaCard, RingCard, Spinner
from .layout import scroll_area, Section, when_visible
from .tables import fill_acceleration_table
from .theme import PALETTE, PINK, muted_label, style

CARD_MAX_W = 430                # each of the Dataset and Model boxes
BUTTON_W, BUTTON_H = 180, 40
REPORT_FIG_H = 380
_VCRIT_MIN, _VCRIT_MAX, _VCRIT_STEP = 2.0, 10.0, 0.25


def _model_version(path):
    """Version implied by the model filename, e.g. binary1_1 -> 1.1."""
    if not path:
        return None
    m = re.search(r"(\d+(?:_\d+)*)$", Path(path).stem)
    return m.group(1).replace("_", ".") if m else None


def _performance(metrics):
    """One row's value: "Accuracy = 0.959, Sensitivity = 0.966, ..." -
    the measures a model has saved, by the names used everywhere
    (model_measures; None if none)."""
    parts = []
    for name in ("Accuracy", "Sensitivity", "Specificity", "ROC AUC"):
        v = model_measures.value(metrics, name)
        if v is not None:
            parts.append(f"{name} = {float(v):.3f}")
    return ", ".join(parts) or None


def model_card_rows(s):
    """The Model card: each model and its out-of-fold performance (a
    multiclass model trained before 29 October 2026 has no ROC AUC or
    specificity saved - the latter comes from its confusion matrix)."""
    bm = s.bin_metrics or {}
    channels = bm.get("channels") or []
    rows = [
        ("Binary model",       s.bin_model_path.name if s.bin_model_path else None),
        ("Model type",         bm.get("model")),
        ("Version",            _model_version(s.bin_model_path)),
        ("Mode",               "Binary + multiclass" if s.mc_model_path
                               else ("Binary only" if s.bin_model_path else None)),
        ("Channels",           f"{len(channels)} ({', '.join(channels[:3])}"
                               f"{'…' if len(channels) > 3 else ''})"
                               if channels else None),
        ("Training samples",   bm.get("n_samples")),
        ("Trained on",         recording_rate.describe(*recording_rate.model_identity(bm))
                               if s.bin_model_path else None),
        ("Binary performance", _performance(bm)),
    ]
    if s.mc_model_path:
        rows += [
            ("Multiclass model",       s.mc_model_path.name),
            ("Classes",                ", ".join(s.class_names or []) or None),
            ("Multiclass performance", _performance(s.mc_metrics)),
        ]
    elif s.bin_model_path:
        rows.append(("Multiclass model", "not found (binary only)"))
    return rows


def dataset_card_rows(s):
    m = s.dataset_meta
    if not m:
        return [("Dataset", "No dataset loaded")]
    sr = m.get("sampling_rate_hz")
    seq = None
    if m.get("seq_len_min") is not None:
        if m["seq_len_min"] == m["seq_len_max"]:
            seq = f"{m['seq_len_max']} samples"
            if sr:
                seq += f" ({m['seq_len_max'] / sr * 1000:.0f} ms)"
        else:
            seq = f"{m['seq_len_min']}-{m['seq_len_max']} samples (varying)"
    req = set(s.required_channels())
    n_chan_present = (len([c for c in m.get("columns", []) if c in req])
                      if req else None)
    return [
        ("Dataset",       m.get("name")),
        ("Source",        s.dataset_source),
        ("Recordings",    m.get("n_files")),
        ("Sensor rows",   f"{m.get('n_rows'):,}" if m.get("n_rows") else None),
        ("Treatments",    f"{len(m['treatments'])} "
                          f"({', '.join(m['treatments'])})"
                          if m.get("treatments") else None),
        ("Sensor",        recording_rate.sensor_name(
            m["identity"][recording_rate.SENSOR_COL]) if m.get("identity") else None),
        ("Sampling rate", f"{sr} Hz" if sr else None),
        ("Window length", seq),
        ("Model channels",
         f"{n_chan_present}/{len(req)} present" if req else None),
        ("Annotations",   s.annotation_status()),
    ]


# ── mortality (BSM) ──────────────────────────────────────────────────────────
# Scaly and eel each come from their own BSM run (BSMState.results):
# collision exposure differs by species (Leff_m / Leff_t), not just the
# mortality regression.
def mortality_text(bsm):
    results = bsm.results if bsm else {}
    lines = []
    for species in ("scaly", "eel"):
        res = results.get(species)
        if res is None:
            continue
        out = recompute_mortality(res, species, eel_vcrit=bsm.eel_vcrit,
                                  threshold=None)
        lines.append(
            f"{species}: Pm={out['Pm'] * 100:.2f}%, "
            f"S={out['S'] * 100:.2f}% (Cen Pco {res['Pco_tip'] * 100:.2f}%)")
    return ("\n".join(lines) if lines else
            "Run the Blade strike calculator first.")


def draw_mortality(fig, bsm):
    results = bsm.results if bsm else {}
    vcrit_vals = np.arange(_VCRIT_MIN, _VCRIT_MAX + 1e-9, _VCRIT_STEP)
    series = []
    for species in ("scaly", "eel"):
        res = results.get(species)
        if res is None:
            series.append((species, None, None, None, None))
            continue
        pm_vals = np.array([
            recompute_mortality_at_vcrit(res, species, float(v))["Pm"] * 100
            for v in vcrit_vals])
        default_v = default_vcrit(res, species, eel_vcrit=bsm.eel_vcrit)
        default_pm = recompute_mortality_at_vcrit(
            res, species, default_v)["Pm"] * 100
        series.append((species, vcrit_vals, pm_vals, default_v, default_pm))
    treatment = bsm.mortality_treatment if bsm else None
    title = f"Treatment: {treatment}" if treatment else "No treatment selected"
    bsm_figures.draw_vcrit_sweep(fig, series, title=title)


# ═════════════════════════════════════════════════════════════════════════════
class AdvancedFeaturesWindow(QDialog):
    """Model mode, the decision threshold, HIG peak analysis and the blade
    strike mortality inputs - a window that doesn't block (shown, not
    exec'd), like Annotations and notes, gone when its page is."""

    def __init__(self, page, owner, state, bsm_state=None):
        super().__init__(owner)
        self.page = page
        self.state = state
        self.bsm = bsm_state
        self.setWindowTitle("Advanced features")
        self._build()
        state.config_changed.connect(self._refresh_config)
        state.run_finished.connect(self._refresh_treatments)
        if bsm_state is not None:
            bsm_state.calculated_all.connect(self._refresh_mortality)
            bsm_state.mortality_changed.connect(self._refresh_mortality)
        self._refresh_config()
        self._refresh_treatments()
        self._refresh_mortality()
        self.setMinimumWidth(440)
        # it belongs to the page: gone when the page is (another page, or
        # the window closed or minimised)
        page.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.page and event.type() == QEvent.Type.Hide:
            self.hide()
        return super().eventFilter(obj, event)

    def bring_up(self):
        self.show()
        self.raise_()
        self.activateWindow()

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(8)

        grp = Section("Prediction")
        g = QGridLayout(grp)
        g.setVerticalSpacing(8)
        g.setColumnStretch(1, 1)
        g.addWidget(muted_label("Model mode"), 0, 0)
        self.cmb_mode = QComboBox()
        self.cmb_mode.currentIndexChanged.connect(self._on_mode_changed)
        g.addWidget(self.cmb_mode, 0, 1, 1, 2)

        self.lbl_thresh = QLabel("Decision threshold: -")
        g.addWidget(self.lbl_thresh, 1, 0, 1, 3)
        self.chk_override = QCheckBox("Override deployed threshold")
        self.chk_override.toggled.connect(self._on_override_toggled)
        self.spin_thresh = QDoubleSpinBox()
        self.spin_thresh.setRange(0.0, 1.0)
        self.spin_thresh.setDecimals(3)
        self.spin_thresh.setSingleStep(0.01)
        self.spin_thresh.setEnabled(False)
        self.spin_thresh.valueChanged.connect(self._on_threshold_edited)
        g.addWidget(self.chk_override, 2, 0, 1, 2)
        g.addWidget(self.spin_thresh, 2, 2)
        self.lbl_override_note = QLabel(
            "⚠ You are overriding the deployed model threshold.")
        style(self.lbl_override_note, tone="warn")
        self.lbl_override_note.setVisible(False)
        g.addWidget(self.lbl_override_note, 3, 0, 1, 3)

        self.chk_hig_peaks = QCheckBox("HIG peak analysis")
        self.chk_hig_peaks.toggled.connect(self.state.set_hig_peaks)
        g.addWidget(self.chk_hig_peaks, 4, 0, 1, 3)
        v.addWidget(grp)
        v.addWidget(self._hig_section())

        # the mortality inputs: from the BSM run, independent of the
        # prediction. Scaly and eel are shown together; only eel's
        # critical velocity is an input (scaly's regression sets its own
        # floor).
        grp_bsm = Section("Blade strike model")
        b = QGridLayout(grp_bsm)
        b.setVerticalSpacing(8)
        b.setColumnStretch(1, 1)
        b.addWidget(muted_label("Treatment"), 0, 0)
        self.cmb_mortality_treatment = QComboBox()
        self.cmb_mortality_treatment.setToolTip(
            "Which pump condition the mortality plot represents - a "
            "label only, since the BSM run itself has no per-treatment "
            "input; populated from the current prediction's treatments.")
        self.cmb_mortality_treatment.currentIndexChanged.connect(
            self._on_treatment_picked)
        b.addWidget(self.cmb_mortality_treatment, 0, 1)
        b.addWidget(muted_label("Eel critical velocity"), 1, 0)
        self.spin_eel_vcrit = QDoubleSpinBox()
        self.spin_eel_vcrit.setRange(0.0, 50.0)
        self.spin_eel_vcrit.setDecimals(2)
        self.spin_eel_vcrit.setSuffix(" m/s")
        self.spin_eel_vcrit.valueChanged.connect(self._on_vcrit_edited)
        b.addWidget(self.spin_eel_vcrit, 1, 1)
        self.lbl_mortality = QLabel("")
        style(self.lbl_mortality, role="strong")
        self.lbl_mortality.setWordWrap(True)
        b.addWidget(self.lbl_mortality, 2, 0, 1, 2)
        grp_bsm.setVisible(self.bsm is not None)
        v.addWidget(grp_bsm)
        v.addStretch()

    # ── prediction configuration ─────────────────────────────────────────────
    # (setting, label, suffix, range, decimals, step, shown as: value x scale)
    _HIG_FIELDS = (
        ("height_g", "Peak height", " g", (1, 2000), 1, 5, 1),
        ("prominence_g", "Prominence", " g", (0, 1000), 1, 5, 1),
        ("interpeak_s", "Minimum gap between peaks", " ms", (0.1, 100), 1, 0.5, 1000),
        ("shear_fraction", "Shear: share of the peak", " %", (1, 99), 0, 5, 100),
        ("shear_s", "Shear: at least this long above it", " ms", (0.1, 100), 1, 0.5, 1000),
    )

    def _hig_section(self):
        """HIG peak analysis's detection settings - and its event bands and
        collision value, shown but fixed for now (ROADMAP.md)."""
        grp = Section("HIG peak analysis")
        h = QGridLayout(grp)
        h.setVerticalSpacing(6)
        h.setColumnStretch(1, 1)
        self._hig_spins = {}
        for row, (name, label, suffix, (lo, hi), decimals, step, scale) in enumerate(
                self._HIG_FIELDS):
            h.addWidget(muted_label(label), row, 0)
            spin = QDoubleSpinBox()
            spin.setRange(lo, hi)
            spin.setDecimals(decimals)
            spin.setSingleStep(step)
            spin.setSuffix(suffix)
            spin.valueChanged.connect(
                lambda value, n=name, k=scale: self.state.set_hig_setting(n, value / k))
            h.addWidget(spin, row, 1)
            self._hig_spins[name] = (spin, scale)
        row = len(self._HIG_FIELDS)
        fixed = "Fixed for now - see ROADMAP.md, \"Editable HIG bands\"."
        for text, value in (
                ("Event bands", ", ".join(f"{g}" for g in hig_peaks.THRESHOLDS_G) + " g"),
                ("Collision / severe", f"{hig_peaks.COLLISION_G} g")):
            h.addWidget(muted_label(text), row, 0)
            box = QLineEdit(value)
            box.setReadOnly(True)
            box.setEnabled(False)
            box.setToolTip(fixed)
            h.addWidget(box, row, 1)
            row += 1
        self.btn_hig_defaults = QPushButton("Defaults")
        self.btn_hig_defaults.setToolTip("Put the detection settings back to "
                                         "the shipped defaults.")
        self.btn_hig_defaults.clicked.connect(self.state.reset_hig_settings)
        h.addWidget(self.btn_hig_defaults, row, 1, Qt.AlignmentFlag.AlignRight)
        return grp

    def _refresh_hig(self):
        s = self.state
        d = s.hig_settings
        for spin, _scale in self._hig_spins.values():
            spin.setEnabled(s.hig_peaks)
        for name, (spin, scale) in self._hig_spins.items():
            spin.blockSignals(True)
            spin.setValue(d[name] * scale)
            spin.blockSignals(False)
        self.btn_hig_defaults.setEnabled(s.hig_peaks)
        self.chk_hig_peaks.setToolTip(
            "Find the acceleration events in each recording's high-g "
            f"magnitude: peaks of at least {d['height_g']:g} g with a "
            f"prominence of {d['prominence_g']:g} g, at least "
            f"{d['interpeak_s'] * 1000:g} ms apart. Counts them over "
            + ", ".join(f"{g}" for g in hig_peaks.THRESHOLDS_G)
            + f" g within {hig_peaks.NADIR_WINDOW_S:g} s of the nadir, and gives the "
            f"collision probability (an event of {hig_peaks.COLLISION_G} g "
            "or more). Measured, alongside the model's prediction.")

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
                if dep is not None else "Decision threshold: -")

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

        self.chk_hig_peaks.blockSignals(True)
        self.chk_hig_peaks.setChecked(s.hig_peaks)
        self.chk_hig_peaks.blockSignals(False)
        self._refresh_hig()

    def _on_mode_changed(self):
        mode = self.cmb_mode.currentData()
        if mode:
            self.state.set_mode(mode)

    def _on_override_toggled(self, checked):
        # the spinbox shows the deployed threshold while unchecked, so
        # enabling the override starts from the deployed value
        value = self.spin_thresh.value() if checked else None
        self.state.set_threshold_override(checked, value)

    def _on_threshold_edited(self, value):
        if self.chk_override.isChecked():
            self.state.set_threshold_override(True, value)

    # ── mortality inputs ─────────────────────────────────────────────────────
    def _refresh_treatments(self):
        """The treatments of the current prediction (the plot's label)."""
        if self.bsm is None:
            return
        summary = self.state.summary
        names = (sorted(summary["treatment"].astype(str).unique())
                 if summary is not None and len(summary) else [])
        cmb = self.cmb_mortality_treatment
        cmb.blockSignals(True)
        cmb.clear()
        cmb.addItem("None", None)
        for name in names:
            cmb.addItem(name, name)
        cmb.blockSignals(False)
        if self.bsm.mortality_treatment not in names + [None]:
            self.bsm.set_mortality_treatment(None)
        self._refresh_mortality()

    def _refresh_mortality(self, *_args):
        if self.bsm is None:
            return
        cmb = self.cmb_mortality_treatment
        cmb.blockSignals(True)
        idx = cmb.findData(self.bsm.mortality_treatment)
        cmb.setCurrentIndex(idx if idx >= 0 else 0)
        cmb.blockSignals(False)
        self.spin_eel_vcrit.blockSignals(True)
        self.spin_eel_vcrit.setValue(self.bsm.eel_vcrit)
        self.spin_eel_vcrit.blockSignals(False)
        self.lbl_mortality.setText(mortality_text(self.bsm))

    def _on_treatment_picked(self):
        self.bsm.set_mortality_treatment(self.cmb_mortality_treatment.currentData())

    def _on_vcrit_edited(self, value):
        self.bsm.set_eel_vcrit(value)


# ═════════════════════════════════════════════════════════════════════════════
class PredictPanel(QWidget):
    """The Predict page (see the module docstring), bound to `state`.
    `owner` is the window its dialogs belong to; `goto_inspect` (the
    toolkit's) adds the "Inspect low confidence" shortcut - StrikeWorks
    has no Inspect."""

    def __init__(self, state, owner, bsm_state=None, goto_inspect=None):
        super().__init__()
        self.state = state
        self.owner = owner
        self._goto_inspect = goto_inspect

        self._elapsed = QElapsedTimer()
        self._tick = QTimer(self)
        self._tick.setInterval(500)
        self._tick.timeout.connect(self._update_elapsed)

        self._build()
        self.advanced = AdvancedFeaturesWindow(self, owner, state, bsm_state)
        self.btn_advanced.clicked.connect(self.advanced.bring_up)

        s = state
        s.models_changed.connect(self._refresh_model)
        s.dataset_changed.connect(self._refresh_dataset)
        s.validation_changed.connect(self._sync_run_button)
        s.config_changed.connect(self._refresh_collisions)
        s.run_started.connect(self._on_run_started)
        s.run_finished.connect(self._on_run_finished)
        s.run_failed.connect(self._on_run_failed)
        self._refresh_model()
        self._refresh_dataset()
        self._show_results()

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self):
        v = QVBoxLayout(self)
        # (8, and the spinner no taller than the status line: the page
        # fits StrikeWorks's window at 690 px high)
        v.setSpacing(8)
        # equal stretch above and below keeps the block centred
        v.addStretch(1)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(16)
        cards_row.addStretch()
        self.card_dataset = MetaCard()
        self.card_model = MetaCard()
        self.card_model.setToolTip(
            "The default models (Settings). Performance is out-of-fold "
            "(cross-validation); the multiclass sensitivity and "
            "specificity are averaged over its classes.")
        for title, card in (("Dataset", self.card_dataset),
                            ("Model", self.card_model)):
            grp = Section(title)
            grp.setMaximumWidth(CARD_MAX_W)
            QVBoxLayout(grp).addWidget(card)
            cards_row.addWidget(grp, stretch=1)
        cards_row.addStretch()
        v.addLayout(cards_row)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_load_dataset = QPushButton("Load dataset CSV…")
        self.btn_load_dataset.clicked.connect(self.load_dataset_csv)
        self.btn_run_predict = QPushButton("Run prediction")
        self.btn_run_predict.clicked.connect(self.run)
        self.btn_advanced = QPushButton("Advanced features")
        self.btn_advanced.setToolTip(
            "Model mode, the decision threshold, HIG peak analysis and the "
            "blade strike model's inputs, in a window that stays open.")
        for btn in (self.btn_load_dataset, self.btn_run_predict,
                    self.btn_advanced):
            btn.setMinimumSize(BUTTON_W, BUTTON_H)
            btn_row.addWidget(btn)
        btn_row.addStretch()
        v.addLayout(btn_row)

        status_row = QHBoxLayout()
        status_row.addStretch()
        self.spinner = Spinner(size=18)
        self.spinner.setVisible(False)
        status_row.addWidget(self.spinner)
        self.lbl_status = QLabel("")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        status_row.addWidget(self.lbl_status)
        status_row.addStretch()
        v.addLayout(status_row)

        # the toolkit's shortcut into Inspect (_on_run_finished)
        self.btn_low_conf = QPushButton("")
        self.btn_low_conf.setVisible(False)
        self.btn_low_conf.clicked.connect(self._inspect_low_conf)
        v.addWidget(self.btn_low_conf, alignment=Qt.AlignmentFlag.AlignHCenter)

        rings = QHBoxLayout()
        rings.setSpacing(16)
        rings.addStretch()
        self.card_predicted_strikes = RingCard("Predicted strikes")
        self.card_predicted_strikes.setToolTip(
            "Recordings predicted a strike; the strike rate in the centre.")
        rings.addWidget(self.card_predicted_strikes)
        self.card_strike_classes = RingCard("Strike classes")
        rings.addWidget(self.card_strike_classes)
        # the HIG peak analysis, shown while it's ticked (Advanced features)
        self.card_collisions = RingCard(f"Collisions (≥ {hig_peaks.COLLISION_G} g)")
        rings.addWidget(self.card_collisions)
        rings.addStretch()
        v.addLayout(rings)

        v.addStretch(1)

    # ── cards ────────────────────────────────────────────────────────────────
    def _refresh_model(self):
        self.card_model.set_rows(model_card_rows(self.state))

    def _refresh_dataset(self):
        self.card_dataset.set_rows(dataset_card_rows(self.state))
        self._sync_run_button()

    def _sync_run_button(self):
        s = self.state
        self.btn_run_predict.setEnabled(s.dataset_df is not None and not s.running)

    # ── dataset and run ──────────────────────────────────────────────────────
    def load_dataset_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self.owner, "Load dataset CSV", str(settings.get_input_data_dir()),
            "CSV files (*.csv)")
        if not path:
            return
        ok, msg = self.state.load_dataset_csv(path)
        style(self.lbl_status, role="muted", tone=None if ok else "bad")
        self.lbl_status.setText(msg)

    def run(self):
        self.state.run_prediction()

    def _on_run_started(self):
        self.btn_run_predict.setEnabled(False)
        self.btn_run_predict.setText("Running…")
        self.btn_low_conf.setVisible(False)
        self.spinner.start()
        self._elapsed.start()
        self._tick.start()
        style(self.lbl_status, tone="accent")
        self._update_elapsed()

    def _update_elapsed(self):
        n = self.state.dataset_meta.get("n_files", "?")
        self.lbl_status.setText(f"Predicting {n} recordings…  "
                                f"{self._elapsed.elapsed() // 1000} s elapsed")

    def _stop_run_ui(self):
        self._tick.stop()
        self.spinner.stop()
        self.btn_run_predict.setText("Run prediction")
        self._sync_run_button()

    def _on_run_finished(self):
        secs = self._elapsed.elapsed() / 1000 if self._elapsed.isValid() else None
        self._stop_run_ui()
        s = self.state
        n = s.run_meta.get("n_files", 0)
        style(self.lbl_status, role="strong", tone="ok")
        self.lbl_status.setText(
            f"Blade strike predicted: {n} recordings"
            + (f" in {secs:.1f} s" if secs is not None else ""))

        # the toolkit's low-confidence shortcut into Inspect
        if (self._goto_inspect and s.predictions is not None
                and "confidence" in s.predictions.columns):
            n_low = int((s.predictions["confidence"]
                         < s.low_conf_threshold).sum())
            if n_low:
                self.btn_low_conf.setText(f"Inspect low confidence ({n_low}) →")
                self.btn_low_conf.setToolTip(
                    f"{n_low} prediction(s) below confidence "
                    f"{s.low_conf_threshold:.2f} - open them in Inspect")
                self.btn_low_conf.setVisible(True)
        self._show_results()

    def _on_run_failed(self, msg):
        self._stop_run_ui()
        style(self.lbl_status, tone="bad")
        msg = msg.strip() or "Unknown error"
        if msg.startswith("Prediction is not ready"):
            # a pre-flight compatibility failure - short, already itemised
            # by validate(), and expected (missing dataset, wrong mode) -
            # the status line is enough
            self.lbl_status.setText(f"✗ {msg}")
            return
        first = msg.splitlines()[-1]
        self.lbl_status.setText(f"✗ Prediction failed: {first}")
        if not self.isVisible():
            return      # the other app's page - it reports there
        dlg = QMessageBox(self.owner)
        dlg.setWindowTitle("Prediction error")
        dlg.setIcon(QMessageBox.Icon.Critical)
        dlg.setText("The prediction worker failed.\n\n"
                    f"{first}\n\nFull details below.")
        dlg.setDetailedText(msg)
        dlg.exec()

    # ── result rings ─────────────────────────────────────────────────────────
    def _show_results(self):
        s = self.state
        df = s.summary
        if df is not None and len(df):
            n_total = int(df["n"].sum())
            n_strike = int(df["n_strike"].sum())
            rate = n_strike / n_total if n_total else 0.0
            self.card_predicted_strikes.set_segments([
                ("Strike", n_strike, PINK),
                ("No strike", n_total - n_strike, PALETTE[0]),
            ], f"{rate * 100:.1f}%")
        else:
            self.card_predicted_strikes.clear()

        have_classes = (s.run_meta.get("mode") == "multiclass" and df is not None
                        and len(df) and s.class_names
                        and all(f"n_{cn}" in df.columns for cn in s.class_names))
        self.card_strike_classes.setVisible(bool(have_classes))
        if have_classes:
            self.card_strike_classes.set_segments([
                (cn, int(df[f"n_{cn}"].sum()), PALETTE[i % len(PALETTE)])
                for i, cn in enumerate(s.class_names)
            ])
        else:
            self.card_strike_classes.clear()
        self._refresh_collisions()

    def _refresh_collisions(self):
        """The Collisions ring: shown only while HIG peak analysis is
        ticked, filled when the last run did the analysis."""
        s = self.state
        self.card_collisions.setVisible(s.hig_peaks)
        acc = s.acc_summary
        if acc is None or not len(acc):
            self.card_collisions.clear()
            self.card_collisions.setToolTip(
                f"Recordings with an acceleration event of "
                f"{hig_peaks.COLLISION_G} g or more within 0.1 s of the "
                "nadir (HIG peak analysis). Measured, not predicted.")
            return
        total = acc.iloc[-1]       # the "All recordings" row, or the only one
        k, n_rec = int(total["n_collision"]), int(total["n_sensors"])
        rate = float(total["collision_rate"])
        self.card_collisions.set_segments([
            ("Collision", k, PINK), ("No collision", n_rec - k, PALETTE[0]),
        ], f"{rate * 100:.1f}%")
        self.card_collisions.setToolTip(
            f"Recordings with an acceleration event of "
            f"{hig_peaks.COLLISION_G} g or more within 0.1 s of the nadir "
            f"(HIG peak analysis; 95% CI {total['ci_lo'] * 100:.1f}-"
            f"{total['ci_hi'] * 100:.1f}%). Measured, not predicted.")

    def _inspect_low_conf(self):
        if self._goto_inspect:
            self._goto_inspect("low_conf")


# ═════════════════════════════════════════════════════════════════════════════
class ResultsPanel(QWidget):
    """The Results page (see the module docstring): redrawn when it's
    next shown after a run, or a blade strike calculation, changes it."""

    def __init__(self, state, bsm_state=None):
        super().__init__()
        self.state = state
        self.bsm = bsm_state
        self._build()
        self._stale = True
        when_visible(self, self._refresh_if_stale, "results")
        state.run_finished.connect(self._mark_stale)
        if bsm_state is not None:
            bsm_state.calculated_all.connect(self._mark_stale)
            bsm_state.mortality_changed.connect(self._mark_stale)

    def _build(self):
        v = QVBoxLayout(self)
        v.setSpacing(10)

        self.tbl_results = QTableWidget(0, 0)
        self.tbl_results.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_results.setMinimumHeight(150)
        v.addWidget(self.tbl_results)

        # the HIG peak analysis table, as in the reports
        self.tbl_acc = QTableWidget(0, 0)
        self.tbl_acc.setProperty("noRowNumbers", True)   # its own header rows
        self.tbl_acc.horizontalHeader().setVisible(False)
        self.tbl_acc.verticalHeader().setVisible(False)
        self.tbl_acc.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_acc.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        v.addWidget(self.tbl_acc)
        self.lbl_acc_notes = muted_label("\n".join(hig_peaks.TABLE_NOTES))
        self.lbl_acc_notes.setWordWrap(True)
        v.addWidget(self.lbl_acc_notes)

        # the two model figures side by side; the HIG peak figure (three
        # panels) the full width under them; the acceleration centred on
        # the peak and on the nadir; then mortality, half width
        grp_figs = Section("")
        fv = QGridLayout(grp_figs)
        fv.setColumnStretch(0, 1)
        fv.setColumnStretch(1, 1)
        self.canvases = {}
        for key, size, row, col, span in (
                ("bin", (4.3, 3.2), 0, 0, 1), ("mc", (4.3, 3.2), 0, 1, 1),
                ("peaks", (8.6, 3.2), 1, 0, 2),
                ("acc", (4.3, 3.2), 2, 0, 1), ("nadir", (4.3, 3.2), 2, 1, 1),
                ("mortality", (4.3, 3.2), 3, 0, 1)):
            canvas = FigureCanvas(Figure(figsize=size, dpi=100))
            canvas.setSizePolicy(QSizePolicy.Policy.Expanding,
                                 QSizePolicy.Policy.Expanding)
            canvas.setMinimumHeight(REPORT_FIG_H)
            fv.addWidget(canvas, row, col, 1, span)
            self.canvases[key] = canvas
        v.addWidget(grp_figs, stretch=1)

    def _mark_stale(self, *_args):
        self._stale = True
        when_visible(self, self._refresh_if_stale, "results")

    def _refresh_if_stale(self):
        if self._stale:
            self.refresh()

    def refresh(self):
        self._stale = False
        s = self.state
        df = s.summary
        mc_run = s.run_meta.get("mode") == "multiclass"
        class_names = (s.class_names if mc_run and s.class_names
                       and df is not None
                       and all(f"n_{cn}" in df.columns for cn in s.class_names)
                       else [])
        # severity columns only without the HIG peak analysis (its own table)
        measured = severity.available(df) and s.acc_summary is None
        headers = (["Treatment", "N", "Strikes", "No strike", "Strike rate",
                    "95% CI", "Mean prob", "Mean conf"] + list(class_names)
                   + (severity.TABLE_HEADERS if measured else []))
        self.tbl_results.setColumnCount(len(headers))
        self.tbl_results.setHorizontalHeaderLabels(headers)
        self.tbl_results.setRowCount(0 if df is None else len(df))
        if df is not None:
            for row, (_, r) in enumerate(df.iterrows()):
                n_strike = int(r["n_strike"])
                vals = [
                    str(r["treatment"]), str(int(r["n"])), str(n_strike),
                    str(int(r["n_no_strike"])),
                    f"{r['strike_rate'] * 100:.1f}%",
                    f"{r['ci_lo'] * 100:.1f}% - {r['ci_hi'] * 100:.1f}%",
                    f"{r['mean_prob']:.3f}", f"{r['mean_conf']:.3f}",
                ]
                for cn in class_names:
                    nc = int(r[f"n_{cn}"])
                    pct = nc / n_strike * 100 if n_strike else 0
                    vals.append(f"{nc} ({pct:.0f}%)")
                if measured:
                    vals += severity.table_values(r)
                for col, val in enumerate(vals):
                    self.tbl_results.setItem(row, col, QTableWidgetItem(val))
        self.tbl_results.resizeColumnsToContents()

        c = self.canvases
        ml_figures.draw_strike_rate(c["bin"].figure, df, dark=True)
        ml_figures.draw_region(c["mc"].figure, df,
                               class_names if mc_run else [], dark=True)
        drawn = ["bin", "mc"]

        have_peaks = s.acc_summary is not None
        for w in (self.tbl_acc, self.lbl_acc_notes,
                  c["peaks"], c["acc"], c["nadir"]):
            w.setVisible(have_peaks)
        if have_peaks:
            fill_acceleration_table(self.tbl_acc, s.acc_summary)
            ml_figures.draw_peak_summary(c["peaks"].figure, s.acc_summary,
                                         s.predictions, dark=True)
            traces = s.collision_traces()
            ml_figures.draw_acc_centred(c["acc"].figure, traces, "acc", dark=True)
            ml_figures.draw_acc_centred(c["nadir"].figure, traces, "nadir",
                                        dark=True)
            drawn += ["peaks", "acc", "nadir"]

        # once a blade strike model has been calculated this session
        have_bsm = bool(self.bsm and self.bsm.results)
        c["mortality"].setVisible(have_bsm)
        if have_bsm:
            draw_mortality(c["mortality"].figure, self.bsm)
            drawn.append("mortality")
        for key in drawn:
            c[key].draw()


# ═════════════════════════════════════════════════════════════════════════════
class PredictTab(QWidget):
    """Model prediction > Predict: the shared Predict and Results pages,
    as two tabs."""

    def __init__(self, state, main_window, goto_inspect=None, bsm_state=None):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        outer.addWidget(self.tabs)
        self.predict = PredictPanel(state, main_window, bsm_state,
                                    goto_inspect=goto_inspect)
        self.results = ResultsPanel(state, bsm_state)
        self.tabs.addTab(scroll_area(self.predict), "Predict")
        self.tabs.addTab(scroll_area(self.results), "Results")
