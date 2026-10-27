"""HIG peak analysis (modules/hig_peaks.py) on synthetic 2000 Hz signals."""
import unittest

import numpy as np
import pandas as pd

from modules import hig_peaks as hp

FS = 2000


def _time(n, t0=10.0):
    return t0 + np.arange(n) / FS


def _signal():
    """400 samples: a narrow 300 g collision at 50; two peaks 3 samples
    apart at 100 (200 g) and 103 (250 g); a 90 g peak (too low) at 150; a
    bumpy 160 g plateau around 200 (not prominent enough); a broad 300 g
    shear at 300."""
    acc = np.zeros(400)
    acc[48:53] = [50, 150, 300, 150, 50]
    acc[98:106] = [0, 60, 200, 60, 100, 250, 80, 0]
    acc[149:152] = [0, 90, 0]
    acc[195:206] = [140, 145, 150, 155, 150, 160, 150, 155, 150, 145, 140]
    acc[290:311] = 250
    acc[300] = 300
    return acc


class FindPeaks(unittest.TestCase):
    def test_height_prominence_distance_and_type(self):
        peaks = hp.find_peaks(_signal(), _time(400))
        self.assertEqual(list(peaks["peak_index"]), [50, 103, 300])
        self.assertEqual(list(peaks["peak_number"]), [1, 2, 3])
        self.assertEqual(list(peaks["peak_g"]), [300.0, 250.0, 300.0])
        self.assertEqual(list(peaks["peak_type"]),
                         ["collision", "collision", "shear"])
        self.assertEqual(list(peaks["duration_samples"]), [2, 2, 22])
        self.assertAlmostEqual(peaks["peak_time_s"].iloc[0], 10.025)

    def test_nothing_to_find(self):
        self.assertEqual(len(hp.find_peaks(np.zeros(400), _time(400))), 0)
        self.assertEqual(len(hp.find_peaks([1.0, 2.0], _time(2))), 0)


def _dataset():
    """a: the signal above; b: one 150 g event; c: a 450 g collision just
    after the nadir; d: a 600-row window whose 500 g event is 0.14 s
    before the nadir, outside the region of interest."""
    parts = []

    def add(name, acc, treatment):
        parts.append(pd.DataFrame({"file": name, "time_s": _time(len(acc)),
                                   "higacc_mag_g": acc,
                                   "treatment": treatment}))
    add("a", _signal(), "T1")
    b = np.zeros(400)
    b[209:212] = [0, 150, 0]
    add("b", b, "T1")
    c = np.zeros(400)
    c[204:207] = [100, 450, 100]
    add("c", c, "T2")
    d = np.zeros(600)
    d[19:22] = [0, 500, 0]
    add("d", d, "T2")
    return pd.concat(parts, ignore_index=True)


