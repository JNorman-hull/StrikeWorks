"""Reports: the central report's figures come out at their fixed sizes, and
Analysis and reporting's own button writes the same BSM section."""
import unittest
from pathlib import Path

from support import BSM_CONFIG, isolate, main_window, pump, qt_app, temp_dir


def _size_cm(png, dpi=300):
    from PIL import Image
    with Image.open(png) as im:
        return tuple(round(v / dpi * 2.54, 1) for v in im.size)


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

    def test_analysis_page_report(self):
        from PySide6.QtWidgets import QFileDialog
        out = temp_dir("bsm_report_")
        original = QFileDialog.getExistingDirectory
        QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: str(out))
        try:
            self.window.bsm_sensitivity_page._generate_report()
        finally:
            QFileDialog.getExistingDirectory = original
        self.assertTrue((out / "report.html").exists())
        self.assertTrue((out / "bsm_results.csv").exists())
        self.assertTrue((out / "bsm_figures" / "bsm_results_panels.png").exists())


if __name__ == "__main__":
    unittest.main()
