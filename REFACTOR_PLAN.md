# StrikeWorks clean-up and refactor (September 2026)

**Status: finished.** Every phase is merged into `main`; the last, the
app-wide stylesheet, went in with `bf4df7e` on 30 September 2026, and the
follow-up of 6 October (lint, one page pattern, RAPID reader) after it.
This file is now the record: what the audit found, what was done, the
decisions taken and the conventions new code should follow. What is left
open is at the end and in `ROADMAP.md`.

## Before and after

| | Audit, 25 Sep 2026 | 6 Oct 2026 |
|---|---|---|
| Modules | 70, ~30,000 hand-written lines | 81, ~25,000 (smaller modules, no duplicate copies) |
| `main.py` | 827 lines | 424 |
| `modules/ui_main.py` (generated from `main.ui`) | 2,794 lines | 760 (`main.ui` is the window frame only) |
| Per-widget `setStyleSheet` calls | 241 | 2 in code (the size grip, one sidebar icon) and 34 sidebar-icon styles in `main.ui`, plus the one app stylesheet |
| Error handlers that failed silently | 32 | 0 that hide a failure (one cosmetic Windows taskbar call ignores errors) |
| Tests | none | 65 in `tests/`, both demos end to end, a lint check, and a smoke test for the packaged app |
| `.gitignore` | 3,890 lines | 29 |
| Processed RAPID recording | 30 MB | 15 MB |
| Start-up (main window) | 3.4 s | 1.4 s |
| Reading a RAPID .imp/.hig pair | byte by byte | numpy records, ~28x faster, identical output |
| `build.py` | deleted the data next to the exe | never touches the data folders |

## What was done

| Phase | Commit | What changed |
|---|---|---|
| A | e69c102 | **Build safety and repo.** `build.py` builds into `build/staging` and swaps in only `StrikeWorks.exe` and `_internal`. Training runs and BSM results follow `settings.app_root()` (beside the exe once packaged, not inside the bundle). `.gitignore` rewritten, ~100 MB of generated output untracked, `.gitattributes` added |
| B | b08a6ec | **Tests.** `tests/` (standard-library unittest): BSM model and Wilson intervals pinned to their outputs, the EEL reader on synthetic files, the validation rules, the folder layout, every page and dialog opening off-screen, and both demos end to end (`STRIKEWORKS_E2E=1`). `tools/smoke_test.ps1` for the packaged app |
| C | 275e534 | **Dead code.** 35 unused functions and classes (~390 lines), unused imports and variables |
| D | a8780ce | **Shared logic out of the pages.** `plot_widgets.py`, `dataset_build.py` and `processing.py` take code the hidden pages held; `raw_layout.py` is the one place for a library's folder paths and its list of processed files (there were three, with different rules); Annotate uses `validation_core`'s nadir and window code; one HTML report wrapper |
| E | d928462 | **Template leftovers.** No `from main import *` (the circular import every test had to work around); `app_settings` became `ui_config`; `app_functions.py` and the unused template themes deleted; unused Designer pages cut from `main.ui` |
| F | a4fa30c | **Structure and names.** `ml_widgets.py` split into `theme`, `layout`, `tables`, `cards` and `level_grouper`; shared helpers replace per-page copies; page modules renamed to what the app shows (model comparison, BSM analysis, settings, deployment, setup); `main.py` 825 -> 461 lines, start-up helpers in `startup.py` |
| G | bfcbae0 | **Comments and docs.** Comments and docstrings say what the code does, without the history; no internal column names in messages; `ROADMAP.md` cut to open work (2,223 -> ~90 lines); `README.md` rewritten |
| H | 933d088 | **Settings and errors.** One `settings.json` (old home-folder files read once, left in place); recent datasets keep absolute, existing paths only; silent catch-alls now report (report warnings, console, status bar) or catch the specific error; the running dataset is never overwritten when it can't be read |
| I | 9e499f6 | **Speed.** Processed CSVs at 10 significant figures (half the size, 35 % faster to read, no recorded value changed); Evaluate's model discovery and Analysis and reporting's figures run when first shown |
| Stylesheet | bf4df7e | **One app stylesheet.** `themes/app.qss` styles every window, dialogs included, with `@name` colours filled from the active palette (`modules/theme.py`); widgets take a look by role and tone (`theme.style()`); sidebar highlights are properties. This made the University of Hull theme a second palette |
| Follow-up | 6 Oct 2026 | **Lint, pages, RAPID reader.** ruff (`ruff.toml`, `requirements-dev.txt`, `tests/test_lint.py`) and its findings fixed; every page a self-building `QWidget` (`layout.Page` / `TabbedPage`) added to the page stack by `main.py`, the hidden Segmentation and dataset pages included, so `main.ui` holds only the window frame (2,260 lines, from 3,649); the RAPID `.imp`/`.hig` readers on numpy structured records, the way `eel_format.py` reads, byte-identical on the Testbed recordings (`tests/test_rapid_format.py`) |

