"""Raw processing's Stop (modules/processing.py, inventory_widgets.py):
the recording in hand finishes, the rest are left, and what was done is
kept."""
import time
import unittest
from unittest import mock

from support import isolate, pump, qt_app


class Stop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qt_app()

    def test_stops_before_the_next_recording(self):
        from modules import processing, sensor_config

        def slow_parse(paths, out_dir, config):
            time.sleep(0.2)
            return None, {}

        files = [{"stem": f"S{i}", "paths": {}} for i in range(6)]
        with mock.patch.object(sensor_config, "get_parser",
                               return_value=slow_parse):
            thread = processing.ProcessThread(
                files, None, None, sensor_config.active())
            done, codes = [], []
            thread.processed.connect(done.append)
            thread.done.connect(codes.append)
            thread.processed.connect(lambda _s: thread.request_stop())
            thread.start()
            for _ in range(100):
                pump(50)
                if codes:
                    break
        self.assertEqual(codes, [processing.DONE_STOPPED])
        self.assertLess(len(done), len(files))
        self.assertGreaterEqual(len(done), 1)


class EachRecordingsSensor(unittest.TestCase):
    """A batch spanning deployments: each recording read and labelled as its
    own sensor."""

    @classmethod
    def setUpClass(cls):
        qt_app()
        isolate()
        from modules import sensor_config
        sensor_config._store = None

    def _batch(self):
        from modules import sensor_config
        return [{"stem": key, "paths": {}, "config": sensor_config.get(key),
                 "deployment": key, "treatment": "T", "run": "1"}
                for key in ("rapid", "micro_eel")]

    def test_each_recording_goes_through_its_own_parser(self):
        from modules import processing, sensor_config
        read = []

        def parser(name):
            def parse(_paths, _out_dir, config):
                read.append((name, config.key))
                return None, {}
            return parse

        with mock.patch.object(sensor_config, "get_parser", side_effect=parser):
            thread = processing.ProcessThread(self._batch(), None, None)
            codes = []
            thread.done.connect(codes.append)
            thread.start()
            for _ in range(100):
                pump(50)
                if codes:
                    break
        self.assertEqual(codes, [processing.DONE_OK])
        self.assertEqual(read, [("rapid_imp_hig", "rapid"), ("eel_imp_hig", "micro_eel")])

    def test_each_recording_is_labelled_with_its_own_sensor(self):
        from modules import deployment_index as di
        from modules import inventory_widgets, processing
        inventory = inventory_widgets.FileInventory()
        self.addCleanup(inventory.deleteLater)
        batch = self._batch()
        inventory._batch = batch
        inventory._batch_done = [f["stem"] for f in batch]
        with mock.patch.object(di, "stamp_by_location", return_value=1) as stamp:
            inventory._on_done(processing.DONE_OK)
        stamped = {c.kwargs["sensor_key"]: [f["stem"] for f in c.args[1]]
                   for c in stamp.call_args_list}
        self.assertEqual(stamped, {"rapid": ["rapid"], "micro_eel": ["micro_eel"]})


if __name__ == "__main__":
    unittest.main()
