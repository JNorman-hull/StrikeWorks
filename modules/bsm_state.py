"""Shared state for the Blade strike calculator. Calculator runs the model
and writes `LATEST_RESULT_PATH`; Advanced analysis, Model comparison and
Predict follow `calculated`, `calculated_all` and `sweep_options_changed`.
`bsm_model.compute()` is fast enough to run on the GUI thread.
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
    """The result summary written to LATEST_RESULT_PATH and shown on
    Calculator's output card."""
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
        # Predict's mortality inputs (Advanced features), shared by both
        # windows: eel critical velocity (the first run's own until changed)
        # and the treatment the mortality plot is labelled with
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
        """Store both species' results from one Calculate. `last_result` and
        `calculated` stay the Species combo's choice (Advanced analysis's sweeps,
        Study design's Load); `results` and `calculated_all` hold both, keyed by
        species, for Model comparison and Predict's mortality."""
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
