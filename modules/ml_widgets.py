# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Reusable widgets for the Machine Learning Analysis pages.

The RingCard and Spinner are ports of the MVP prediction page's widgets,
recoloured for the StrikeWorks dark theme. MetaCard, CheckList and ProbBars
are new but follow the same card language as page_process.StatCard.
"""
from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QPushButton, QSizePolicy, QTableWidget,
    QVBoxLayout, QWidget,
)

# theme colours (match the PyDracula palette used by the app)
CARD_BG = "#21252b"          # rgb(33,37,43)
BORDER  = "#2c313a"          # rgb(44,49,58)
TEXT    = "#dddddd"
MUTED   = "#8a95aa"
ACCENT  = "#bd93f9"          # purple
PINK    = "#ff79c6"
OK      = "#22c55e"
WARN    = "#f59e0b"
BAD     = "#ef4444"
INFO    = "#568af2"
EMPTY   = "#3a4150"

# category palette for ring segments / stacked bars
PALETTE = [INFO, PINK, WARN, OK, ACCENT, "#00bcd4"]

# Minimum widths only - every card expands to share the row, so a page
# never forces a horizontal scrollbar at a sensible window size.
CARD_W, CARD_H   = 205, 124
CARD_W2, CARD_H2 = 112, 112


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
    tbl.setStyleSheet(
        f"QTableWidget{{background-color:{CARD_BG};"
        f"border:1px solid {BORDER};border-radius:5px;}}")
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


# ── ring card (ported from the MVP, dark theme) ──────────────────────────────
class RingCard(QFrame):
    """Card with a donut ring; fixed height, expands horizontally.

    Metric mode   (set_value):    single arc fills 0-1, value in the centre.
    Category mode (set_segments): segmented colour ring with legend.
    Both modes start empty (grey ring) until data is supplied.
    """

    RING_D = 64
    RING_T = 11
    PAD    = 10

    def __init__(self, title, w=None, h=None, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(w or CARD_W)
        self.setFixedHeight(h or CARD_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setFrameShape(QFrame.Shape.NoFrame)

        self._title    = title
        self._value    = None
        self._segments = None
        self._centre   = ""
        self._empty    = True

    def set_title(self, title):
        self._title = title
        self.update()

    def set_value(self, v: float, centre_text: str = ""):
        self._value    = max(0.0, min(1.0, v))
        self._segments = None
        self._centre   = centre_text or f"{v:.3f}"
        self._empty    = False
        self.update()

    def set_segments(self, segments):
        """segments: [(label, count, colour), ...]"""
        self._segments = segments
        self._value    = None
        self._centre   = ""
        self._empty    = len(segments) == 0
        self.update()

    def clear(self):
        self._value = self._segments = None
        self._centre = ""
        self._empty = True
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        p.setPen(QPen(QColor(BORDER), 1.5))
        p.setBrush(QColor(CARD_BG))
        p.drawRoundedRect(1, 1, w - 2, h - 2, 8, 8)

        tf = QFont("Segoe UI", 10)
        tf.setBold(True)
        p.setFont(tf)
        p.setPen(QColor(TEXT))
        # elide rather than clip - metric cards can be narrow
        title_w = w - self.PAD * 2
        title = QFontMetrics(tf).elidedText(
            self._title, Qt.TextElideMode.ElideRight, title_w)
        p.drawText(self.PAD, 0, title_w, 26,
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   title)

        rx = w - self.RING_D - self.PAD
        ry = (h - self.RING_D) // 2 + 4

        p.setPen(QPen(QColor(EMPTY), self.RING_T,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rx, ry, self.RING_D, self.RING_D)

        if self._empty:
            p.end()
            return

        if self._value is not None:
            span = int(self._value * 360 * 16)
            p.setPen(QPen(QColor(ACCENT), self.RING_T,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(rx, ry, self.RING_D, self.RING_D, 90 * 16, -span)

            vf = QFont("Segoe UI", 11)
            vf.setBold(True)
            p.setFont(vf)
            p.setPen(QColor(TEXT))
            p.drawText(rx, ry, self.RING_D, self.RING_D,
                       Qt.AlignmentFlag.AlignCenter, self._centre)

        elif self._segments:
            total = sum(s[1] for s in self._segments) or 1
            angle = 90 * 16
            for _label, val, colour in self._segments:
                span = int(val / total * 360 * 16)
                p.setPen(QPen(QColor(colour), self.RING_T,
                              Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawArc(rx, ry, self.RING_D, self.RING_D, angle, -span)
                angle -= span

            lf = QFont("Segoe UI", 9)
            p.setFont(lf)
            text_w = rx - self.PAD * 2
            y = 28
            for label, val, colour in self._segments:
                if y + 28 > h - 4:
                    break
                pct = val / total * 100
                p.setBrush(QColor(colour))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(self.PAD, y + 4, 8, 8)

                p.setPen(QColor(TEXT))
                p.drawText(self.PAD + 13, y, text_w, 15,
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                           label)
                p.setPen(QColor(MUTED))
                p.drawText(self.PAD + 13, y + 15, text_w, 14,
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                           f"n={int(val)}  ({pct:.0f}%)")
                y += 31

        p.end()


# ── spinner ──────────────────────────────────────────────────────────────────
class Spinner(QWidget):
    """Small rotating arc drawn with QPainter. Show/hide around long ops."""

    def __init__(self, parent=None, size=24, colour=PINK):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._colour = colour
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self):
        self.setVisible(True)
        self._timer.start(40)   # ~25 fps

    def stop(self):
        self._timer.stop()
        self.setVisible(False)

    def _tick(self):
        self._angle = (self._angle + 14) % 360
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(BORDER), 3, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        m = 3
        p.drawEllipse(m, m, self.width() - m * 2, self.height() - m * 2)
        p.setPen(QPen(QColor(self._colour), 3, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap))
        p.drawArc(m, m, self.width() - m * 2, self.height() - m * 2,
                  self._angle * 16, 100 * 16)
        p.end()


# ── metadata card ────────────────────────────────────────────────────────────
class MetaCard(QFrame):
    """Key/value metadata card. Unknown values display as an em dash."""

    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.setObjectName("metaCard")
        self.setStyleSheet(
            f"#metaCard{{background-color:{CARD_BG};border-radius:6px;"
            f"border:1px solid {BORDER};}}")

        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(4)

        self._title = QLabel(title)
        self._title.setStyleSheet(
            f"color:{TEXT};font-weight:bold;border:none;")
        self._title.setVisible(bool(title))
        v.addWidget(self._title)

        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(14)
        self._grid.setVerticalSpacing(3)
        self._grid.setColumnStretch(1, 1)
        v.addLayout(self._grid)
        v.addStretch()

        self._rows = {}

    def set_title(self, title):
        self._title.setText(title)
        self._title.setVisible(bool(title))

    def set_rows(self, rows):
        """rows: [(label, value)] - value None/'' renders as an em dash."""
        # clear existing (detach immediately so stale rows never paint)
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._rows = {}

        for i, (label, value) in enumerate(rows):
            lab = QLabel(label)
            lab.setStyleSheet(f"color:{MUTED};border:none;")
            lab.setAlignment(Qt.AlignmentFlag.AlignTop)
            val = QLabel(self._fmt(value))
            val.setStyleSheet(f"color:{TEXT};border:none;")
            val.setWordWrap(True)
            val.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            self._grid.addWidget(lab, i, 0)
            self._grid.addWidget(val, i, 1)
            self._rows[label] = val

    def set_value(self, label, value):
        if label in self._rows:
            self._rows[label].setText(self._fmt(value))

    @staticmethod
    def _fmt(value):
        if value is None or value == "" or value == []:
            return "—"
        if isinstance(value, (list, tuple)):
            return ", ".join(str(v) for v in value)
        return str(value)


# ── validation checklist ─────────────────────────────────────────────────────
class CheckList(QFrame):
    """Renders (state, label, detail) validation rows plus a verdict banner."""

    _ICON = {"ok": ("✓", OK), "warn": ("⚠", WARN),
             "fail": ("✗", BAD), "off": ("–", MUTED)}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("checkList")
        self.setStyleSheet(
            f"#checkList{{background-color:{CARD_BG};border-radius:6px;"
            f"border:1px solid {BORDER};}}")
        self._v = QVBoxLayout(self)
        self._v.setContentsMargins(12, 10, 12, 10)
        self._v.setSpacing(4)

        self._verdict = QLabel("")
        vf = QFont("Segoe UI", 10)
        vf.setBold(True)
        self._verdict.setFont(vf)
        self._verdict.setStyleSheet("border:none;")
        self._items = []

    def set_checks(self, checks, ready, ready_text=None,
                   blocked_text=None):
        """Render the checks. A verdict banner is drawn only when
        ready_text/blocked_text are supplied; pages that show the outcome
        elsewhere (e.g. via a gated Run button) omit it."""
        for w in self._items:
            w.setParent(None)
            w.deleteLater()
        self._items = []
        self._v.removeWidget(self._verdict)

        for state, label, detail in checks:
            icon, colour = self._ICON.get(state, self._ICON["off"])
            row = QLabel(f"<span style='color:{colour};'>{icon}</span>&nbsp; "
                         f"<span style='color:{TEXT};'>{label}</span>"
                         + (f"<br/><span style='color:{MUTED};'>"
                            f"&nbsp;&nbsp;&nbsp;{detail}</span>"
                            if detail else ""))
            row.setStyleSheet("border:none;")
            row.setWordWrap(True)
            self._v.addWidget(row)
            self._items.append(row)

        if ready_text is None and blocked_text is None:
            self._verdict.setVisible(False)
            return
        self._verdict.setVisible(True)
        if ready:
            self._verdict.setText(ready_text or "")
            self._verdict.setStyleSheet(f"color:{OK};border:none;")
        else:
            self._verdict.setText(blocked_text or "")
            self._verdict.setStyleSheet(f"color:{BAD};border:none;")
        self._v.addWidget(self._verdict)

    def set_running(self):
        self._verdict.setText("PREDICTION RUNNING…")
        self._verdict.setStyleSheet(f"color:{ACCENT};border:none;")


# ── horizontal probability bars ──────────────────────────────────────────────
class ProbBars(QWidget):
    """Compact horizontal bar chart for class probabilities.

    set_probs([(label, prob, colour), ...]) - probs in 0-1.
    """

    ROW_H  = 26
    LAB_W  = 130
    VAL_W  = 48

    def __init__(self, parent=None):
        super().__init__(parent)
        self._probs = []
        self.setMinimumHeight(self.ROW_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)

    def set_probs(self, probs):
        self._probs = list(probs)
        self.setFixedHeight(max(1, len(self._probs)) * self.ROW_H)
        self.update()

    def clear(self):
        self.set_probs([])

    def paintEvent(self, _event):
        if not self._probs:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        bar_w = max(30, w - self.LAB_W - self.VAL_W - 16)

        f = QFont("Segoe UI", 9)
        p.setFont(f)
        for i, (label, prob, colour) in enumerate(self._probs):
            y = i * self.ROW_H
            p.setPen(QColor(TEXT))
            p.drawText(0, y, self.LAB_W, self.ROW_H,
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       label)

            # track
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(EMPTY))
            p.drawRoundedRect(self.LAB_W, y + 7, bar_w, self.ROW_H - 14, 4, 4)
            # fill
            fill = int(bar_w * max(0.0, min(1.0, float(prob))))
            if fill > 0:
                p.setBrush(QColor(colour))
                p.drawRoundedRect(self.LAB_W, y + 7, fill, self.ROW_H - 14, 4, 4)

            p.setPen(QColor(MUTED))
            p.drawText(self.LAB_W + bar_w + 8, y, self.VAL_W, self.ROW_H,
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       f"{float(prob):.3f}")
        p.end()


# ── collapsible section ──────────────────────────────────────────────────────
# Which sections start open. Keys are the section titles passed to Section();
# anything not listed defaults to open. Set a title to False here to have that
# panel start collapsed.
SECTION_DEFAULTS = {
    # Prepare - Sensor configuration
    "Session sensor": True,
    "Rates and raw files": True,
    "Channels": True,
    "Parser": True,
    # Prepare - Study design
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


# ── level grouping ───────────────────────────────────────────────────────────
class LevelGrouper(QWidget):
    """Assign the observed levels of a variable to named classes.

    The levels come from the data, so a column gaining a new level (a sixth
    pump region, a new hub_type) simply appears here. Each level is mapped
    to a named group or excluded from training, and the group names are
    free text - they become the model's class names.

    Reused wherever levels need collapsing or recoding, so the behaviour is
    defined once.
    """

    changed = Signal()
    EXCLUDE = -1

    def __init__(self, parent=None):
        super().__init__(parent)
        self._levels = []
        self._groups = []          # [{"name": str, "levels": [key, ...]}]
        self._updating = False
        self._name_edits = []
        self._level_combos = {}

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        self._names_box = QVBoxLayout()
        self._names_box.setSpacing(2)
        v.addLayout(self._names_box)

        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("Add class")
        self.btn_add.clicked.connect(self._add_group)
        btn_row.addWidget(self.btn_add)
        btn_row.addStretch()
        v.addLayout(btn_row)

        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(12)
        self._grid.setVerticalSpacing(2)
        v.addLayout(self._grid)

        self.lbl_summary = QLabel("")
        self.lbl_summary.setStyleSheet(f"color:{MUTED};")
        self.lbl_summary.setWordWrap(True)
        v.addWidget(self.lbl_summary)

    # ── public API ───────────────────────────────────────────────────────────
    def set_data(self, levels, groups):
        """levels: [(key, display, count)]; groups: [{"name", "levels"}]"""
        self._levels = list(levels)
        self._groups = [{"name": g["name"], "levels": list(g["levels"])}
                        for g in groups]
        self._rebuild()

    def groups(self):
        return [{"name": g["name"], "levels": list(g["levels"])}
                for g in self._groups]

    # ── rebuild ──────────────────────────────────────────────────────────────
    def _clear(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
            elif item.layout() is not None:
                self._clear(item.layout())

    def _rebuild(self):
        self._updating = True
        try:
            self._clear(self._names_box)
            self._clear(self._grid)
            self._name_edits = []
            self._level_combos = {}

            for i, g in enumerate(self._groups):
                row = QHBoxLayout()
                lab = QLabel(f"Class {i + 1}")
                lab.setStyleSheet(f"color:{MUTED};")
                lab.setMinimumWidth(56)
                ed = QLineEdit(g["name"])
                ed.setPlaceholderText("class name")
                ed.textChanged.connect(
                    lambda text, idx=i: self._name_changed(idx, text))
                btn = QPushButton("✕")
                btn.setFixedWidth(28)
                btn.setToolTip("Remove this class")
                btn.setEnabled(len(self._groups) > 1)
                btn.clicked.connect(lambda _c=False, idx=i:
                                    self._remove_group(idx))
                row.addWidget(lab)
                row.addWidget(ed, stretch=1)
                row.addWidget(btn)
                self._names_box.addLayout(row)
                self._name_edits.append(ed)

            assign = self._assignment()
            for r, (key, display, count) in enumerate(self._levels):
                lab = QLabel(f"{display}   (n={count})" if count is not None
                             else str(display))
                lab.setStyleSheet(f"color:{TEXT};")
                cmb = QComboBox()
                for i, g in enumerate(self._groups):
                    cmb.addItem(g["name"] or f"Class {i + 1}", i)
                cmb.addItem("Exclude", self.EXCLUDE)
                idx = cmb.findData(assign.get(key, self.EXCLUDE))
                cmb.setCurrentIndex(idx if idx >= 0 else cmb.count() - 1)
                cmb.currentIndexChanged.connect(
                    lambda _i, k=key: self._level_changed(k))
                self._grid.addWidget(lab, r, 0)
                self._grid.addWidget(cmb, r, 1)
                self._level_combos[key] = cmb
        finally:
            self._updating = False
        self._refresh_summary()

    def _assignment(self):
        out = {}
        for i, g in enumerate(self._groups):
            for key in g["levels"]:
                out[key] = i
        return out

    def _refresh_summary(self):
        counts = {key: c for key, _d, c in self._levels}
        parts = []
        for g in self._groups:
            n = sum(counts.get(k) or 0 for k in g["levels"])
            parts.append(f"{g['name'] or '(unnamed)'}: {n}")
        excluded = [d for k, d, _c in self._levels
                    if k not in self._assignment()]
        text = "   ".join(parts)
        if excluded:
            text += f"    excluded: {', '.join(str(e) for e in excluded)}"
        self.lbl_summary.setText(text)

    # ── edits ────────────────────────────────────────────────────────────────
    def _name_changed(self, idx, text):
        if self._updating or idx >= len(self._groups):
            return
        self._groups[idx]["name"] = text
        for key, cmb in self._level_combos.items():
            cmb.setItemText(idx, text or f"Class {idx + 1}")
        self._refresh_summary()
        self.changed.emit()

    def _level_changed(self, key):
        if self._updating:
            return
        cmb = self._level_combos.get(key)
        if cmb is None:
            return
        target = cmb.currentData()
        for g in self._groups:
            if key in g["levels"]:
                g["levels"].remove(key)
        if target != self.EXCLUDE and target < len(self._groups):
            self._groups[target]["levels"].append(key)
        self._refresh_summary()
        self.changed.emit()

    def _add_group(self):
        self._groups.append({"name": f"class_{len(self._groups) + 1}",
                             "levels": []})
        self._rebuild()
        self.changed.emit()

    def _remove_group(self, idx):
        if len(self._groups) <= 1 or idx >= len(self._groups):
            return
        del self._groups[idx]
        self._rebuild()
        self.changed.emit()
