"""Nadir detection during processing (modules/rapid_functions.py): the
pressure step at the pump, and the fallback for a recording without one."""
import unittest

import numpy as np
import pandas as pd

from modules import rapid_functions as rf
from modules import sensor_config

FS = 2000.0


def _frame(pressure):
    time = np.arange(len(pressure)) / FS
    return pd.DataFrame({"time_s": time, "pressure_kpa": pressure})


def _at(seconds):
    return int(round(seconds * FS))


def _pump(p, at, low, high, settle, tau=1.5):
    """A dip to `low` over the 0.1 s before `at`, a step up to `high`, then
    a decay towards `settle`."""
    start = p[_at(at - 0.1) - 1]
    p[_at(at - 0.1):_at(at)] = np.linspace(start, low, _at(0.1))
    after = np.arange(len(p) - _at(at)) / FS
    p[_at(at):] = settle + (high - settle) * np.exp(-after / tau)
    return p


def rig_with_a_pressurised_stage():
    """In air, released, pressurised for 2 s, a low-pressure approach, the
    pump at 30 s."""
    p = np.full(_at(45), 100.0)
    p[_at(5):_at(12)] = 102.0
    p[_at(12):_at(14)] = 146.0
    p[_at(14):_at(30)] = np.linspace(85.0, 96.0, _at(16))
    return _pump(p, 30.0, low=88.0, high=145.0, settle=105.0)


def rig_without_one():
    """In air, into the water at 7 s, the pump at 15 s."""
    p = np.full(_at(40), 100.0)
    p[_at(7):_at(8)] = np.linspace(100.0, 113.0, _at(1))
    p[_at(8):_at(15)] = np.linspace(113.0, 118.0, _at(7))
    return _pump(p, 15.0, low=110.0, high=140.0, settle=106.0, tau=6.0)


class PressureStep(unittest.TestCase):
    def _nadir(self, pressure, peak_at=None):
        data = _frame(pressure)
        peak = None if peak_at is None else _at(peak_at)
        _idx, when, value, notes = rf.nadir_pressure_step(data, peak, FS)
        return float(when), float(value), notes

    def test_the_pump_not_the_pressurised_stage(self):
        when, value, notes = self._nadir(rig_with_a_pressurised_stage())
        self.assertAlmostEqual(when, 30.0, delta=0.01)
        self.assertAlmostEqual(value, 88.0, delta=0.1)
        self.assertEqual(notes, [])

    def test_the_release_knock_no_longer_places_it(self):
        pressure = rig_with_a_pressurised_stage()
        # the largest acceleration is the knock at release, 5 s in
        _i, near_peak, _v, _n = rf.nadir_pressure_min_near_peak(
            _frame(pressure), _at(5.0), FS)
        self.assertLess(float(near_peak), 7.0)
        when, _value, _notes = self._nadir(pressure, peak_at=5.0)
        self.assertAlmostEqual(when, 30.0, delta=0.01)

    def test_a_long_pressurised_stage(self):
        pressure = rig_with_a_pressurised_stage()
        pressure[_at(6):_at(14)] = 146.0          # held 8 s, not 2
        when, _value, _notes = self._nadir(pressure)
        self.assertAlmostEqual(when, 30.0, delta=0.01)

    def test_a_rig_with_no_pressurised_stage(self):
        when, value, _notes = self._nadir(rig_without_one())
        self.assertAlmostEqual(when, 15.0, delta=0.01)
        self.assertAlmostEqual(value, 110.0, delta=0.1)

    def test_a_sensor_that_stays_in_the_pressurised_section(self):
        pressure = rig_without_one()
        rng = np.random.default_rng(1)
        pressure[_at(15):] = 135.0 + rng.normal(0.0, 4.0, len(pressure) - _at(15))
        when, _value, _notes = self._nadir(pressure)
        self.assertAlmostEqual(when, 15.0, delta=0.01)

    def test_pressure_spikes_are_not_steps(self):
        pressure = rig_with_a_pressurised_stage()
        rng = np.random.default_rng(2)
        burst = slice(_at(8), _at(10))
        spikes = rng.random(_at(2)) < 0.2
        pressure[burst][spikes] = 480.0
        when, _value, _notes = self._nadir(pressure)
        self.assertAlmostEqual(when, 30.0, delta=0.01)

    def test_no_step_falls_back_to_the_acceleration_peak(self):
        rng = np.random.default_rng(3)
        pressure = 100.0 + rng.normal(0.0, 0.2, _at(30))
        pressure[_at(12.3)] = 98.0
        data = _frame(pressure)
        self.assertIsNone(rf.pressure_step_time(
            data["time_s"].to_numpy(), pressure, FS))
        _i, when, value, notes = rf.nadir_pressure_step(data, _at(12.0), FS)
        _i, near_peak, _v, _n = rf.nadir_pressure_min_near_peak(
            data, _at(12.0), FS)
        self.assertEqual(float(when), float(near_peak))
        self.assertAlmostEqual(float(when), 12.3, delta=0.001)
        self.assertEqual(value, 98.0)
        self.assertEqual(notes, [rf.NO_STEP_NOTE])

    def test_other_rates(self):
        for fs in (2500.0, 5000.0):
            every = int(fs / 500)
            pressure = np.repeat(rig_without_one()[::4], every)   # 500 Hz -> fs
            time = np.arange(len(pressure)) / fs
            at = rf.pressure_step_time(time, pressure, fs)
            self.assertAlmostEqual(at, 15.0, delta=0.6, msg=fs)


class Configuration(unittest.TestCase):
    def test_sensor_configuration_lists_every_method(self):
        rf_methods = set(rf.NADIR_METHODS)
        self.assertEqual(set(sensor_config.NADIR_METHOD_LABELS), rf_methods)
        self.assertEqual(set(sensor_config.NADIR_METHOD_NOTES), rf_methods)
        self.assertEqual(sensor_config.DEFAULT_NADIR_METHOD, "pressure_step")
        self.assertEqual(rf.DEFAULT_NADIR_METHOD, "pressure_step")

    def test_built_in_sensors_use_the_pressure_step(self):
        for key in sensor_config.BUILTIN:
            cfg = sensor_config.SensorConfig.from_dict(sensor_config.BUILTIN[key])
            self.assertEqual(cfg.nadir_method, "pressure_step", key)
            self.assertEqual(cfg.problems(), [], key)

    def test_a_configuration_saved_before_takes_the_pressure_step(self):
        saved = dict(sensor_config.SensorConfig.from_dict(
            sensor_config.BUILTIN["rapid"]).to_dict(),
            nadir_method="pressure_min_near_peak")
        cfg = sensor_config.SensorConfig.from_dict(saved)
        self.assertEqual(cfg.nadir_method, "pressure_step")
        # the former method chosen on purpose stays chosen
        kept = sensor_config.SensorConfig.from_dict(
            dict(saved, nadir_method="pressure_near_peak"))
        self.assertEqual(kept.nadir_method, "pressure_near_peak")


if __name__ == "__main__":
    unittest.main()
