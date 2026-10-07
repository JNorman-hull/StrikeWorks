# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Model training: Train (with model deployment) and Evaluate (the
sidebar picks the tab).

Owns the single shared TrainingState.

The tabs enforce the scientific workflow: configure and cross-validate the
run on Train, review the evaluation, then explicitly accept it by training
and deploying the final models. Deployed models land in the models folder
Model Prediction auto-discovers.
"""
from PySide6.QtCore import Signal

from .layout import TabbedPage
from .ml_train_state import TrainingState
from .ml_tab_train_configure import TrainTab
from .ml_tab_train_evaluate import EvaluateTab


class MLTrainingPage(TabbedPage):
    """Model training > Train and Evaluate."""

    model_deployed = Signal(str)   # path of the deployed model

    def __init__(self, main_window):
        super().__init__(main_window)
        self.state = TrainingState(self)
        self.state.app_version = f"StrikeWorks {main_window.ui.version.text()}"
        self.state.status.connect(self.status)
        self.state.deployed.connect(self.model_deployed)

        self.tab_train = TrainTab(self.state, main_window,
                                  goto_evaluate=self.goto_evaluate)
        self.tab_evaluate = EvaluateTab(self.state, main_window)
        self.tabs.addTab(self.tab_train, "Train")
        self.tabs.addTab(self.tab_evaluate, "Evaluate")
        # Train's "Model deployment" box
        self.deployment = self.tab_train.deployment

        # a deployment makes a new model evaluatable straight away
        self.state.deployed.connect(
            lambda _p: self.tab_evaluate.reload_sources())

    # ── cross-page navigation ────────────────────────────────────────────────
    def goto_evaluate(self):
        self.main_window.navigate_to("btn_evaluate_train")
