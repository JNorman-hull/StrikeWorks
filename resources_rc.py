# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Top-level shim for the compiled Qt resources.

``pyside6-uic`` always emits a plain ``import resources_rc`` into the generated
``modules/ui_main.py``. The real compiled resources live in
``modules/resources_rc.py``, so without this shim that import would fail and the
generated file would have to be hand-edited after every regeneration.

This module exists purely so the generated code works untouched. Do not add
anything to it.
"""
from modules.resources_rc import *  # noqa: F401,F403
