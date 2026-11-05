# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Blade strike calculator (the sidebar's button of that name - no
section panel): two tabs, Calculator (page_bsm_calculator.py) and
Advanced analysis (page_bsm_analysis.py), the second also opened by
Calculator's "Advanced model outputs". Both follow the shared BSMState.
"""
from PySide6.QtWidgets import QTabWidget, QVBoxLayout

from .layout import Page
from .page_bsm_analysis import BSMAnalysisPage
from .page_bsm_calculator import CalculatorPage

CALCULATOR, ADVANCED = 0, 1          # the tabs


class BladeStrikePage(Page):

    def __init__(self, main_window, bsm_state):
        super().__init__(main_window)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.calculator = CalculatorPage(main_window, bsm_state)
        self.analysis = BSMAnalysisPage(main_window, bsm_state)
        self.tabs = QTabWidget()
        for page, name in ((self.calculator, "Calculator"),
                           (self.analysis, "Advanced analysis")):
            page.setContentsMargins(0, 0, 0, 0)      # (this page has its own)
            page.status.connect(self.status)
            self.tabs.addTab(page, name)
        v.addWidget(self.tabs)
        self.calculator.advanced_requested.connect(
            lambda: self.show_tab(ADVANCED))

    def show_tab(self, index):
        self.tabs.setCurrentIndex(index)
