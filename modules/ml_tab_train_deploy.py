"""Train final model, model version, Deploy model and the Model
information window, in the Train tab's Model box.

The final model is retrained on all training data once the user has
reviewed cross-validation. Deploying writes the model and metrics into the
models folder (binary*/multiclass*, which Model prediction picks up) with a
package folder (model card, config, channels, CV predictions), then opens
the folder.
"""
from pathlib import Path

from PySide6.QtCore import QObject
from PySide6.QtWidgets import (
    QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from . import settings, win_utils
from .cards import MetaCard
from .layout import ToolWindow
from .theme import muted_label, style

# every button in the Model box: one size, one look - wide enough for
# "(2) Evaluate performance"
ACTION_W, ACTION_H = 176, 32
FIELD_W = 90                     # number fields and the version box


def action_button(text, tooltip=""):
    """A Model-box button ((1) Train model (CV), (2) Evaluate performance,
    (3) Train final model, (4) Deploy model, Console, Model information)."""
    btn = QPushButton(text)
    btn.setFixedSize(ACTION_W, ACTION_H)
    btn.setToolTip(tooltip)
    return btn


def column(heading):
    """(widget, its QVBoxLayout) - one column of the Model box under a
    muted heading."""
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(8)
    v.addWidget(muted_label(heading))
    return w, v


class ModelInfoWindow(ToolWindow):
    """The run's model card. Non-modal; hides with its page."""

    def __init__(self, page, owner):
        # (the page, without a window - the tests: never parentless)
        super().__init__(owner if owner is not None else page, page)
        self.page = page
        self.setWindowTitle("Model information")
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 12)
        self.card = MetaCard()
        v.addWidget(self.card)
        self.setMinimumWidth(460)


