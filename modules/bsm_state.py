# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Shared state for the Mathematical Blade Strike Modelling section - the
same "one state object, several pages react to its signal" shape
`ml_state.PredictionState`/`ml_train_state.TrainingState` already use.

Calculator owns the run; Sensitivity re-sweeps whenever a new result comes
in (`calculated`), Reporting exports whatever the state is currently
holding. Nothing here is Qt-multithreaded - `bsm_model.compute()` is fast
(one 200-point NumPy loop), so it runs straight on the GUI thread.
"""
from pathlib import Path

from PySide6.QtCore import QObject, Signal

_APP_ROOT = Path(__file__).parent.parent
LATEST_RESULT_PATH = _APP_ROOT / "bsm_results" / "latest_result.json"


class BSMState(QObject):
    calculated = Signal(dict)   # the full result dict from bsm_model.compute()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.last_result = None

    def set_result(self, res):
        self.last_result = res
        self.calculated.emit(res)
