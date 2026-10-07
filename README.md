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
| Model training | **Train** (with Model deployment beside it), **Evaluate**, **Misclassification analysis** |
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
(kept in the settings file); only its reader is code, written and
registered under `sensor_config.PARSERS`.

### Settings

One file, `settings.json`: beside `StrikeWorks.exe` in the packaged app
(so the folder is self-contained and starts on its own libraries, models,
input_data and output_data folders), or `%APPDATA%\StrikeWorks\` when
running from source. The `STRIKEWORKS_SETTINGS` environment variable
overrides the location.

### Themes

Settings > Appearance chooses the theme, applied the next time the app
starts: **StrikeWorks (dark)**, or **University of Hull** (the brand's
Core, low-intensity look: white pages, Ink Blue sidebar, Chartreuse and
Mid Blue accents, brand colours in charts; its brandmark in About and on
Simple mode's welcome page; the StrikeWorks logo outlined for white,
`PyDracula_vertical_white.png`). The University of Hull logo sits at the
foot of the sidebar above Simple mode (white; the collapsed sidebar shows
its shield) and on Simple mode's Download page, in either theme
(`startup.uoh_logo_pixmap`). Every window is styled by one stylesheet,
`themes/app.qss`, whose `@name` colours `modules/theme.py` fills from the
active palette; widgets take a look with `theme.style(widget, role=...,
tone=...)` rather than stylesheets of their own. A new theme is a new
palette in `theme.THEMES`.

### Models

Model training runs `modules/train_worker.py` in a subprocess: a binary
strike model and, when region labels exist, a multiclass pump-region model.
Model deployment (on the Train tab, beside Train) trains the final
model and writes `binary<v>.joblib`, `multiclass<v>.joblib` and a
`BladeStrikeModel_v<v>/` package into the models folder (Settings), where
Model prediction finds them. Prediction runs `modules/predict_worker.py` in
a subprocess, so the model stack never loads into the GUI.

Alongside the model's verdict, prediction measures **strike severity**:
each recording's peak high-g acceleration magnitude (`higacc_mag_g`) over
its window, counted over 95, 200 and 400 g. Only a peak over 400 g is a
severe strike - the model flags contacts of any size, so severity shows
how many of its strikes were hard hits. It appears in the Predict results
(cards, treatment table, figure), Inspect (per recording, with severe and
"strike, ≤ 400 g" filters), Simple mode and the reports
(`severity_summary.csv`; `hig_peak_g`, `severity`, `severe_strike` in
`predictions.csv`). The thresholds are in `modules/severity.py`.

**HIG peak analysis** (the *HIG peak analysis* box on Predict and on
Simple mode's Predict step - one setting, ticked by default) goes further: it finds every acceleration event in each
recording's HIG magnitude - peaks of at least 95 g with a prominence of
25 g, at least 2 ms apart, each typed collision or shear by how long it
stays above 70 % of its height - the peak finder of the original R
analysis (`modules/hig_peaks.py`; tested against it). Events are counted
within ±0.1 s of the nadir, the whole of a dataset's 200 ms window; a
recording with an event of 400 g or more there has a **collision**, and
the collision probability is the share of recordings with one (Wilson 95%
CI). Predict's results then show the event and collision cards, the peak
figure (a: events over 95, 200 and 400 g; b: collision probability) and
an **HIG peak analysis** section: the acceleration table (event counts,
collision probability, and the minimum, maximum and IQR of the events'
acceleration) and the acceleration- and nadir-aligned figures of every
recording with a collision. The reports carry the same table and figures
(`acceleration_summary.csv`, `hig_peaks.csv`; per recording `n_events`,
`collision`, `collision_g` ... in `predictions.csv`).

### Demos

Settings > Dev mode opens the **Dev console**, which shows all app output
and runs two demos:

* **Simple** - Simple mode's wizard end to end: deployment, processing,
  validation, export, prediction with the default models, report (no
  training).
* **Advanced** - the full app: Calculator > Study design > deployment >
  processing > Annotate (Auto process all, Import annotations CSV, Save
  and export) > Train > Deploy > Predict (with the default models) >
  Model comparison > report.

Reports go to the demo library's output folder,
`libraries/StrikeWorks_demo/StrikeWorks_user_output/`. The same demos run
unattended with `StrikeWorks.exe --demo simple|advanced [--log <file>]`
(or `python main.py --demo ...`), exiting 0 when they pass.

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

Environment: Python 3.13 (`.venv/`), PySide6. `requirements.txt` lists the
dependencies; `requirements-lock.txt` pins the exact versions the app was
built and tested with. Run the app:

```
.venv\Scripts\python.exe main.py
```

Video review (Annotate, Export animations, Misclassification analysis)
opens clips in LosslessCut, which isn't in the repo or the build (900 MB).
Copy LosslessCut.exe and the files that come with it into
`external_software/` - in the repo, or beside `StrikeWorks.exe` in a
packaged copy, where the build puts that folder with a readme saying so.

### Tests

```
.venv\Scripts\python.exe -m unittest discover -s tests
```

The tests use a temporary settings folder and an off-screen Qt. Set
`STRIKEWORKS_E2E=1` to also run both demos end to end (about 7 minutes;
needs `libraries/Testbed`).

### Lint

```
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\ruff.exe check .
```

`ruff.toml` holds the settings (pyflakes, pycodestyle's error classes,
bugbear; the generated `ui_main.py` and `resources_rc.py` are skipped).
`tests/test_lint.py` runs it with the tests, and skips when ruff isn't
installed.

### Building

```
.venv\Scripts\python.exe build.py
```

PyInstaller builds into `build/staging/`; only `StrikeWorks.exe` and
`_internal/` are then swapped into `dist/StrikeWorks/`, so anything made
with the built app stays. The build also places what ships with it: the
default models, the BSM presets, an example model dataset in `input_data`
and the demo pack in `libraries/demo_data` (copied from
`libraries/Testbed`).

```
powershell -File tools\smoke_test.ps1 -Demos
.venv\Scripts\python.exe build.py --zip-only
```

The smoke test checks the packaged app starts and predicts the example
dataset, and with `-Demos` runs both demos on a fresh copy of the folder.
`--zip-only` (or `--zip` to build and zip in one go) zips
`dist/StrikeWorks` for handing over - refusing, with a list, if the folder
holds anything the build didn't put there.

**Simple edition.** `build.py --simple` builds a second, separate app into
`dist/StrikeWorks_Simple`: Simple mode only, with the development toolkit
(the full app) locked - no Development toolkit button, and only the Simple
demo in the Dev console. The lock is a start-up hook compiled into the exe
(`tools/simple_edition_hook.py`, `modules/edition.py`); from source,
`set STRIKEWORKS_EDITION=simple` shows the same thing. Test and zip it with
`tools\smoke_test.ps1 -Simple -Demos` and `build.py --simple --zip-only`.

### Pages and the UI file

Every page builds its own contents: a `layout.Page` (a `QWidget`, or a
`layout.TabbedPage` for a page of tabs the sidebar picks between) in
`modules/page_*.py`, given what it needs (the main window, shared state)
in its constructor. `main.py` creates them and adds them to the main
window's page stack; `_SUBMENU_TARGETS` maps each sidebar button to its
page and tab.

`main.ui` (Qt Designer: `.venv\Scripts\pyside6-designer.exe main.ui`)
holds only the window frame: title bar, sidebar, the empty page stack,
the settings panel and the status bar. `modules/ui_main.py` is generated
from it and never edited by hand; PyCharm's **StrikeWorks** run
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
