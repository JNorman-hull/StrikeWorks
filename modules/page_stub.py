"""Placeholder content for a page that isn't built yet (Data analysis)."""
from PySide6.QtWidgets import QLabel, QVBoxLayout

from .layout import Page
from .theme import style


class StubPage(Page):
    """Title + a short note on what's coming."""

    def __init__(self, main_window, title, note="Not built yet."):
        super().__init__(main_window)
        v = QVBoxLayout(self)
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
