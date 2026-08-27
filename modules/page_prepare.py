# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Controller for the two tabs behind Setup and deploy's Sensor
configuration and Study design sidebar entries (see ROADMAP.md Chunk 5).

Sensor configuration chooses and edits the device this session works with.
Study design is a sampling-precision calculator (Wilson score interval) -
deployment/treatment planning itself moved to the standalone Create and
edit deployment page, which now owns writing the plan into the library and
building its folder structure.

The tab skeleton - the QTabWidget itself - lives in main.ui; the tab
contents are built programmatically into the placeholder frames, the same
pattern the Machine Learning Analysis pages use. (`tabs_prepare`'s own tab
bar is hidden - Setup and deploy's sidebar drives which tab shows, per
`main.py`'s `_SUBMENU_TARGETS`.)
"""
from PySide6.QtCore import QObject, Signal

from .prepare_tab_sensor import SensorTab
from .prepare_tab_precision import PrecisionCalcTab


class PreparePage(QObject):
    """Binds the Prepare page widgets defined in main.ui."""

    status = Signal(str, int)

    def __init__(self, ui, window):
        super().__init__(window)
        self.ui = ui
        self.window = window

        self.tab_sensor = SensorTab(
            ui.frame_prepare_sensor, window, status=self.status.emit)
        self.tab_precision = PrecisionCalcTab(
            ui.frame_prepare_study, window, status=self.status.emit)
