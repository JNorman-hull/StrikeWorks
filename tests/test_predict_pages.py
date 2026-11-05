"""The Predict and Results pages: one of each (ml_tab_predict), shared by
StrikeWorks's Predict and Report steps and the toolkit's Model prediction
> Predict - the Model card, Advanced features, the rings' rates and the
mortality plot."""
import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from support import isolate, main_window, pump, qt_app


class PredictPages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qt_app()
        cls.env = isolate()
        cls.main, cls.window = main_window()
        cls.state = cls.window.ml_prediction_page.state
        cls.sw = cls.window.simple_mode_dialog
        cls.tk = cls.window.ml_prediction_page.tab_predict

    @classmethod
    def tearDownClass(cls):
        cls.window.close()

    def test_both_apps_use_the_same_pages(self):
        from PySide6.QtWidgets import QComboBox
        from modules.ml_tab_predict import PredictPanel, ResultsPanel
        for panel, kind in ((self.sw.predict_panel, PredictPanel),
                            (self.tk.predict, PredictPanel),
                            (self.sw.results_panel, ResultsPanel),
                            (self.tk.results, ResultsPanel)):
            self.assertIs(type(panel), kind)
        # no model or folder pickers - the models are Settings' defaults
        self.assertEqual(self.tk.predict.findChildren(QComboBox), [])
        self.assertEqual(
            [b.text() for b in (self.tk.predict.btn_load_dataset,
                                self.tk.predict.btn_run_predict,
                                self.tk.predict.btn_advanced)],
            ["Load dataset CSV…", "Run prediction", "Advanced features"])
        # the low-confidence shortcut only where there's an Inspect
        self.assertIsNotNone(self.tk.predict._goto_inspect)
        self.assertIsNone(self.sw.predict_panel._goto_inspect)

    def test_model_card(self):
        from modules.ml_tab_predict import model_card_rows
        from modules.train_worker import macro_specificity
        state = SimpleNamespace(
            bin_model_path=Path("binary1_2.joblib"),
            bin_metrics={"model": "MiniRocket", "n_samples": 565,
                         "channels": ["a", "b"],
                         "out_of_fold_performance": {
                             "overall_accuracy": 0.9, "sensitivity": 0.8,
                             "specificity": 0.95, "roc_auc": 0.97}},
            mc_model_path=Path("multiclass1.joblib"),
            mc_metrics={"out_of_fold_performance": {
                "overall_accuracy": 0.6, "macro_recall": 0.5,
                "confusion_matrix": [[8, 2], [1, 9]]}},
            class_names=["r1", "r2"])
        rows = dict(model_card_rows(state))
        self.assertEqual(list(rows), [
            "Binary model", "Model type", "Version", "Mode", "Channels",
            "Training samples", "Binary performance", "Multiclass model",
            "Classes", "Multiclass performance"])
        self.assertEqual(rows["Version"], "1.2")
        self.assertEqual(rows["Training samples"], 565)
        self.assertEqual(rows["Channels"], "2 (a, b)")
        self.assertEqual(rows["Binary performance"],
                         "Accuracy = 0.900, Sensitivity = 0.800, "
                         "Specificity = 0.950, ROC AUC = 0.970")
        # no multiclass ROC AUC (not saved); specificity each class
        # against the rest: 9/10 and 8/10
        self.assertEqual(rows["Multiclass performance"],
                         "Accuracy = 0.600, Sensitivity = 0.500, "
                         "Specificity = 0.850")
        self.assertAlmostEqual(
            macro_specificity([[23, 15, 9], [13, 49, 34], [5, 23, 76]]),
            (182 / 200 + 113 / 151 + 100 / 143) / 3)
        self.assertIsNone(macro_specificity([]))

    def test_advanced_features_window(self):
        """Doesn't block, closes with its page, and is the same settings
        in both apps."""
        state = self.state
        self.window.home_page._go_advanced()
        self.window.show()
        target = next(name for name, (page, tab)
                      in self.window._SUBMENU_TARGETS.items()
                      if page == "ml_prediction_page" and tab == 0)
        self.window.navigate_to(target)
        self.tk.tabs.setCurrentIndex(0)
        pump(100)
        advanced = self.tk.predict.advanced
        advanced.bring_up()
        pump(50)
        self.assertTrue(advanced.isVisible())
        self.assertFalse(advanced.isModal())
        before = state.hig_peaks
        advanced.chk_hig_peaks.setChecked(not before)
        self.assertEqual(state.hig_peaks, not before)
        self.assertEqual(
            self.sw.predict_panel.advanced.chk_hig_peaks.isChecked(), not before)
        state.set_hig_peaks(before)
        self.tk.tabs.setCurrentIndex(1)    # the Predict page hidden
        pump(50)
        self.assertFalse(advanced.isVisible())
        self.window.hide()

    def test_rates_in_the_rings_and_one_line_when_done(self):
        state, panel = self.state, self.tk.predict
        saved = (state.summary, state.acc_summary, state.run_meta,
                 state.hig_peaks)
        try:
            state.summary = pd.DataFrame({"treatment": ["A"], "n": [10],
                                          "n_strike": [4]})
            state.acc_summary = pd.DataFrame({
                "n_collision": [1], "n_sensors": [10], "collision_rate": [0.1],
                "ci_lo": [0.02], "ci_hi": [0.4]})
            state.run_meta = {"mode": "binary", "n_files": 10}
            state.hig_peaks = True
            panel._on_run_started()
            self.assertIn("s elapsed", panel.lbl_status.text())
            self.assertFalse(panel.spinner.isHidden())
            panel._on_run_finished()
            self.assertTrue(panel.spinner.isHidden())
            self.assertRegex(panel.lbl_status.text(),
                             r"^Blade strike predicted: 10 recordings in [\d.]+ s$")
            self.assertEqual(panel.card_predicted_strikes._centre, "40.0%")
            self.assertEqual(panel.card_collisions._centre, "10.0%")
            self.assertTrue(panel.card_strike_classes.isHidden())
            panel._on_run_failed("Prediction is not ready.\nNo dataset")
            self.assertTrue(panel.lbl_status.text().startswith("✗ Prediction is not ready"))
        finally:
            (state.summary, state.acc_summary, state.run_meta,
             state.hig_peaks) = saved
            panel._show_results()

    def test_mortality(self):
        """The inputs are one pair for both apps; the plot shows once a
        blade strike model has been calculated, and a later calculation
        keeps the eel critical velocity set here."""
        bsm = self.window.bsm_state
        bsm.results = {}
        self.tk.results.refresh()
        self.assertTrue(self.tk.results.canvases["mortality"].isHidden())
        self.tk.predict.advanced.spin_eel_vcrit.setValue(6.5)
        self.assertEqual(bsm.eel_vcrit, 6.5)
        self.assertEqual(
            self.sw.predict_panel.advanced.spin_eel_vcrit.value(), 6.5)
        self.window.bsm_calculator_page.calculate()
        self.assertEqual(sorted(bsm.results), ["eel", "scaly"])
        self.assertEqual(bsm.eel_vcrit, 6.5)
        self.assertIn("eel: Pm=",
                      self.sw.predict_panel.advanced.lbl_mortality.text())
        self.sw.results_panel.refresh()
        self.assertFalse(self.sw.results_panel.canvases["mortality"].isHidden())


if __name__ == "__main__":
    unittest.main()
