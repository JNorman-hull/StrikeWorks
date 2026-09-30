# PyInstaller runtime hook for the Simple edition (build.py --simple). It
# runs inside the exe before the app starts, so the Simple-mode-only lock
# (modules/edition.py) can't be switched off with an environment variable.
import os

os.environ["STRIKEWORKS_EDITION"] = "simple"
