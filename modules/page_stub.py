# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Placeholder content for a page whose real build hasn't landed yet.

One reusable builder rather than a near-identical controller file per new
page - every stub page in the Chunk 5 restructure (see ROADMAP.md) uses
this until its own task replaces it.
"""
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QLabel, QVBoxLayout

from .ml_widgets import MUTED, TEXT


class StubPage(QObject):
    """Title + a short note on what's coming and when."""

    def __init__(self, frame, title, note="Not built yet."):
        super().__init__(frame)
        v = QVBoxLayout(frame)
        v.setContentsMargins(4, 6, 4, 6)
        v.setSpacing(4)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"color:{TEXT};font-size:16px;font-weight:bold;")
        v.addWidget(lbl_title)

        lbl_note = QLabel(note)
        lbl_note.setStyleSheet(f"color:{MUTED};")
        lbl_note.setWordWrap(True)
        v.addWidget(lbl_note)
        v.addStretch()
