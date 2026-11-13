"""Home: the session library, New session, and a summary of what has been
done in the library, read from its own files (sensor index,
model_features.csv, StrikeWorks_user_output/).
"""


from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QInputDialog, QLabel, QMessageBox, QPushButton,
    QVBoxLayout, QWidget,
)

from . import deployment_index as di
from . import raw_layout, settings
from .cards import MetaCard
from .layout import on_show, Page, Section
from .library_widgets import library_picker, show_library_path
from .theme import style
from .session_state import OUTPUT_DIR_NAME
from .startup import icon_pixmap

_CARD_WIDTH = 360
# the app icon beside the session box
HOME_ICON_PX = 320


class HomePage(Page):
    """Home: the session library and its summary."""

    MARGIN = 0    # its own 24 px border (_build)

    def __init__(self, main_window, session_state):
        super().__init__(main_window)
        self.session_state = session_state

        self._build(self)
        self._connect()
        self._refresh_library_combo()
        # refreshed whenever Home is shown: other pages change the library
        # while Home is hidden
        on_show(self, self._refresh_summary)

    # layout
    def _build(self, frame):
        # no background image; the logo is added below
        style(frame, role="bare")
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(0)

        outer.addStretch(1)
        content_row = QHBoxLayout()
        content_row.setSpacing(24)
        content_row.addStretch(1)
        content_row.addWidget(self._build_card_column(), stretch=0)
        content_row.addWidget(self._build_logo(), stretch=0)
        content_row.addStretch(1)
        outer.addLayout(content_row)
        outer.addStretch(1)


    def _build_logo(self):
        lab = QLabel()
        pix = icon_pixmap(HOME_ICON_PX)
        if not pix.isNull():
            lab.setPixmap(pix)
        lab.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        return lab

    def _build_card_column(self):
        """The session-library card + resume summary + mode buttons,
        bounded to a fixed width - a "login box" rather than content
        stretched across the whole page."""
        col = QWidget()
        col.setObjectName("homeSessionBox")
        col.setMaximumWidth(_CARD_WIDTH)
        v = QVBoxLayout(col)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(12)

        grp = Section("Session library")
        gv = QVBoxLayout(grp)
        gv.setSpacing(8)

        self.cmb_library = QComboBox()
        # the folder is the tooltip; right-click opens it
        library_picker(self.cmb_library)
        gv.addWidget(self.cmb_library)

        action_row = QHBoxLayout()
        self.btn_new_library = QPushButton("New library")
        self.btn_new_library.setFlat(True)
        style(self.btn_new_library, role="link")
        action_row.addWidget(self.btn_new_library)
        action_row.addStretch()
        self.btn_new_session = QPushButton("New session")
        self.btn_new_session.setFlat(True)
        style(self.btn_new_session, role="link")
        action_row.addWidget(self.btn_new_session)
        gv.addLayout(action_row)
        v.addWidget(grp)

        grp_sum = Section("Library status")
        sv = QVBoxLayout(grp_sum)
        self.card_status = MetaCard("Nothing selected yet")
        sv.addWidget(self.card_status)
        v.addWidget(grp_sum)

        v.addStretch()
        return col

    def _connect(self):
        self.cmb_library.currentIndexChanged.connect(self._on_combo_changed)
        self.btn_new_library.clicked.connect(lambda: self._new_library())
        self.btn_new_session.clicked.connect(lambda: self._new_session())
        self.session_state.library_changed.connect(self._on_session_library_changed)

    # library combo
    def _refresh_library_combo(self, select=None):
        self.cmb_library.blockSignals(True)
        self.cmb_library.clear()
        libs = settings.list_libraries()
        for lib in libs:
            self.cmb_library.addItem(lib.name, str(lib))

        want = str(select) if select else (
            str(self.session_state.library) if self.session_state.library else None)
        idx = self.cmb_library.findData(want) if want else -1
        if idx >= 0:
            self.cmb_library.setCurrentIndex(idx)
        self.cmb_library.blockSignals(False)

        # signals were blocked, so push the combo's choice (index 0 when
        # `want` wasn't found) into the session explicitly
        current = self.cmb_library.currentData()
        if str(self.session_state.library or "") != str(current or ""):
            self.session_state.set_library(current)

    def _new_library(self, parent=None):
        parent = parent or self.main_window
        name, ok = QInputDialog.getText(
            parent, "New library", "Library name:")
        name = name.strip()
        if not ok or not name:
            return
        lib_dir = settings.get_libraries_dir()
        new_root = lib_dir / name
        if new_root.exists():
            QMessageBox.warning(
                parent, "Already exists",
                f"A library named “{name}” already exists.")
            return
        try:
            new_root.mkdir(parents=True)
        except Exception as e:
            QMessageBox.critical(parent, "Could not create library", str(e))
            return
        self._refresh_library_combo(select=str(new_root))
        self.status.emit(f"Created library: {name}", 4000)

    def _on_combo_changed(self, _idx):
        path = self.cmb_library.currentData()
        self.session_state.set_library(path)

    def _on_session_library_changed(self, path):
        idx = self.cmb_library.findData(str(path)) if path else -1
        if idx != self.cmb_library.currentIndex():
            self.cmb_library.blockSignals(True)
            self.cmb_library.setCurrentIndex(idx)
            self.cmb_library.blockSignals(False)
        show_library_path(self.cmb_library)
        if self.isVisible():
            self._refresh_summary()
        else:
            # not on screen: on_show refreshes it next time Home opens
            self.card_status.set_title(path.name if path else "Nothing selected yet")
            self.card_status.set_rows([])
        # the one "Library: X" message for a session change (each
        # LibrarySelector stays quiet while syncing)
        if path is not None:
            self.status.emit(f"Library: {path.name}", 4000)

    # new session
    def _new_session(self, parent=None):
        parent = parent or self.main_window
        reply = QMessageBox.warning(
            parent, "New session",
            "Starting a new session clears the selected library here and "
            "on every page that follows it. Anything already saved to "
            "disk (processed files, annotations, deployed models, "
            "reports) is untouched - this only resets which library the "
            "app is currently pointed at.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.session_state.new_session()
        self.status.emit("New session started.", 4000)

    # resume summary
    def _refresh_summary(self):
        title, rows = library_status_rows(
            self.session_state.library, self.session_state)
        self.card_status.set_title(title)
        self.card_status.set_rows(rows)


# shared "library status" summary
def library_status_rows(root, session_state):
    """(title, rows) for a MetaCard: Deployments / Treatments / Sensors
    indexed / Dataset built / StrikeWorks_user_output. Used by Home's
    summary and the deployment editor's Library status card."""
    if root is None:
        return "Nothing selected yet", []
    rows = []

    # the index read once, not once per question asked of it
    index_df = di.read_index(root)
    deployments = di.deployments(root, df=index_df)
    treatments = di.treatments(root, df=index_df)
    rows.append(("Deployments", len(deployments) or "None recorded"))
    rows.append(("Treatments", len(treatments) or "None recorded"))

    if index_df is not None:
        sensors = di.sensor_rows(index_df)
        n = len(sensors)
        bad = 0
        if di.BAD_SENS_COL in sensors.columns:
            bad = int((sensors[di.BAD_SENS_COL].astype(str).str.strip()
                      .str.upper() == "Y").sum())
        rows.append(("Sensors indexed",
                    f"{n} ({bad} flagged bad)" if bad else n))
    else:
        rows.append(("Sensors indexed", "Not processed yet"))

    dataset_path = root / raw_layout.DATASET_REL
    if dataset_path.exists():
        try:
            # a line count, not a pandas parse - this file can be hundreds
            # of MB, and this summary is shown every time Home/Deploy opens
            n_lines = 0
            with open(dataset_path, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    n_lines += chunk.count(b"\n")
            rows.append(("Dataset built", f"Yes ({max(0, n_lines - 1)} rows)"))
        except OSError:
            rows.append(("Dataset built", "Yes"))
    else:
        rows.append(("Dataset built", "Not yet"))

    out_dir = session_state.output_dir(create=False)
    if out_dir is not None and out_dir.exists():
        n_items = sum(1 for _ in out_dir.iterdir())
        rows.append((OUTPUT_DIR_NAME, f"{n_items} item(s)"))
    else:
        rows.append((OUTPUT_DIR_NAME, "Nothing generated yet"))

    return root.name, rows
