# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Raw processing: each recording's raw files through the parser the
sensor configuration names (sensor_config.PARSERS), into the library's
processed_sens_data (processed CSV + sensor index row)."""
from PySide6.QtCore import QThread, Signal

from . import sensor_config


class ProcessThread(QThread):
    """Runs the sensor configuration's parser over a batch of
    recordings off the GUI thread, logging each one."""
    log = Signal(str)
    done = Signal(int)          # 0 = all ok, 1 = some failed
    processed = Signal(str)     # stem of each successfully processed file

    def __init__(self, files, out_dir, root, config):
        super().__init__()
        self._files = files
        self._out_dir = out_dir
        self._root = root
        self._config = config

    def run(self):
        # the reader is whichever one the sensor configuration names
        parse = sensor_config.get_parser(self._config.parser)

        n_ok = n_fail = 0
        for f in self._files:
            self.log.emit(f"\n-- Processing: {f['stem']}")
            try:
                _, summary = parse(f["paths"], self._out_dir, self._config)
                msg = summary.get("messages", "")
                flag = ("  Flagged bad." if summary.get("bad_sens", "N") == "Y"
                        else "")
                self.log.emit(f"   Done.{flag}  {msg}")
                self.processed.emit(f["stem"])
                n_ok += 1
            except Exception as e:
                self.log.emit(f"   FAILED: {e}")
                n_fail += 1

        self.log.emit(f"\n-- Complete: {n_ok} succeeded, {n_fail} failed.")
        self.done.emit(0 if n_fail == 0 else 1)
