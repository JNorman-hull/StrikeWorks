# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Controller for the Model Training page (Machine Learning Analysis).

Owns the single shared TrainingState and the four tab controllers
(Configure / Cross-validate / Evaluate / Deploy). The page skeleton lives in
main.ui; the tab contents are built programmatically into the placeholder
frames, as on the Model Prediction page.

The tabs enforce the scientific workflow: configure the run, cross-validate,
review the evaluation, then explicitly accept it by training and deploying
the final model. Deployed models land in the models folder Model Prediction
auto-discovers.
"""
from PySide6.QtCore import QObject, Signal

from .ml_train_state import TrainingState
from .ml_tab_train_configure import ConfigureTab
from .ml_tab_train_cv import CrossValidateTab
from .ml_tab_train_evaluate import EvaluateTab
from .ml_tab_train_deploy import DeployTab


class MLTrainingPage(QObject):
    """Binds the Model Training workflow to the widgets in main.ui."""

    status = Signal(str, int)
    model_deployed = Signal(str)   # path of the deployed model

    def __init__(self, ui, window):
        super().__init__(window)
        self.ui = ui
        self.window = window

        self.state = TrainingState(self)
        try:
            self.state.app_version = f"StrikeWorks {ui.version.text()}"
        except AttributeError:
            pass
        self.state.status.connect(self.status)
        self.state.deployed.connect(self.model_deployed)

        self.tab_configure = ConfigureTab(
            ui.frame_train_configure, self.state, window,
            goto_cv=self.goto_cv)
        self.tab_cv = CrossValidateTab(
            ui.frame_train_cv, self.state, window,
            goto_evaluate=self.goto_evaluate)
        self.tab_evaluate = EvaluateTab(
            ui.frame_train_evaluate, self.state, window)
        self.tab_deploy = DeployTab(
            ui.frame_train_deploy, self.state, window)

    # ── cross-tab navigation ─────────────────────────────────────────────────
    def goto_cv(self):
        self.ui.tabs_ml_training.setCurrentWidget(self.ui.tab_train_cv)

    def goto_evaluate(self):
        self.ui.tabs_ml_training.setCurrentWidget(self.ui.tab_train_evaluate)
