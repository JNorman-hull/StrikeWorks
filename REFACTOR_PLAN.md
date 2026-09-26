# StrikeWorks clean-up and refactoring plan

Status: **in progress** on branch `cleanup-2026-09` - phases A-F done
(see the progress table in section 9). Each phase ends in a working app,
so the work can stop after any of them.

Numbers come from an audit of the source on 2026-09-25 (70 modules,
~30,000 hand-written lines, plus the generated `ui_main.py` and
`resources_rc.py`).

---

## 1. Fix first: things that lose data or are simply wrong

These come before any tidying.

**1.1 The build deletes whatever is inside `dist\StrikeWorks`.**
PyInstaller empties that folder before every build. The packaged app keeps
its default `libraries`, `input_data`, `output_data` and `models` folders
right there, next to the exe, so anything made while using the built app
(libraries, exported datasets, reports, deployed models) is wiped by the
next build. This happened on 2026-09-25: an exported dataset, the
`demo_data` pack and one library index were deleted before the build
stopped on a locked folder.
- `build.py`: build into a separate folder and copy only the program
  (`StrikeWorks.exe` + `_internal`) into `dist\StrikeWorks`, never touching
  the data folders. Refuse to build if it would have to delete a data
  folder that has anything in it.
- Longer term: default data folders under the user's Documents (e.g.
  `Documents\StrikeWorks\libraries`) rather than inside the program folder,
  which also makes the app installable under Program Files.

**1.2 Two modules write runtime files inside the program bundle.**
`bsm_state.py` and `ml_train_state.py` work out their folder from
`Path(__file__).parent.parent`. From source that is the repo; in the built
app it is `_internal`, so training runs (`_internal\training_runs`, 12 MB
already) and the latest BSM result are written inside the bundle and lost at
every rebuild. `DEFAULT_MODELS_DIR` points into `_internal` too. Use
`settings.app_root()` (or the user data folder from 1.1) - the helper
already exists for exactly this.

**1.3 Settings are spread over three files in the home folder** -
`.hifistrike_settings.json` (still the old HiFiStrike name),
`.strikeworks_sensors.json`, `.strikeworks_annotations.json` - and the
recent-datasets list keeps stale and relative paths (`input_data\...`).
Move to one `StrikeWorks\settings.json` in the user's AppData, read the old
files once on first start, drop missing/relative entries from the recent
lists.

**1.4 32 places catch every error and carry on silently.**
The worst is `report_center.py` (8): a figure that fails to render simply
disappears from the report with no message. Others: `validation_core`,
`train_worker`, `predict_worker`, `sensor_config`, `deployment_index`,
`dev_console` (2 each), and one each in 12 more files. Each one should
either report the problem (the report's warnings list, the console, the
status bar) or catch only the specific error it expects.

---

## 2. Structure

**2.1 Core logic that lives inside page modules.** Several pages hold code
other parts of the app depend on - including two pages that are now hidden:

| Code | Lives in | Used by | Move to |
|---|---|---|---|
| `_ExtractThread`, `_standardise` (dataset building) | `page_dataset.py` (hidden page) | `validation_core`, `page_annotate` | new `dataset_build.py` |
| `_ProcessThread` (raw processing) | `page_process.py` | `inventory_widgets` | new `processing.py` |
| `_Spinner`, `_NavViewBox`, `_CsvLoadThread`, `_find_col`, `_CHANNELS` | `page_validate.py` (hidden page) | Annotate, Inspect, Export animations, Misclassification | `plot_widgets.py` / `signal_io.py` (`_Spinner` duplicates `ml_widgets.Spinner` - drop it) |
| `build_video_index` | `page_misclassification.py` | `report_center` | `raw_layout.py` (next to the other folder scanning) |

Once moved, the hidden pages can be deleted outright (see 2.6) without
breaking anything.

**2.2 The same job written more than once.**
- Nadir time + ROI window: `validation_core` (shared), plus separate copies
  in `page_annotate` (`_index_nadir_time`, `_window_bounds`) and
  `page_validate`. Keep the `validation_core` one.
