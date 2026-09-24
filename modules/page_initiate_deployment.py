# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Controller for Create and edit deployment (Setup and deploy).

Object names (`page_initiate_deployment`, `btn_initiate_deployment`, this
module's filename) still say "initiate deployment" - that was this page's
working name; renaming the object graph for a label change isn't worth the
main.ui/main.py churn (see ROADMAP.md Chunk 5's "renames are text-only"
note), so only the sidebar button text says "Create and edit deployment".

The page is the shared deployment editor (deployment_editor.py) - exactly
what Simple mode's Deploy step shows: session library, library status,
sensor, deployment, treatment table, Create & open data folder / Update.
Libraries now always live in the libraries folder (Adjustments), like
everywhere else in the app; the old "Choose library…" arbitrary-folder
picker is gone with the rest of this page's own form.
"""
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QVBoxLayout

from . import raw_layout
from .deployment_editor import DeploymentEditor

# kept for anything still importing it from here - the text itself now
# lives with the folder layout it describes
_README_TEXT = raw_layout.README_TEXT


class InitiateDeploymentPage(QObject):
    """Binds Create and edit deployment to `ui.content_initiate_deployment`."""

    status = Signal(str, int)

    def __init__(self, ui, window, session_state=None):
        super().__init__(window)
        self.ui = ui
        self.window = window
        self.session_state = session_state

        v = QVBoxLayout(ui.content_initiate_deployment)
        v.setContentsMargins(4, 6, 4, 6)
        self.editor = DeploymentEditor(window, session_state,
                                       show_configure_link=True)
        self.editor.status.connect(self.status.emit)
        v.addWidget(self.editor)

    @property
    def _lib_root(self):
        """report_center's Study design section reads the library here."""
        return self.editor.lib_root
