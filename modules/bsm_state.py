# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Shared state for the Mathematical Blade Strike Modelling section - the
same "one state object, several pages react to its signal" shape
`ml_state.PredictionState`/`ml_train_state.TrainingState` already use.

Calculator owns the run and publishes `LATEST_RESULT_PATH`; Analysis and
reporting re-sweeps and exports whenever a new result comes in
(`calculated`). Nothing here is Qt-multithreaded - `bsm_model.compute()`
is fast (one 200-point NumPy loop), so it runs straight on the GUI thread.
"""
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QObject, Signal

_APP_ROOT = Path(__file__).parent.parent
LATEST_RESULT_PATH = _APP_ROOT / "bsm_results" / "latest_result.json"


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
    builds it) and Analysis and reporting (which shows the same card)."""
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
    calculated = Signal(dict)   # the full result dict from bsm_model.compute()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.last_result = None

    def set_result(self, res):
        self.last_result = res
        self.calculated.emit(res)
