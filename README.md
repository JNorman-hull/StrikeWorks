# StrikeWorks
StrikeWorks is a data extraction, validation, processing and model development tool for underwater passive sensor devices used in fish passage science.

Copyright University of Hull (2026)

* Development: Josh Norman, University of Hull - J.Norman2@hull.ac.uk
* Sensor implementation: Jeffrey Tuhtan, Tallinn University of Technology
  (TalTech) - jeffrey.tuhtan@taltech.ee

Built in Python 3.13; package citations and the PyDracula theme credit are
in the app under **About** (`modules/about_dialog.py`, shared by Simple mode
and the full app).

## Workflow

The app opens in **Simple mode** (`modules/page_simple_mode.py`), a guided
wizard: Deploy > Process > Validate > Predict > Report. **Development
toolkit** opens the full app, where the same steps are spread over pages
(Setup and deploy > Create and edit deployment, Sensor processing > Raw data
processing, Validate and annotate > Annotate, Model training, Model
prediction) alongside blade strike modelling, study design, training and the
rest. The first three steps are literally the same code in both modes:

* **Deployment editor** (`modules/deployment_editor.py`) - session library,
  library status, sensor, deployment and treatment table. *Create & open data
  folder* builds a new deployment's folders; *Update* saves changes and makes
  the folders match (renames carry folders and already-processed sensors
  with them; removing a treatment/run removes its folder after a "Remove
  folder and content" confirmation). Leaving with unsaved changes asks Save
  and continue / Continue / Cancel. The sensor configuration is saved with
  the deployment.
* **File inventory** (`modules/inventory_widgets.py`) - every raw recording
  with its Deployment, Treatment and Run read from its folder; processing
  labels each recording from its own folder, so one batch can span several
  treatments and runs.
* **Validation** (`modules/validation_core.py`) - *Auto process all* saves
  every sensor's detected nadir window and flags the ones whose window shows
  a weak HIG peak (< 95 g) for review; the list puts flagged-and-unreviewed
  sensors first; Save + next records a human review. *Save and export*
  binds the saved windows (with any annotations) into one dataset in the
  input data folder and hands it to Model prediction.

### Raw folder layout

```
<library>/raw_sens_data/<deployment>/<treatment>/Run <n>/<sensor files>
                                                        VIDEO/<stem>_vid_*.mp4
```

Every treatment has at least Run 1. Older libraries with files directly in
the treatment folder still work (read as Run 1). `modules/raw_layout.py` is
the one definition of this.

### Demo mode

Adjustments > Dev mode opens the **Dev console**, which mirrors all app
output and runs the demos:

* **Simple** - drives Simple mode's wizard end to end (no training).
* **Advanced** - drives the full app: BSM Calculator > Study design >
  deployment > processing > Annotate (Auto process all, Import annotations
  CSV, Save and export) > Train > Deploy > Predict > Model comparison >
  report.

Both use a **demo pack**: a folder called `demo_data`, placed in the
libraries folder (or the app's own `libraries/`), shaped like a library:

```
demo_data/raw_sens_data/<deployment>/<treatment>/[Run <n>/]<recordings>
demo_data/*annotations*.csv     (Advanced demo's annotations)
demo_data/demo.json             (optional: site/machine, treatment conditions,
                                 sensor, BSM config)
```

Recordings are copied (never moved) into a `StrikeWorks_demo` library
created in the user's libraries folder, so output stays wherever their
libraries live. `demo_data` is never listed as a library.

## Pages

* **Sensor Processing** - Prepare, Process, Validate & segment.

  **Prepare** sets the session's sensor and plans the study around it:
  * **Sensor configuration** - the active `sensor_config.SensorConfig`
    (`modules/sensor_config.py`). A sensor is two rates plus one entry per
    raw file: the `timebase_hz` counter clock the files are stamped from,
    the `output_rate_hz` grid the processed CSV is written on, and for each
    file its extension, packet size, native rate and how it reaches that
    grid. RAPID's `.imp` arrives at 100 Hz and is interpolated up to
    2000 Hz; its `.hig` arrives at 2000 Hz but only in bursts around
    events, so it is standardised onto the same grid with the gaps filled
    with 0. The tab also carries the computed magnitude channels and the
    nadir detection method. Everything downstream reads it - Process scans
    those extensions and runs that parser, Validate plots at that rate,
    Dataset creation turns its 200 ms window into that many rows. Two
    configurations ship (`rapid`, the current device, and `micro_eel`,
    anticipated); a third is a New or Duplicate plus a Save, stored in
    `~/.strikeworks_sensors.json`. Only a new device's reader is code: write
    it and register it under `sensor_config.PARSERS`;
  * **Study design** - a sampling-precision calculator: an expected strike
    rate (typed, or loaded from Blade Strike Modelling) and a planned N give
    the Wilson interval that N would achieve; a target precision gives the
    N needed for it.
  * **Create and edit deployment** - the deployment editor (see Workflow).
    Saving writes one row per treatment per run into the library's
    `global_sensor_index.csv` marked `file = label_pad`
    (`modules/deployment_index.py`), plus the sensor configuration used.
    A library can hold several deployments; one filled in before this
    existed has its deployments read back from its processed sensors.
    Plan rows are filtered out of every sensor listing.

  The index's columns are the app's, in `modules/index_schema.py`, so a
  library needs no `config/index_config.txt` to be processed.

* **Annotation & Video Analysis** - **Annotate**, **Dataset creation**.

  **Annotate** reviews a recording against its signal - and, where a
  matching clip exists, its video - and records what happened: a nadir
  window, a manual `bad_sens` flag, and free-form annotation values, all in
  one pass. Half the width is the signal plot (built on
  `page_validate.py`'s already-standalone `_CsvLoadThread`/`_NavViewBox`,
  not a copy of the page itself - `page_validate.py` stays under Sensor
  Processing, it is what later grows into the Delineation tool), the other
  half is the annotation panel. Saved windows land in the same
  `processed_sens_data/nadir_window/` folder Validate & segment uses, so
  Dataset creation's segmented mode binds them either way. Annotation
  variables (`modules/annotation_schema.py`) default to the four columns
  the old `model_labels.csv` workflow used and are user add/remove/rename;
  values are written straight onto the sensor's row in
  `global_sensor_index.csv` (`deployment_index.set_row_values`), no
  separate CSV. The video column/button finds `<stem>_vid_*.mp4` in the
  recording's run (or, for older libraries, treatment) `VIDEO` folder and
  launches `exteneral_software/LosslessCut.exe`.

  **Dataset creation** is unchanged - relocated here from Sensor Processing
  since it belongs with the rest of the annotation/curation workflow.

* **Machine Learning Analysis** - **Model Training**, **Model Performance**
  and **Model Prediction**.

  **Model Training** ports the ML pipeline scripts (01_binary_model /
  05_multiclass_collapsed) into three tabs sharing one training state
  (`modules/ml_train_state.py`), run by `modules/train_worker.py` in a
  streaming subprocess. One run trains the full two-stage prediction
  pipeline: the binary strike model plus (when region labels exist) the
  multiclass region model for predicted strikes. Run outputs live in
  `training_runs/` (gitignored).
  * **Train** - dataset loading/filtering, the two-stage target definition
    with both class distributions, channel selection, sequence preparation,
    hold-out/CV setup, class balancing and model parameters, then the run
    itself: the TRAIN MODEL control, live fold progress, the streaming
    training console and both models' out-of-fold performance;
  * **Evaluate** - evaluates any model, whether trained in this session or
    already deployed in the models folder (`modules/ml_model_library.py`):
    performance cards, CV mean±SD, ROC/PR/confusion/probability/
    strike-type figures, error analysis, stratification, and an exportable
    model report;
  * **Deploy** - the explicit accept step: train the final models on all
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
  * **Predict** - model/dataset cards, compatibility validation, prediction
    configuration and the asynchronous run (`modules/predict_worker.py` in a
    subprocess, so the sktime/numba model stack never loads into the GUI
    process);
  * **Inspect** - per-recording prediction browser with filters, class
    probabilities, ground-truth comparison and the exact model-input signal;
  * **Report** - Blade Strike Analysis report with provenance, plus table,
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

The layout lives in `main.ui` - edit it in Qt Designer (`.venv\Scripts\pyside6-designer.exe main.ui`).
`modules/ui_main.py` is **generated** from it and must never be edited by hand.

Use `build_ui.py` (see below) rather than calling `pyside6-uic` directly - it
normalises `main.ui` first and checks the generated file actually compiles.

Icons and images are compiled from `resources.qrc` into
`modules/resources_rc.py`. Qt loads them through the `:/...` resource system,
**not from disk** - so replacing a PNG under `images/` has no effect on the
running app until the resources are rebuilt. `build_ui.py` detects a changed
image and rebuilds them automatically. To do it by hand:

```
.venv\Scripts\pyside6-rcc.exe resources.qrc -o modules\resources_rc.py
```

## Licence

MIT - see `LICENSE`. The GUI is built on the PyDracula template by Wanderson M. Pimenta;
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
