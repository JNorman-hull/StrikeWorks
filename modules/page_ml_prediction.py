# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Model prediction: Predict and Inspect (the sidebar picks the tab), and
the Export and report dialog.

Owns the single shared PredictionState.

The tabs never hold their own copies of the model, dataset or results:
everything flows through PredictionState signals, so loading a model or
dataset, running a prediction, or selecting a record updates every tab.
"""
from .layout import TabbedPage
from .ml_state import PredictionState
from .ml_tab_predict import PredictTab
from .ml_tab_inspect import InspectTab
from .ml_tab_report import ReportDialog


class MLPredictionPage(TabbedPage):
    """Model prediction > Predict and Inspect."""

    def __init__(self, main_window, bsm_state=None):
        super().__init__(main_window)
        self.bsm_state = bsm_state

        self.state = PredictionState(self)
        self.state.app_version = main_window.ui.version.text()
        self.state.status.connect(self.status)

        self.tab_predict = PredictTab(self.state, main_window,
                                      goto_inspect=self.goto_inspect,
                                      bsm_state=bsm_state)
        self.tab_inspect = InspectTab(self.state, main_window)
        self.tabs.addTab(self.tab_predict, "Predict")
        self.tabs.addTab(self.tab_inspect, "Inspect")
        self.report_dialog = ReportDialog(self.state, main_window)

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
        self.main_window.navigate_to("btn_inspect_pred")
        if preset:
            self.tab_inspect.apply_filter_preset(preset)

    def open_report(self):
        """Export and report - a pop-up dialog (see ml_tab_report.py)
        rather than a page/tab, opened from the pinned sidebar button."""
        self.report_dialog.refresh()
        self.report_dialog.exec()
