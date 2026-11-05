# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Shared state for the Blade strike calculator - the
same "one state object, several pages react to its signal" shape
`ml_state.PredictionState`/`ml_train_state.TrainingState` already use.

Calculator owns the run and publishes `LATEST_RESULT_PATH`; Advanced
analysis re-sweeps whenever a new result comes in (`calculated`) or the
sweep options change (`sweep_options_changed`). Nothing here is Qt-multithreaded - `bsm_model.compute()`
is fast (one 200-point NumPy loop), so it runs straight on the GUI thread.
"""
from datetime import datetime, timezone

from PySide6.QtCore import QObject, Signal

from . import settings
from .bsm_model import SWEEP_N_SPAN, SWEEP_Q_SPAN, SWEEP_Q_STEP

# next to the exe once packaged, the repo root from source
LATEST_RESULT_PATH = settings.app_root() / "bsm_results" / "latest_result.json"
# matches every saved bsm_config file's own eel_vcrit (input_data/
# BSM_config/*.txt)
EEL_VCRIT_DEFAULT = 8.0


def build_latest_payload(res):
    """The small JSON shape written to LATEST_RESULT_PATH and shown on
    Calculator's own output card - one definition so the two never drift:
    Reporting publishes it to disk, Calculator just displays it."""
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "species": res["params"]["species"],
        "pco_cen_percent": res["Pco_tip"] * 100,
        "pm_cen_percent": res["Pm"] * 100,
        "s_cen_percent": res["S"] * 100,
    }
    if "Pco_obs" in res:
        payload.update({
            "pco_observed_percent": res["Pco_obs"] * 100,
            "pm_observed_percent": res["Pm_obs"] * 100,
            "wilson_lo_percent": res["wilson_lo"] * 100,
            "wilson_hi_percent": res["wilson_hi"] * 100,
        })
    return payload


def output_card_rows(res):
    """Every equation result, CEN and (if included) Observed - the
    "Blade strike output" card's content, shared by Calculator (which
    builds it) and Advanced analysis (which shows the same cards)."""
    rows = [
        ("Species", res["params"]["species"]),
        ("Lmax (m)", f"{res['Lmax']:.4f}"),
        ("Leff,m / Leff,t (m)", f"{res['Leff_m']:.4f} / {res['Leff_t']:.4f}"),
        ("Omega (rad/s)", f"{res['Omega']:.4f}"),
        ("vm (m/s)", f"{res['vm']:.4f}"),
        ("Regime (tip)", res["regime_tip"]),
        ("vcrit at tip (m/s)", f"{res['vcrit_tip']:.4f}"),
        ("Pco - CEN (%)", f"{res['Pco_tip'] * 100:.4f}"),
        ("fMR - CEN (%)", f"{res['fMR_tip'] * 100:.4f}"),
        ("Pm - CEN (%)", f"{res['Pm'] * 100:.4f}"),
        ("S - CEN (%)", f"{res['S'] * 100:.4f}"),
    ]
    if "Pco_obs" in res:
        rows += [
            ("Pco - Observed (%)", f"{res['Pco_obs'] * 100:.4f}"),
            ("Pm - Observed (%)", f"{res['Pm_obs'] * 100:.4f}"),
            ("S - Observed (%)", f"{res['S_obs'] * 100:.4f}"),
        ]
    return rows


class BSMState(QObject):
    calculated = Signal(dict)      # the full result dict from bsm_model.compute()
    calculated_all = Signal(dict)  # {"scaly": res, "eel": res} - see set_results()
    mortality_changed = Signal()   # Predict's mortality inputs (below)
    sweep_options_changed = Signal()   # Calculator's Advanced options

    def __init__(self, parent=None):
        super().__init__(parent)
        self.last_result = None
        self.results = {}   # {"scaly": res, "eel": res} - dual-species default
        # Predict's mortality inputs (its Advanced features), one pair for
        # StrikeWorks and the toolkit: eel's critical velocity - the first
        # run's own (every saved config says 8 m/s) until changed there -
        # and the treatment the mortality plot is labelled with (a label
        # only: the BSM run has no per-treatment input)
        self.eel_vcrit = EEL_VCRIT_DEFAULT
        self.mortality_treatment = None
        self._eel_vcrit_set = False
        # the sensitivity sweeps' ranges (Calculator's Advanced options):
        # `bsm_model.sensitivity_sweeps(params, **sweep_options)`
        self.sweep_options = {"q_span": SWEEP_Q_SPAN, "q_step": SWEEP_Q_STEP,
                              "n_span": SWEEP_N_SPAN}

    def set_result(self, res):
        self.last_result = res
        self.calculated.emit(res)

    def set_results(self, results_by_species):
        """Dual-species default: Calculator computes both scaly and eel
        every run (all other inputs - fish/pump/blade geometry, eel_vcrit
        - are shared, so this costs one extra `compute()` call, not a
        second data-entry pass). `last_result`/`calculated` are untouched
        and keep meaning "whichever species the Calculator's own Species
        combo has selected" for every pre-existing single-result consumer
        (Advanced analysis's sweeps, Study design's Load);
        `results`/`calculated_all` are for the newer dual-species
        consumers (Model comparison's Cen bars, Predict's mortality
        panel) that want both at once, keyed by species name."""
        self.results = results_by_species
        eel = results_by_species.get("eel")
        if not self._eel_vcrit_set and eel is not None:
            self._eel_vcrit_set = True
            self.eel_vcrit = eel["params"]["eel_vcrit"]
        self.calculated_all.emit(results_by_species)

    def set_eel_vcrit(self, value):
        """Changed on Predict - kept, never overwritten by a later run."""
        self._eel_vcrit_set = True
        self.eel_vcrit = float(value)
        self.mortality_changed.emit()

    def set_mortality_treatment(self, name):
        self.mortality_treatment = name
        self.mortality_changed.emit()

    def set_sweep_options(self, **options):
        """Any of q_span, q_step, n_span (each x the design value)."""
        options = {k: v for k, v in options.items()
                   if self.sweep_options.get(k) != v}
        if options:
            self.sweep_options.update(options)
            self.sweep_options_changed.emit()
