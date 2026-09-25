"""EEL tag reader against synthetic files that exercise the format
specification's rules (headers, re-emitted records, firmware generation,
wrapped pressure, timebase checks)."""
import unittest

import numpy as np

from support import temp_dir

import modules  # noqa: F401
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
    wrapped pressure sample, 2 stray trailing bytes, and a .log at 2500 Hz."""
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
    (folder / "EEL-0020903.log").write_text(
        "Filename,Time,RecordTime,Pressure,Temp,BatVoltage,Filter,Samplerate,End\r\n"
        f"{STEM},10:15,1,1020.00,26.00,4.08,0,{RATE},Time\r\n")
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

    def test_sample_rate_from_log(self):
        self.assertIn(f"Sample rate {RATE} Hz from the deployment .log", self.messages)

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
        step = self.df["time_s"].diff().median()
        self.assertAlmostEqual(step, 1 / self.config.output_rate_hz, places=9)

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
        self.assertEqual(self.config.parse_stem("EEL-0010829034703"),
                         ("EEL-001", "29/08", "03:47:03"))
        self.assertEqual(self.config.parse_stem("EEEEL-0827222047"),
                         ("EEEEL", "27/08", "22:20:47"))


if __name__ == "__main__":
    unittest.main()