- Listing a library's processed CSVs: three versions with different
  exclusion rules (`inventory_widgets`, `library_widgets.list_sensor_csvs`,
  `validation_core.processed_sensor_files`). Keep one, in `raw_layout.py`.
- Reports: 10 entry points - page buttons on Annotate, Analysis and
  reporting and Evaluate, Simple mode's Download, `ml_report.export_analysis`,
  and the central Export and report dialog - on top of two HTML page
  wrappers (`ml_report.wrap_html_document`, `report_center._wrap_document`)
  and four HTML builders. Make `report_center` the only way a report is
  written: a page's own "Generate report" becomes "the central report with
  just this section ticked", and Simple mode's Download calls the same code.

**2.3 `main.ui` is mostly unused.** Every page but the two hidden ones now
builds its own contents in Python. The `.ui` file still carries the old
Designer pages (the Process tabs that get hidden, the Dataset page groups,
an unused `page_final_report`). Cut it down to
the window frame, sidebar and one empty frame per page, and regenerate
`ui_main.py` (2,794 lines today; a few hundred after).

**2.4 PyDracula template leftovers.**
- `app_functions.py` - styles PyDracula demo widgets that are no longer in
  the UI, so it would crash if it ever ran; it only runs when
  `useCustomTheme` is on, which it never is. Delete, with the unused
  `themes/*.qss`.
- `ui_functions.py` does `from main import *`, the circular import that
  forces the "import modules, then reload main" trick in every test. Pass
  the window in instead. Also drops `GLOBAL_STATE` globals, `setStatus`,
  `selectStandardMenu`, `selectPanelMenu` (unused).
- `app_settings.Settings` (sidebar widths/colours) clashes in name with the
  app's `settings` module - rename it `ui_config`.

**2.5 One way to write a page.** Pages are currently written three ways:
Qt objects that bind to `ui` widgets, Qt widgets that build themselves, and
plain classes. Settle on one: a `QWidget` subclass that builds its own UI
and is handed what it needs (state, session) in its constructor.

**2.6 Hidden pages - decide.** Segmentation (`page_validate.py`, 781 lines),
Data analysis (stub) and Advanced dataset options (`page_dataset.py`,
767 lines) are built at every start-up but not shown. After 2.1, either
delete them or build them only when un-hidden. Recommendation: delete
Segmentation and the Dataset page (both fully replaced), keep the Data
analysis stub as a placeholder.

**2.7 Names that don't match the app.** Module and class names still carry
old page names. Rename to match what the user sees:

| Now | Shown as | Rename to |
|---|---|---|
| `page_bsm_biological.py` / `BiologicalPage` | Model comparison | `page_model_comparison.py` / `ModelComparisonPage` |
| `page_bsm_sensitivity.py` / `SensitivityPage` | Analysis and reporting | `page_bsm_analysis.py` / `BSMAnalysisPage` |
| `page_adjustments.py` / `AdjustmentsDialog` | Settings | `page_settings.py` / `SettingsDialog` |
| `page_initiate_deployment.py` | Create and edit deployment | `page_deployment.py` |
| `page_prepare.py`, `prepare_tab_*` | Setup and deploy | `page_setup.py`, `setup_*` |
| `btn_adjustments`, `btn_biological`, ... | | matching button names |

**2.8 `main.py` (827 lines, 37 % comments).** 14 identical
`status -> print` hook-ups become one loop; the splash screen, default
folder creation and app-ID helpers move out; the navigation tables stay.

**2.9 `ml_widgets.py` is a grab bag (878 lines).** Split into `theme.py`
(colours, fonts, stylesheets), `cards.py` (MetaCard, RingCard, StatCard),
`layout.py` (`hsplit`, `centred`, `when_visible`, `on_show`,
`discard_widget`) and `tables.py` (`style_table`, table copy).

---

## 3. Repeated UI code

