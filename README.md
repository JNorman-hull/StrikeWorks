# StrikeWorks
StrikeWorks is a data extraction, validation, processing and model development tool for underwater passive sensor devices used in fish passage science.

Credit: 

Dr. Josh Norman (University of Hull)
Prof. Jeffrey Tuhtan (University of Talinn)

Copyright University of Hull (2026)

## Pages

* **Sensor Processing** — Prepare, Process, Validate & segment, Dataset creation.

  **Prepare** sets the session's sensor and plans the study around it:
  * **Sensor configuration** — the active `sensor_config.SensorConfig`
    (`modules/sensor_config.py`). A sensor is two rates plus one entry per
    raw file: the `timebase_hz` counter clock the files are stamped from,
    the `output_rate_hz` grid the processed CSV is written on, and for each
    file its extension, packet size, native rate and how it reaches that
    grid. RAPID's `.imp` arrives at 100 Hz and is interpolated up to
    2000 Hz; its `.hig` arrives at 2000 Hz but only in bursts around
    events, so it is standardised onto the same grid with the gaps filled
    with 0. The tab also carries the computed magnitude channels and the
    nadir detection method. Everything downstream reads it — Process scans
    those extensions and runs that parser, Validate plots at that rate,
    Dataset creation turns its 200 ms window into that many rows. Two
    configurations ship (`rapid`, the current device, and `micro_eel`,
    anticipated); a third is a New or Duplicate plus a Save, stored in
    `~/.strikeworks_sensors.json`. Only a new device's reader is code: write
    it and register it under `sensor_config.PARSERS`;
  * **Study design** — plans a deployment before any sensor is wetted: site,
    deployment ID, machine and type, then one treatment per row (head,
    flow, BEP, RPM) with a run count, each `+` copying the row above.
    Saving writes one row per treatment per run into the library's
    `global_sensor_index.csv` marked `file = label_pad`
    (`modules/deployment_index.py`). A library can hold several
    deployments; one filled in before this existed has its deployments read
    back from its processed sensors. Process then offers those treatments
    and runs: select a batch of sensors, pick what they were recorded
    under, and processing labels every one of them and sets
    `deployment_info` to Y — a deployment is worked treatment by treatment
    instead of typing metadata per file. Plan rows are filtered out of
    every sensor listing, and the Metadata tab still edits individual
    sensors.

  The index's columns are the app's, in `modules/index_schema.py`, so a
  library needs no `config/index_config.txt` to be processed.

* **Machine Learning Analysis** — **Model Training**, **Model Performance**
  and **Model Prediction**.

  **Model Training** ports the ML pipeline scripts (01_binary_model /
  05_multiclass_collapsed) into three tabs sharing one training state
  (`modules/ml_train_state.py`), run by `modules/train_worker.py` in a
  streaming subprocess. One run trains the full two-stage prediction
  pipeline: the binary strike model plus (when region labels exist) the
  multiclass region model for predicted strikes. Run outputs live in
  `training_runs/` (gitignored).
  * **Train** — dataset loading/filtering, the two-stage target definition
    with both class distributions, channel selection, sequence preparation,
    hold-out/CV setup, class balancing and model parameters, then the run
    itself: the TRAIN MODEL control, live fold progress, the streaming
    training console and both models' out-of-fold performance;
  * **Evaluate** — evaluates any model, whether trained in this session or
    already deployed in the models folder (`modules/ml_model_library.py`):
    performance cards, CV mean±SD, ROC/PR/confusion/probability/
    strike-type figures, error analysis, stratification, and an exportable
    model report;
  * **Deploy** — the explicit accept step: train the final models on all
    data, then deploy the pipeline under one shared version
    (`binary<v>.joblib` + `multiclass<v>.joblib` plus a
    `BladeStrikeModel_v<v>/` package with metrics, config, channels and the
    model card) into the models folder that Model Prediction
    auto-discovers.

  **Model Performance** reuses the Evaluate tab with no training session
  attached, so any deployed model can be reviewed and reported on
  independently.

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
