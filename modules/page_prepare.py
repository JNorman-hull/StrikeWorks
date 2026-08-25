# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Controller for the Prepare page (Sensor Processing).

Two tabs: Sensor configuration, which chooses and edits the device this
session works with, and Study design, which plans a deployment - the site,
the machine and one set of conditions per treatment - and writes it into
the library so Process can label sensors treatment by treatment.

The page skeleton - title, subtitle and the QTabWidget - lives in main.ui;
the tab contents are built programmatically into the placeholder frames,
the same pattern the Machine Learning Analysis pages use.

Prepare comes first in the Sensor Processing workflow because everything
after it depends on the answer: Process scans for the sensor's extensions
and runs its parser, Validate plots at its sample rate, and Dataset creation
cuts windows of its length.
"""
from PySide6.QtCore import QObject, Signal

from .prepare_tab_sensor import SensorTab
from .prepare_tab_study import StudyTab


class PreparePage(QObject):
    """Binds the Prepare page widgets defined in main.ui."""

    status = Signal(str, int)

    def __init__(self, ui, window):
        super().__init__(window)
        self.ui = ui
        self.window = window

        self.tab_sensor = SensorTab(
            ui.frame_prepare_sensor, window, status=self.status.emit)
        self.tab_study = StudyTab(
            ui.frame_prepare_study, window, status=self.status.emit)