| Pattern | Copies | Replace with |
|---|---|---|
| a private `_muted(text)` label helper | 13 files | one `muted_label()` in `layout.py` |
| the accent button stylesheet | 11 | `accent_button(text)` |
| hand-built scroll area + the same stylesheet | 14 / 12 | `scroll_page(frame)` returning the body layout |
| `setStyleSheet(...)` calls | 241 | one app stylesheet with named rules (`setObjectName`) |
| hard-coded hex colours outside the palette | 143 | the `theme.py` constants |

---

## 4. Dead code and lint

Remove (none are referenced anywhere):
- `bsm_figures`: `draw_pco`, `draw_pm`, `draw_sens_wf`, `draw_sweep_lines`
  (replaced by the 4-panel figures)
- `sensor_config`: `resample_frame`, `primary_extension`,
  `nadir_search_samples`; `register_parser` only if no plug-in use is
  planned
- `library_widgets`: `_DirsOnlyProxy`, `video_dir_for`, `selected_path`
- `ml_report`: `export_tables`, `export_figures`
- `ml_widgets`: `set_checks`, `set_running`
- `raw_layout.video_dirs_for`, `deployment_index.runs_for`,
  `ml_state.has_ground_truth`, `ml_train_state.trained_kinds`,
  `page_home._go_simple`, `page_ml_prediction.goto_report`,
  `page_annotate._deployment_map`, `page_process._parse_name`,
  `dev_console.set_app_window`, `eel_format.device_and_time`
- the PyDracula functions listed in 2.4

Plus 26 unused imports, 5 unused variables and one empty f-string reported
by pyflakes, and the old `_min.csv` exclusions once no library still has
those files.

---

## 5. Comments, docstrings and wording

About one line in six is a comment or docstring, which is fine; the problem
is what many of them say. Around 180 of them tell the story of how the code
got here rather than what it does now: "used to", "no longer", "moved here
from", "renamed from", ROADMAP item numbers, "the MVP", "the user asked
for", dates. That belongs in git history.

Rules for the pass:
- A docstring says what the function does and anything surprising about
  how to use it. One line where one line will do.
- A comment explains *why* the code is written the way it is, only where it
  isn't obvious. No history, no ticket or roadmap numbers, no "deliberately",
  no restating the code.
- Plain words in the UI: no internal names (`hstrike_flagged`,
  `pres_min.time.`) in labels, tooltips or messages.
- `main.py` first (22 history references), then the page modules.

Documents:
- `ROADMAP.md` (2,223 lines, mostly finished work) - keep only open items
  and the "Hidden for now" list; the finished-work history is in git.
- `README.md` - bring up to date with the current workflow (Simple mode,
  demos, sensor configurations including the EEL tag).

---

## 6. Speed and size

