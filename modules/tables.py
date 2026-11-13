"""Every table in the app, from one place: the look (the HIG peak
analysis table's - headers drawn as its cells are, text centred), sorting
and filtering from the column headers, right-click copy, sizing a table to
its rows, and the HIG peak analysis table itself.

`install` (once, from MainWindow) gives every QTableWidget all of it as it
is first shown - no table needs wiring of its own, including the
Designer-generated ones in ``ui_main.py``.
"""
import re

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractSpinBox, QApplication, QComboBox, QHeaderView, QLineEdit,
    QStyledItemDelegate, QTableView, QTableWidget, QTableWidgetItem,
)

from . import hig_peaks
from .layout import popup_menu


def install(app):
    """Style, sort/filter and copy for every table in `app`. Call once,
    before any table is shown."""
    global _installed
    if _installed is None:
        _installed = _Tables(app)
        app.installEventFilter(_installed)


_installed = None


class _Tables(QObject):
    """The app-wide event filter: sets each table up as it's first
    polished (just before it's first shown), and opens the copy menu on a
    right-click - which lands on a table's viewport, not the table."""

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind == QEvent.Type.Polish and isinstance(obj, QTableWidget):
            set_up(obj)
        elif kind == QEvent.Type.ContextMenu:
            tbl = _table_for(obj)
            if tbl is not None:
                copy_menu(tbl, event.globalPos())
                return True
        return False


def _table_for(obj):
    if isinstance(obj, QTableView):
        return obj
    parent = obj.parentWidget() if hasattr(obj, "parentWidget") else None
    return parent if isinstance(parent, QTableView) else None


def set_up(tbl):
    """The look and the header menu, once per table."""
    if tbl.property("tableSetUp"):
        return
    tbl.setProperty("tableSetUp", True)
    style_table(tbl)
    header_menu(tbl)


# the look
def style_table(tbl: QTableWidget, row_numbers=True, columns=True):
    """The app's table look, centred text and user-resizable rows. Row
    resizing needs a visible vertical header, so `row_numbers` defaults to
    True (a table with the `noRowNumbers` property never gets them).
    `columns=True` makes columns draggable too, filling the table's width when
    first shown; `columns=False` leaves column sizing alone.
    """
    if tbl.property("noRowNumbers"):
        row_numbers = False
    tbl.verticalHeader().setVisible(row_numbers)
    tbl.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    if type(tbl.itemDelegate()) is QStyledItemDelegate:
        tbl.setItemDelegate(_Centred(tbl))
    if columns:
        tbl.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive)
        tbl.horizontalHeader().setStretchLastSection(False)
        # Interactive columns start at Qt's default width; they are fitted
        # each time the table is shown, until the user drags one
        tbl.installEventFilter(_TableFillOnShow.instance())
        if not getattr(tbl, "_fits_new_columns", False):
            tbl._fits_new_columns = True
            tbl.horizontalHeader().sectionResized.connect(
                lambda *_a: _note_drag(tbl))
            # ...and again once a page has filled in new columns
            timer = QTimer(tbl)
            timer.setSingleShot(True)
            timer.setInterval(0)
            timer.timeout.connect(lambda: _fit_new_columns(tbl))
            tbl.model().columnsInserted.connect(lambda *_a: timer.start())


class _Centred(QStyledItemDelegate):
    """Cell text centred, as in the HIG table - unless the cell has an
    alignment of its own."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if index.data(Qt.ItemDataRole.TextAlignmentRole) is None:
            option.displayAlignment = Qt.AlignmentFlag.AlignCenter


#: set on a table once the user has dragged one of its columns
DRAGGED = "columnsDragged"


def _note_drag(tbl):
    """A column resized with the mouse button down is the user's doing."""
    if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
        tbl.setProperty(DRAGGED, True)


def _fit_new_columns(tbl):
    tbl.setProperty(DRAGGED, False)
    fill_table_width(tbl)


class _TableFillOnShow(QObject):
    """Event filter (one instance) that fills a table's width each time
    it is shown, unless the user has set the column widths."""
    _shared = None

    @classmethod
    def instance(cls):
        if cls._shared is None:
            cls._shared = cls()
        return cls._shared

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Show and not obj.property(DRAGGED):
            fill_table_width(obj)
        return False


