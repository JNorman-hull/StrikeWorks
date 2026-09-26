# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""The session library, shared by every page (set on Home), in the same
shared-object pattern as `BSMState`, `PredictionState` and
`TrainingState`. Pages with library filters follow `library_changed`.

`output_dir()` is `<library>/StrikeWorks_user_output/`, the default place
for reports, deployed models and synced video. Loading is unaffected:
models and training data can still be loaded from anywhere.
"""
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from . import settings

#: the unified per-library output folder name (deployed models, reports,
#: synced video default here when a session library is selected)
OUTPUT_DIR_NAME = "StrikeWorks_user_output"


class SessionState(QObject):
    """The session's current library. `library_changed(path_or_None)` -
    every soft-synced picker and Home's own status view listen for this."""

    library_changed = Signal(object)   # Path or None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._library = settings.get_last_library()

    @property
    def library(self):
        return self._library

    def set_library(self, path):
        path = Path(path) if path else None
        if path == self._library:
            return
        self._library = path
        settings.set_last_library(path)
        self.library_changed.emit(path)

    def new_session(self):
        """Clears the session library - the confirm dialog lives on the
        Home page, this is just the state reset once confirmed."""
        self.set_library(None)

    def output_dir(self, create=False):
        """`<library>/StrikeWorks_user_output/`, or None with no library
        selected. Never creates the folder by default - callers that
        actually write into it already do their own `mkdir(parents=True,
        exist_ok=True)` right before writing (matching how every other
        output path in this app works), so merely computing "where would
        this go" - at page construction, in a resume-summary check -
        shouldn't leave empty folders behind on disk. Pass `create=True`
        only at an actual write site that doesn't already mkdir itself."""
        if self._library is None:
            return None
        out = self._library / OUTPUT_DIR_NAME
        if create:
            out.mkdir(parents=True, exist_ok=True)
        return out
