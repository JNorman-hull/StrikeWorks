"""The EEL tag at every rate it offers, on tools/make_eel_dummy.py's recordings:
each recording's rate read from its own file and followed from there, and the
places mixed rates have to be stopped. Set STRIKEWORKS_E2E=1 for the training
and prediction end of it too."""
import os
import sys
import unittest
from unittest import mock

import numpy as np
import pandas as pd

from support import ROOT, isolate, pump, qt_app, temp_dir

sys.path.insert(0, str(ROOT / "tools"))
import make_eel_dummy as dummy  # noqa: E402

COUNT = 3


def _library(**kwargs):
    lib = temp_dir("eel_pipeline_") / "EEL_Dummy"
    dummy.make_library(lib, **{"count": COUNT, **kwargs})
    return lib


def _wait(condition, seconds=30):
    for _ in range(int(seconds * 20)):
        if condition():
            return True
        pump(50)
    return condition()


class Inventory(unittest.TestCase):
    """The file list's Frequency column and its question."""

    @classmethod
    def setUpClass(cls):
        qt_app()
        isolate()
        from modules import sensor_config
        sensor_config._store = None
        sensor_config.set_active("micro_eel")
        cls.lib = _library()

    def setUp(self):
        from modules import inventory_widgets, raw_layout
        self.inventory = inventory_widgets.FileInventory()
        self.inventory.set_source(self.lib, raw_layout.raw_root(self.lib))
        self.inventory.refresh(block=True)
        self.addCleanup(self._close)
        self.assertTrue(_wait(lambda: all(f["frequency"] for f in self.inventory.files)))

    def _close(self):
        self.assertTrue(_wait(lambda: not self.inventory._frequency_threads
                              and not self.inventory._scan_threads
                              and not self.inventory.running))
        self.inventory.deleteLater()
        pump(50)

    def _column(self, name):
        from modules.inventory_widgets import COLUMNS
        col = COLUMNS.index(name)
        return [self.inventory.table.item(r, col).text()
                for r in range(self.inventory.table.rowCount())]

    def test_each_recording_shows_the_rate_in_its_own_header(self):
        self.assertEqual(sorted(self._column("Frequency")),
                         sorted(f"{r} Hz" for r in dummy.RATES for _ in range(COUNT)))
        for stem, text in zip(self._column("Filename"), self._column("Frequency")):
            rate = next(r for r in dummy.RATES if dummy.stem_for(r, 0)[:14] == stem[:14])
            self.assertEqual(text, f"{rate} Hz")

    def test_one_frequency_is_not_asked_about(self):
        from modules import frequency_dialog
        with mock.patch.object(frequency_dialog, "_ask") as ask:
            files = [f for f in self.inventory.files if f["frequency"] == 5000]
            self.assertEqual(self.inventory._choose_frequency(files), files)
        ask.assert_not_called()

    def test_mixed_frequencies_offer_all_or_one_of_those_present(self):
        from modules import frequency_dialog
        files = list(self.inventory.files)
        seen = {}

        def answer(value):
            def ask(_parent, _text, options):
                seen["labels"] = [label for label, _ in options]
                return value
            return ask

        with mock.patch.object(frequency_dialog, "_ask", answer("all")):
            self.assertEqual(self.inventory._choose_frequency(files), files)
        self.assertEqual(seen["labels"], ["Process all", "Process 2000 Hz only",
                                          "Process 2500 Hz only", "Process 5000 Hz only"])
        with mock.patch.object(frequency_dialog, "_ask", answer(2500.0)):
            only = self.inventory._choose_frequency(files)
        self.assertEqual({f["frequency"] for f in only}, {2500.0})
        self.assertEqual(len(only), COUNT)
        with mock.patch.object(frequency_dialog, "_ask", answer(None)):
            self.assertIsNone(self.inventory._choose_frequency(files))

        without_2500 = [f for f in files if f["frequency"] != 2500]
        with mock.patch.object(frequency_dialog, "_ask", answer(None)):
            self.inventory._choose_frequency(without_2500)
        self.assertEqual(seen["labels"], ["Process all", "Process 2000 Hz only",
                                          "Process 5000 Hz only"])

    def test_a_sensor_with_one_configured_rate_opens_no_file(self):
        from modules import eel_format, inventory_widgets, raw_layout, sensor_config
        with mock.patch.object(eel_format, "read_header") as read:
            records = inventory_widgets.scan_raw(
                self.lib, raw_layout.raw_root(self.lib), sensor_config.get("rapid"))
        read.assert_not_called()
        self.assertEqual({f["frequency"] for f in records}, {2000.0})

    def test_processing_stamps_the_rate_and_sensor_into_the_index(self):
        from modules import deployment_index as di
        lib = _library(rates=(2500,))
        from modules import raw_layout
        self.inventory.set_source(lib, raw_layout.raw_root(lib))
        self.inventory.refresh(block=True)
        self.assertTrue(_wait(lambda: all(f["frequency"] for f in self.inventory.files)))
        self.assertIsNotNone(self.inventory.process(list(self.inventory.files)))
        self.assertTrue(_wait(lambda: not self.inventory.running, seconds=60))
        pump(100)
        rows = di.sensor_rows(di.read_index(lib))
        self.assertEqual(len(rows), COUNT)
        self.assertEqual(set(pd.to_numeric(rows["sampling_rate_hz"])), {2500})
        self.assertEqual(set(rows["sensor_config"]), {"micro_eel"})


