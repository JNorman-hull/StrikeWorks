"""The source passes the linter (ruff, settings in ruff.toml). Skipped when
ruff isn't installed (`pip install -r requirements-dev.txt`)."""
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _ruff():
    """The ruff command beside this Python (the venv's Scripts folder),
    else on PATH; None when it isn't installed."""
    scripts = Path(sys.executable).parent
    for name in ("ruff.exe", "ruff"):
        if (scripts / name).exists():
            return str(scripts / name)
    return shutil.which("ruff")


class Lint(unittest.TestCase):
    def test_ruff_check_passes(self):
        ruff = _ruff()
        if ruff is None:
            self.skipTest("ruff is not installed")
        result = subprocess.run([ruff, "check", "--output-format", "concise", "."],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
