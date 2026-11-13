"""Blade strike calculator: one sidebar button straight to its page (no
section panel), Calculator and Advanced analysis tabs, Calculate under the
configuration list, the blade profile table as tall as its rows, Advanced
options setting the sensitivity sweeps' ranges, and Advanced analysis
showing both species."""
import unittest
from pathlib import Path

from support import BSM_CONFIG, isolate, main_window, pump, qt_app


class RangeSliderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qt_app()

    def test_handles_keep_a_step_apart(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from modules.range_slider import RangeSlider
        s = RangeSlider(0.2, 2.0, 0.05, 0.6, 1.6)
        self.addCleanup(s.deleteLater)
        seen = []
        s.valuesChanged.connect(lambda a, b: seen.append((a, b)))
        self.assertEqual(s.values(), (0.6, 1.6))
        s.setValues(1.0, 0.4)                  # high under low: kept apart
        lo, hi = s.values()
        self.assertLess(lo, hi)
        s.setValues(0.6, 1.4)
        QTest.keyClick(s, Qt.Key.Key_Right)    # the high handle, by default
        self.assertEqual(seen[-1], (0.6, 1.45))
        self.assertEqual(seen[0], seen[-1])    # setValues doesn't signal


class BladeStrikePage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qt_app()
        isolate()
        cls.main, cls.window = main_window()
        cls.window.resize(1290, 690)
        cls.window.show()
        cls.window.expand_sidebar()
        pump(200)
        calc = cls.window.bsm_calculator_page
        calc.cmb_config.setCurrentIndex(
            max(calc.cmb_config.findText(Path(BSM_CONFIG).stem), 0))
        calc._load_selected_config()

    @classmethod
    def tearDownClass(cls):
        cls.window.close()
        cls.window.deleteLater()
        pump(50)

    def test_sidebar_button_opens_the_page(self):
        w, ui = self.window, self.window.ui
        self.assertEqual(ui.btn_bsm.text(), "Blade strike calculator")
        ui.btn_bsm.click()
        pump(400)
        self.assertIs(w.current_page(), w.bsm_page)
        self.assertEqual(ui.extraLeftBox.width(), 0)     # no section panel
        for name in ("btn_bsm_calculator", "btn_bsm_sensitivity"):
            self.assertTrue(getattr(ui, name).isHidden())
        self.assertEqual([w.bsm_page.tabs.tabText(i) for i in range(2)],
                         ["Calculator", "Advanced analysis"])

    def test_calculator(self):
        w = self.window
        w.navigate_to("btn_bsm")
        w.bsm_page.show_tab(0)
        pump(300)
        calc = w.bsm_calculator_page
        # Calculate under the configuration list
        self.assertIs(calc.btn_calc.parentWidget(),
                      calc.cmb_config.parentWidget())
        # every blade row shown, no scrolling
        tbl = calc.blade_tbl
        self.assertEqual(tbl.verticalScrollBar().maximum(), 0)
        self.assertEqual(tbl.minimumHeight(), tbl.maximumHeight())
        # Advanced options: today's sweep by default, in BSMState
        self.assertEqual(calc.sld_Q.values(), (0.6, 1.6))
        self.assertEqual(calc.sld_N.values(), (0.6, 1.4))
        self.assertEqual(calc.spin_q_step.value(), 0.2)
        self.assertIn("6 lines", calc.lbl_Q_range.text())
        self.assertIn("m³/s", calc.lbl_Q_range.text())
        calc.spin_q_step.setValue(0.5)
        self.assertEqual(w.bsm_state.sweep_options["q_step"], 0.5)
        self.assertIn("4 lines", calc.lbl_Q_range.text())   # 0.6 1 1.1 1.6
        calc.spin_q_step.setValue(0.2)
        # "Advanced model outputs" opens the other tab
        calc.btn_advanced.click()
        self.assertEqual(w.bsm_page.tabs.currentIndex(), 1)

    def test_advanced_analysis_both_species(self):
        from PySide6.QtWidgets import QPushButton
        from modules.bsm_model import sweep_q_multipliers
        w = self.window
        w.navigate_to("btn_bsm")
        w.bsm_page.show_tab(0)
        w.bsm_calculator_page.calculate()
        pump(100)
        page = w.bsm_analysis_page
        self.assertEqual(
            [page.results_tbl.item(r, 0).text()
             for r in range(page.results_tbl.rowCount())], ["Scaly", "Eel"])
        self.assertEqual(page.results_tbl.verticalScrollBar().maximum(), 0)
        for card in page.cards.values():
            self.assertIn("Pco - CEN (%)", card._rows)
        self.assertEqual(page.findChildren(QPushButton), [])  # no Generate report
        # the sweeps, at Advanced options' ranges, once the tab is shown
        self.assertIsNone(page.sweeps)
        w.bsm_page.show_tab(1)
        pump(200)
        opts = w.bsm_state.sweep_options
        self.assertEqual(len(page.sweeps["pco_n"]),
                         len(sweep_q_multipliers(opts["q_span"], opts["q_step"])))
        w.bsm_calculator_page.sld_Q.setValues(1.0, 1.4)
        w.bsm_calculator_page.sld_Q.valuesChanged.emit(1.0, 1.4)
        pump(200)                        # on screen: worked out again now
        self.assertEqual(len(page.sweeps["pco_n"]), 3)
        w.bsm_calculator_page.sld_Q.setValues(0.6, 1.6)
        w.bsm_calculator_page.sld_Q.valuesChanged.emit(0.6, 1.6)


if __name__ == "__main__":
    unittest.main()