def fill_table_width(tbl: QTableWidget):
    """Size `tbl`'s columns to their contents, then share any spare
    viewport width between them."""
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


def fit_height(tbl: QTableWidget):
    """As tall as its rows (and column headers, if shown) - the whole
    table on the page, never a scrolling box."""
    tbl.ensurePolished()        # (the stylesheet's padding is in frameWidth)
    tbl.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    tbl.resizeRowsToContents()
    header = tbl.horizontalHeader()
    head = 0 if header.isHidden() else header.sizeHint().height()
    tbl.setFixedHeight(head + tbl.verticalHeader().length()
                       + 2 * tbl.frameWidth() + 2)


# cells and headers as text
_NAME = Qt.ItemDataRole.UserRole         # a header's column name...
_SHOWN = Qt.ItemDataRole.UserRole + 1    # ...and the text a filter gave it


def header_name(tbl, col):
    """Column `col`'s name, without the filter its header may show."""
    if not isinstance(tbl, QTableWidget):
        value = tbl.model().headerData(col, Qt.Orientation.Horizontal)
        return "" if value is None else str(value)
    item = tbl.horizontalHeaderItem(col)
    if item is None:
        return str(col + 1)
    text = item.text()
    # a header the page has relabelled since is named by its new text
    if item.data(_SHOWN) == text and item.data(_NAME) is not None:
        return item.data(_NAME)
    return text


def cell_text(tbl, row, col):
    """What a cell shows - an item's text, or a box's value for a cell
    holding a dropdown, spin box or text field."""
    index = tbl.model().index(row, col)
    widget = tbl.indexWidget(index)
    if isinstance(widget, QComboBox):
        return widget.currentText()
    if isinstance(widget, (QAbstractSpinBox, QLineEdit)):
        return widget.text()
    value = index.data()
    return "" if value is None else str(value)


def table_rows(tbl):
    """(column names, [row of cell texts]) - every row, in the table's
    order: for a report."""
    cols = range(tbl.model().columnCount())
    return ([header_name(tbl, c) for c in cols],
            [[cell_text(tbl, r, c) for c in cols]
             for r in range(tbl.model().rowCount())])


# right-click copy
def copy_menu(tbl, pos):
    """Copy highlighted cells / Copy entire table, at `pos` (global)."""
    menu = popup_menu(tbl)
    act = menu.addAction("Copy highlighted cells")
    act.setEnabled(bool(tbl.selectedIndexes()))
    act.triggered.connect(lambda: _to_clipboard(selection_text(tbl)))
    menu.addAction("Copy entire table",
                   lambda: _to_clipboard(table_text(tbl)))
    menu.exec(pos)
    menu.deleteLater()


def _to_clipboard(text):
    QApplication.clipboard().setText(text)


def _shown(tbl):
    """The rows and columns on screen (not filtered out or hidden)."""
    model = tbl.model()
    return ([r for r in range(model.rowCount()) if not tbl.isRowHidden(r)],
            [c for c in range(model.columnCount())
             if not tbl.isColumnHidden(c)])


def selection_text(tbl):
    """The highlighted cells, tab-separated, a line per row."""
    rows, cols = _shown(tbl)
    rows, cols = set(rows), set(cols)
    picked = {}
    for idx in tbl.selectedIndexes():
        if idx.row() in rows and idx.column() in cols:
            picked.setdefault(idx.row(), set()).add(idx.column())
    return "\n".join(
        "\t".join(cell_text(tbl, r, c) for c in sorted(picked[r]))
        for r in sorted(picked))


def table_text(tbl):
    """The table as shown - its column names (when they're shown), then
    every row the filters leave - tab-separated, a line per row."""
    rows, cols = _shown(tbl)
    lines = []
    if not tbl.horizontalHeader().isHidden():
        lines.append("\t".join(header_name(tbl, c) for c in cols))
    lines += ["\t".join(cell_text(tbl, r, c) for c in cols) for r in rows]
    return "\n".join(lines)


# sort and filter from the column headers
# Qt's tables sort on a header click but have no filter: a click on a
# header opens a menu instead, with both.
_MAX_LISTED = 50                 # more values than this aren't listed
_NO_FILTER = {"file"}            # one value per sensor: sort only


