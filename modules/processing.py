# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Raw processing: each recording's raw files through the parser its
sensor configuration names (sensor_config.PARSERS), into the library's
processed_sens_data (processed CSV + sensor index row)."""
from PySide6.QtCore import QThread, Signal

from . import sensor_config


# ProcessThread.done codes
DONE_OK, DONE_ERRORS, DONE_STOPPED = 0, 1, 2


class ProcessThread(QThread):
    """Runs each recording's parser over a batch off the GUI thread,
    logging each one. A recording's own `config` says how it is read, and
    `config` here answers for any without one. `request_stop()` stops it
    before the next recording (the one in hand finishes)."""
    log = Signal(str)
    done = Signal(int)          # DONE_OK, DONE_ERRORS or DONE_STOPPED
    processed = Signal(str)     # stem of each successfully processed file

    def __init__(self, files, out_dir, root, config=None):
        super().__init__()
        self._files = files
        self._out_dir = out_dir
        self._root = root
        self._config = config
        self._stop = False

    def request_stop(self):
        self._stop = True

    def run(self):
        n_ok = n_fail = 0
        for f in self._files:
            if self._stop:
                self.log.emit(f"\n-- Stopped: {len(self._files) - n_ok - n_fail} "
                              "recording(s) not processed.")
                break
            self.log.emit(f"\n-- Processing: {f['stem']}")
            try:
                # the reader is whichever one the sensor configuration names
                config = f.get("config") or self._config
                parse = sensor_config.get_parser(config.parser)
                _, summary = parse(f["paths"], self._out_dir, config)
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
        self.done.emit(DONE_STOPPED if self._stop
                       else DONE_OK if n_fail == 0 else DONE_ERRORS)
