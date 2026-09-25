"""StrikeWorks tests - run them all with

    python -m unittest discover -s tests

or one file with `python -m unittest tests.test_rules`. The slow
end-to-end demos (tests/test_demos.py) only run with STRIKEWORKS_E2E=1.
"""
import sys
from pathlib import Path

# the test modules import their shared set-up as `support`
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
