# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Layout helpers shared by the pages: collapsible Section boxes,
splitters and centring, and running code when a widget is first shown.
"""
from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QScrollArea, QSplitter, QVBoxLayout, QWidget,
)

from .theme import style


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


# ── collapsible section ──────────────────────────────────────────────────────
# Which sections start open. Keys are the section titles passed to Section();
# anything not listed defaults to open. Set a title to False here to have that
# panel start collapsed.
SECTION_DEFAULTS = {
    # Setup and deploy - Sensor configuration
    "Session sensor": True,
    "Rates and raw files": True,
    "Channels": True,
    "Parser": True,
    # Setup and deploy - Study design
    "Deployment": True,
    "Treatments": True,
    "Save to library": True,
    # Model Prediction - Predict
    "Model": True,
    "Dataset": True,
    "Compatibility": True,
    "Prediction configuration": True,
    "Run": True,
    "Prediction summary": True,
    "Results by treatment": True,
    "Prediction figures": True,
    # Model Prediction - Inspect
    "Filter predictions": True,
    "Selected prediction": True,
    "Class probabilities": True,
    "Model input signal": True,
    # Model Prediction - Report
    "Report preview": True,
    # Model Training - Train
    "Training dataset": True,
    "Dataset filtering": True,
    "Labelling": True,
    "Dataset preview (file-level metadata)": True,
    "Model input channels": True,
    "Sequence configuration": True,
    "Validation": True,
    "Class balancing": True,
    "Train": True,
    "Training console": True,
    # Model Training / Model Performance - Evaluate
    "Performance (out-of-fold)": True,
    "Cross-validation (mean ± SD across folds)": True,
    "Error analysis": True,
    "Evaluation figures": True,
    "Performance by strike type / class": True,
    "Performance by treatment": True,
    # Model Training - Deploy
    "Model deployment": True,
    "Model information": True,
}


def _set_layout_visible(layout, visible):
    for i in range(layout.count()):
        item = layout.itemAt(i)
        w = item.widget()
        if w is not None:
            w.setVisible(visible)
            continue
        sub = item.layout()
        if sub is not None:
            _set_layout_visible(sub, visible)


class Section(QGroupBox):
    """Checkable group box that collapses to its title bar when unchecked.

    Used for every panel on the Machine Learning Analysis pages so the user
    can fold away what they are not working on. Default open/closed state
    comes from SECTION_DEFAULTS, applied once the contents are built via
    apply_section_defaults().
    """

    COLLAPSED_H = 26

    def __init__(self, title, key=None, parent=None):
        super().__init__(title, parent)
        self.key = key or title
        self.setCheckable(True)
        self.setChecked(True)
        self.toggled.connect(self._apply)

    def _apply(self, on):
        lay = self.layout()
        if lay is not None:
            _set_layout_visible(lay, on)
        self.setMaximumHeight(16777215 if on else self.COLLAPSED_H)

    def apply_default(self):
        want = SECTION_DEFAULTS.get(self.key, True)
        if self.isChecked() != want:
            self.setChecked(want)
        else:
            self._apply(want)


def apply_section_defaults(root):
    """Apply SECTION_DEFAULTS to every Section under `root`.

    Call after a tab has finished building, so the collapse can measure and
    hide real contents.
    """
    for sec in root.findChildren(Section):
        sec.apply_default()
