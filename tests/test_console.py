"""The console (modules/dev_console.py): everything printed from start-up,
errors included, in the window and in the session's log file; and the
demos' pacing (dev_runner.MIN_STEP_MS)."""
import os
import subprocess
import sys
import textwrap
import time
import unittest

from support import ROOT, pump, qt_app, temp_dir

_SCRIPT = textwrap.dedent("""
    import sys, threading
    sys.path.insert(0, {root!r})
    from pathlib import Path
    logs = Path({logs!r})
    for i in range(25):
        (logs / f"strikeworks_20200101_0000{{i:02d}}.log").write_text("old")
    from modules import dev_console
    cap = dev_console.install_capture(logs)
    print("hello from print")
    def boom():
        raise RuntimeError("thread boom")
    t = threading.Thread(target=boom, name="worker")
    t.start(); t.join()
    try:
        raise ValueError("slot boom")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    from PySide6.QtWidgets import QApplication
    app = QApplication([])
    console = dev_console.DevConsole()
    text = console.log.toPlainText()
    sys.__stdout__.write("CONSOLE_OK\\n" if "hello from print" in text
                         and "slot boom" in text else "CONSOLE_MISSING\\n")
    sys.__stdout__.write(f"LOG={{cap.log_path}}\\n")
""")


class Capture(unittest.TestCase):
    def test_output_and_errors_reach_the_console_and_the_log(self):
        logs = temp_dir("strikeworks_logs_")
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        r = subprocess.run(
            [sys.executable, "-c", _SCRIPT.format(root=str(ROOT), logs=str(logs))],
            capture_output=True, text=True, env=env, timeout=120)
        self.assertIn("CONSOLE_OK", r.stdout, r.stdout + r.stderr)
        log_line = next(ln for ln in r.stdout.splitlines() if ln.startswith("LOG="))
        with open(log_line[4:], encoding="utf-8") as f:
            text = f.read()
        for expected in ("this session's log", "hello from print",
                         "unhandled in thread worker", "thread boom",
                         "ValueError: slot boom"):
            self.assertIn(expected, text)
        # the newest 20 kept, this session's among them
        self.assertEqual(len(list(logs.glob("strikeworks_*.log"))), 20)


class DemoPacing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qt_app()

    def test_every_step_stays_up_two_seconds(self):
        from PySide6.QtWidgets import QWidget
        from modules import dev_runner
        holder = QWidget()
        for paced in (True, False):
            runner = dev_runner._RunnerBase(holder, paced=paced)
            shown = []
            t0 = time.monotonic()
            for step in range(3):
                runner._next_step(lambda s=step, out=shown: out.append(s))
            runner._hold_step()
            elapsed = time.monotonic() - t0
            self.assertEqual(shown, [0, 1, 2])
            if paced:
                self.assertGreaterEqual(elapsed,
                                        3 * dev_runner.MIN_STEP_MS / 1000 - 0.1)
            else:
                self.assertLess(elapsed, 1.0)
        pump(10)


if __name__ == "__main__":
    unittest.main()