def sort_key(text):
    """Numbers (a cell's leading number: "12.5%", "0.93 ± 0.02") before
    text, numbers by value, text in natural order ("S2" before "S10")."""
    parts = re.split(r"(\d+)", text.lower())
    natural = tuple(int(p) if i % 2 else p for i, p in enumerate(parts))
    m = re.match(r"\s*[-+]?(\d+\.?\d*|\.\d+)(e[-+]?\d+)?", text, re.I)
    return (0, float(m.group(0)), natural) if m else (1, 0.0, natural)


class SortItem(QTableWidgetItem):
    """A cell that sorts by `sort_key`. Sorting from a header turns that
    column's cells into these (a copy of each, data and all)."""

    def __lt__(self, other):
        # (compared here: handing text back to QTableWidgetItem's own
        # operator calls this again, endlessly - a crash)
        return sort_key(self.text()) < sort_key(other.text())


def header_menu(tbl: QTableWidget):
    """Sort and filter `tbl` from its column headers: a click on a header
    opens a menu - sort ascending or descending, then All and the column's
    values (one shows only its rows). Filters on several columns combine,
    a filtered column's header shows the value, and they're re-applied
    whenever the table is refilled. `set_up` gives every table this."""
    if getattr(tbl, "_header_menu", False):
        return
    tbl._header_menu = True
    tbl._header_filters = getattr(tbl, "_header_filters", {})
    tbl._rows_filtered = False
    tbl.setSortingEnabled(False)     # a click opens the menu, nothing more
    header = tbl.horizontalHeader()
    header.setSectionsClickable(True)
    header.sectionClicked.connect(lambda col: _open_header_menu(tbl, col))
    # once the refilling's done - not after every cell
    timer = QTimer(tbl)
    timer.setSingleShot(True)
    timer.setInterval(0)
    timer.timeout.connect(lambda: apply_header_filters(tbl))

    def changed(*_args):
        if tbl._header_filters or tbl._rows_filtered:
            timer.start()

    model = tbl.model()
    for signal in (model.rowsInserted, model.rowsRemoved, model.modelReset,
                   model.dataChanged, model.columnsInserted,
                   model.columnsRemoved):
        signal.connect(changed)


def _column_keys(tbl):
    """{key: column} - a column's name, or "name (2)" for the second
    column of that name."""
    keys, seen = {}, {}
    for c in range(tbl.columnCount()):
        name = header_name(tbl, c)
        seen[name] = seen.get(name, 0) + 1
        keys[name if seen[name] == 1 else f"{name} ({seen[name]})"] = c
    return keys


def _open_header_menu(tbl, col):
    key = next(k for k, c in _column_keys(tbl).items() if c == col)
    menu = popup_menu(tbl)
    has_items = any(tbl.item(r, col) is not None
                    for r in range(tbl.rowCount()))
    for text, order in (("Sort ascending", Qt.SortOrder.AscendingOrder),
                        ("Sort descending", Qt.SortOrder.DescendingOrder)):
        act = menu.addAction(text, lambda o=order: sort_column(tbl, col, o))
        act.setEnabled(has_items)
    values = filter_values(tbl, col)
    if values is not None:
        menu.addSeparator()
        current = tbl._header_filters.get(key)
        act = menu.addAction("All")
        act.setCheckable(True)
        act.setChecked(current is None)
        act.triggered.connect(lambda: set_header_filter(tbl, key, None))
        if len(values) > _MAX_LISTED:
            menu.addAction(f"({len(values)} values - too many to list)"
                           ).setEnabled(False)
        else:
            for value in values:
                act = menu.addAction(value or "(blank)")
                act.setCheckable(True)
                act.setChecked(value == current)
                act.triggered.connect(
                    lambda _c=False, v=value: set_header_filter(tbl, key, v))
    header = tbl.horizontalHeader()
    menu.exec(header.mapToGlobal(
        QPoint(header.sectionViewportPosition(col), header.height())))
    menu.deleteLater()


