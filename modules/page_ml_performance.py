# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Controller for the Model Performance page (Machine Learning Analysis).

Evaluates deployed models independently of any training session, reusing
the Evaluate tab built for Model Training (``ml_tab_train_evaluate``) with
no session state attached: the model list is whatever the models folder
holds, and the same model report can be exported from here.
"""
from PySide6.QtCore import QObject, Signal

from .ml_tab_train_evaluate import EvaluateTab


class MLPerformancePage(QObject):
    """Binds deployed-model evaluation to the Model Performance page."""

    status = Signal(str, int)

    def __init__(self, ui, window):
        super().__init__(window)
        self.ui = ui
        self.window = window

        self.evaluate = EvaluateTab(ui.content_ml_performance, None, window)

    def reload(self):
        """Re-scan the models folder (e.g. after a deployment)."""
        self.evaluate._reload_sources()