- **Processed CSV writing is ~90 % of processing time** (about 1.8 s of
  2.3 s per RAPID recording, all in pandas' number formatting). Writing
  with 6 significant figures halves the file size (29 → 14 MB per RAPID
  recording; EEL files are 48 MB per minute) and is a little faster.
  Parquet would be much faster still, but needs `pyarrow` and changes the
  file type users open.
- **Start-up builds every page**, hidden ones included. Build pages the
  first time they are opened.
- **Bundle size** (590 MB when last built): all of sktime and its test
  suites are collected, but only MiniRocket is used; `excludes` is empty.
  `opencv-python` (112 MB) could be `opencv-python-headless` if the video
  preview only decodes frames. `llvmlite`/numba (115 MB) is needed by
  sktime's MiniRocket.
- The RAPID binary reader loops byte by byte; it is fast enough (0.1 s per
  recording) but could be rewritten the way `eel_format.py` reads, for
  clarity rather than speed.

---

## 7. Repository

- `.gitignore` is 3,890 lines - 3,857 of them individual `dist/` files.
  Replace with `/dist/`, `/build/`, and ignore generated output folders
  (`bsm_results/`, `output_data/`, exported `input_data/*.csv`, `.idea/`).
- About 100 MB of generated output and data is tracked in git (old
  `bsm_results`, bar plots, dataset CSVs). Untrack them (`git rm
  --cached`); keep one small sample dataset for the demo, or use Git LFS.
- Stray files in the repo root: `.Rhistory`, `format-specification.html`,
  `strikeworks_dev_log.txt`.
- Add `.gitattributes` (`* text=auto`) - git currently warns about line
  endings on most modules.

---

## 8. Tests and tooling

There are no tests in the repo; every check so far has been a throwaway
script. Add:
- `tests/` with pytest for the pure code first: `bsm_model`, `wilson_calc`,
  `eel_format` (the synthetic-file checks already written), the
  `validation_core` flag rules, `deployment_index`, `raw_layout`, report
  figure sizes.
- A start-up test with pytest-qt (offscreen): the main window builds and
  every page opens. Simple once 2.4 removes the circular import.
- The Simple and Advanced demos as an end-to-end test on a small demo pack.
- `ruff` for lint and import order, run before each commit.
- The frozen-build smoke test (launch the exe, run the prediction and
  training workers) as `tools/smoke_test.ps1`.

---

## 9. Order of work

Each phase ends with: lint clean, tests + both demos passing, a look at
the changed pages, then a commit.

| Phase | Covers | Size | Risk |
|---|---|---|---|
| A | 1.1-1.2 build safety and runtime paths, 7 repo hygiene | small | low |
| B | 8 test harness (pure-code tests, start-up test, demos) | medium | low |
| C | 4 dead code and lint | small | low |
| D | 2.1-2.2 move core logic out of pages, remove duplicates | medium | medium |
| E | 2.4, 2.3 template leftovers, cut `main.ui` down | medium | medium |
| F | 2.5-2.9, 3 page pattern, renames, shared UI helpers | large | medium |
| G | 5 comments and docs pass | medium | low |
| H | 1.3-1.4 settings file, error reporting | medium | medium |
| I | 6 speed and bundle size | small-medium | low |

Phase B comes early on purpose: everything after it changes a lot of code,
and the tests are what show nothing broke.

### Progress

| Phase | Commit | Notes |
|---|---|---|
| A | e69c102 | `build.py` builds into `build/staging` and swaps in only the exe and `_internal` |
| B | b08a6ec | `tests/` (unittest), `tools/smoke_test.ps1` |
| C | 275e534 | 35 unused functions/classes removed |
| D | a8780ce | `plot_widgets`, `dataset_build`, `processing`, `raw_layout` paths; one report wrapper. The Evaluate model-package export and Simple mode's analysis export stay separate deliverables |
| E | d928462 | template leftovers gone, `main.ui` trimmed, no star imports |
| F | this phase | `ml_widgets` split into `theme` / `layout` / `tables` / `cards` / `level_grouper`; `muted_label`, `ACCENT_BUTTON`, `CONSOLE_STYLE`, `scroll_page`, `scroll_area`; modules renamed per 2.7; `main.py` 825 -> 461 lines, start-up helpers in `startup.py` |

Decisions taken on the way:
- **2.6 hidden pages are kept, not deleted** - they are hidden temporarily
  (ROADMAP.md, "Hidden for now"). Building them lazily is left to phase I.
- **2.5 one page pattern is deferred.** Converting the `QObject` page
  controllers that bind to `main.ui` widgets into self-building `QWidget`s
  means moving each page's layout out of `main.ui`; worth doing page by
  page when a page is next reworked, not as one sweep.
- **2.7 Designer object names stay** (`page_prepare`, `btn_adjustments`,
  `btn_biological`, ...): renaming them touches `main.ui`, the generated
  file and every lookup for no visible gain. Only modules, classes and
  attributes were renamed.
- **3, the app-wide stylesheet** (241 `setStyleSheet` calls) is not done:
  the repeated ones are now theme constants; the rest are one-offs, and a
  named-rule stylesheet is a visual change to check page by page.

## 10. Not changing

The science and the file formats: the BSM maths, the Wilson intervals, the
RAPID and EEL decoding, the index and dataset column names, and the model
pipeline. The refactor moves and tidies code around them; it must not change
a single output number (the tests in phase B pin that down).
