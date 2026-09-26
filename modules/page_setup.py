# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Setup and deploy's Sensor configuration and Study design tabs.

Sensor configuration chooses and edits the device the session works with;
Study design is a sampling-precision calculator (Wilson score interval).
The tab widget itself is in main.ui with its tab bar hidden - the sidebar
picks the tab (`main.py`'s `_SUBMENU_TARGETS`).
"""
from PySide6.QtCore import QObject, Signal

from .setup_sensor import SensorTab
from .setup_precision import PrecisionCalcTab


class SetupPage(QObject):
    """Builds the two tabs into main.ui's `tabs_prepare`."""

    status = Signal(str, int)

    def __init__(self, ui, window):
        super().__init__(window)
        self.ui = ui
        self.window = window

        self.tab_sensor = SensorTab(
            ui.frame_prepare_sensor, window, status=self.status.emit)
        self.tab_precision = PrecisionCalcTab(
            ui.frame_prepare_study, window, status=self.status.emit)
