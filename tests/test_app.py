"""The app starts, and every page and dialog opens, offscreen, with
throwaway settings."""
import unittest

from support import isolate, main_window, pump, qt_app


class AppStarts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qt_app()
        cls.env = isolate()
        cls.main, cls.window = main_window()
        cls.window.resize(1400, 900)
        cls.window.show()
        cls.window.home_page._go_advanced()
        pump(300)

    @classmethod
    def tearDownClass(cls):
        cls.window.close()

    def test_every_page_opens(self):
        stacked = self.window.ui.stackedWidget
        for name, (page, _tabs, _index) in self.window._SUBMENU_TARGETS.items():
            with self.subTest(page=name):
                self.window.navigate_to(name)
                pump(50)
                self.assertIs(stacked.currentWidget(),
                              getattr(self.window.ui, page))

    def test_hidden_pages_stay_hidden(self):
        self.window.openPanel("sensor")
        pump(600)
        for name in self.window._HIDDEN_PAGES:
            self.assertFalse(getattr(self.window.ui, name).isVisible(), name)

    def test_dialogs_build(self):
        from modules.about_dialog import AboutDialog
        from modules.ml_tab_report import ReportDialog
        from modules.page_adjustments import AdjustmentsDialog
        for dialog in (AboutDialog(self.window), AdjustmentsDialog(self.window),
                       ReportDialog(self.window.ml_prediction_page.state,
                                    self.window)):
            dialog.show()
            pump(50)
            dialog.close()

    def test_simple_mode_steps(self):
        dialog = self.window.simple_mode_dialog
        dialog.show()
        for index in range(dialog.stack.count()):
            dialog.stack.setCurrentIndex(index)
            pump(50)
        dialog.hide()

    def test_no_stray_windows(self):
        from PySide6.QtWidgets import QDialog, QMainWindow
        pump(200)
        strays = [type(w).__name__ for w in qt_app().topLevelWidgets()
                  if w.isVisible() and not isinstance(w, (QDialog, QMainWindow))]
        self.assertEqual(strays, [])


if __name__ == "__main__":
    unittest.main()
