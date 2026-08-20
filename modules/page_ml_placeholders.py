# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Placeholder content for the Model Training and Model Performance pages.

These pages are part of the Machine Learning Analysis navigation now, but
their functionality is deliberately not implemented yet. The placeholders
document the planned architecture so the pages can be developed later and
eventually feed the deployed models used by Model Prediction.
"""
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

from .ml_widgets import MUTED, MetaCard

_TRAINING_SECTIONS = [
    ("Training dataset", "Select a curated, annotated sensor dataset "
                         "produced by Sensor Processing."),
    ("Features & channels", "Choose the sensor channels and windowing "
                            "supplied to the model."),
    ("Model configuration", "Classifier setup: binary strike detection and "
                            "optional pump-region multiclass stage."),
    ("Training & validation", "Cross-validated training with held-out "
                              "performance estimation."),
    ("Model saving & versioning", "Save versioned model + performance "
                                  "metrics JSON for deployment."),
]

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


def build_training_page(ui):
    _fill(ui.content_ml_training, _TRAINING_SECTIONS,
          "Model training is not implemented yet. This page will train new "
          "blade-strike models from curated datasets and publish them, with "
          "their performance metrics, for use in Model Prediction.")


def build_performance_page(ui):
    _fill(ui.content_ml_performance, _PERFORMANCE_SECTIONS,
          "Model performance analysis is not implemented yet. Deployed-model "
          "metrics are currently shown on the Model Prediction → Predict tab; "
          "this page will provide the full evaluation suite.")