class DeploymentSensor(unittest.TestCase):
    """A deployment is read as the sensor saved on it, not whichever sensor
    this copy of the app happens to have selected."""

    @classmethod
    def setUpClass(cls):
        qt_app()
        isolate()
        from modules import sensor_config
        sensor_config._store = None
        sensor_config.set_active("rapid")

    def _select(self, key):
        from modules import sensor_config
        sensor_config.set_active(key)
        self.addCleanup(sensor_config.set_active, "rapid")

    def _saved_as(self, key):
        """A one-rate library, its deployment saved as sensor `key`."""
        from modules import deployment_index as di
        lib = _library(rates=(2000,))
        treatment = {**dummy.CONDITIONS, "treatment": "2000 Hz", "runs": 1}
        di.save_plan(lib, dummy.DEPLOYMENT, [treatment], sensor_key=key)
        return lib

    def _inventory(self, lib):
        from modules import inventory_widgets, raw_layout
        inventory = inventory_widgets.FileInventory()
        self.addCleanup(inventory.deleteLater)
        inventory.set_source(lib, raw_layout.raw_root(lib))
        inventory.refresh(block=True)
        self.assertTrue(_wait(lambda: all(f["frequency"] for f in inventory.files)))
        self.assertTrue(_wait(lambda: not inventory._frequency_threads))
        return inventory

    def test_saved_eel_is_read_as_eel_with_rapid_selected(self):
        lib = _library(rates=(2000, 5000))
        inventory = self._inventory(lib)
        files = inventory.files
        self.assertEqual({f["config"].key for f in files}, {"micro_eel"})
        self.assertEqual(sorted({f["frequency"] for f in files}), [2000.0, 5000.0])
        self.assertTrue(all(f["date"] and f["time"] for f in files))
        self.assertEqual({f["sensor"] for f in files}, {"EEL_001"})

    def test_processing_follows_the_deployment_and_leaves_the_selection_alone(self):
        from modules import deployment_index as di
        from modules import sensor_config
        lib = _library(rates=(2000, 5000))
        inventory = self._inventory(lib)
        self.assertIsNotNone(inventory.process(list(inventory.files)))
        self.assertTrue(_wait(lambda: not inventory.running, seconds=60))
        pump(100)
        rows = di.sensor_rows(di.read_index(lib))
        self.assertEqual(len(rows), 2 * COUNT)
        self.assertEqual(set(rows["sensor_config"]), {"micro_eel"})
        self.assertEqual(set(pd.to_numeric(rows["sampling_rate_hz"])), {2000, 5000})
        self.assertEqual(sensor_config.active_key(), "rapid")

    def test_saved_rapid_is_read_as_rapid_with_eel_selected(self):
        self._select("micro_eel")
        files = self._inventory(self._saved_as("rapid")).files
        self.assertEqual({f["config"].key for f in files}, {"rapid"})
        self.assertEqual({f["frequency"] for f in files}, {2000.0})

    def test_selected_sensor_answers_when_none_is_saved(self):
        self._select("micro_eel")
        files = self._inventory(self._saved_as(None)).files
        self.assertEqual({f["config"].key for f in files}, {"micro_eel"})

    def test_a_saved_sensor_that_no_longer_exists_falls_back(self):
        files = self._inventory(self._saved_as("deleted_sensor")).files
        self.assertEqual({f["config"].key for f in files}, {"rapid"})


