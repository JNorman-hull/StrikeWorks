"""EEL tag reader against synthetic files that exercise the format
specification's rules (headers, re-emitted records, firmware generation,
wrapped pressure, timebase checks)."""
import unittest

import numpy as np

from support import temp_dir

from modules import eel_format as ef, sensor_config as sc

RATE = 2500
STEP = RATE // 100
STEM = "EEL-0020903101500"
EVENT_TICK = 10 * RATE


def _hig_bytes(records):
    arr = np.zeros(len(records), dtype=ef.HIG_DTYPE)
    for i, (tick, ax, ay, az) in enumerate(records):
        arr[i] = (tick, ax, ay, az, ef.TERMINATOR)
    return arr.tobytes()


def _imp_bytes(records, header):
    arr = np.zeros(len(records) + 1, dtype=ef.IMP_DTYPE)
    arr[0] = header
    for i, r in enumerate(records, start=1):
        arr[i] = r
    return arr.tobytes()


def _write_deployment(folder):
    """E10 header (640 Hz filter, 60 g threshold), a 2000-sample start-up
    flush, one 250 g event at 10 s with 20 re-emitted records in it, gen-1
    IMP (gyro Y copies accel Z) with a pressure dip at the event and one
    wrapped pressure sample and 2 stray trailing bytes."""
    flush = [(t, 0, -10, 0) for t in range(1, 2001)]
    event = []
    for k in range(1500):
        g = int(2500 * np.exp(-((k - 100) / 30.0) ** 2))
        event.append((EVENT_TICK + k, g, -10, g // 2))
    hig = [(0, 640, RATE, 60)] + flush + event[:400] + event[200:220] + event[400:]
    (folder / f"{STEM}.HIG").write_bytes(_hig_bytes(hig) + b"\x00\x01")

    imp = []
    for k in range(2000):
        t = (k + 1) * STEP
        p = 10000 - int(3000 * np.exp(-((t / RATE - 10.02) / 0.05) ** 2))
        if k == 500:
            p = 0
        az = 2048 + (k % 7)
        imp.append((t, 3, -2040, az, 11, az, -4, p, 2700, 410, ef.TERMINATOR))
    (folder / f"{STEM}.IMP").write_bytes(
        _imp_bytes(imp, (0, 0, 0, 0, 0, 0, 0, 10000, 0, 0, ef.TERMINATOR)))
    return hig, event


class EelFormat(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = temp_dir("eel_")
        cls.hig_records, cls.event = _write_deployment(cls.folder)
        cls.config = sc.get("micro_eel")
        cls.df, cls.summary = ef.process_eel(
            {".hig": cls.folder / f"{STEM}.HIG", ".imp": cls.folder / f"{STEM}.IMP"},
            cls.folder / "processed_sens_data", cls.config)
        cls.messages = cls.summary["messages"]

    def test_sample_rate_from_the_header(self):
        self.assertEqual(self.config.timebase_hz, 5000)     # what's configured...
        self.assertIn(f"Sample rate {RATE} Hz from the HIG header", self.messages)
        self.assertEqual(self.summary["sampling_rate_hz"], RATE)    # ...is overruled
        self.assertEqual(ef.read_header(self.folder / f"{STEM}.HIG"),
                         {"filter_hz": 640, "samplerate": RATE, "trigger_g": 60})

    def test_headers_discarded(self):
        self.assertIn("E10 header discarded - filter 640 Hz, trigger threshold 60 g",
                      self.messages)
        self.assertIn("IMP: header record discarded", self.messages)

    def test_reemitted_records_removed(self):
        self.assertIn("20 re-emitted pre-trigger record(s) removed", self.messages)
        # every real HIG sample lands on the grid exactly once
        self.assertEqual(int((self.df["higacc_mag_g"] > 0).sum()), 2000 + 1500)

    def test_trailing_bytes_reported(self):
        self.assertIn("2 trailing byte(s)", self.messages)

    def test_event_count(self):
        self.assertIn("1 triggered event(s)", self.messages)

    def test_gen1_gyro_not_published(self):
        self.assertIn("gen-1 firmware", self.messages)
        rot = self.df[["rot_x_degs", "rot_y_degs", "rot_z_degs"]]
        self.assertTrue((rot == 0).all().all())

    def test_wrapped_pressure_is_not_a_nadir(self):
        self.assertIn("1 over-range pressure", self.messages)
        self.assertGreater(self.df["pressure_kpa"].min(), 50)

    def test_peak_and_nadir(self):
        self.assertAlmostEqual(self.summary["HIG_max[time]"],
                               (EVENT_TICK + 100) / RATE, places=3)
        self.assertAlmostEqual(self.summary["pres_min[time]"], 10.02, delta=0.02)
        self.assertLess(self.summary["pres_min[kPa]"], 71)

    def test_output_grid(self):
        # the recording's own rate, so no HIG sample is left between zeros
        step = self.df["time_s"].diff().median()
        self.assertAlmostEqual(step, 1 / RATE, places=9)
        burst = self.df[self.df["time_s"] <= 2000 / RATE]
        self.assertGreater((burst["higacc_mag_g"] > 0).mean(), 0.99)

    def test_a_file_without_a_rate_in_its_header_takes_the_configured_one(self):
        folder = temp_dir("eel_")
        hig = [(0, 0, 0, 0)] + [(t, 0, -10, 0) for t in range(1, 2001)]
        (folder / "A-0101000000.HIG").write_bytes(_hig_bytes(hig))
        imp = [((k + 1) * 50, 3, -2040, 2048, 11, 5, -4, 10000 - k % 5, 2700, 410,
                ef.TERMINATOR) for k in range(500)]
        (folder / "A-0101000000.IMP").write_bytes(
            _imp_bytes(imp, (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x27)))
        self.assertIsNone(ef.read_header(folder / "A-0101000000.HIG"))
        _df, summary = ef.process_eel(
            {".hig": folder / "A-0101000000.HIG", ".imp": folder / "A-0101000000.IMP"},
            folder / "out", self.config)
        self.assertEqual(summary["sampling_rate_hz"], 5000)
        self.assertIn("No sample rate in the HIG header", summary["messages"])

    def test_conflicting_repeat_is_refused(self):
        bad = list(self.hig_records)
        bad.insert(700, (self.event[250][0], 999, 999, 999))
        path = self.folder / "bad.HIG"
        path.write_bytes(_hig_bytes(bad))
        with self.assertRaises(ef.EelFormatError):
            ef.read_hig(path, RATE)

    def test_wrong_tick_step_is_refused(self):
        with self.assertRaises(ef.EelFormatError):
            ef.read_imp(self.folder / f"{STEM}.IMP", 5000)

    def test_filename_rule(self):
        self.assertEqual(self.config.parse_stem("EEL_001-1030160046"),
                         ("EEL_001", "30/10", "16:00:46"))
        self.assertEqual(self.config.parse_stem("EEL-0010829034703"),
                         ("EEL-001", "29/08", "03:47:03"))
        self.assertEqual(self.config.parse_stem("EEEEL-0827222047"),
                         ("EEEEL", "27/08", "22:20:47"))


class StartupBurst(unittest.TestCase):
    """The burst at record start isn't an event, so it can't place the nadir."""

    def _process(self, spike_tick=None, rate=5000):
        folder = temp_dir("eel_")
        hig = [(0, 640, rate, 60)] + [(t, 0, -40, 0) for t in range(1, 2001)]
        if spike_tick:
            hig += [(spike_tick + k, 1500, 0, 0) for k in range(-50, 50)]
        (folder / "B-0101000000.HIG").write_bytes(_hig_bytes(hig))
        imp = []
        for k in range(1000):
            t = (k + 1) * rate // 100
            p = 10000 - int(2500 * np.exp(-((t / rate - 5.0) / 0.05) ** 2))
            imp.append((t, 3, -2040, 300, 11, 5, -4, p, 2700, 410, ef.TERMINATOR))
        (folder / "B-0101000000.IMP").write_bytes(
            _imp_bytes(imp, (0, 0, 0, 0, 0, 0, 0, 10000, 0, 0, ef.TERMINATOR)))
        return ef.process_eel(
            {".hig": folder / "B-0101000000.HIG", ".imp": folder / "B-0101000000.IMP"},
            folder / "out", sc.get("micro_eel"))[1]

    def test_no_events_means_the_lowest_pressure_of_the_recording(self):
        summary = self._process()
        self.assertAlmostEqual(summary["pres_min[time]"], 5.0, delta=0.01)
        self.assertLess(summary["pres_min[kPa]"], 76)
        self.assertEqual(summary["HIG_max[g]"], 0.0)
        self.assertIsNone(summary["HIG_max[time]"])
        self.assertEqual(summary["bad_sens"], "N")
        self.assertIn("no triggered events", summary["messages"])

    def test_an_event_is_the_peak_however_small_beside_the_burst(self):
        summary = self._process(spike_tick=int(5.01 * 5000))
        self.assertAlmostEqual(summary["HIG_max[time]"], 5.01, delta=0.02)
        self.assertAlmostEqual(summary["pres_min[time]"], 5.0, delta=0.01)
        self.assertAlmostEqual(summary["HIG_max[g]"], 150.0, places=1)

    def test_every_rate_the_tag_offers(self):
        for rate in ef.VALID_SAMPLERATES:
            summary = self._process(spike_tick=int(5.01 * rate), rate=rate)
            self.assertEqual(summary["sampling_rate_hz"], rate)
            self.assertAlmostEqual(summary["pres_min[time]"], 5.0, delta=0.01)


if __name__ == "__main__":
    unittest.main()
