"""The session library, set on Home. Pages with library filters follow
`library_changed`. `output_dir()` is the library's StrikeWorks_user_output/
folder, the default for reports, deployed models and synced video.
"""
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from . import settings

#: each library's output folder (reports, deployed models, synced video)
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
        """<library>/StrikeWorks_user_output/, or None with no library. Made
        only with `create=True`; writers normally make it themselves."""
        if self._library is None:
            return None
        out = self._library / OUTPUT_DIR_NAME
        if create:
            out.mkdir(parents=True, exist_ok=True)
        return out
