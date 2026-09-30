"""Strike severity: the HIG peak bands the prediction worker writes and the
app shows."""
import unittest

import numpy as np
import pandas as pd

from modules import predict_worker as pw
from modules import severity


class SeverityTest(unittest.TestCase):
    def test_worker_and_app_agree_on_the_thresholds(self):
        self.assertEqual(tuple(pw.SEVERITY_THRESHOLDS_G), severity.THRESHOLDS_G)
        self.assertEqual(pw.SEVERE_G, severity.SEVERE_G)
        self.assertEqual(tuple(pw.SEVERITY_BANDS), severity.BANDS)

    def test_bands_are_over_each_threshold(self):
        peaks = np.array([10.0, 95.0, 95.1, 200.0, 250.0, 400.0, 400.1, 900.0])
        self.assertEqual(list(pw._severity_band(peaks)), [
            "<=95 g", "<=95 g", "95-200 g", "95-200 g", "200-400 g",
            "200-400 g", ">400 g", ">400 g"])

    def test_peak_per_recording(self):
        df = pd.DataFrame({"file": ["a", "a", "b", "b"],
                           "higacc_mag_g": [50.0, 420.0, 10.0, 120.0]})
        meta = pd.DataFrame({"file": ["b", "a"]})
        peaks, source = pw._hig_peaks(df, meta)
        self.assertEqual(list(peaks), [120.0, 420.0])
        self.assertEqual(source, "higacc_mag_g")

    def test_peak_from_the_axes_without_a_magnitude_column(self):
        df = pd.DataFrame({"file": ["a"], "higacc_x_g": [300.0],
                           "higacc_y_g": [400.0], "higacc_z_g": [0.0]})
        peaks, _ = pw._hig_peaks(df, pd.DataFrame({"file": ["a"]}))
        self.assertAlmostEqual(peaks[0], 500.0)

    def test_no_hig_means_no_severity(self):
        df = pd.DataFrame({"file": ["a"], "pressure_kpa": [100.0]})
        self.assertEqual(pw._hig_peaks(df, pd.DataFrame({"file": ["a"]})),
                         (None, None))
        self.assertFalse(severity.available(pd.DataFrame({"n": [3]})))

    def test_table_and_band_counts(self):
        row = pd.Series({"n": 10, "n_strike": 9, "n_over_95g": 6,
                         "n_over_200g": 3, "n_over_400g": 1,
                         "severe_ci_lo": 0.018, "severe_ci_hi": 0.404,
                         "n_strike_severe": 1})
        self.assertEqual(severity.table_values(row), [
            "6 (60%)", "3 (30%)", "1 (10%)", "1.8% – 40.4%", "1 of 9"])
        preds = pd.DataFrame({"severity": ["<=95 g", ">400 g", "<=95 g",
                                           "95-200 g"]})
        self.assertEqual([c for _l, c in severity.band_counts(preds)],
                         [2, 1, 0, 1])


if __name__ == "__main__":
    unittest.main()