class Downstream(unittest.TestCase):
    """A processed library holding all three rates: Validate's windows, the
    dataset built from them and the HIG peak analysis."""

    @classmethod
    def setUpClass(cls):
        qt_app()
        isolate()
        from modules import deployment_index as di
        from modules import eel_format, inventory_widgets, raw_layout, sensor_config
        from modules import validation_core as vc
        sensor_config._store = None
        cfg = sensor_config.get("micro_eel")
        cls.lib = _library()
        records = inventory_widgets.scan_raw(cls.lib, raw_layout.raw_root(cls.lib), cfg)
        out = cls.lib / raw_layout.PROCESSED_DIR
        for f in records:
            eel_format.process_eel(f["paths"], out, cfg)
        di.stamp_by_location(cls.lib, records, sensor_key=cfg.key)
        # the windows are cut with the wrong sensor selected on purpose: the
        # rate has to come from each file, not from the selection
        sensor_config.set_active("rapid")
        cls.index = di.read_index(cls.lib)
        for f in records:
            df = pd.read_csv(out / "csv" / f"{f['stem']}.csv")
            time, pres, _hig = vc.signals(df)
            nadir = vc.detect_nadir_idx(f["stem"], df, time, pres, cls.index)
            cls.index = vc.save_window(cls.lib, cls.index, f["stem"], df, nadir, 0.2)
        vc.write_index(cls.lib, cls.index)

    def _build(self, selected=()):
        from modules import dataset_build as db
        thread = db.ExtractThread(self.lib, db.OPT_SEGMENTED, set(selected), self.index)
        thread.run()
        return thread

    def _stems(self, rate):
        return {dummy.stem_for(rate, n) for n in range(COUNT)}

    def test_the_nadir_is_the_pressure_dip_at_every_rate(self):
        from modules import deployment_index as di
        rows = di.sensor_rows(self.index)
        times = pd.to_numeric(rows["pres_min.time."])
        self.assertEqual(len(times), COUNT * len(dummy.RATES))
        self.assertTrue(((times - dummy.NADIR_S).abs() < 0.015).all(), times.tolist())

    def test_windows_are_200_ms_whatever_is_selected(self):
        from modules import raw_layout
        for rate in dummy.RATES:
            for stem in self._stems(rate):
                win = pd.read_csv(self.lib / raw_layout.WINDOW_DIR / f"{stem}_200ms.csv")
                self.assertEqual(len(win), int(0.2 * rate) + 1, stem)
                self.assertAlmostEqual(win["time_s"].iloc[-1] - win["time_s"].iloc[0],
                                       0.2, places=6)

    def test_window_rates_come_from_the_index_or_the_window(self):
        from modules import validation_core as vc
        rates = vc.window_rates(self.lib)
        self.assertEqual(sorted(rates.values()),
                         sorted(float(r) for r in dummy.RATES for _ in range(COUNT)))
        stems = self._stems(2500)
        self.assertEqual(set(vc.window_rates(self.lib, stems)), stems)
        with mock.patch("modules.deployment_index.index_rates", return_value={}):
            self.assertEqual(vc.window_rates(self.lib), rates)

    def test_a_dataset_at_one_rate_has_the_right_rows_at_every_rate(self):
        from modules import recording_rate as rr
        for rate in dummy.RATES:
            thread = self._build(self._stems(rate))
            self.assertIsNone(thread.error)
            df = thread.result
            self.assertEqual(df.groupby("file").size().unique().tolist(), [int(0.2 * rate)])
            self.assertEqual(rr.identity(df), {"sensor_config": "micro_eel",
                                               "sampling_rate_hz": rate})
            self.assertIsNone(rr.dataset_problem(df))

    def test_a_dataset_of_mixed_rates_is_refused(self):
        thread = self._build()
        self.assertIsNone(thread.result)
        self.assertIn("mixes frequencies", thread.error)
        self.assertIn("2000 Hz, 2500 Hz, 5000 Hz", thread.error)

    def test_export_asks_for_one_frequency(self):
        from modules import frequency_dialog as fd
        from modules import validation_core as vc
        rates = vc.window_rates(self.lib)
        seen = {}

        def ask(_parent, _text, options):
            seen["labels"] = [label for label, _ in options]
            return 5000.0

        with mock.patch.object(fd, "_ask", ask):
            keep = fd.choose_for_dataset(None, rates)
        self.assertEqual(seen["labels"], ["Use 2000 Hz only", "Use 2500 Hz only",
                                          "Use 5000 Hz only"])
        self.assertEqual(keep, self._stems(5000))

    def test_hig_peaks_find_the_spikes_at_every_rate(self):
        from modules import hig_peaks
        for rate in dummy.RATES:
            df = self._build(self._stems(rate)).result
            events, per_file = hig_peaks.analyse(df)
            strike = dummy.stem_for(rate, 0)
            self.assertEqual(per_file.loc[strike, "collision"], 1)
            self.assertGreaterEqual(per_file.loc[strike, "max_event_g"], 400)
            types = set(events[events["file"] == strike]["peak_type"])
            self.assertEqual(types, {"collision", "shear"})
            self.assertEqual(per_file.loc[dummy.stem_for(rate, 1), "collision"], 0)
            self.assertEqual(per_file.loc[dummy.stem_for(rate, 1), "n_events_200g"], 1)
            self.assertEqual(per_file.loc[dummy.stem_for(rate, 2), "n_events"], 0)


