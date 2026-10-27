# Handing over StrikeWorks

## Where things stand (22 October 2026)

- `main` is pushed to GitHub (`origin/main` = `94bd884`, everything up to
  13 October). Not tagged yet. The 21-22 October changes (below) are in the
  working copy only - not committed or built.
- Latest builds: `dist/StrikeWorks` (full app) on 13 October, with
  everything up to the 8 October changes - not smoke-tested (not wanted
  that time); `dist/StrikeWorks_Simple` (StrikeWorks only) on 6 October,
  smoke-tested then, without the 7-8 October changes. No zips yet.
  `dist/StrikeWorks` now also holds `external_software` (LosslessCut) and
  a `settings.json`, and `dist/StrikeWorks_Simple` a Pentair run
  (`input_data`, `output_data`, `settings.json`), so `--zip-only` refuses
  for either until those are moved out.
- New since the 26 September builds: the University of Hull theme
  (Settings > Appearance) on one app-wide stylesheet; the review counter
  reads "Flagged for review: k/n sensors"; **strike severity** - each
  recording's HIG peak counted over 95, 200 and 400 g, only > 400 g a
  severe strike - in Predict, Inspect, Simple mode and the reports.
- Why severity: on the Pentair dataset (66 recordings) the model calls 64
  strikes, but only 1 peaks over 400 g. It is flagging low-magnitude
  contacts (task 3).
- New on 6-8 October (committed; in the 13 October full-app build):
  - **HIG peak analysis** (Predict and Simple mode's Predict step, ticked
    by default): the original R
    analysis's peak finder - events of at least 95 g, collisions of at
    least 400 g within ±0.1 s of the nadir, collision probability with a
    Wilson CI - shown as cards, the peak figure (a: each recording's
    peak g as a box plot, b: event counts, c: collision probability),
    the acceleration table (the
    `Acceleration_table.xlsx` template, with the events' minimum, maximum
    and IQR) and the acceleration- and nadir-aligned figures, in Predict
    and the reports (`modules/hig_peaks.py`, README "Models").
  - **Lint**: ruff (`ruff.toml`, `requirements-dev.txt`), run by the tests.
  - **Pages**: every page builds itself (`layout.Page`); `main.ui` is the
    window frame only.
  - **RAPID reader** on numpy records: same output, ~28x faster.
  - **Model deployment** is part of Model training > Train's Model box;
    the Deploy page and its sidebar entry are gone.
  - **Simple mode**: Deploy's left column and Validate now sit on the
    same section boxes as File inventory and Treatments (scroll areas no
    longer paint the default grey).
  - **Logos** (27 October): one logo, StrikeWorks | University of Hull
    (`images/strikeworks_uoh_*.png`), wherever the StrikeWorks logo or the
    University brandmark was (splash, StrikeWorks Home / Finished / bottom
    bar, the toolkit's Home and sidebar foot, About); white on dark, navy
    on light; the sidebar's top badge kept.
  - **Windows** (7 October): the standard Windows frame for both windows
    (Simple mode gained minimise/maximise); both open within the screen's
    work area (taskbar excluded); every page and Simple mode step scrolls
    rather than growing the window; Raw data processing's Summary cards
    two by two; the splash sized to its logos; a saved report opens its
    folder; unticking HIG peak analysis hides the HIG cards and skips the
    analysis; no "Blade strike (next)" button in the Simple edition.
    Then: the settings panel's text white (its "More" button gone); the
    title without "Passive sensor data toolkit"; no border round the
    window; Model comparison's inputs scroll in their own column; Export
    and report is Preview / Export / Export all, with sections that have
    nothing to report greyed out; Simple mode's main steps bold. Then:
    Model comparison's inputs column narrows to about half its old
    minimum (counts one per row, each species' values under its tick
    box, filter lists that shrink), its two figures half the width each;
    figures app-wide redraw once a resize is over, not during a drag; a
    sensor plot's Export (PNG/SVG) saves the window the plot shows - its
    time range and both y ranges - not the whole recording.
  - **HIG peak figure** (8 October): three panels in the layout of the
    user's reformatted version - a) each recording's peak acceleration
    (box plot per treatment), b) event counts, c) collision probability
    on 0-100% - "a)" letters, n (and CI) top right, no grid; a full row
    of its own on Predict.
