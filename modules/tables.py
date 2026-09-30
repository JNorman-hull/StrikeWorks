# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Table styling shared by every QTableWidget in the app.
"""
from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QHeaderView, QTableWidget


def style_table(tbl: QTableWidget, row_numbers=True, columns=True):
    """The one table look used everywhere in the app: the same card
    background + outline every other container gets, and rows left
    user-resizable (drag a row boundary) rather than a fixed grid. Row
    resizing needs a visible vertical header to grab (Qt gives a hidden
    header no drag handle at all), so `row_numbers` defaults to True; pass
    False only for a table dense enough that a numbered gutter would be
    pure clutter and its rows never need resizing (e.g. a single-purpose
    two-column key/value listing).

    `columns=True` (the default) also makes column widths user-draggable
    (`Interactive`, matching the rows) - call `tbl.resizeColumnsToContents()`
    once after populating so they start at a sensible width rather than
    Qt's generic default. Pass `columns=False` to leave a table's own
    column-sizing choice alone (e.g. `ResizeToContents` + stretch-last on a
    wide sortable results table, where auto-fit matters more than manual
    dragging) and only pick up the background/border/row treatment here.
    """
    tbl.verticalHeader().setVisible(row_numbers)
    tbl.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    if columns:
        tbl.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive)
        tbl.horizontalHeader().setStretchLastSection(False)
        # Interactive columns start at Qt's generic default width (a
        # freshly populated table looks squeezed into its left edge until
        # dragged wider by hand) - fill_table_width() on first Show fixes
        # that without giving up manual dragging afterward.
        tbl.installEventFilter(_TableFillOnShow.instance())


class _TableFillOnShow(QObject):
    """Singleton event filter: widens a table's columns to fill its
    viewport the first time it becomes visible with data, then gets out
    of the way - it only ever adds spare width, never fights a drag the
    user makes afterward."""
    _shared = None

    @classmethod
    def instance(cls):
        if cls._shared is None:
            cls._shared = cls()
        return cls._shared

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Show:
            fill_table_width(obj)
        return False


def fill_table_width(tbl: QTableWidget):
    """Widen `tbl`'s (already `Interactive`) columns to fill its viewport
    when their natural content width leaves space spare, so a populated
    table reads full-width instead of needing a manual drag first. Safe
    to call on an empty table (no columns to widen) or repeatedly (only
    ever adds width, so it will not undo a user's own drag)."""
    n = tbl.columnCount()
    if n == 0:
        return
    tbl.resizeColumnsToContents()
    total = sum(tbl.columnWidth(c) for c in range(n))
    available = tbl.viewport().width()
    extra = available - total
    if extra <= 0:
        return
    share, remainder = divmod(extra, n)
    for c in range(n):
        tbl.setColumnWidth(
            c, tbl.columnWidth(c) + share + (1 if c < remainder else 0))
