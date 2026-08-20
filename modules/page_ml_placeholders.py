# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Placeholder content for the Model Performance page.

Model Performance is part of the Machine Learning Analysis navigation, but
its functionality is deliberately not implemented yet. The placeholder
documents the planned architecture so the page can be developed later.
(Model Training and Model Prediction are fully implemented in their own
page modules.)
"""
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

from .ml_widgets import MUTED, MetaCard

_PERFORMANCE_SECTIONS = [
    ("Performance metrics", "Accuracy, sensitivity, specificity, precision, "
                            "F1 and AUC for deployed and candidate models."),
    ("Confusion matrix", "Binary and per-class confusion matrices."),
    ("ROC / PR curves", "Threshold-free performance visualisation."),
    ("Class-specific performance", "Per-region precision/recall for the "
                                   "multiclass stage."),
    ("Threshold analysis", "Operating-point selection for the binary "
                           "decision threshold."),
    ("Validation dataset", "Which data the reported performance was "
                           "estimated on."),
]


def _fill(frame, sections, note):
    v = QVBoxLayout(frame)
    v.setContentsMargins(0, 4, 0, 0)
    v.setSpacing(8)

    banner = QLabel(note)
    banner.setStyleSheet(f"color:{MUTED};font-size:10px;")
    banner.setWordWrap(True)
    v.addWidget(banner)

    row = None
    for i, (title, desc) in enumerate(sections):
        if i % 3 == 0:
            row = QHBoxLayout()
            row.setSpacing(8)
            v.addLayout(row)
        card = MetaCard(title)
        card.set_rows([("Planned", desc)])
        card.setMinimumWidth(240)
        card.setMaximumHeight(120)
        row.addWidget(card)
    if row is not None:
        row.addStretch()
    v.addStretch()


def build_performance_page(ui):
    _fill(ui.content_ml_performance, _PERFORMANCE_SECTIONS,
          "Model performance analysis is not implemented yet. "
          "Cross-validated performance for a training run is shown on "
          "Model Training → Evaluate; deployed-model metrics appear on "
          "Model Prediction → Predict. This page will provide the full "
          "evaluation suite across models.")