def _dataset(rate, sensor="micro_eel", files=3, rows=None):
    rows = rows or int(0.2 * rate)
    parts = []
    for n in range(files):
        parts.append(pd.DataFrame({
            "file": f"{sensor}_{rate}_{n}", "sensor_config": sensor,
            "time_s": [10 + i / rate for i in range(rows)],
            "pressure_kpa": 100.0, "higacc_mag_g": 1.0}))
    return pd.concat(parts, ignore_index=True)


class Identity(unittest.TestCase):
    """recording_rate: what a dataset is, and what a model will take."""

    def test_a_dataset_says_what_it_is(self):
        from modules import recording_rate as rr
        self.assertEqual(rr.identity(_dataset(5000)),
                         {"sensor_config": "micro_eel", "sampling_rate_hz": 5000})
        self.assertIsNone(rr.dataset_problem(_dataset(2500)))

    def test_older_datasets_are_rapid(self):
        from modules import recording_rate as rr
        old = _dataset(2000).drop(columns="sensor_config")
        self.assertEqual(rr.identity(old),
                         {"sensor_config": "rapid", "sampling_rate_hz": 2000})
        blank = _dataset(2000)
        blank["sensor_config"] = float("nan")
        self.assertEqual(rr.sensors_in(blank), {"rapid"})

    def test_mixes_are_problems(self):
        from modules import recording_rate as rr
        rates = pd.concat([_dataset(2000), _dataset(5000)], ignore_index=True)
        self.assertIn("mixes frequencies (2000 Hz, 5000 Hz)", rr.dataset_problem(rates))
        sensors = pd.concat([_dataset(2000), _dataset(2000, "rapid")], ignore_index=True)
        self.assertIn("mixes sensors (Micro-EEL, RAPID)", rr.dataset_problem(sensors))

    def test_a_model_only_takes_its_own_sensor_and_rate(self):
        from modules import recording_rate as rr
        eel_5k = {"sensor_config": "micro_eel", "sampling_rate_hz": 5000}
        old_model = {"max_sequence_length": 401}    # every model before this
        self.assertIsNone(rr.model_problem(eel_5k, rr.identity(_dataset(5000))))
        self.assertIn("trained on Micro-EEL at 5000 Hz",
                      rr.model_problem(eel_5k, rr.identity(_dataset(2000))))
        self.assertIsNone(rr.model_problem(
            old_model, rr.identity(_dataset(2000).drop(columns="sensor_config"))))
        self.assertIn("trained on RAPID at 2000 Hz; this dataset is Micro-EEL at 5000 Hz",
                      rr.model_problem(old_model, rr.identity(_dataset(5000))))
        # the same rate from the other device is still another device
        self.assertIn("trained on RAPID at 2000 Hz; this dataset is Micro-EEL at 2000 Hz",
                      rr.model_problem(old_model, rr.identity(_dataset(2000))))

    def test_bind_refuses_a_mix_and_takes_a_match(self):
        from modules import bind_datasets as bd
        folder = temp_dir("eel_bind_")
        for name, df in (("a", _dataset(5000, files=2)), ("b", _dataset(2000)),
                         ("c", _dataset(5000, "micro_eel", files=1))):
            df.to_csv(folder / f"{name}.csv", index=False)
        with self.assertRaises(bd.MixedDataError):
            bd.bind_csvs([folder / "a.csv", folder / "b.csv"])
        joined, _differ = bd.bind_csvs([folder / "a.csv", folder / "c.csv"])
        self.assertEqual(joined["time_s"].count(), 3 * 1000)


