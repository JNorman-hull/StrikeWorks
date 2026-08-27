# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""App-wide right-click "Copy" for every table in the app.

Installed once on the ``QApplication`` as an event filter, so no table
constructor needs individual wiring - every ``QTableWidget``/``QTableView``
gets a "Copy" context-menu item for free, including the Designer-generated
tables in ``ui_main.py`` and any added later.

Context-menu events land on the item view's viewport widget, not the view
itself, so the filter checks both.
"""
from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication, QMenu, QTableView


def _table_for(obj):
    if isinstance(obj, QTableView):
        return obj
    parent = obj.parentWidget() if hasattr(obj, "parentWidget") else None
    return parent if isinstance(parent, QTableView) else None


def _copy_selection(table):
    indexes = table.selectedIndexes()
    if not indexes:
        return
    rows = {}
    for idx in indexes:
        rows.setdefault(idx.row(), {})[idx.column()] = idx.data()
    lines = []
    for r in sorted(rows):
        cols = rows[r]
        lines.append("\t".join(
            "" if cols[c] is None else str(cols[c]) for c in sorted(cols)))
    QApplication.clipboard().setText("\n".join(lines))


class _TableCopyFilter(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.ContextMenu:
            table = _table_for(obj)
            if table is not None:
                menu = QMenu(table)
                act = menu.addAction("Copy")
                act.setEnabled(bool(table.selectedIndexes()))
                act.triggered.connect(lambda: _copy_selection(table))
                menu.exec(event.globalPos())
                return True
        return False


_installed = None


def install(app):
    """Enable right-click copy on every table in `app`. Call once at startup."""
    global _installed
    if _installed is None:
        _installed = _TableCopyFilter(app)
        app.installEventFilter(_installed)
