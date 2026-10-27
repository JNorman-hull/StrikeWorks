# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Layout helpers shared by the pages: the Page base every sidebar page
is built on, collapsible Section boxes, splitters and centring, and
running code when a widget is first shown.
"""
from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QScrollArea, QSplitter, QTabWidget, QVBoxLayout,
    QWidget,
)

from .theme import style


class Page(QWidget):
    """A sidebar page: a widget that builds its own contents in its
    constructor, given what it needs (the main window, shared state) by
    main.py, which adds it to the main window's page stack. `status`
    messages go to the console."""

    status = Signal(str, int)
    MARGIN = 10   # round the page, inside the main window's content area

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setContentsMargins(*(self.MARGIN,) * 4)


class TabbedPage(Page):
    """A page of tabs with the tab bar hidden: the sidebar picks the tab
    (main.py's `_SUBMENU_TARGETS`)."""

    def __init__(self, main_window):
        super().__init__(main_window)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.tabs.tabBar().setVisible(False)
        # no frame round the tab shown
        self.tabs.setDocumentMode(True)
        v.addWidget(self.tabs)

    def show_tab(self, index):
        self.tabs.setCurrentIndex(index)


def discard_widget(w):
    """Throw away a child widget that has just been taken out of a layout.

    Deliberately NOT `w.setParent(None)`: a widget added to a layout inside
    a visible window gets a *queued* "show if not hidden" from Qt. If it is
    discarded again before the event loop runs (a card refreshed twice in a
    row - e.g. a library switch followed straight away by another refresh)
    and orphaned with setParent(None), that queued show then pops it up as
    its own tiny top-level window (titled "python"), which stays on screen
    until deleteLater gets its turn - and inside a nested event loop (the
    demo runners' waits) that can be a long time. Hiding it explicitly
    cancels the queued show, and keeping its parent means it can never
    become a window at all."""
    w.hide()
    w.deleteLater()


def hsplit(*items):
    """A row of boxes that fills the page's width and can be resized by
    dragging the boundaries between them - the app's standard for boxes
    that sit side by side (a plain QHBoxLayout row can't be resized, and
    anything with a fixed/maximum width leaves dead space on a wide
    screen). Each item is a widget, or (widget, weight): the weights set
    the starting proportions and how extra width is shared."""
    split = QSplitter(Qt.Orientation.Horizontal)
    split.setChildrenCollapsible(False)
    weights = []
    for i, item in enumerate(items):
        widget, weight = item if isinstance(item, tuple) else (item, 1)
        split.addWidget(widget)
        split.setStretchFactor(i, weight)
        weights.append(weight)
    split.setSizes([w * 1000 for w in weights])
    return split


def centred(widget, max_width=None, share=None):
    """`widget` centred horizontally in a holder, rather than stretched
    across the full width of a wide page: capped at `max_width` pixels, or
    - with `share` (0-1) - taking that fraction of the available width."""
    holder = QWidget()
    h = QHBoxLayout(holder)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(0)
    if share is not None:
        side = max(1, round((1 - share) * 50))
        mid = max(1, round(share * 100))
        h.addStretch(side)
        h.addWidget(widget, stretch=mid)
        h.addStretch(side)
    else:
        if max_width:
            widget.setMaximumWidth(max_width)
        h.addStretch(0)
        h.addWidget(widget, stretch=1)
        h.addStretch(0)
    return holder


def group_box(title, margin=6, spacing=6):
    """(a plain QGroupBox titled `title`, its QVBoxLayout)."""
    box = QGroupBox(title)
    v = QVBoxLayout(box)
    v.setContentsMargins(margin, margin, margin, margin)
    v.setSpacing(spacing)
    return box, v


def scroll_area(widget=None):
    """A borderless scroll area that resizes `widget` to its width."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    style(scroll, role="bare")
    if widget is not None:
        scroll.setWidget(widget)
    return scroll


def scroll_page(frame):
    """Fill `frame` with a scroll area and return the layout of the page
    body inside it - the standard page/tab frame."""
    outer = QVBoxLayout(frame)
    outer.setContentsMargins(0, 0, 0, 0)
    body = QWidget()
    style(body, role="bare")
    outer.addWidget(scroll_area(body))
    v = QVBoxLayout(body)
    v.setContentsMargins(4, 6, 4, 6)
    v.setSpacing(10)
    return v


class _ShowWatcher(QObject):
    """Holds one pending callback per widget and runs it the next time that
    widget is shown (see `when_visible`)."""

    def __init__(self, widget):
        super().__init__(widget)
        self.pending = {}
        widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Show and self.pending:
            calls, self.pending = list(self.pending.values()), {}
            # after the show has painted - the page appears first, then
            # its (possibly slow) refresh runs
            for fn in calls:
                QTimer.singleShot(0, fn)
        return False


class _OnShow(QObject):
    def __init__(self, widget, fn):
        super().__init__(widget)
        self._fn = fn
        widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Show:
            QTimer.singleShot(0, self._fn)
        return False


def on_show(widget, fn):
    """Run `fn` every time `widget` is shown (just after it has painted) -
    for summaries that go stale while their page isn't being looked at."""
    _OnShow(widget, fn)


def when_visible(widget, fn, key="default"):
    """Run `fn` now if `widget` is on screen, else the next time it is shown.
    Only the latest pending call per `key` is kept - so a page that isn't
    being looked at does no work at all for a library switch (or three),
    just once when it's next opened."""
    if widget.isVisible():
        fn()
        return
    watcher = next((c for c in widget.children() if isinstance(c, _ShowWatcher)),
                   None)
    if watcher is None:
        watcher = _ShowWatcher(widget)
    watcher.pending[key] = fn


# ── section box ──────────────────────────────────────────────────────────────
class Section(QGroupBox):
    """A titled part of a page: the title as a plain heading over the
    contents - no frame, no tick box; an untitled one keeps no room for a
    heading. Its layout's own margins go the first time it's shown, so the
    contents line up under the heading."""

    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self._margins_set = False
        style(self, role="plain" if title else "plain-untitled")

    def showEvent(self, event):
        if not self._margins_set and self.layout() is not None:
            self.layout().setContentsMargins(0, 4, 0, 0)
            self._margins_set = True
        super().showEvent(event)
