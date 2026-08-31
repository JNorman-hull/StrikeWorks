# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Controller for the Model Prediction page (Machine Learning Analysis).

Owns the single shared PredictionState and the three tab controllers
(Predict / Inspect / Report). The page skeleton - title, subtitle and the
Predict/Inspect/Report QTabWidget - lives in main.ui; the tab contents are
built programmatically into the placeholder frames, following the same
pattern the other pages use for their matplotlib/pyqtgraph panels.

The tabs never hold their own copies of the model, dataset or results:
everything flows through PredictionState signals, so loading a model or
dataset, running a prediction, or selecting a record updates every tab.
"""
from PySide6.QtCore import QObject, Signal

from .ml_state import PredictionState
from .ml_tab_predict import PredictTab
from .ml_tab_inspect import InspectTab
from .ml_tab_report import ReportTab


class MLPredictionPage(QObject):
    """Binds the Model Prediction workflow to the widgets in main.ui."""

    status = Signal(str, int)

    def __init__(self, ui, window):
        super().__init__(window)
        self.ui = ui
        self.window = window

        self.state = PredictionState(self)
        try:
            self.state.app_version = ui.version.text()
        except AttributeError:
            pass
        self.state.status.connect(self.status)

        self.tab_predict = PredictTab(ui.frame_ml_predict, self.state, window,
                                      goto_inspect=self.goto_inspect)
        self.tab_inspect = InspectTab(ui.frame_ml_inspect, self.state, window)
        self.tab_report  = ReportTab(ui.frame_ml_report, self.state, window)

        # auto-load the deployed models from the default folder (silent -
        # a missing folder just leaves the compatibility check red)
        ok, msg = self.state.load_models_from_dir(self.state.models_dir)
        if ok:
            self.status.emit(msg, 4000)

    # ── dataset hand-off from Sensor Processing ──────────────────────────────
    def on_dataset_ready(self, df, source):
        """Receives the curated dataset from the Dataset creation page."""
        if df is None:
            return
        self.state.set_dataset(df, source=source)
        self.status.emit(
            f"Prediction dataset updated from Sensor Processing "
            f"({df['file'].nunique()} recordings).", 5000)

    # ── cross-page navigation ────────────────────────────────────────────────
    def goto_inspect(self, preset=None):
        self.window.navigate_to("btn_inspect_pred")
        if preset:
            self.tab_inspect.apply_filter_preset(preset)

    def goto_report(self):
        self.window.navigate_to("btn_export_report")
