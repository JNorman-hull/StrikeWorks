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
        for name, (page, tab) in self.window._SUBMENU_TARGETS.items():
            with self.subTest(page=name):
                self.window.navigate_to(name)
                pump(50)
                shown = getattr(self.window, page)
                self.assertIs(self.window.current_page(), shown)
                if tab is not None:
                    self.assertEqual(shown.tabs.currentIndex(), tab)

    def test_hidden_pages_stay_hidden(self):
        self.window.openPanel("sensor")
        pump(600)
        for name in self.window._HIDDEN_PAGES:
            self.assertFalse(getattr(self.window.ui, name).isVisible(), name)

    def test_dialogs_build(self):
        from modules.about_dialog import AboutDialog
        from modules.ml_tab_report import ReportDialog
        from modules.page_settings import SettingsDialog
        for dialog in (AboutDialog(self.window), SettingsDialog(self.window),
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
        # the "Process" and "Report" headings open their first sub-step
        for row, page in ((2, 2), (6, 5)):
            dialog._on_step_clicked(dialog.step_list.item(row))
            pump(50)
            self.assertEqual(dialog.stack.currentIndex(), page)
            self.assertEqual(dialog.step_list.currentRow(), row + 1)
        # the small StrikeWorks | University of Hull logo, away from Home
        self.assertEqual(dialog.logos.layout().count(), 1)
        self.assertTrue(dialog.logos.isVisible())
        # the step's title in the top row; every box a plain heading
        self.assertTrue(dialog.lbl_title.text().startswith("Report blade strike"))
        from modules.layout import Section
        boxes = dialog.findChildren(Section)
        self.assertTrue(boxes)
        self.assertFalse(any(box.isCheckable() for box in boxes))
        # the session library's folder is its picker's tooltip
        self.assertNotIn("No library", dialog.editor.cmb_library.toolTip()
                         if self.window.session_state.library else "x")
        dialog.stack.setCurrentIndex(0)
        dialog._sync_step_highlight()
        self.assertFalse(dialog.logos.isVisible())
        dialog.hide()

    def test_windows_fit_the_screen_work_area(self):
        """Both windows, title bar and borders included, inside the screen
        without the taskbar (win_utils.fit_to_screen) - here the off-screen
        platform's 800 x 800 screen, smaller than either window's own size."""
        from modules import win_utils
        for window in (self.window, self.window.simple_mode_dialog):
            with self.subTest(window=type(window).__name__):
                win_utils.fit_to_screen(window, 1340, 860)
                area = window.screen().availableGeometry()
                self.assertTrue(area.contains(window.frameGeometry()),
                                (area, window.frameGeometry()))
                self.assertLess(window.height(), 860)
        self.window.resize(1400, 900)

    def test_no_stray_windows(self):
        from PySide6.QtWidgets import QDialog, QMainWindow
        pump(200)
        strays = [type(w).__name__ for w in qt_app().topLevelWidgets()
                  if w.isVisible() and not isinstance(w, (QDialog, QMainWindow))]
        self.assertEqual(strays, [])


class SimpleEdition(unittest.TestCase):
    """build.py --simple: Simple mode only, no way into the full app."""

    def test_the_full_app_is_locked(self):
        import os
        from unittest import mock
        qt_app()
        isolate()
        with mock.patch.dict(os.environ, {"STRIKEWORKS_EDITION": "simple"}):
            _main, window = main_window()
            dialog = window.simple_mode_dialog
            dialog.show()
            pump(100)
            self.assertFalse(dialog.btn_dev_toolkit.isVisible())
            dialog._go_development_toolkit()
            pump(100)
            self.assertFalse(window.isVisible())
            self.assertFalse(dialog.went_to_dev_toolkit)
            demos = [window.dev_console.cmb_demo.itemData(i)
                     for i in range(window.dev_console.cmb_demo.count())]
            self.assertEqual(demos, ["simple"])
            from modules.dev_runner import run_headless
            passed, message = run_headless(window, "advanced")
            self.assertFalse(passed)
            self.assertIn("isn't available", message)
            dialog.hide()
        # the full edition keeps its way in
        _main, window = main_window()
        self.assertFalse(window.simple_mode_dialog.btn_dev_toolkit.isHidden())


class DevelopmentToolkitDoor(unittest.TestCase):
    """StrikeWorks's "Development toolkit" button asks for the password;
    only the right one opens the full app, maximised."""

    def test_password(self):
        from unittest import mock
        from PySide6.QtWidgets import QInputDialog, QMessageBox
        from modules import page_simple_mode
        qt_app()
        isolate()
        _main, window = main_window()
        dialog = window.simple_mode_dialog
        dialog.show()
        pump(50)
        self.assertEqual(dialog.btn_dev_toolkit.text(), "Development toolkit")
        # on Home only
        self.assertTrue(dialog.btn_dev_toolkit.isVisible())
        dialog._go_next()
        pump(50)
        self.assertFalse(dialog.btn_dev_toolkit.isVisible())
        dialog._go_back()
        pump(50)
        self.assertTrue(dialog.btn_dev_toolkit.isVisible())
        self.assertEqual(window.ui.btn_simple_mode_nav.text(), "Go to StrikeWorks")
        with mock.patch.object(QMessageBox, "warning") as warned:
            for answer in (("", False), ("devmode", True)):
                with mock.patch.object(QInputDialog, "getText",
                                       return_value=answer):
                    dialog._go_development_toolkit()
                pump(50)
                self.assertFalse(window.isVisible())
                self.assertFalse(dialog.went_to_dev_toolkit)
            self.assertEqual(warned.call_count, 1)    # the wrong one, not Cancel
        with mock.patch.object(
                QInputDialog, "getText",
                return_value=(page_simple_mode._DEV_TOOLKIT_PASSWORD, True)):
            dialog._go_development_toolkit()
        pump(100)
        self.assertTrue(dialog.went_to_dev_toolkit)
        self.assertTrue(window.isVisible())
        self.assertTrue(window.isMaximized())
        self.assertFalse(dialog.isVisible())
        window.close()


if __name__ == "__main__":
    unittest.main()
