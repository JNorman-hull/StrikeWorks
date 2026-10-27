# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""About StrikeWorks - one dialog, shown from both Simple mode's About
button and the full app's (settings panel > About).

Package versions are read from the running install (importlib.metadata,
falling back to an already-imported module's __version__) rather than
typed in, so they stay right as dependencies are upgraded; the citations
themselves are the ones each project asks users to cite.
"""
import platform
import sys
from importlib import metadata

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from .layout import centred, scroll_area
from .startup import logo_label
from .theme import ACCENT, MUTED, style

_COLUMN_WIDTH = 760
PYDRACULA_URL = "https://github.com/Wanderson-Magalhaes/Modern_GUI_PyDracula_PySide6_or_PyQt6"

DESCRIPTION = ("A data extraction, validation, processing and model "
               "development tool for underwater passive sensor devices used "
               "in fish passage science.")

CREDITS = [
    ("Development", "Josh Norman, University of Hull",
     "J.Norman2@hull.ac.uk"),
    ("Sensor implementation",
     "Jeffrey Tuhtan, Tallinn University of Technology (TalTech)",
     "jeffrey.tuhtan@taltech.ee"),
]

# (display name, distribution name, module name, citation, link)
PACKAGES = [
    ("PySide6 (Qt for Python)", "PySide6", "PySide6",
     "The Qt Company. Qt for Python.", "https://doc.qt.io/qtforpython-6/"),
    ("pyqtgraph", "pyqtgraph", "pyqtgraph",
     "Campagnola, L. et al. PyQtGraph: Scientific Graphics and GUI Library "
     "for Python.", "https://www.pyqtgraph.org"),
    ("NumPy", "numpy", "numpy",
     "Harris, C.R. et al. (2020) Array programming with NumPy. Nature 585, "
     "357–362.", "https://doi.org/10.1038/s41586-020-2649-2"),
    ("pandas", "pandas", "pandas",
     "McKinney, W. (2010) Data structures for statistical computing in "
     "Python. Proc. 9th Python in Science Conference, 56–61.",
     "https://doi.org/10.25080/Majora-92bf1922-00a"),
    ("SciPy", "scipy", "scipy",
     "Virtanen, P. et al. (2020) SciPy 1.0: fundamental algorithms for "
     "scientific computing in Python. Nature Methods 17, 261–272.",
     "https://doi.org/10.1038/s41592-019-0686-2"),
    ("scikit-learn", "scikit-learn", "sklearn",
     "Pedregosa, F. et al. (2011) Scikit-learn: Machine Learning in Python. "
     "Journal of Machine Learning Research 12, 2825–2830.",
     "https://jmlr.org/papers/v12/pedregosa11a.html"),
    ("sktime", "sktime", "sktime",
     "Löning, M. et al. (2019) sktime: A Unified Interface for Machine "
     "Learning with Time Series. arXiv:1909.07872.",
     "https://doi.org/10.48550/arXiv.1909.07872"),
    ("Numba", "numba", "numba",
     "Lam, S.K., Pitrou, A. & Seibert, S. (2015) Numba: a LLVM-based Python "
     "JIT compiler. Proc. 2nd Workshop on the LLVM Compiler Infrastructure "
     "in HPC.", "https://doi.org/10.1145/2833157.2833162"),
    ("joblib", "joblib", "joblib",
     "Joblib Development Team. Joblib: running Python functions as "
     "pipeline jobs.", "https://joblib.readthedocs.io"),
    ("Matplotlib", "matplotlib", "matplotlib",
     "Hunter, J.D. (2007) Matplotlib: A 2D graphics environment. Computing "
     "in Science & Engineering 9(3), 90–95.",
     "https://doi.org/10.1109/MCSE.2007.55"),
    ("OpenCV", "opencv-python", "cv2",
     "Bradski, G. (2000) The OpenCV Library. Dr. Dobb's Journal of Software "
     "Tools.", "https://opencv.org"),
    ("LosslessCut (video review)", None, None,
     "Finstad, M. LosslessCut.", "https://github.com/mifi/lossless-cut"),
]


def _version(dist, module):
    if dist:
        try:
            return metadata.version(dist)
        except metadata.PackageNotFoundError:
            pass
    mod = sys.modules.get(module) if module else None
    return getattr(mod, "__version__", "") if mod is not None else ""


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About StrikeWorks")
        self.resize(820, 760)
        self.setWindowModality(Qt.WindowModality.WindowModal)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = scroll_area()
        outer.addWidget(scroll)

        # everything sits in one centred column (capped width), so nothing
        # stretches edge to edge when the dialog is made wide
        body = QWidget()
        scroll.setWidget(body)
        body_v = QVBoxLayout(body)
        body_v.setContentsMargins(20, 18, 20, 10)
        column = QWidget()
        v = QVBoxLayout(column)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        body_v.addWidget(centred(column, max_width=_COLUMN_WIDTH))

        centre = Qt.AlignmentFlag.AlignHCenter
        title = QLabel("StrikeWorks")
        style(title, role="app-title")
        title.setAlignment(centre)
        v.addWidget(title)
        desc = QLabel(DESCRIPTION)
        desc.setWordWrap(True)
        style(desc, role="lead")
        desc.setAlignment(centre)
        v.addWidget(desc)

        # the StrikeWorks | University of Hull logo
        logo = logo_label(width=300)
        if logo is not None:
            v.addWidget(logo)
        copyright_ = QLabel("Copyright © University of Hull (2026)")
        style(copyright_, role="strong")
        copyright_.setAlignment(centre)
        v.addWidget(copyright_)

        v.addWidget(self._heading("Credits"))
        credits = "".join(
            f"<p style='margin:0 0 6px 0;'><span style='color:{MUTED};'>{role}"
            f"</span><br/>{who} – <a style='color:{ACCENT};' "
            f"href='mailto:{email}'>{email}</a></p>"
            for role, who, email in CREDITS)
        v.addWidget(self._rich(credits, centre=True))

        v.addWidget(self._heading(
            f"Built in Python {platform.python_version()}"))
        items = [
            f"<li>Python {platform.python_version()} – Python Software "
            f"Foundation. <a style='color:{ACCENT};' href='https://www.python.org'>"
            "python.org</a></li>"]
        for name, dist, module, cite, link in PACKAGES:
            ver = _version(dist, module)
            items.append(
                f"<li>{name}{' ' + ver if ver else ''} – {cite} "
                f"<a style='color:{ACCENT};' href='{link}'>{link}</a></li>")
        v.addWidget(self._rich(
            "<ul style='margin-left:-18px;'>" + "".join(items) + "</ul>"))

        v.addWidget(self._heading("Theme"))
        v.addWidget(self._rich(
            "Interface theme modified from PyDracula by Wanderson M. "
            f"Pimenta (MIT licence) – <a style='color:{ACCENT};' "
            f"href='{PYDRACULA_URL}'>{PYDRACULA_URL}</a>", centre=True))
        v.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(20, 6, 20, 12)
        btn_row.addStretch()
        btn_close = QPushButton("Close")
        btn_close.setAutoDefault(False)
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        outer.addLayout(btn_row)

    @staticmethod
    def _heading(text):
        lab = QLabel(text)
        style(lab, role="section-title")
        lab.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        return lab

    @staticmethod
    def _rich(html, centre=False):
        lab = QLabel(html)
        lab.setWordWrap(True)
        if centre:
            lab.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lab.setTextFormat(Qt.TextFormat.RichText)
        lab.setOpenExternalLinks(True)
        lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        style(lab, role="panel")
        return lab
