# StrikeWorks
StrikeWorks is a data extraction, validation, processing and model development tool for underwater passive sensor devices used in fish passage science.

Copyright University of Hull (2026)

* Development: Josh Norman, University of Hull - J.Norman2@hull.ac.uk
* Sensor implementation: Jeffrey Tuhtan, Tallinn University of Technology
  (TalTech) - jeffrey.tuhtan@taltech.ee

Built in Python 3.13; package citations and the PyDracula theme credit are
in the app under **About**.

## Workflow

The app opens as **StrikeWorks**, a guided window: Deploy > Process >
Validate > Predict > Report. **Development toolkit** (its bottom-left
button, behind a password - `devmode_123`) opens the full app, where the
same steps have their own pages alongside the blade strike calculator, study
design and model training; its sidebar's **Go to StrikeWorks** goes back.
Deploy, Process and Validate run the same code in both:

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
* **Sensor lists** (`modules/sensor_sort.py`) - every list of sensors
  (Validate, Annotate, Export animations) has the same **Sort by**: needs
  review first, sensor name, or recording time (from the name); one
  choice, remembered, shared by every list.

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
| Blade strike calculator | One page, no section panel, two tabs: **Calculator** (CEN 2025 collision and mortality, scaly and eel together, each species' collision probability; Advanced options set the sensitivity sweeps' Q and N ranges and Q step, as multiples of the design value) and **Advanced analysis** ("Advanced model outputs": both species' results table and output cards, the results and sensitivity figures; the report is in Export and report) |
| Setup and deploy | **Sensor configuration**, **Study design** (Wilson-interval sample size), **Create and edit deployment** |
| Sensor processing | **Raw data processing** (filters, summary cards, file inventory, console) |
| Validate and annotate | **Annotate** (the same page as StrikeWorks's Validate step - `modules/page_annotate.py` - the library's filters, the validation screen and an Annotations and notes window), **Export animations** (sensor graph synced onto high-speed video) |
| Model training | **Train** (training dataset, labelling, inputs, cross-validation, and one Model box: train, final model, deploy), **Evaluate**, **Misclassification analysis** |
| Model prediction | **Predict** (two tabs, Predict and Results - the same pages as StrikeWorks's Predict and Report steps, `modules/ml_tab_predict.py`), **Inspect**, **Model comparison** (model vs BSM collision and mortality per treatment) |
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
starts. There is one, **StrikeWorks (dark)** (the University of Hull
theme was removed on 29 October 2026); the selector stays for any added
to `theme.THEMES` later. The app's one logo is StrikeWorks with the
University of Hull beside it (`images/strikeworks_uoh_*.png`), in the
same places throughout - the loading splash, StrikeWorks's Home
and Finished steps and bottom bar, the toolkit's Home and the foot of its
sidebar, About - in white, for the dark theme; the
300 dpi files for the big ones, 96 dpi for the small (`startup.logo_label`,
`startup.ScaledLogo`). The small badge at the top of the toolkit's sidebar
stays.

### Annotations

Annotate records each sensor's annotation variables (`modules/
annotation_schema.py`) on its row of the library's sensor index, under
each variable's name. The variables live in the settings file; until it
has its own list, they come from the shipped defaults,
`config/default_settings.json` (none are written in code):

| Variable | Label | Values |
|---|---|---|
| `passage_type` | Overall passage type | no_contact, leading_edge, other |
| `leading_type` | Leading edge type | direct, indirect |
| `other_type` | Other contact type | hub_0, hub_1, hub_2, surface |
| `concentric_pump_region` | Concentric pump region | 1-5 |
| `strike_location` *(position)* | Sensor strike location | 1-5 |
| `approach_orientation` *(position)* | Approach orientation | 1-3 |

Position annotations show on Annotate while its *Position annotations*
box is ticked (unticked by default; remembered). Manage variables adds,
renames and removes variables and moves them between the two lists; each
variable's Edit… adds, renames or removes its values.
Misclassification analysis shows the variables the model's training
dataset has a column for - position ones too, under their own heading.
Its corrections go to the corrected training
dataset and to the recording's row of its library's sensor index, so
Annotate and the next export carry them.

**Names and values are used as they are.** Nothing renames or recodes a
label anywhere - not in the index, a dataset, Bind training data or the
workers - so datasets to be bound together must use the same names and
spellings (Bind training data says when files' columns differ). On the
Train page you choose the target column and its null value (0); each of
the target's values is coded 0, 1 (the positive value, `blade_strike` by
default) or left out, so the derived 0/1 variable is in plain view. Then
the class column (its levels grouped into classes by you - each level
starts as its own class) and the columns the performance is broken down by
(each
strike's type: direct, indirect, hub_0 ...). A loaded dataset starts from
the settings' `model_training` choices (`passage_type`, `no_contact`,
`concentric_pump_region`, `leading_type` + `other_type`), each only if the
dataset has it. Prediction doesn't use annotations; it compares its
predictions with them only on the binary model's own terms - its target
column holding its "no strike" value (`modules/model_labels.py`) - and
otherwise says it can't compare.

### Windows

Both windows use the standard Windows frame (minimise, maximise, snap,
resize; `UIConfig.ENABLE_CUSTOM_TITLE_BAR` brings back the template's own
title bar). Each opens maximised; restored, it is sized and centred within
the screen's work area - the screen less the taskbar
(`win_utils.fit_to_screen`) - and every page (and every StrikeWorks step)
sits in a scroll area, so a small screen
scrolls a page rather than pushing the window past its edge. Figures are
redrawn once a resize is over - on releasing a splitter handle or the
window's edge - and stretched until then (`modules/canvas.py`), so
dragging stays smooth on pages with several figures. Every window is styled by one stylesheet,
`themes/app.qss`, whose `@name` colours `modules/theme.py` fills from the
active palette; widgets take a look with `theme.style(widget, role=...,
tone=...)` rather than stylesheets of their own. A new theme is a new
palette in `theme.THEMES`.

### Models

Model training runs `modules/train_worker.py` in a subprocess: a binary
strike model and, when region labels exist, a multiclass pump-region model.
The Model box on the Train tab trains it (the worker's output goes to
the app Console - a button beside Train model), then trains the final
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
"strike, ≤ 400 g" filters), StrikeWorks and the reports
(`severity_summary.csv`; `hig_peak_g`, `severity`, `severe_strike` in
`predictions.csv`). The thresholds are in `modules/severity.py`.

**HIG peak analysis** (the *HIG peak analysis* box in Predict's
**Advanced features** - one setting, ticked by default) goes further: it finds every acceleration event in each
recording's HIG magnitude - peaks of at least 95 g with a prominence of
25 g, at least 2 ms apart, each typed collision or shear by how long it
stays above 70 % of its height - the peak finder of the original R
analysis (`modules/hig_peaks.py`; tested against it). Events are counted
within ±0.1 s of the nadir, the whole of a dataset's 200 ms window; a
recording with an event of 400 g or more there has a **collision**, and
the collision probability is the share of recordings with one (Wilson 95%
CI). Predict then shows the collision ring (the collision probability in
its centre) and Results the peak
figure (a: each recording's peak acceleration as a box plot; b: events
over 95, 200 and 400 g; c: collision probability, 0-100%), the
acceleration table (event counts,
collision probability, and the minimum, maximum and IQR of the events'
acceleration) and the acceleration- and nadir-aligned figures of every
recording with a collision. The reports carry the same table and figures
(`acceleration_summary.csv`, `hig_peaks.csv`; per recording `n_events`,
`collision`, `collision_g` ... in `predictions.csv`).

### Demos

Settings > **Console** (bottom left) opens the console: everything the
app has printed since it started - status messages, worker output, Qt
warnings, and unhandled errors with their tracebacks - also written as it
goes to the session's log file (`logs/strikeworks_<date>_<time>.log`
beside the settings file, the last 20 kept; a hard crash writes its
traceback there too) (`modules/dev_console.py`). It runs two demos, each
step on screen at least 2 s:

* **StrikeWorks** - the StrikeWorks window's steps end to end: deployment,
  processing, validation, export, prediction with the default models,
  report (no training).
* **Development toolkit** - the full app: Calculator > Study design >
  deployment > processing > Annotate (Auto process all, Import annotations
  CSV, Save and export) > Train > Deploy > Predict (with the default
  models) > Model comparison > report.

Reports go to the demo library's output folder,
`libraries/StrikeWorks_demo/StrikeWorks_user_output/`. The same demos run
unattended with `StrikeWorks.exe --demo simple|advanced [--log <file>]`
(or `python main.py --demo ...`), exiting 0 when they pass.

Both use a **demo pack**: a folder called `demo_data` in the libraries
folder (or the app's own `libraries/`), shaped like a library:

```
demo_data/raw_sens_data/<deployment>/<treatment>/[Run <n>/]<recordings>
demo_data/*annotations*.csv     (the Development toolkit demo's annotations)
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
`dist/StrikeWorks_Simple`: the StrikeWorks window only, with the
Development toolkit (the full app) locked - no Development toolkit button,
and only the StrikeWorks demo in the console. The lock is a start-up hook compiled into the exe
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
