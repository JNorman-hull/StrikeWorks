# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Model deployment - the explicit accept / train-final / deploy workflow:
the Final model and Deploy columns of the Train tab's Model box, the
model's information card under Deploy.

Cross-validation estimates performance; the final deployment model is a
separate, deliberate step that retrains on all available training data.
Deployment writes the model + metrics into the models folder under the
binary*/multiclass* naming that Model Prediction auto-discovers, together
with a fully self-describing package folder (model card, config, channels,
CV predictions).
"""
import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout,
    QWidget,
)

from . import settings
from .cards import MetaCard, Spinner
from .theme import muted_label, style

# every button in the Model box: one size, one look
ACTION_W, ACTION_H = 150, 32
FIELD_W = 90                     # number fields and the version box


def action_button(text, tooltip=""):
    """A Model-box button (Train model, Console, Evaluate results, Train
    final model, Deploy model)."""
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


class DeploymentPanel(QWidget):
    """The Final model and Deploy columns, bound to `state`."""

    def __init__(self, state, main_window):
        super().__init__()
        self.state = state
        self.main_window = main_window
        self.models_dir = self._default_models_dir()

        self._build()
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

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self):
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(24)

        # ── final model: retrain on all the data ───────────────────────────
        # what each step will do (and the models folder) are the buttons'
        # tooltips
        final, fv = column("Final model")
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.btn_final = action_button("Train final model")
        self.btn_final.setEnabled(False)
        self.btn_final.clicked.connect(self._train_final)
        btn_row.addWidget(self.btn_final)
        self.spinner = Spinner(size=24)
        self.spinner.setVisible(False)
        btn_row.addWidget(self.spinner)
        btn_row.addStretch()
        fv.addLayout(btn_row)
        self.lbl_final_status = QLabel("")
        self.lbl_final_status.setWordWrap(True)
        style(self.lbl_final_status, role="muted")
        fv.addWidget(self.lbl_final_status)
        self.card_final = MetaCard("Deployment model")
        fv.addWidget(self.card_final)
        fv.addStretch()
        row.addWidget(final, stretch=1)

        # ── deploy: version, Deploy model, the model card ──────────────────
        deploy, dv = column("Deploy")
        ver_row = QHBoxLayout()
        ver_row.setSpacing(8)
        ver_row.addWidget(muted_label("Model version"))
        self.ed_version = QLineEdit()
        self.ed_version.setFixedWidth(FIELD_W)
        self.ed_version.setToolTip("major_minor, e.g. 1_2 → binary1_2.joblib")
        ver_row.addWidget(self.ed_version)
        ver_row.addStretch()
        dv.addLayout(ver_row)
        self.btn_deploy = action_button("Deploy model")
        self.btn_deploy.setEnabled(False)
        self.btn_deploy.clicked.connect(self._deploy)
        dv.addWidget(self.btn_deploy)
        self.lbl_deploy_status = QLabel("")
        self.lbl_deploy_status.setWordWrap(True)
        style(self.lbl_deploy_status, role="muted")
        self.lbl_deploy_status.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        dv.addWidget(self.lbl_deploy_status)
        # the model card / provenance
        self.card_prov = MetaCard("Model information")
        dv.addWidget(self.card_prov)
        dv.addStretch()
        row.addWidget(deploy, stretch=1)

    # ── state wiring ─────────────────────────────────────────────────────────
    def _connect_state(self):
        s = self.state
        s.cv_finished.connect(self._refresh)
        s.cv_started.connect(self._refresh)
        s.dataset_changed.connect(self._refresh)
        s.final_started.connect(self._on_final_started)
        s.final_finished.connect(self._on_final_finished)
        s.final_failed.connect(self._on_final_failed)

    # ── refresh ──────────────────────────────────────────────────────────────
    def _refresh(self):
        s = self.state
        self.btn_final.setEnabled(s.cv_done and not s.running)
        self.btn_deploy.setEnabled(s.final_done and not s.running)
        self.btn_deploy.setToolTip(
            f"Deploy the final model(s) to {self.models_dir}")

        if not s.cv_done:
            self.btn_final.setToolTip(
                "Train a model first, review the results (Evaluate), then "
                "accept them here by training the final models.")
            self.card_final.set_rows([])
            self.card_prov.set_rows([])
            self.lbl_final_status.setText("")
            self.lbl_deploy_status.setText("")
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
        self._fill_final_card()

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
        self.card_prov.set_rows(rows)

    # ── final model ──────────────────────────────────────────────────────────
    def _train_final(self):
        self.state.run_final()

    def _on_final_started(self):
        self.btn_final.setEnabled(False)
        self.btn_final.setText("Training…")
        self.spinner.start()
        style(self.lbl_final_status, tone="accent")
        self.lbl_final_status.setText(
            "Training the final deployment model on all training data… "
            "(progress in the Console)")

    def _fill_final_card(self):
        """Deployment-model details, read from the run's final-model
        artefacts so the card reflects what will actually be deployed."""
        s = self.state
        if not s.final_done or s.out_dir is None:
            self.card_final.set_rows([])
            return

        rows = []
        for kind in ("binary", "multiclass"):
            d = s.out_dir / kind
            model_file = d / "final_model_for_deployment.joblib"
            if not model_file.exists():
                continue
            cfg = {}
            cfg_path = d / "model_config.json"
            if cfg_path.exists():
                try:
                    with open(cfg_path, encoding="utf-8") as f:
                        cfg = json.load(f)
                except (OSError, ValueError):
                    cfg = {}
            metrics = (s.model_results(kind) or {}).get("metrics", {})
            perf = metrics.get("out_of_fold_performance", {})

            title = "Binary" if kind == "binary" else "Multiclass"
            rows.append((f"{title} model", metrics.get("model")))
            rows.append((f"{title} observations",
                         cfg.get("n_training_observations")
                         or metrics.get("n_samples")))
            if cfg.get("class_names") and kind == "multiclass":
                rows.append((f"{title} classes", cfg["class_names"]))
            if "optimal_threshold" in perf:
                rows.append((f"{title} threshold",
                             f"{perf['optimal_threshold']:.4f}"))
            size_mb = model_file.stat().st_size / (1024 * 1024)
            rows.append((f"{title} file",
                         f"{kind}<version>.joblib  ({size_mb:.1f} MB)"))

        bin_cfg_metrics = (s.model_results("binary") or {}).get("metrics", {})
        rows += [
            ("Channels", bin_cfg_metrics.get("n_channels")),
            ("Sequence length", bin_cfg_metrics.get("max_sequence_length")),
            ("Run directory", str(s.out_dir)),
        ]
        self.card_final.set_rows(rows)

    def _on_final_finished(self):
        s = self.state
        self.spinner.stop()
        self.btn_final.setText("Train final model")
        self.btn_final.setEnabled(True)
        self.btn_deploy.setEnabled(True)
        mc_m = (s.model_results("multiclass") or {}).get("metrics", {})
        style(self.lbl_final_status, tone="ok")
        self.lbl_final_status.setText(
            "Final models trained" if mc_m else "Final model trained")
        self._fill_final_card()
        s.status.emit("Final deployment model(s) trained.", 5000)

    def _on_final_failed(self, msg):
        self.spinner.stop()
        self.btn_final.setText("Train final model")
        self.btn_final.setEnabled(self.state.cv_done)
        style(self.lbl_final_status, tone="bad")
        first = msg.strip().splitlines()[-1] if msg.strip() else "Unknown error"
        self.lbl_final_status.setText(f"✗ Final training failed: {first}")
        dlg = QMessageBox(self.main_window)
        dlg.setWindowTitle("Final model error")
        dlg.setIcon(QMessageBox.Icon.Critical)
        dlg.setText(f"Training the final model failed.\n\n{first}")
        dlg.setDetailedText(msg)
        dlg.exec()

    # ── deployment ───────────────────────────────────────────────────────────
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
        style(self.lbl_deploy_status, tone="ok")
        self.lbl_deploy_status.setText(
            f"Deployed {names}\n"
            f"Package: {pkg}\n"
            "Model Prediction will discover them from the models folder.")
        s.status.emit(f"Pipeline deployed: {names}", 6000)
        QMessageBox.information(
            self.main_window, "Pipeline deployed",
            f"Deployed {names} to\n{self.models_dir}\n\n"
            f"Full package (model card, config, CV predictions):\n{pkg}")