def sort_column(tbl, col, order=Qt.SortOrder.AscendingOrder):
    """Sort `tbl`'s rows by column `col`, in `sort_key` order, keeping its
    filters."""
    _sortable(tbl, col)
    tbl.sortItems(col, order)
    apply_header_filters(tbl)   # hidden rows don't move with a sort


def filter_values(tbl, col):
    """The values column `col` can be filtered to - those the other
    columns' filters leave, in `sort_key` order - or None for a column
    that's never filtered ("file": a value per sensor)."""
    if header_name(tbl, col).strip().lower() in _NO_FILTER:
        return None
    keys = _column_keys(tbl)
    others = {keys[k]: v for k, v in getattr(tbl, "_header_filters", {}).items()
              if k in keys and keys[k] != col}
    return sorted({cell_text(tbl, r, col) for r in range(tbl.rowCount())
                   if all(cell_text(tbl, r, c) == v
                          for c, v in others.items())}, key=sort_key)


def _sortable(tbl, col):
    """Column `col`'s cells as SortItems, so it sorts by `sort_key`."""
    blocked = tbl.blockSignals(True)     # (not an edit of the table's own)
    try:
        for r in range(tbl.rowCount()):
            item = tbl.item(r, col)
            if item is not None and not isinstance(item, SortItem):
                tbl.setItem(r, col, SortItem(item))
    finally:
        tbl.blockSignals(blocked)


def set_header_filter(tbl, name, value):
    """Show only the rows whose column `name` holds `value` (None: every
    row, as far as this column goes)."""
    filters = getattr(tbl, "_header_filters", None)
    if filters is None:
        filters = tbl._header_filters = {}
    if value is None:
        filters.pop(name, None)
    else:
        filters[name] = value
    apply_header_filters(tbl)


def apply_header_filters(tbl):
    """Hide the rows the header filters leave out and show each filtered
    column's value in its header; a filter on a column that's gone is
    dropped."""
    keys = _column_keys(tbl)
    filters = {k: v for k, v in getattr(tbl, "_header_filters", {}).items()
               if k in keys}
    tbl._header_filters = filters
    for key, c in keys.items():
        name = header_name(tbl, c)
        value = filters.get(key)
        shown = name if value is None else f"{name}: {value or '(blank)'}"
        item = tbl.horizontalHeaderItem(c)
        if item is None:
            if value is None:
                continue
            item = QTableWidgetItem(name)
            tbl.setHorizontalHeaderItem(c, item)
        item.setData(_NAME, name)
        item.setData(_SHOWN, shown)
        item.setText(shown)
    cols = {keys[k]: v for k, v in filters.items()}
    hidden = False
    for r in range(tbl.rowCount()):
        hide = not all(cell_text(tbl, r, c) == v for c, v in cols.items())
        tbl.setRowHidden(r, hide)
        hidden = hidden or hide
    tbl._rows_filtered = hidden


# the HIG peak analysis table
def fill_acceleration_table(tbl, acc_summary):
    """The HIG peak analysis table in the report template's layout: two
    header rows (Event count / Collision probability / Acceleration over
    their columns), then a row per treatment. Empty without a summary."""
    with_tx = hig_peaks.show_treatment(acc_summary)
    lead = (["Treatment"] if with_tx else []) + ["Region of interest"]
    rows = hig_peaks.table_rows(acc_summary) if acc_summary is not None else []
    tbl.clearSpans()
    tbl.clear()
    tbl.setColumnCount(len(lead) + len(hig_peaks.TABLE_COLUMNS))
    tbl.setRowCount(2 + len(rows))

    def put(r, c, text):
        tbl.setItem(r, c, QTableWidgetItem(text))

    for c, text in enumerate(lead):
        put(0, c, text)
        tbl.setSpan(0, c, 2, 1)
    c = len(lead)
    for title, span in hig_peaks.TABLE_GROUPS:
        put(0, c, title)
        tbl.setSpan(0, c, 1, span)
        c += span
    for i, text in enumerate(hig_peaks.TABLE_COLUMNS):
        put(1, len(lead) + i, text)
    for r, (treatment, roi, cells) in enumerate(rows, start=2):
        values = ([treatment] if with_tx else []) + [roi] + cells
        for c, value in enumerate(values):
            put(r, c, value)
    tbl.resizeColumnsToContents()
    fit_height(tbl)
