# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Setup and deploy's Sensor configuration and Study design tabs.

Sensor configuration chooses and edits the device the session works with;
Study design is a sampling-precision calculator (Wilson score interval).
The tab bar is hidden - the sidebar picks the tab (`main.py`'s
`_SUBMENU_TARGETS`).
"""
from .layout import TabbedPage
from .setup_sensor import SensorTab
from .setup_precision import PrecisionCalcTab


class SetupPage(TabbedPage):
    """Sensor configuration and Study design."""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.tab_sensor = SensorTab(main_window, status=self.status.emit)
        self.tab_precision = PrecisionCalcTab(main_window,
                                              status=self.status.emit)
        self.tabs.addTab(self.tab_sensor, "Sensor configuration")
        self.tabs.addTab(self.tab_precision, "Study design")