class Gates(unittest.TestCase):
    """Train and Predict's checks, the ones that hold the Run button."""

    @classmethod
    def setUpClass(cls):
        qt_app()
        isolate()

    def _prediction_checks(self, df, metrics=None):
        from modules.ml_state import PredictionState
        state = PredictionState()
        state.bin_model_path = temp_dir() / "binary1.joblib"
        state.bin_metrics = {"channels": ["pressure_kpa"], "max_sequence_length": 1000,
                             **(metrics or {})}
        state.set_dataset(df)
        self.addCleanup(state.deleteLater)
        return state, {label: (level, detail) for level, label, detail in state.checks}

    def test_predict_blocks_a_rapid_model_on_eel_data(self):
        state, checks = self._prediction_checks(_dataset(5000))
        self.assertFalse(state.ready)
        level, detail = checks["Binary model matches the dataset"]
        self.assertEqual(level, "fail")
        self.assertIn("Micro-EEL at 5000 Hz", detail)

    def test_predict_takes_a_model_trained_on_this_sensor_and_rate(self):
        state, checks = self._prediction_checks(
            _dataset(2500), {"sensor_config": "micro_eel", "sampling_rate_hz": 2500})
        self.assertEqual(checks["Binary model matches the dataset"][0], "ok")
        self.assertTrue(state.ready)

    def test_predict_blocks_a_model_of_another_frequency(self):
        state, _checks = self._prediction_checks(
            _dataset(2000), {"sensor_config": "micro_eel", "sampling_rate_hz": 5000})
        self.assertFalse(state.ready)

    def test_predict_keeps_taking_rapid_data_with_rapid_models(self):
        state, checks = self._prediction_checks(_dataset(2000).drop(columns="sensor_config"))
        self.assertEqual(checks["Binary model matches the dataset"][0], "ok")
        self.assertTrue(state.ready)

    def test_predict_blocks_a_mixed_dataset(self):
        mixed = pd.concat([_dataset(2000), _dataset(5000)], ignore_index=True)
        state, checks = self._prediction_checks(mixed)
        self.assertFalse(state.ready)
        self.assertEqual(checks["One sensor and frequency"][0], "fail")

    def test_numeric_class_names_stay_text(self):
        """Classes called "2" and "3" - what a model's pump regions default to."""
        from modules.ml_state import PredictionState
        out = temp_dir("eel_results_")
        pd.DataFrame({"file": ["a", "b", "c"], "predicted_strike": [1, 1, 0],
                      "predicted_region": ["2", "3", ""]}).to_csv(
            out / "predictions.csv", index=False)
        pd.DataFrame({"treatment": ["t"], "n": [3]}).to_csv(out / "summary.csv", index=False)
        pd.DataFrame({"treatment": ["t", "t"], "region": ["2", "3"], "n": [1, 1]}).to_csv(
            out / "region_summary.csv", index=False)
        state = PredictionState()
        self.addCleanup(state.deleteLater)
        state._apply_results(out)
        self.assertEqual(state.predictions["predicted_region"].dropna().tolist(), ["2", "3"])
        totals = state.region_summary.groupby("region")["n"].sum().reindex(["2", "3"])
        self.assertEqual(totals.tolist(), [1, 1])

    def test_training_blocks_a_mixed_dataset(self):
        from modules.ml_train_state import TrainingState
        path = temp_dir() / "mixed.csv"
        pd.concat([_dataset(2000), _dataset(5000)], ignore_index=True).to_csv(path, index=False)
        state = TrainingState()
        self.addCleanup(state.deleteLater)
        ok, _message = state.load_dataset_csv(path)
        self.assertTrue(ok)
        state.validate()
        checks = {label: (level, detail) for level, label, detail in state.checks}
        self.assertEqual(checks["One sensor and frequency"][0], "fail")
        self.assertFalse(state.ready)


