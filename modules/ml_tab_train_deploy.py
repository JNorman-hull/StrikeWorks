# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Deploy tab - the explicit accept / train-final / deploy workflow.

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
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from . import settings
from .ml_widgets import ACCENT, BAD, MUTED, OK, MetaCard, Spinner, Section, apply_section_defaults


class DeployTab:
    """Builds the Deploy tab UI into `frame`, bound to `state`."""

    def __init__(self, frame, state, window):
        self.state = state
        self.window = window
        self.models_dir = self._default_models_dir()

        self._build(frame)
        self._connect_state()
        self._refresh()

    def _default_models_dir(self):
        """`<session library>/StrikeWorks_user_output/models/` when a
        session library is selected, else the original app-root
        `models/` folder - "Change models folder…" below still points
        this anywhere; deploying was never meant to be library-locked,
        only its *default* destination follows the session library."""
        session_state = getattr(self.window, "session_state", None)
        out = session_state.output_dir() if session_state is not None else None
        return (out / "models") if out is not None else settings.get_models_dir()

    # ── layout ───────────────────────────────────────────────────────────────
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

        # ── Model deployment: final model + deploy, merged ──────────────────
        grp_deploy = Section("Model deployment")
        dv = QVBoxLayout(grp_deploy)
        dv.setSpacing(8)

        self.lbl_flow_status = QLabel("")
        self.lbl_flow_status.setWordWrap(True)
        self.lbl_flow_status.setStyleSheet(f"color:{MUTED};")
        dv.addWidget(self.lbl_flow_status)

        run_row = QHBoxLayout()
        self.btn_final = QPushButton("Train final model")
        self.btn_final.setMinimumHeight(36)
        self.btn_final.setEnabled(False)
        self.btn_final.clicked.connect(self._train_final)
        self.spinner = Spinner(size=24)
        self.spinner.setVisible(False)
        run_row.addWidget(self.btn_final, stretch=1)
        run_row.addWidget(self.spinner)
        dv.addLayout(run_row)
        self.lbl_final_status = QLabel("")
        self.lbl_final_status.setWordWrap(True)
        self.lbl_final_status.setStyleSheet(f"color:{MUTED};")
        dv.addWidget(self.lbl_final_status)
        self.card_final = MetaCard("Deployment model")
        dv.addWidget(self.card_final)

        ver_row = QHBoxLayout()
        lab_v = QLabel("Model version")
        lab_v.setStyleSheet(f"color:{MUTED};")
        self.ed_version = QLineEdit()
        self.ed_version.setFixedWidth(90)
        self.ed_version.setToolTip("major_minor, e.g. 1_2 → binary1_2.joblib")
        ver_row.addWidget(lab_v)
        ver_row.addWidget(self.ed_version)
        ver_row.addStretch()
        dv.addLayout(ver_row)

        dir_row = QHBoxLayout()
        self.lbl_models_dir = QLabel("")
        self.lbl_models_dir.setStyleSheet(f"color:{MUTED};")
        self.lbl_models_dir.setWordWrap(True)
        btn_dir = QPushButton("Change…")
        btn_dir.setFixedWidth(80)
        btn_dir.clicked.connect(self._change_models_dir)
        dir_row.addWidget(self.lbl_models_dir, stretch=1)
        dir_row.addWidget(btn_dir)
        dv.addLayout(dir_row)

        self.btn_deploy = QPushButton("Deploy model")
        self.btn_deploy.setMinimumHeight(36)
        self.btn_deploy.setEnabled(False)
        self.btn_deploy.setStyleSheet(
            f"QPushButton{{background-color:{ACCENT};color:#ffffff;"
            "border-radius:5px;font-weight:bold;}"
            "QPushButton:disabled{background-color:#3a4150;color:#8a95aa;}")
        self.btn_deploy.clicked.connect(self._deploy)
        dv.addWidget(self.btn_deploy)
        self.lbl_deploy_status = QLabel("")
        self.lbl_deploy_status.setWordWrap(True)
        self.lbl_deploy_status.setStyleSheet(f"color:{MUTED};")
        self.lbl_deploy_status.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        dv.addWidget(self.lbl_deploy_status)
        v.addWidget(grp_deploy)

        # ── model card / provenance ──────────────────────────────────────────
        grp_card = Section("Model information")
        cv = QVBoxLayout(grp_card)
        self.card_prov = MetaCard("")
        cv.addWidget(self.card_prov)
        v.addWidget(grp_card)
        v.addStretch()

        apply_section_defaults(frame)

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
        self.lbl_models_dir.setText(f"Models folder: {self.models_dir}")

        if not s.cv_done:
            self.lbl_flow_status.setText(
                "Train a model first (Train tab), review the results "
                "(Evaluate tab), then accept them here by training the "
                "final models.")
            self.card_final.set_rows([])
            self.card_prov.set_rows([])
            self.lbl_final_status.setText("")
            self.lbl_deploy_status.setText("")
            return

        bin_m = (s.model_results("binary") or {}).get("metrics", {})
        mc_m = (s.model_results("multiclass") or {}).get("metrics", {})
        n = bin_m.get("n_samples", "?")
        if mc_m:
            self.lbl_flow_status.setText(
                f"Cross-validation complete for both pipeline stages. The "
                f"final binary model will be trained on all {n} "
                f"observations and the final region model on all "
                f"{mc_m.get('n_samples', '?')} ground-truth strikes.")
        else:
            self.lbl_flow_status.setText(
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
            ("Negative class", card["negative_class"]),
            ("Included records", card["include_values"]),
            ("Input channels", len(card["input_channels"])
             if isinstance(card["input_channels"], list) else "—"),
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
        self.lbl_final_status.setStyleSheet(f"color:{ACCENT};")
        self.lbl_final_status.setText(
            "Training the final deployment model on all training data… "
            "(progress in the Cross-validate console)")

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
                except Exception:
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
        self.btn_final.setText("TRAIN FINAL MODEL")
        self.btn_final.setEnabled(True)
        self.btn_deploy.setEnabled(True)
        mc_m = (s.model_results("multiclass") or {}).get("metrics", {})
        self.lbl_final_status.setStyleSheet(f"color:{OK};")
        self.lbl_final_status.setText(
            "Final models trained" if mc_m else "Final model trained")
        self._fill_final_card()
        s.status.emit("Final deployment model(s) trained.", 5000)

    def _on_final_failed(self, msg):
        self.spinner.stop()
        self.btn_final.setText("TRAIN FINAL MODEL")
        self.btn_final.setEnabled(self.state.cv_done)
        self.lbl_final_status.setStyleSheet(f"color:{BAD};")
        first = msg.strip().splitlines()[-1] if msg.strip() else "Unknown error"
        self.lbl_final_status.setText(f"✗ Final training failed: {first}")
        dlg = QMessageBox(self.window)
        dlg.setWindowTitle("Final model error")
        dlg.setIcon(QMessageBox.Icon.Critical)
        dlg.setText(f"Training the final model failed.\n\n{first}")
        dlg.setDetailedText(msg)
        dlg.exec()

    # ── deployment ───────────────────────────────────────────────────────────
    def _change_models_dir(self):
        path = QFileDialog.getExistingDirectory(
            self.window, "Select models folder", str(self.models_dir))
        if path:
            self.models_dir = Path(path)
            self.ed_version.setText(
                self.state.suggest_version(self.models_dir))
            self._refresh()

    def _deploy(self):
        s = self.state
        version = self.ed_version.text().strip()
        if not version:
            QMessageBox.warning(self.window, "Deploy model",
                                "Enter a model version (e.g. 1_2).")
            return
        try:
            pkg, deployed = s.deploy(self.models_dir, version)
        except Exception as e:
            QMessageBox.critical(self.window, "Deploy model", str(e))
            return
        names = ", ".join(p.name for p in deployed)
        self.lbl_deploy_status.setStyleSheet(f"color:{OK};")
        self.lbl_deploy_status.setText(
            f"Deployed {names}\n"
            f"Package: {pkg}\n"
            "Model Prediction will discover them from the models folder.")
        s.status.emit(f"Pipeline deployed: {names}", 6000)
        QMessageBox.information(
            self.window, "Pipeline deployed",
            f"Deployed {names} to\n{self.models_dir}\n\n"
            f"Full package (model card, config, CV predictions):\n{pkg}")