class Analyse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = _dataset()
        cls.events, cls.per_file = hp.analyse(cls.df)

    def test_per_recording(self):
        pf = self.per_file
        self.assertEqual(list(pf.index), ["a", "b", "c", "d"])
        self.assertEqual(list(pf["n_events"]), [3, 1, 1, 0])
        self.assertEqual(list(pf["n_events_200g"]), [3, 0, 1, 0])
        self.assertEqual(list(pf["n_events_400g"]), [0, 0, 1, 0])
        self.assertEqual(list(pf["collision"]), [0, 0, 1, 0])
        self.assertEqual(pf.loc["c", "collision_g"], 450.0)
        self.assertAlmostEqual(pf.loc["c", "collision_time_s"], 10.1025)
        self.assertTrue(np.isnan(pf.loc["d", "max_event_g"]))

    def test_events_outside_the_nadir_window_are_kept_but_not_counted(self):
        d = self.events[self.events["file"] == "d"]
        self.assertEqual(len(d), 1)
        self.assertFalse(bool(d["in_roi"].iloc[0]))
        self.assertAlmostEqual(d["time_from_nadir_s"].iloc[0], -0.14)

    def test_no_hig_channel(self):
        self.assertEqual(hp.analyse(self.df.drop(columns="higacc_mag_g")),
                         (None, None))

    def test_summary_by_treatment(self):
        tx = self.df.groupby("file")["treatment"].first()
        sm = hp.summary(self.events, self.per_file, tx).set_index("treatment")
        self.assertEqual(list(sm.index), ["T1", "T2", hp.ALL_LABEL])
        self.assertEqual(list(sm["n_events_95g"]), [4, 1, 5])
        self.assertEqual(list(sm["n_events_200g"]), [3, 1, 4])
        self.assertEqual(list(sm["n_events_400g"]), [0, 1, 1])
        self.assertEqual(list(sm["n_sensors"]), [2, 2, 4])
        self.assertEqual(list(sm["n_collision"]), [0, 1, 1])
        t1 = sm.loc["T1"]
        self.assertEqual((t1["acc_min_g"], t1["acc_q1_g"], t1["acc_median_g"],
                          t1["acc_q3_g"], t1["acc_max_g"]),
                         (150.0, 225.0, 275.0, 300.0, 300.0))
        p, lo, hi = hp.wilson_ci(1, 2)
        self.assertAlmostEqual(sm.loc["T2", "collision_rate"], p)
        self.assertAlmostEqual(sm.loc["T2", "ci_lo"], round(lo, 6))
        self.assertAlmostEqual(sm.loc["T2", "ci_hi"], round(hi, 6))

    def test_table_cells(self):
        tx = self.df.groupby("file")["treatment"].first()
        sm = hp.summary(self.events, self.per_file, tx)
        rows = hp.table_rows(sm)
        self.assertTrue(hp.show_treatment(sm))
        treatment, roi, cells = rows[1]
        self.assertEqual((treatment, roi), ("T2", hp.ROI_LABEL))
        self.assertEqual(cells, ["1", "1", "1", "2", "1",
                                 "50.0% [9.5 - 90.5] †",
                                 "450.0", "450.0", "450.0 - 450.0"])
        self.assertEqual(len(cells), len(hp.TABLE_COLUMNS))

    def test_one_group_without_treatments(self):
        sm = hp.summary(self.events, self.per_file)
        self.assertEqual(list(sm["treatment"]), [hp.ALL_LABEL])
        self.assertFalse(hp.show_treatment(sm))

    def test_peak_figure(self):
        """a) a box of per-recording peaks per treatment, b) the event
        counts, c) the collision probability on 0-100%."""
        from matplotlib.figure import Figure

        from modules import ml_figures
        tx = self.df.groupby("file")["treatment"].first()
        sm = hp.summary(self.events, self.per_file, tx)
        predictions = pd.DataFrame({
            "file": ["a", "b", "c", "d"], "treatment": ["T1", "T1", "T2", "T2"],
            "hig_peak_g": self.df.groupby("file")["higacc_mag_g"].max().values})
        fig = Figure(figsize=(10.5, 3.6))
        ml_figures.draw_peak_summary(fig, sm, predictions)
        ax_a, ax_b, ax_c = fig.axes
        self.assertEqual([t.get_text() for t in ax_a.get_xticklabels()],
                         ["T1", "T2"])
        self.assertEqual(len(ax_a.patches), 2)       # one box per treatment
        self.assertEqual(ax_c.get_ylim(), (0.0, 100.0))
        texts = [t.get_text() for ax in fig.axes for t in ax.texts]
        self.assertEqual(texts[:2], ["a)", "n = 4"])
        self.assertIn("CI = 95%\nn = 4", texts)
        self.assertIn("50.0%", [t.get_text() for t in ax_c.texts])

        # treatments read back from CSV as numbers still find their peaks
        sm_num = sm.assign(treatment=sm["treatment"].map(
            {"T1": 500, "T2": 700, hp.ALL_LABEL: hp.ALL_LABEL}))
        pred_num = predictions.assign(treatment=[500.0, 500.0, 700.0, 700.0])
        ml_figures.draw_peak_summary(fig, sm_num, pred_num)
        self.assertEqual(len(fig.axes[0].patches), 2)


class CentredTraces(unittest.TestCase):
    def test_peak_and_nadir_sit_at_one_half(self):
        df = _dataset()
        tr = hp.centred_traces(df, ["a"], facet_col="treatment")
        self.assertEqual(len(tr), 400)
        self.assertEqual(set(tr["facet"]), {"T1"})
        # the first of the two 300 g maxima, sample 50; the nadir, sample 200
        self.assertAlmostEqual(tr["time_norm_acc"].iloc[50], 0.5)
        self.assertAlmostEqual(tr["time_norm_nadir"].iloc[200], 0.5)
        for col in ("time_norm_acc", "time_norm_nadir"):
            self.assertAlmostEqual(tr[col].iloc[0], 0.0)
            self.assertAlmostEqual(tr[col].iloc[-1], 1.0)
        med = hp.median_trace(tr, "time_norm_nadir")
        self.assertEqual(set(med["facet"]), {"T1"})
        self.assertAlmostEqual(med["time_bin"].diff().dropna().min(),
                               hp.MEDIAN_BIN)

    def test_one_panel_per_treatment(self):
        """Prediction's traces are faceted by treatment, whatever else the
        dataset has (a deployment_id only some recordings carry), and a
        recording with no treatment is "Not recorded", not "nan"."""
        from matplotlib.figure import Figure
        from support import isolate, qt_app
        from modules import ml_figures
        from modules.ml_state import PredictionState
        qt_app()
        isolate()
        df = _dataset()
        df["deployment_id"] = np.where(df["file"] == "c", "Dep1", None)
        df.loc[df["file"] == "d", "treatment"] = np.nan
        state = PredictionState()
        state.acc_summary = pd.DataFrame()
        state.dataset_df = df
        state.run_id = "r"
        state.predictions = pd.DataFrame({"file": list("abcd"),
                                          "collision": [1, 0, 1, 1]})
        tr = state.collision_traces()
        self.assertEqual(set(tr["facet"]), {"T1", "T2", hp.NOT_RECORDED_LABEL})
        fig = Figure()
        ml_figures.draw_acc_centred(fig, tr)
        titles = [ax.get_title() for ax in fig.axes if ax.get_visible()]
        self.assertEqual([t.split(" (")[0] for t in titles],
                         sorted(["T1", "T2", hp.NOT_RECORDED_LABEL]))


if __name__ == "__main__":
    unittest.main()
