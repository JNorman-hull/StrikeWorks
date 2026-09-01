# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""The session-wide library selection (Home page).

Before this existed, every page that needed a library (Process, Annotate,
Export animations - each via their own `LibrarySelector`; Initiate
deployment, Validate, Dataset, Biological via their own bespoke pickers)
had entirely independent selection state - picking a library on one had no
effect on any other. `SessionState` is a single shared "which library is
this session working in" value, following the same shared-object pattern
`BSMState`/`PredictionState`/`TrainingState` already use in this app.

Soft sync, deliberately (2026-08-31 design decision): existing pickers stay
as they are and simply *default* to the session library, rather than being
torn out for one single picker everywhere - that unification is a planned
follow-up, not this pass. `LibrarySelector.__init__`'s optional
`session_state` argument is the wiring: it seeds the combo from
`session_state.library` and re-syncs whenever `library_changed` fires, but
the combo remains independently changeable per page as it always was.

Output location: `output_dir()` is `<library>/StrikeWorks_user_output/` -
the unified per-library destination for reports, deployed models, and
synced video. This does not restrict *loading* those things - the model/
training-data pickers throughout the app remain free file/folder browsers,
so a model or a bound multi-library training set can still be loaded from
anywhere; only the *default write location* for new output changes.
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
