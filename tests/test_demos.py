"""Both demos end to end on a small demo pack built from libraries/Testbed -
processing, validation (including the flagged-sensor review checks), export,
training (Advanced), prediction and the report.

Slow (a few minutes), so it only runs with STRIKEWORKS_E2E=1:
    set STRIKEWORKS_E2E=1 && python -m unittest tests.test_demos
"""
import contextlib
import io
import os
import shutil
import unittest

from support import TESTBED, isolate, main_window, qt_app

N_RECORDINGS = 20


def _demo_pack(libraries):
    src = TESTBED / "raw_sens_data" / "DevTest_PF" / "500 RPM"
    dst = libraries / "demo_data" / "raw_sens_data" / "DevTest_PF" / "500 RPM"
    (dst / "VIDEO").mkdir(parents=True)
    for stem in sorted({p.stem for p in src.glob("*.IMP")})[:N_RECORDINGS]:
        for f in src.glob(f"{stem}.*"):
            shutil.copy2(f, dst / f.name)
    for csv in TESTBED.glob("*annotation*.csv"):
        shutil.copy2(csv, libraries / "demo_data" / csv.name)


@unittest.skipUnless(os.environ.get("STRIKEWORKS_E2E") == "1",
                     "set STRIKEWORKS_E2E=1 to run the end-to-end demos")
@unittest.skipUnless(TESTBED.is_dir(), "libraries/Testbed not present")
class Demos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qt_app()
        cls.env = isolate()
        _demo_pack(cls.env / "libraries")
        cls.main, cls.window = main_window()

    def _run(self, mode):
        from modules.dev_runner import RUNNERS
        result = {}
        runner = RUNNERS[mode](self.window)
        runner.finished.connect(lambda ok, msg: result.update(ok=ok, msg=msg))
        log = io.StringIO()
        with contextlib.redirect_stdout(log):
            runner.run()
        return result, log.getvalue()

    def test_simple(self):
        result, log = self._run("simple")
        self.assertTrue(result.get("ok"), log[-3000:])
        self.assertNotIn("Validate check FAIL", log)
        self.assertIn("review checks all passed", log)

    def test_advanced(self):
        result, log = self._run("advanced")
        self.assertTrue(result.get("ok"), log[-3000:])
        self.assertIn("Model training: final model trained", log)


if __name__ == "__main__":
    unittest.main()
