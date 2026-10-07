"""The RAPID .imp/.hig readers on synthetic files built packet by packet."""
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

from modules import rapid_functions as rf


def _imp_packet(counter, imu, pressure, temp, battery):
    """29 bytes: int32 counter, 9 x int16 IMU, uint16 pressure, int16
    temperature and battery, one unused byte."""
    return (struct.pack(">i", counter) + struct.pack(">9h", *imu)
            + struct.pack(">H", pressure) + struct.pack(">hh", temp, battery)
            + b"\x0b")


def _hig_packet(counter, x, y, z):
    return struct.pack(">I3h", counter, x, y, z) + b"\x0b"


class RapidFormat(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="strikeworks_rapid_"))

    def _write(self, name, packets, tail=b""):
        path = self.dir / name
        path.write_bytes(b"".join(packets) + tail)
        return path

    def test_imp_packets_decode_and_pair_with_the_previous_readings(self):
        packets = [_imp_packet(1000 + 20 * k,
                               [k + 1, -(k + 1), 200 * k, 10, 20, 30, 1, 2, 3],
                               10130 + k, 2150 + k, 370)
                   for k in range(5)]
        df = rf.read_imp_raw(self._write("a.imp", packets, tail=b"\x00" * 7),
                             fs=2000)
        # 5 whole packets (the partial one ignored), the last one unused
        self.assertEqual(len(df), 4)
        np.testing.assert_array_equal(df["time_s"], [0.5, 0.51, 0.52, 0.53])
        # row k holds packet k-1's readings; row 0 repeats packet 0's
        np.testing.assert_array_equal(df["inacc_x_ms"],
                                      [0.005, 0.005, 0.01, 0.015])
        np.testing.assert_array_equal(df["inacc_y_ms"],
                                      [-0.005, -0.005, -0.01, -0.015])
        np.testing.assert_array_equal(df["inacc_z_ms"], [0.0, 0.0, 1.0, 2.0])
        np.testing.assert_array_equal(df["rot_z_degs"], [3.0] * 4)
        np.testing.assert_array_equal(df["mag_y_mt"], [0.2] * 4)
        # 0.1 mbar -> kPa
        np.testing.assert_allclose(df["pressure_kpa"],
                                   [101.3, 101.3, 101.31, 101.32])
        np.testing.assert_array_equal(df["temp_c"], [21.5, 21.5, 21.51, 21.52])
        np.testing.assert_array_equal(df["battery_v"], [3.7] * 4)

    def test_hig_packets_decode(self):
        packets = [_hig_packet(4000, 3000, -4000, 0),
                   _hig_packet(4001, 1, 2, 2),
                   _hig_packet(2 ** 31 + 6, -1, 0, 0)]
        df = rf.read_hig_raw(self._write("a.hig", packets, tail=b"\x01\x02"),
                             fs=2000)
        np.testing.assert_array_equal(df["time_s"],
                                      [2.0, 2.0005, (2 ** 31 + 6) / 2000])
        np.testing.assert_array_equal(df["higacc_x_g"], [300.0, 0.1, -0.1])
        np.testing.assert_array_equal(df["higacc_y_g"], [-400.0, 0.2, 0.0])
        np.testing.assert_array_equal(df["higacc_mag_g"], [500.0, 0.3, 0.1])

    def test_a_file_too_short_to_read_is_refused(self):
        path = self._write("short.imp", [_imp_packet(0, [0] * 9, 0, 0, 0)] * 2)
        with self.assertRaises(ValueError):
            rf.read_imp_raw(path)

    def test_empty_hig_reads_as_no_samples(self):
        self.assertEqual(len(rf.read_hig_raw(self._write("e.hig", []))), 0)


if __name__ == "__main__":
    unittest.main()
