"""The shared validation screen (modules/sensor_validation.py) - StrikeWorks's
Validate step and Validate and annotate both: marking a sensor bad and good
again, the counts, Open video."""
import unittest

import numpy as np
import pandas as pd

from support import isolate, pump, qt_app, temp_dir


def _library():
    """A library with two processed sensors, S1 and S2."""
    lib = temp_dir("validation_view_")
    csv_dir = lib / "processed_sens_data" / "csv"
    csv_dir.mkdir(parents=True)
    t = np.arange(800) / 2000
    for stem in ("S1", "S2"):
        pd.DataFrame({"time_s": t, "pressure_kpa": 100 - 20 * np.exp(-((t - 0.2) / 0.02) ** 2),
                      "higacc_mag_g": np.abs(np.sin(t * 50)) * 30}).to_csv(
            csv_dir / f"{stem}.csv", index=False)
    return lib


class ValidationViewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qt_app()

    def setUp(self):
        isolate()
        from PySide6.QtWidgets import QWidget
        from modules import validation_core as vc
        from modules.sensor_validation import ValidationView
        self.lib = _library()
        self.host = QWidget()
        self.view = ValidationView(self.host)
        self.view.setParent(self.host)
        self.addCleanup(lambda: (self.host.deleteLater(), pump(50)))
        self.video = self.lib / "S1_vid_1.mp4"
        self.view.set_source(
            self.lib, vc.processed_sensor_files(self.lib),
            video_lookup=lambda stem: [self.video] if stem == "S1" else [])

    def _load(self, stem):
        self.view.load_sensor(stem)
        for _ in range(100):
            pump(20)
            if not self.view.loading:
                break
        self.assertEqual(self.view.current_stem, stem)

    def test_mark_bad_and_good_again(self):
        from modules import deployment_index as di
        self._load("S2")
        self.assertEqual(self.view.btn_mark.text(), "Mark bad")
        self.view.toggle_bad()
        index = di.read_index(self.lib).set_index("file")
        self.assertEqual(index.loc["S2", di.BAD_SENS_COL], "Y")
        self.assertEqual(self.view.btn_mark.text(), "Mark good")
        # bad sensors leave the list unless Show bad is ticked
        self.assertNotIn("S2", self.view.order())
        self.view.chk_show_bad.setChecked(True)
        self.assertIn("S2", self.view.order())
        self.view.toggle_bad()
        index = di.read_index(self.lib).set_index("file")
        self.assertEqual(index.loc["S2", di.BAD_SENS_COL], "N")
        self.assertEqual(self.view.btn_mark.text(), "Mark bad")

    def test_save_and_next_and_counts(self):
        self._load("S1")
        self.view.save_and_next()
        pump(50)
        self.assertIn("S1", self.view.validation_status()[1])    # user-validated
        self.assertIn("Reviewed by you: 1/2", self.view.lbl_counts.text())

    def test_open_video_only_with_a_video(self):
        self._load("S1")
        self.assertTrue(self.view.btn_video.isEnabled())
        self._load("S2")
        self.assertFalse(self.view.btn_video.isEnabled())


if __name__ == "__main__":
    unittest.main()