## Decisions taken on the way

- **Hidden pages are kept**, not deleted - they are hidden temporarily
  (`ROADMAP.md`, "Hidden for now"). Building them lazily wasn't worth it:
  they take 0.02 s together.
- **One page pattern**, deferred at first, was done in the follow-up for
  every page at once: the per-page conversions were small, and leaving
  half the pages in `main.ui` kept two ways of writing a page.
- **Designer object names stay** (`page_prepare`, `btn_adjustments`,
  `btn_biological`, ...): renaming them touches `main.ui`, the generated
  file and every lookup for no visible gain. Modules, classes and
  attributes were renamed.
- **Reports**: one HTML wrapper and the central Export and report dialog;
  Evaluate's model-package export and Simple mode's analysis export stay
  separate deliverables.
- **The packaged app is portable** rather than installed: `settings.json`
  and the data folders sit beside the exe. Moving the data folders to
  Documents (so the app could live under Program Files) was not done.
- **10 significant figures, not 6**, for processed CSVs: 6 moves values by
  up to 0.005 and loses the time step beyond 100 s; 10 gives the same size
  saving without changing any recorded value.
- **Tests use unittest** (they also run under pytest), so nothing extra is
  needed to run them. **Lint is ruff**, a development requirement only
  (`requirements-dev.txt`): pyflakes' checks, pycodestyle's error classes
  and bugbear; line length and import order are left alone.
- **The template's unused icons stay** in `resources.qrc` (223 of 257
  unused): they may be used for new pages, and cost 1 MB.
- **The RAPID reader keeps the original pairing**: each .imp row pairs a
  packet's counter with the previous packet's readings, and the last
  packet is unused - what the original reader produced, kept so no
  processed recording changes.
- **Exported figures and HTML reports keep their own colours** (36 in
  `ml_report`, `report_center`, `bsm_report` and the figure modules):
  publication styling on white, independent of the on-screen theme.

## Still open

| Item | Notes |
|---|---|
| Bundle size | `_internal` is 539 MB. Exclude PySide6's unused Qt parts (`Qt6Quick`, `Qt6Qml`, `Qt6Pdf`, `opengl32sw.dll`, ~30 MB); consider `opencv-python-headless` (112 MB `cv2`). `llvmlite` (115 MB) is needed by numba for MiniRocket; sktime's test suites are only 3 MB. Each change needs a build and a smoke test (`ROADMAP.md`) |

## Conventions for new code

- **Look**: `theme.style(widget, role=..., tone=...)`, never
  `setStyleSheet`; a new look is a rule in `themes/app.qss`, a new colour
  a token in both palettes in `theme.py`.
- **Shared helpers**: `theme.muted_label`, `layout.scroll_page` /
  `scroll_area` / `hsplit` / `centred`, `cards` (MetaCard, RingCard,
  StatCard), `tables`.
- **Figures** go on `canvas.FigureCanvas`, not Matplotlib's own Qt
  canvas: it redraws once a resize is over (a splitter or window-edge
  drag, maximising, the sidebar) instead of at every step.
- **Folders**: a library's paths come from `raw_layout.py`; files the app
  writes at run time go under `settings.app_root()`, never
  `Path(__file__)`; settings go through `modules/settings.py`.
- **Errors**: report them (console, status bar, a report's warnings list)
  or catch only the error expected.
- **Pages**: a page is a `layout.Page` (`TabbedPage` for tabs the sidebar
  picks) that builds its own UI and is given what it needs (the main
  window as `main_window`, state, session) in the constructor; `main.py`
  adds it to the page stack and to `_SUBMENU_TARGETS`. Nothing goes into
  `main.ui` but the window frame.
- **Comments** say what the code does and why where it isn't obvious - no
  history, dates or ticket numbers; that belongs in git.
- **`modules/ui_main.py`** is generated from `main.ui` by `build_ui.py`;
  never edit it by hand.
- **Before a commit**: `ruff check .`, the tests with both demos
  (`STRIKEWORKS_E2E=1`), and a look at the pages changed.

## Not changed

The science and the file formats: the BSM maths, the Wilson intervals, the
RAPID and EEL decoding, the index and dataset column names, and the model
pipeline. The refactor moved and tidied code around them without changing
a single output number; the tests pin that down.