class PressureOffset(unittest.TestCase):
    """Export animations lines pressure up by the sensor's own offset."""

    def test_each_sensor_has_its_own(self):
        from modules import sensor_config, video_sync
        self.assertEqual(sensor_config.SensorConfig.from_dict(
            sensor_config.BUILTIN["micro_eel"]).pressure_offset_s, 0.0)
        self.assertEqual(sensor_config.SensorConfig.from_dict(
            sensor_config.BUILTIN["rapid"]).pressure_offset_s, 0.01)

        time = np.arange(0, 1, 1 / 5000)
        df = pd.DataFrame({"time_s": time, "pressure_kpa": 100 + time})
        channels = [{"column": "pressure_kpa", "label": "p"}]
        at = {}
        for offset in (0.0, 0.01):
            opts = video_sync.SyncOptions(real_fps=1000, pressure_offset_s=offset,
                                          channels=channels)
            at[offset] = video_sync.build_cursor_arrays(0.5, df, 10, 21, opts)["pressure_kpa"]
        self.assertAlmostEqual(at[0.0][10], 100.5, places=3)
        self.assertAlmostEqual(at[0.01][10], 100.49, places=3)


@unittest.skipUnless(os.environ.get("STRIKEWORKS_E2E"), "slow: set STRIKEWORKS_E2E=1")
class TrainAndPredict(unittest.TestCase):
    """From raw files to predictions through the app's own state objects, once
    per rate. Six recordings, not three: cross-validation needs two of each
    class even at its fewest folds."""

    @classmethod
    def setUpClass(cls):
        qt_app()
        isolate()
        from modules import sensor_config
        sensor_config._store = None
        sensor_config.set_active("micro_eel")

    def _export(self, rate):
        from modules import deployment_index as di
        from modules import eel_format, inventory_widgets, raw_layout, sensor_config
        from modules import validation_core as vc
        cfg = sensor_config.get("micro_eel")
        lib = _library(count=6, rates=(rate,))
        records = inventory_widgets.scan_raw(lib, raw_layout.raw_root(lib), cfg)
        out = lib / raw_layout.PROCESSED_DIR
        for f in records:
            eel_format.process_eel(f["paths"], out, cfg)
        di.stamp_by_location(lib, records, sensor_key=cfg.key)
        index = di.read_index(lib)
        for f in records:
            df = pd.read_csv(out / "csv" / f"{f['stem']}.csv")
            time, pres, _hig = vc.signals(df)
            nadir = vc.detect_nadir_idx(f["stem"], df, time, pres, index)
            index = vc.save_window(lib, index, f["stem"], df, nadir, 0.2)
        vc.write_index(lib, index)
        vc.import_annotations_csv(lib, lib / dummy.LABELS_NAME)

        exporter = vc.DatasetExporter()
        self.addCleanup(exporter.deleteLater)
        got = []
        exporter.finished.connect(lambda *args: got.append(args))
        exporter.start(lib, f"eel_{rate}")
        self.assertTrue(_wait(lambda: bool(got), seconds=60))
        df, path, message = got[0]
        self.assertIsNotNone(df, message)
        return df, path

    def _train(self, path, models_dir):
        from modules.ml_train_state import TrainingState
        state = TrainingState()
        self.addCleanup(state.deleteLater)
        ok, message = state.load_dataset_csv(path)
        self.assertTrue(ok, message)
        state.n_folds = 2
        state.update(fixed_threshold=0.5)
        state.validate()
        self.assertTrue(state.ready, state.checks)

        failed = []
        state.cv_failed.connect(failed.append)
        state.final_failed.connect(failed.append)
        state.run_cv()
        self.assertTrue(_wait(lambda: failed or state.cv_done, seconds=300), "CV never finished")
        self.assertEqual(failed, [])
        state.run_final()
        self.assertTrue(_wait(lambda: failed or state.final_done, seconds=300),
                        "Final training never finished")
        self.assertEqual(failed, [])
        state.deploy(models_dir, "9")

    def _predict(self, path, models_dir):
        from modules.ml_state import PredictionState
        state = PredictionState()
        self.addCleanup(state.deleteLater)
        ok, message = state.load_models_from_dir(models_dir)
        self.assertTrue(ok, message)
        ok, message = state.load_dataset_csv(path)
        self.assertTrue(ok, message)
        self.assertTrue(state.ready, state.checks)
        failed, finished = [], []
        state.run_failed.connect(failed.append)
        state.run_finished.connect(lambda: finished.append(True))
        state.set_hig_peaks(True)
        state.run_prediction()
        self.assertTrue(_wait(lambda: failed or finished, seconds=300), "Prediction never finished")
        self.assertEqual(failed, [])
        return state

    def test_every_rate(self):
        import json
        for rate in dummy.RATES:
            with self.subTest(rate=rate):
                df, path = self._export(rate)
                rows = int(0.2 * rate)
                self.assertEqual(df.groupby("file").size().unique().tolist(), [rows])

                models_dir = temp_dir("eel_models_")
                self._train(path, models_dir)
                metrics = json.loads((models_dir / "binary9performance_metrics.json").read_text())
                self.assertEqual(metrics["sampling_rate_hz"], rate)
                self.assertEqual(metrics["sensor_config"], "micro_eel")
                self.assertEqual(metrics["max_sequence_length"], rows)
                oof = metrics["out_of_fold_performance"]
                self.assertEqual((oof["optimal_threshold"], oof["threshold_selection"]),
                                 (0.5, "fixed"))

                state = self._predict(path, models_dir)
                results = state.predictions
                self.assertEqual(len(results), 6)
                strikes = results[results["file"].isin(
                    [dummy.stem_for(rate, n) for n in (0, 3)])]
                self.assertTrue((strikes["hig_peak_g"] > 400).all(), results.to_string())
                self.assertTrue((strikes["collision"] == 1).all(), results.to_string())

                # the report, whose classes here are called "2" and "3"
                from modules import ml_report
                html = ml_report.build_report_html(state, image_paths={}, embed_images=True)
                self.assertIn("Strike classification", html)
                self.assertIn(f"Micro-EEL at {rate} Hz", html)

                # and this model goes no further than its own sensor and rate
                other = dummy.RATES[(dummy.RATES.index(rate) + 1) % len(dummy.RATES)]
                state.set_dataset(_dataset(other))
                self.assertFalse(state.ready)


if __name__ == "__main__":
    unittest.main()
