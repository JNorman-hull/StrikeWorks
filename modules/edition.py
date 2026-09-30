# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Which edition is running: the full app, or the Simple edition - Simple
mode only, with the development toolkit (the full app) locked.

`build.py --simple` makes the Simple edition by compiling a start-up hook
into the exe (tools/simple_edition_hook.py) that sets
STRIKEWORKS_EDITION=simple before the app starts, so it can't be switched
off from outside. From source, set the variable to try it.
"""
import os


def simple_only() -> bool:
    return os.environ.get("STRIKEWORKS_EDITION", "").strip().lower() == "simple"