class DeploymentPanel(QObject):
    """(3) Train final model, the model version, (4) Deploy model and
    Model information, bound to `state`. `page` (the Train tab) lays the
    widgets out; deployment's messages go to its `status_label`."""

    def __init__(self, state, main_window, page, status_label):
        super().__init__(page)
        self.state = state
        self.main_window = main_window
        self.lbl_status = status_label
        self.models_dir = self._default_models_dir()

        self.btn_final = action_button("(3) Train final model")
        self.btn_final.setEnabled(False)
        self.btn_final.clicked.connect(self.state.run_final)
        self.ed_version = QLineEdit()
        self.ed_version.setFixedWidth(FIELD_W)
        self.ed_version.setToolTip("major_minor, e.g. 1_2 → binary1_2.joblib")
        self.btn_deploy = action_button("(4) Deploy model")
        self.btn_deploy.setEnabled(False)
        self.btn_deploy.clicked.connect(self._deploy)
        self.info = ModelInfoWindow(page, main_window)
        self.btn_info = action_button(
            "Model information", "The run's model card: data, labelling, "
            "inputs, validation and performance.")
        self.btn_info.setEnabled(False)
        self.btn_info.clicked.connect(self.info.bring_up)

        self._connect_state()
        self._refresh()
        session_state = getattr(main_window, "session_state", None)
        if session_state is not None:
            session_state.library_changed.connect(
                lambda _root: self.follow_default_models_dir())

    def follow_default_models_dir(self):
        """Re-point at the models folder after the session library or
        Settings' models folder changes."""
        new = self._default_models_dir()
        if new == self.models_dir:
            return
        self.models_dir = new
        self.ed_version.setText(self.state.suggest_version(self.models_dir))
        self._refresh()

    def _default_models_dir(self):
        """Where models are deployed: `<session library>/
        StrikeWorks_user_output/models/`, or Settings' models folder when
        no session library is selected."""
        session_state = getattr(self.main_window, "session_state", None)
        out = session_state.output_dir() if session_state is not None else None
        return (out / "models") if out is not None else settings.get_models_dir()

    # state wiring
    def _connect_state(self):
        s = self.state
        s.cv_finished.connect(self._refresh)
        s.cv_started.connect(self._refresh)
        s.dataset_changed.connect(self._refresh)
        s.final_started.connect(self._on_final_started)
        s.final_finished.connect(self._on_final_done)
        s.final_failed.connect(self._on_final_done)

    # refresh
    def _refresh(self, *_args):
        s = self.state
        self.btn_final.setEnabled(s.cv_done and not s.running)
        self.btn_deploy.setEnabled(s.final_done and not s.running)
        self.btn_info.setEnabled(s.cv_done)
        self.btn_deploy.setToolTip(
            f"Deploy the final model(s) to {self.models_dir}, then open it")

        if not s.cv_done:
            self.btn_final.setToolTip(
                "Train a model first, review the results (Evaluate), then "
                "accept them here by training the final models.")
            self.info.card.set_rows([])
            return

        bin_m = (s.model_results("binary") or {}).get("metrics", {})
        mc_m = (s.model_results("multiclass") or {}).get("metrics", {})
        n = bin_m.get("n_samples", "?")
        if mc_m:
            self.btn_final.setToolTip(
                f"Cross-validation complete for both pipeline stages. The "
                f"final binary model will be trained on all {n} "
                f"observations and the final region model on all "
                f"{mc_m.get('n_samples', '?')} ground-truth strikes.")
        else:
            self.btn_final.setToolTip(
                f"Cross-validation complete. The final binary model will "
                f"now be trained using all {n} training observations. "
                "(No multiclass stage in this run.)")
        if not self.ed_version.text():
            self.ed_version.setText(s.suggest_version(self.models_dir))
        self._fill_card()

    def _fill_card(self):
        s = self.state
        card = s.model_card()
        rows = [
            ("Pipeline", card["pipeline"]),
            ("Binary model", card["binary_model"]),
        ]
        if card["multiclass_model"]:
            rows.append(("Multiclass model", card["multiclass_model"]))
            rows.append(("Classes", card["class_names"]))
        rows += [
            ("Training dataset", Path(str(card["training_dataset"])).name),
            ("Trained", card["trained"]),
            ("Application", card["application"]),
            ("Python", card["python_version"]),
            ("Target", card["target_column"]),
            ("Null value (0)", card["negative_class"]),
            ("Included records", card["include_values"]),
            ("Input channels", len(card["input_channels"])
             if isinstance(card["input_channels"], list) else "-"),
            ("Sequence length", card["sequence_length"]),
            ("Padding", card["padding"]),
            ("Class weighting", card["class_weighting"]),
            ("CV", f"{card['n_folds']}-fold {card['cv_method']}"),
            ("Random seed", card["random_seed"]),
            ("Split", card["split_mode"]),
            ("Threshold selection", card["threshold_selection"]),
        ]
        bperf = card.get("binary_performance")
        if isinstance(bperf, dict) and bperf.get("roc_auc") is not None:
            rows.append(("Binary performance",
                         f"roc_auc = {bperf['roc_auc']:.3f}"))
        mperf = card.get("multiclass_performance")
        if isinstance(mperf, dict) \
                and mperf.get("overall_accuracy") is not None:
            rows.append(("Multiclass performance",
                         f"accuracy = {mperf['overall_accuracy']:.3f}"))
        self.info.card.set_rows(rows)

    # final model (its messages: the Train tab's status line)
    def _on_final_started(self):
        self.btn_final.setEnabled(False)
        self.btn_final.setText("Training…")
        self.btn_deploy.setEnabled(False)

    def _on_final_done(self, *_args):
        self.btn_final.setText("(3) Train final model")
        self._refresh()

    # deployment
    def _deploy(self):
        s = self.state
        version = self.ed_version.text().strip()
        if not version:
            QMessageBox.warning(self.main_window, "Deploy model",
                                "Enter a model version (e.g. 1_2).")
            return
        try:
            pkg, deployed = s.deploy(self.models_dir, version)
        except Exception as e:
            QMessageBox.critical(self.main_window, "Deploy model", str(e))
            return
        names = ", ".join(p.name for p in deployed)
        style(self.lbl_status, tone="accent")
        self.lbl_status.setText(f"Deployed {names} to {self.models_dir}")
        self.lbl_status.setToolTip(
            f"Full package (model card, config, CV predictions): {pkg}\n"
            "Model prediction finds them in the models folder.")
        s.status.emit(f"Pipeline deployed: {names}", 6000)
        win_utils.open_folder(self.models_dir)
