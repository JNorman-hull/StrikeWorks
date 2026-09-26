# StrikeWorks
StrikeWorks is a data extraction, validation, processing and model development tool for underwater passive sensor devices used in fish passage science.

Copyright University of Hull (2026)

* Development: Josh Norman, University of Hull - J.Norman2@hull.ac.uk
* Sensor implementation: Jeffrey Tuhtan, Tallinn University of Technology
  (TalTech) - jeffrey.tuhtan@taltech.ee

Built in Python 3.13; package citations and the PyDracula theme credit are
in the app under **About**.

## Workflow

The app opens in **Simple mode**, a guided wizard: Deploy > Process >
Validate > Predict > Report. **Development toolkit** opens the full app,
where the same steps have their own pages alongside blade strike modelling,
study design and model training. Deploy, Process and Validate run the same
code in both modes:

* **Deployment editor** (`modules/deployment_editor.py`) - session library,
  library status, sensor, deployment and treatment table. *Create & open
  data folder* builds a new deployment's folders; *Update* saves changes and
  makes the folders match (renames carry folders and already-processed
  sensors with them; removing a treatment or run removes its folder after a
  "Remove folder and content" confirmation). The sensor configuration is
  saved with the deployment.
* **File inventory** (`modules/inventory_widgets.py`) - every raw recording
  with the Deployment, Treatment and Run of its folder; each recording is
  labelled from its own folder, so one batch can span several treatments
  and runs.
* **Validation** (`modules/validation_core.py`) - *Auto process all* saves
  every sensor's detected nadir window and flags the ones with a weak HIG
  peak (< 95 g) for review, listed first; *Save + next* (Ctrl+V) records a
  review and moves to the next flagged sensor. *Save and export* binds the
  saved windows and annotations into one dataset and hands it to Model
  prediction.

### Raw folder layout

```
<library>/raw_sens_data/<deployment>/<treatment>/Run <n>/<sensor files>
                                                        VIDEO/<stem>_vid_*.mp4
```

Every treatment has at least Run 1; files directly in a treatment folder
read as Run 1. `modules/raw_layout.py` is the one definition of this.

## The full app

| Section | Pages |
|---|---|
| Mathematical blade strike modelling | **Calculator** (CEN 2025 collision and mortality, scaly and eel together), **Analysis and reporting** (results and sensitivity figures, report export) |
| Setup and deploy | **Sensor configuration**, **Study design** (Wilson-interval sample size), **Create and edit deployment** |
| Sensor processing | **Raw data processing** (filters, summary cards, file inventory, console) |
| Validate and annotate | **Annotate** (validation plus annotation values, video lookup), **Export animations** (sensor graph synced onto high-speed video) |
| Model training | **Train**, **Evaluate**, **Misclassification analysis**, **Deploy** |
| Model prediction | **Predict**, **Inspect**, **Model comparison** (model vs BSM collision and mortality per treatment) |
| Export and report | one dialog that builds a single HTML report from any page's section |

Pages built but hidden for now are listed in `ROADMAP.md`.

### Sensor configurations

A sensor configuration (`modules/sensor_config.py`) is data: the counter
clock the raw files are stamped from, the grid the processed CSV is written
on, and per raw file its extension, record size, native rate and how it
reaches the grid. Two ship:

* **RAPID** (`rapid`) - `.imp` at 100 Hz, interpolated to 2000 Hz; `.hig`
  at 2000 Hz in bursts around events, placed on the grid with the gaps
  filled with 0.
* **EEL tag** (`micro_eel`) - 23-byte `.imp` and 11-byte `.hig` records on a
  shared master clock; the sample rate comes from the recording's `.log`
  (`modules/eel_format.py`, per the EEL tag binary format specification).

A new device is New or Duplicate in Sensor configuration plus a Save
(stored in `~/.strikeworks_sensors.json`); only its reader is code, written
and registered under `sensor_config.PARSERS`.

### Models

Model training runs `modules/train_worker.py` in a subprocess: a binary
strike model and, when region labels exist, a multiclass pump-region model.
Deploy writes `binary<v>.joblib`, `multiclass<v>.joblib` and a
`BladeStrikeModel_v<v>/` package into the models folder (Settings), where
Model prediction finds them. Prediction runs `modules/predict_worker.py` in
a subprocess, so the model stack never loads into the GUI.

### Demos

Settings > Dev mode opens the **Dev console**, which shows all app output
and runs two demos:

* **Simple** - Simple mode's wizard end to end (no training).
* **Advanced** - the full app: Calculator > Study design > deployment >
  processing > Annotate (Auto process all, Import annotations CSV, Save
  and export) > Train > Deploy > Predict > Model comparison > report.

Both use a **demo pack**: a folder called `demo_data` in the libraries
folder (or the app's own `libraries/`), shaped like a library:

```
demo_data/raw_sens_data/<deployment>/<treatment>/[Run <n>/]<recordings>
demo_data/*annotations*.csv     (Advanced demo's annotations)
demo_data/demo.json             (optional: site/machine, treatment conditions,
                                 sensor, BSM config)
```

Recordings are copied (never moved) into a `StrikeWorks_demo` library in
the user's libraries folder. `demo_data` is never listed as a library.

## Development

Environment: Python 3.13 (`.venv/`), PySide6. Run the app:

```
.venv\Scripts\python.exe main.py
```

### Tests

```
.venv\Scripts\python.exe -m unittest discover -s tests
```

The tests use a temporary settings folder and an off-screen Qt. Set
`STRIKEWORKS_E2E=1` to also run both demos end to end (about 3 minutes;
needs `libraries/Testbed`).

### Building

```
.venv\Scripts\python.exe build.py
```

PyInstaller builds into `build/staging/`; only `StrikeWorks.exe` and
`_internal/` are then swapped into `dist/StrikeWorks/`, so the libraries,
models, input and output folders beside the exe are never touched.
`tools\smoke_test.ps1 -Dataset <dataset.csv>` checks the packaged app
starts and its prediction worker runs (add `-TrainConfig <train_config.json>`
for the training worker).

### The UI file

The layout lives in `main.ui` (Qt Designer:
`.venv\Scripts\pyside6-designer.exe main.ui`). `modules/ui_main.py` is
generated from it and never edited by hand; PyCharm's **StrikeWorks** run
configuration regenerates it before launch, or by hand:

```
.venv\Scripts\python.exe build_ui.py
```

`build_ui.py` also repairs two things Designer does on save that break the
toolchain (fully-scoped enums and empty `<fontweight>` elements), and
rebuilds `modules/resources_rc.py` from `resources.qrc` when an image has
changed - Qt loads icons through `:/...` resources, not from disk.
`resources_rc.py` in the project root is a shim so uic's `import
resources_rc` resolves.

## Licence

MIT - see `LICENSE`. The GUI is built on the PyDracula template by
Wanderson M. Pimenta; the credit and link are in the app under **About**.