- New on 21-22 October, in the working copy (not committed or built):
  - **Names**: "Simple mode" is now just **StrikeWorks** (the app), the
    full app is the **Development toolkit**. StrikeWorks's Home lost its
    two buttons; a **Development toolkit** button at its bottom left asks
    for a password (`devmode_123`, in `page_simple_mode.py` - a door, not
    security); the toolkit's sidebar button reads **Go to StrikeWorks**.
    Both windows open maximised.
  - **Console**: Settings' Dev mode is gone; Settings > **Console**
    (bottom left) shows everything printed since start-up - status, worker
    output, Qt warnings, unhandled errors with tracebacks - and writes it
    as it goes to `logs/strikeworks_<date>_<time>.log` beside the settings
    file (last 20 kept; a hard crash's traceback lands there too).
  - **Demos**: every step stays on screen at least 2 s (not when run
    unattended - `--demo`, the tests).
  - **Annotate**: a **Position annotations** box (unticked by default)
    shows a second list of variables; Manage variables moves variables
    between the two lists (defaults: see "Labels as they are" below). A
    grab bar between the signal plot and the boxes under it, on Annotate
    and Misclassification analysis.
  - **Sort by** on every sensor list (Validate, Annotate, Export
    animations): needs review first, sensor name, recording time - one
    shared, remembered choice (`modules/sensor_sort.py`).
  - **Misclassification analysis** also writes each correction to the
    recording's row of its library's sensor index, and shows the
    variables the model's dataset has (position ones included).
  - **Train page** (26 October): four rows - Training dataset (with the
    preview), Labelling (Target / Null value (0) / Positive value (1), each
    target value coded 0, 1 or Exclude in place of Dataset filtering, the
    multiclass grouping with classes beside levels, distributions, then
    the breakdown), Inputs | Cross-validation, and one Model box
    (Configuration, Train + Console, Final model, Deploy; one button size).
    No training console - the worker's lines go to the app Console; Raw
    data processing likewise has a Console button instead of its log box.
    Typing a class name no longer loses focus each key (LevelGrouper
    doesn't rebuild for its own change). No bold anywhere in the UI or
    figures (exported HTML reports keep their headings).
  - **One validation page** (27 October): StrikeWorks's Validate step is
    the toolkit's Validate and annotate page itself
    (`page_annotate.AnnotationPage(..., for_strikeworks=True)`): the
    library filters, the sensor list (Sort by, Mark bad / Mark good, Show
    bad, counts, Save + Next, Reset sensor, Auto process all), the plot
    (`sensor_validation.ValidationView`) with Left / Right channels, ROI
    window, Open video (LosslessCut; `open_video` is shared with
    Misclassification and Export animations), an "Annotations and notes"
    window (`AnnotationsWindow`: stays open, follows the sensor, holds
    Import annotations CSV…, closes with its page) and Save and export,
    which exports the sensors listed. Only the saving differs: in the
    toolkit Save + Next also adds annotated windows to the running dataset
    (`_after_save`) and Save and export asks first while flagged sensors
    are unreviewed; StrikeWorks asks on Next instead, names the export
    after the Deploy deployment and continues to Predict with it. The
    hidden Segmentation page (`page_validate.py`) is deleted, with its
    sidebar button. Hidden-tab-bar pages (`layout.TabbedPage`) have no
    frame; the plots' Export button is styled like the other buttons. Section boxes have no frame or tick box
    anywhere (`layout.Section`), which also fixed spinners showing all
    the time. Figures are laid out at the size they're drawn
    (`canvas.FigureCanvas`).
  - **Export and report** (23 October): a tick list of the models the
    evaluation covers (this session's ticked to start with) instead of a
    picker + "All models"; report files are written through Windows'
    long-path form, so a library deep in OneDrive no longer loses every
    figure but the ROC curve past the 260-character limit; a figure that
    can't be saved is a report warning. Predict's acceleration-/nadir-
    aligned figures: one panel per treatment. StrikeWorks: the Process
    and Report headings open their first sub-step; the University mark
    sits beside the small logo, bottom left.
  - **Stop** on raw processing (Raw data processing and StrikeWorks's
    Process step): finishes the recording in hand, keeps what was done.
    The Development toolkit button shows on StrikeWorks's Home only.
  - **Labels as they are** (22 October, replacing a name/value
    conversion layer tried the same day): the default annotation
    variables and Model training's starting choices live in
    `config/default_settings.json` (passage_type, leading_type,
    other_type, concentric_pump_region; position strike_location,
    approach_orientation), not in code; nothing renames or recodes labels;
    the Train page's target, "no strike" value, class column, grouping (no
    presets) and performance breakdown are the user's choice; the surface
    -> region 1 option is gone; prediction compares with annotations only
    on the model's own target column and "no strike" value. The PumpFlow
    DI-1 index was moved to the new names and values to match
    `PumpFlow_FS-700_DI-1_2026.csv` (backup
    `global_sensor_index_backup_20261022b.csv`), the demo pack's
    annotations recoded (backup `libraries/Testbed_annotations_backup_20261022.csv`),
    and both settings files' saved variable lists removed so the new
    defaults apply (backups `settings_backup_20261022b.json`).
  - **PumpFlow DI-1 index** (22 October): the 14 corrections made in
    Misclassification analysis before it wrote to the index (all
    `overall_passage_type` -> `no_contact`, in
    `dist/StrikeWorks/input_data/PumpFlow_DI-1_20261021_124437_corrected_.csv`)
    applied to the library's `global_sensor_index.csv`; the previous index
    is beside it as `global_sensor_index_backup_20261022.csv`. Those 14
    still carry their old `other_type` / `leading_type` /
    `concentric_pump_region` values.
  - **Label audit** (`modules/model_labels.py`): prediction's ground truth
    now uses the binary model's own target column and "no strike" value
    and the region model's own class column and level grouping (it was
    fixed to `concentric_pump_region` and whole numbers, and
    `predictions.csv` dropped `passage_type`/`leading_type` and any
    custom target); region models record `region_column`; annotation
    columns are no longer offered as model channels; one table of the
    older column names (`annotation_schema.LEGACY_NAMES`).
- Tests: 91 pass, both demos and the lint check included
  (`STRIKEWORKS_E2E=1`; 11-19 minutes on this machine on 6 October,
  where building the main window alone took 25 s).

## What there is

| Item | Where | Notes |
|---|---|---|
| Source, tests, docs, default models, BSM presets, example datasets | GitHub `JNorman-hull/StrikeWorks`, branch `main` | `README.md` (how it works, how to build), `ROADMAP.md` (open work, hidden pages), `REFACTOR_PLAN.md` (the September 2026 clean-up: what changed, and the conventions for new code) |
| The packaged app | `dist/StrikeWorks_<date>.zip` (made by `build.py --zip` / `--zip-only`) | Self-contained: unzip anywhere and run `StrikeWorks.exe` |
| The Simple edition | `dist/StrikeWorks_Simple_<date>.zip` (made by `build.py --simple --zip` / `--zip-only`) | The same, locked to Simple mode - for users who should only process, validate and predict |
| Demo pack source | `libraries/Testbed` (41 MB, not in git; also on OneDrive in `RAPID_libraries\Testbed`) | The raw recordings and annotations the demos start from; the build copies it to `libraries/demo_data` |
| RAPID sensor recordings | OneDrive: `FSE Hull International Fisheries Institute - Documents\REDEEM 2.0\HS_JOSH_NORMAN\RAPID_libraries` | The real libraries; not in git or the build |
| LosslessCut (video review) | https://github.com/mifi/lossless-cut | Not in git or the build (900 MB); copy it into `external_software/` beside `StrikeWorks.exe` (its readme.txt says how) |

## Task list

For whoever picks this up next - a colleague, or a new Claude chat (read
this file, `README.md` and `ROADMAP.md` first).

1. ~~Clean the project folder~~ - done 6 October (below).
2. ~~Re-run the Pentair prediction with the current build~~ - done 6
   October: of 66 recordings, 41 peak over 95 g, 16 over 200 g, 1 over
   400 g.
3. **Decide on low-magnitude strikes** (`ROADMAP.md`, first open item):
   headline the collision probability (HIG peak analysis: 1 of 66 Pentair
   recordings, 1.5 %), retrain with contact types separated, or re-tune
   the threshold.
4. **Build tooling** (`ROADMAP.md`): `build.py --zip` zips a clean copy
   instead of refusing; `smoke_test.ps1 -Demos` copies only what ships.
5. **Bundle size** (`ROADMAP.md`) - with the next build. (The template's
   unused icons stay: they may be used.)
6. **Release** - the shelving checklist below (tag, remake and publish the
   zips, access).
7. The rest of `ROADMAP.md`.

## Task 1: project folder clean-up (done 6 October 2026)

The folder was about 18 GB, 13.5 GB of it in `dist`. Approved and done:

- **Moved to OneDrive** (`RAPID_libraries\Pentair`, 6.6 GB): the Pentair
  library, which had only existed inside `dist\StrikeWorks_Simple`; its
  exported dataset and analysis are in the library's
  `StrikeWorks_user_output` folder.
- **Sent to the Recycle Bin** (7.3 GB; empty it to free the space):
  - superseded data from older builds (`dist\_kept_from_previous_build_20260926`);
  - all four zips;
  - `build\` (PyInstaller's working folders and the handover copies);
  - demo output in both builds: the `StrikeWorks_demo` libraries, the
    `DevTest_PF_*` datasets and a demo analysis;
  - `input_data\DevTest_PF_*` (16), `training_runs\`, the old
    `output_data` analysis, `__pycache__`, `.Rhistory`,
    `strikeworks_dev_log.txt`, `format-specification.html`;
  - two local working datasets (`..._only500rpm.csv`, `..._only_annotations.csv`;
    the demo pack has its own annotations);
  - the built apps' `settings.json` files - both builds start on their
    defaults again (their own folders).
- **Removed from git** (still in the history): the unreferenced datasets
  `Pumpflow_2024_and_2026_datatset__corrected.csv` and
  `Pumpflow_2026_datatset2_only.csv`.
- **Deleted** the merged local branch `cleanup-2026-09`.
- **Kept**: the logo and brand files in the root, both unzipped builds,
  `.venv`, `external_software` (LosslessCut), `.git`, `libraries\Testbed`,
  `models` and the shipped datasets.

## Checking the packaged app (about 15 minutes)

Everything below stays inside the unzipped folder: it starts on its own
`libraries`, `models`, `input_data` and `output_data`, and keeps its
settings in `settings.json` beside the exe.

1. Unzip, run `StrikeWorks.exe`. StrikeWorks opens.
2. **Settings** (top right) > **Console** (bottom left).
3. Pick **StrikeWorks (no training)**, **Run demo**. It builds a
   `StrikeWorks_demo` library from `libraries/demo_data`, processes and
   validates the recordings, exports a dataset to `input_data`, predicts it
   with the default models and writes
   `libraries/StrikeWorks_demo/StrikeWorks_user_output/BladeStrike_Analysis_<run>/report.html`.
4. Pick **Development toolkit (full workflow, trains a model)**, **Run
   demo**. It
   trains and deploys a model (into the demo library's
   `StrikeWorks_user_output/models`), predicts the dataset with the default
   models and writes a full report to `.../StrikeWorks_user_output/Report_<time>/`.
5. Predicting an existing dataset: **Development toolkit** (bottom left;
   password `devmode_123`), then Model prediction > Predict > load
   `input_data/Pumpflow_2024_datatset1_only.csv` > Run.

The same check runs unattended from the repo: `powershell -File
tools\smoke_test.ps1 -Demos` (on a temporary copy of `dist\StrikeWorks` -
run it on a freshly built folder, see `ROADMAP.md`, Build tooling).

The Simple edition is checked the same way (steps 1-3; there is no
Development toolkit button and no Development toolkit demo), or with `powershell
-File tools\smoke_test.ps1 -Simple -Demos`.

## Shelving checklist

1. ~~Push `main`~~ (done). **Tag it**:
   ```
   git tag -a v1.0 -m "Handover build"
   git push origin v1.0
   ```
2. **Keep the demo pack with the code** - either commit it (a clone can
   then rebuild the zip and run the demo tests):
   ```
   (add  !/libraries/Testbed/  to .gitignore, under /libraries/*)
   git add .gitignore libraries/Testbed
   git commit -m "Demo pack"
   ```
   or point your colleague at the OneDrive copy (`RAPID_libraries\Testbed`).
3. **Make and publish the zips**: `build.py --zip-only` and
   `build.py --simple --zip-only` (or rebuild first with `--zip`), then
   attach `dist/StrikeWorks_<date>.zip` and
   `dist/StrikeWorks_Simple_<date>.zip` to the `v1.0` GitHub release, or
   put them on the shared OneDrive.
4. **Give access**: add your colleague to the GitHub repository and share
   the RAPID_libraries OneDrive folder.
5. **Tidy your own machine**: the project folder is done (task 1; empty
   the Recycle Bin). Outside it, your settings (`%APPDATA%\StrikeWorks\settings.json` and the older
   `~\.hifistrike_settings.json`, `~\.strikeworks_sensors.json`,
   `~\.strikeworks_annotations.json`) hold your own folder paths.
6. **Point your colleague at the open work**: the task list above and
   `ROADMAP.md`.

## For your colleague: working from source

```
git clone https://github.com/JNorman-hull/StrikeWorks
cd StrikeWorks
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.venv\Scripts\python.exe main.py
```

- Tests: `.venv\Scripts\python.exe -m unittest discover -s tests`
  (`set STRIKEWORKS_E2E=1` first to include both demos; needs
  `libraries/Testbed`).
- PyCharm: interpreter `.venv`, run configuration `main.py` with
  `build_ui.py` as a before-launch step (it regenerates `modules/ui_main.py`
  from `main.ui`).
- New release: `build.py`, then `tools\smoke_test.ps1 -Demos`, then
  `build.py --zip-only`; for the Simple edition the same with `--simple`
  (`smoke_test.ps1 -Simple -Demos`).
