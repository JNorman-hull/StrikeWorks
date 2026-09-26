# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Create and edit deployment (Setup and deploy): hosts the shared
deployment editor (deployment_editor.py), the same one Simple mode's Deploy
step shows. The Designer object names (`page_initiate_deployment`,
`btn_initiate_deployment`) keep the page's old working name.
"""
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QVBoxLayout

from .deployment_editor import DeploymentEditor


class DeploymentPage(QObject):
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
