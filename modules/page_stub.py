# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Placeholder content for a page that isn't built yet (Data analysis)."""
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QLabel, QVBoxLayout

from .theme import style


class StubPage(QObject):
    """Title + a short note on what's coming and when."""

    def __init__(self, frame, title, note="Not built yet."):
        super().__init__(frame)
        v = QVBoxLayout(frame)
        v.setContentsMargins(4, 6, 4, 6)
        v.setSpacing(4)

        lbl_title = QLabel(title)
        style(lbl_title, role="title")
        v.addWidget(lbl_title)

        lbl_note = QLabel(note)
        style(lbl_note, role="muted")
        lbl_note.setWordWrap(True)
        v.addWidget(lbl_note)
        v.addStretch()
