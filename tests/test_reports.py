"""Reports: the central report's figures come out at their fixed sizes,
Analysis and reporting's own button writes the same BSM section, and the
model evaluation report keeps every figure in a folder past Windows' path
limit and covers the models ticked in Export and report."""
import shutil
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

from support import BSM_CONFIG, isolate, main_window, pump, qt_app, temp_dir


def _size_cm(png, dpi=300):
    from PIL import Image
    with Image.open(png) as im:
        return tuple(round(v / dpi * 2.54, 1) for v in im.size)


def _model_entries():
    """This session's binary and multiclass models and a deployed binary,
    with enough cross-validation results to draw every figure."""
    from modules.ml_model_library import ModelEntry, roc_pr_from_scores
    rng = np.random.default_rng(0)
    y = np.r_[np.zeros(10, int), np.ones(10, int)]
    p = np.clip(y * 0.5 + rng.random(20) * 0.5, 0, 1)
    pred = (p >= 0.5).astype(int)
    cv_bin = pd.DataFrame({"file": [f"S{i}" for i in range(20)], "y_true": y,
                           "probability": p, "y_pred": pred,
                           "correct": pred == y, "treatment": ["A", "B"] * 10})
    bin_metrics = {
        "out_of_fold_performance": {
            "roc_auc": 0.9, "pr_auc": 0.9, "overall_accuracy": 0.9,
            "optimal_threshold": 0.5, "sensitivity": 0.9, "specificity": 0.9,
            "confusion_matrix": {"tn": 9, "fp": 1, "fn": 1, "tp": 9}},
        "performance_by_strike_type": {"direct": {"n_files": 10,
                                                  "accuracy": 0.9}}}
    names = ["region_1", "region_2"]
    cv_mc = pd.DataFrame({"file": [f"S{i}" for i in range(10)],
                          "true_class": names * 5,
                          "prob_region_1": rng.random(10),
                          "correct": [True, False] * 5, "treatment": "A"})
    cv_mc["prob_region_2"] = 1 - cv_mc["prob_region_1"]
    mc_metrics = {
        "class_names": names,
        "out_of_fold_performance": {
            "overall_accuracy": 0.5, "confusion_matrix": [[3, 2], [2, 3]],
            "per_class_metrics": {n: {"precision": 0.6, "recall": 0.6,
                                      "f1_score": 0.6, "support": 5}
                                  for n in names}}}
    return [
        ModelEntry("This session - binary model", "binary", bin_metrics,
                   cv_bin, roc_pr_from_scores(y, p)),
        ModelEntry("This session - multiclass model", "multiclass",
                   mc_metrics, cv_mc),
        ModelEntry("binary1_0  (deployed binary, v1.0)", "binary",
                   bin_metrics, cv_bin, roc_pr_from_scores(y, p),
                   model_path=Path("models") / "binary1_0.joblib",
                   source="deployed"),
    ]


class TrainingReport(unittest.TestCase):
    def test_every_figure_past_the_path_limit(self):
        """A report folder deep enough that the figures' paths run past
        260 characters (a library in OneDrive) still gets them all."""
        from modules import ml_report, report_center
        entries = _model_entries()
        out = temp_dir("report_")
        deep = out.joinpath(*["a_long_folder_name_like_a_onedrive_path"] * 6)
        self.assertGreater(len(str(deep / "training_figures" / "session_binary"
                                   / "accuracy_by_strike_type.png")), 260)
        try:
            with mock.patch.object(report_center, "available_model_entries",
                                   return_value=entries):
                section = report_center.training_section(
                    None, lambda: entries[:2])
            doc, warnings = report_center.assemble([section], deep,
                                                   {"training"})
            self.assertEqual(warnings, [])
            html = ml_report.long_path(doc).read_text(encoding="utf-8")
            # five figures each for the binary and the multiclass model
            self.assertEqual(html.count("<img "), 10)
        finally:
            shutil.rmtree(ml_report.long_path(out), ignore_errors=True)


class Reports(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qt_app()
        isolate()
        cls.main, cls.window = main_window()
        calc = cls.window.bsm_calculator_page
        calc.cmb_config.setCurrentIndex(
            max(calc.cmb_config.findText(Path(BSM_CONFIG).stem), 0))
        calc._load_selected_config()
        calc.calculate()
        pump(200)

    def test_central_report_figures(self):
        from modules import report_center
        out = temp_dir("report_")
        sections = report_center.all_sections(self.window)
        doc, warnings = report_center.assemble(
            sections, out, {"bsm", "study_design", "biological"})
        self.assertTrue(doc.exists())
        self.assertEqual(warnings, [])
        self.assertEqual(_size_cm(out / "bsm_figures" / "bsm_results_panels.png"),
                         (12.0, 12.0))
        for species in ("scaly", "eel"):
            self.assertEqual(
                _size_cm(out / "bsm_figures" / f"sensitivity_sweeps_{species}.png"),
                (20.0, 16.0))
        self.assertEqual(
            _size_cm(out / "study_design_figures" / "precision_ci_vs_n.png"),
            (14.0, 10.0))
        # two Blade strike model bars and nothing to compare yet: 12 x 10
        self.assertEqual(
            _size_cm(out / "model_comparison_figures" / "comparison_bars.png"),
            (12.0, 10.0))

    def test_dialog_model_checklist(self):
        """Export and report's evaluation section covers the models ticked
        in its list - this session's to start with - and keeps the ticks."""
        from modules import report_center
        from modules.ml_tab_report import ReportDialog
        entries = _model_entries()
        with mock.patch.object(report_center, "available_model_entries",
                               return_value=entries):
            dlg = ReportDialog(self.window.ml_prediction_page.state,
                               self.window)
            try:
                def ticked():
                    return [e.label for e in dlg._ticked_models()]
                self.assertEqual(ticked(), [e.label for e in entries[:2]])
                dlg._model_checks[1][0].setChecked(False)
                dlg._model_checks[2][0].setChecked(True)
                dlg._refresh_checklist()
                self.assertEqual(ticked(), [entries[0].label, entries[2].label])
                training = next(s for s in dlg._sections if s.key == "training")
                self.assertTrue(training.available)
            finally:
                dlg.close()
                dlg.deleteLater()
                pump(50)

    def test_analysis_page_report(self):
        from PySide6.QtWidgets import QFileDialog
        out = temp_dir("bsm_report_")
        original = QFileDialog.getExistingDirectory
        QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: str(out))
        try:
            self.window.bsm_analysis_page._generate_report()
        finally:
            QFileDialog.getExistingDirectory = original
        self.assertTrue((out / "report.html").exists())
        self.assertTrue((out / "bsm_results.csv").exists())
        self.assertTrue((out / "bsm_figures" / "bsm_results_panels.png").exists())


if __name__ == "__main__":
    unittest.main()
