"""Raw processing's Stop (modules/processing.py, inventory_widgets.py):
the recording in hand finishes, the rest are left, and what was done is
kept."""
import time
import unittest
from unittest import mock

from support import pump, qt_app


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


if __name__ == "__main__":
    unittest.main()
