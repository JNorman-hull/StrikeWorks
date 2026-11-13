"""Create and edit deployment (Setup and deploy): the deployment editor
(deployment_editor.py), as in StrikeWorks's Deploy step. Its sidebar button
is main.ui's `btn_initiate_deployment`.
"""
from PySide6.QtWidgets import QVBoxLayout

from .deployment_editor import DeploymentEditor
from .layout import Page


class DeploymentPage(Page):
    """Create and edit deployment: the deployment editor."""

    def __init__(self, main_window, session_state=None):
        super().__init__(main_window)
        self.session_state = session_state

        v = QVBoxLayout(self)
        v.setContentsMargins(4, 6, 4, 6)
        self.editor = DeploymentEditor(main_window, session_state,
                                       show_configure_link=True)
        self.editor.status.connect(self.status.emit)
        v.addWidget(self.editor)

    @property
    def _lib_root(self):
        """report_center's Study design section reads the library here."""
        return self.editor.lib_root
