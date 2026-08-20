# StrikeWorks
StrikeWorks is a data extraction, validation, processing and model development tool for underwater passive sensor devices used in fish passage science.

Credit: 

Dr. Josh Norman (University of Hull)
Prof. Jeffrey Tuhtan (University of Talinn)

Copyright University of Hull (2026)

## Pages

* **Sensor Processing** — Prepare, Process, Validate & segment, Dataset creation.
* **Machine Learning Analysis** — Model performance (placeholder for now),
  **Model Training** and **Model Prediction**.

  **Model Training** ports the ML pipeline scripts (01_binary_model /
  05_multiclass_collapsed) into four tabs sharing one training state
  (`modules/ml_train_state.py`), run by `modules/train_worker.py` in a
  streaming subprocess. One run trains the full two-stage prediction
  pipeline: the binary strike model plus (when region labels exist) the
  multiclass region model for predicted strikes. Run outputs live in
  `training_runs/` (gitignored).
  * **Configure** — dataset loading/filtering, the two-stage target
    definition with both class distributions, channel selection, sequence
    preparation, hold-out/CV setup, class balancing, model parameters,
    readiness checks;
  * **Cross-validate** — stratified K-fold run over both stages with live
    fold progress and the full training console;
  * **Evaluate** — per-model results (selector): performance cards, CV
    mean±SD, ROC/PR/confusion/probability/strike-type figures, error
    analysis and stratification by strike type and treatment;
  * **Deploy** — the explicit accept step: train the final models on all
    data, then deploy the pipeline under one shared version
    (`binary<v>.joblib` + `multiclass<v>.joblib` plus a
    `BladeStrikeModel_v<v>/` package with metrics, config, channels and the
    model card) into the models folder that Model Prediction
    auto-discovers.

  **Model Prediction** applies the deployed blade-strike models to a curated
  dataset through three tabs sharing one analysis state
  (`modules/ml_state.py`):
  * **Predict** — model/dataset cards, compatibility validation, prediction
    configuration and the asynchronous run (`modules/predict_worker.py` in a
    subprocess, so the sktime/numba model stack never loads into the GUI
    process);
  * **Inspect** — per-recording prediction browser with filters, class
    probabilities, ground-truth comparison and the exact model-input signal;
  * **Report** — Blade Strike Analysis report with provenance, plus table,
    figure and one-click self-contained analysis-package export.

  Datasets created on the Dataset creation page feed Model Prediction
  automatically (`DatasetPage.dataset_ready`); a saved `model_features.csv`
  can also be loaded directly.

## Development

Environment: Python 3.13 (`.venv/`), PySide6.

Run the app:

```
.venv\Scripts\python.exe main.py
```

### Regenerating the UI

The layout lives in `main.ui` — edit it in Qt Designer (`.venv\Scripts\pyside6-designer.exe main.ui`).
`modules/ui_main.py` is **generated** from it and must never be edited by hand.

Use `build_ui.py` (see below) rather than calling `pyside6-uic` directly — it
normalises `main.ui` first and checks the generated file actually compiles.

Icons and images are compiled from `resources.qrc` into
`modules/resources_rc.py`. Qt loads them through the `:/...` resource system,
**not from disk** — so replacing a PNG under `images/` has no effect on the
running app until the resources are rebuilt. `build_ui.py` detects a changed
image and rebuilds them automatically. To do it by hand:

```
.venv\Scripts\pyside6-rcc.exe resources.qrc -o modules\resources_rc.py
```

## Licence

MIT — see `LICENSE`. The GUI is built on the PyDracula template by Wanderson M. Pimenta;
the project credit and link are available in the app under **Settings > About**.

### Build the UI

`main.ui` is compiled to `modules/ui_main.py`. PyCharm does this automatically
before launching (Run configuration **StrikeWorks** has **Build UI** as a
before-launch task), so normally you just edit `main.ui` and press Run.

To do it by hand:

```
.venv\Scripts\python.exe build_ui.py
```

`build_ui.py` also repairs two things Qt Designer does on save that break the
toolchain: fully-scoped enums (which make Designer show a modal warning per
occurrence next time the file is opened) and empty `<fontweight>` elements
(which uic turns into a syntax error).

The generated file is never hand-edited. `resources_rc.py` in the project root
is a shim so uic's default `import resources_rc` resolves to
`modules/resources_rc.py`.
