# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Study design tab - structure only.

The helpers that will plan a deployment before any sensor is wetted:
how many passages a treatment needs, how sensors and runs are allocated
across the treatments, and what the resulting schedule looks like. None of
them compute anything yet; the panels are here so the shape of the page is
agreed before the maths is written, and so each tool has an obvious home.

Each panel below names its inputs and what it will produce. Building one
means filling in its Section - the tab, its place in the workflow and the
page around it do not change.
"""
from PySide6.QtWidgets import (
    QLabel, QScrollArea, QVBoxLayout, QWidget,
)

from .ml_widgets import MUTED, TEXT, WARN, Section, apply_section_defaults

# title -> (what it does, what it needs, what it produces)
_TOOLS = [
    ("Sample size and power",
     "How many passages per treatment are needed to detect a strike-rate "
     "difference of a given size.",
     "Expected strike rate, the difference worth detecting, significance "
     "level and power.",
     "Passages per treatment, and the total deployment count that implies."),
    ("Treatment allocation",
     "Spread sensors and runs across treatments so no treatment is "
     "confounded with a sensor, a time of day or an operating point.",
     "Treatments, available sensors, runs per day.",
     "An allocation table, one row per planned deployment."),
    ("Operating points",
     "The pump/turbine conditions each treatment is run at, so the "
     "deployment metadata on the Process page is filled from a plan rather "
     "than typed per file.",
     "Head, flow, RPM and best-efficiency point for each condition.",
     "A named set of operating points reusable across deployments."),
    ("Deployment schedule",
     "The plan as a running order, with the sensor index it should produce.",
     "The allocation table and the site's daily window.",
     "A schedule to work from, and the expected file count to check "
     "processing against."),
]


class StudyTab:
    """Builds the Study design placeholder into `frame`."""

    def __init__(self, frame, window, status=None):
        self.window = window
        self._status = status
        self._build(frame)

    def _build(self, frame):
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        outer.addWidget(scroll)
        body = QWidget()
        body.setStyleSheet("background:transparent;")
        scroll.setWidget(body)
        v = QVBoxLayout(body)
        v.setContentsMargins(4, 6, 4, 6)
        v.setSpacing(10)

        intro = QLabel(
            "Planning tools for a study, used before any sensor is deployed. "
            "None of these are built yet - the panels below record what each "
            "one is for so the work can be picked up one tool at a time.")
        intro.setStyleSheet(f"color:{MUTED};")
        intro.setWordWrap(True)
        v.addWidget(intro)

        for title, purpose, inputs, outputs in _TOOLS:
            v.addWidget(self._panel(title, purpose, inputs, outputs))

        v.addStretch()
        apply_section_defaults(frame)

    @staticmethod
    def _panel(title, purpose, inputs, outputs):
        grp = Section(title)
        gv = QVBoxLayout(grp)
        gv.setSpacing(4)

        lab = QLabel(purpose)
        lab.setStyleSheet(f"color:{TEXT};")
        lab.setWordWrap(True)
        gv.addWidget(lab)

        for name, text in (("Needs", inputs), ("Produces", outputs)):
            row = QLabel(f"<b>{name}:</b> {text}")
            row.setStyleSheet(f"color:{MUTED};")
            row.setWordWrap(True)
            gv.addWidget(row)

        todo = QLabel("Not implemented.")
        todo.setStyleSheet(f"color:{WARN};font-size:10px;")
        gv.addWidget(todo)
        return grp
