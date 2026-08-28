# StrikeWorks roadmap

Outstanding work, in the order agreed. Chunks 1 to 3 are done. Chunk 4's
sidebar section and its Annotate page are done; Delineation is shelved and
the Misclassification tool is not started. Each chunk is independent enough
to be picked up cold from this file plus the code.

A dummy library, "Testbed" (single treatment), exists in the libraries
folder for exercising the whole pipeline end to end during development -
see "Future — end-to-end pipeline test bed" below.

## Done

**Chunk 1 — ML analysis polish** (commit `f05f200`)
Collapsible `Section` panels everywhere with `SECTION_DEFAULTS` in
`modules/ml_widgets.py` (all open; flip to `False` to start collapsed).
Predict: compatibility folded into the Dataset box, READY TO PREDICT
removed, annotation detection de-hardcoded (`ANNOTATION_COLUMNS`,
`is_strike_value` in `modules/ml_state.py`). Inspect: magnitude channels
offered, defaults `pressure_kpa` (white) / `higacc_mag_g` (red). Evaluate /
Model Performance: deployment packages carry `cv_curves.json` and
misclassifications, ROC/PR derived from CV predictions when absent,
multiclass gained one-vs-rest ROC and accuracy-by-treatment, report export
includes misclassifications and per-treatment performance.

**Chunk 2 — label/target flexibility** (commit `6a4de50`)
`LevelGrouper` widget; class variable is any small-cardinality per-file
column; `GROUPING_PRESETS` are templates applied to observed levels;
`level_key()` shared by `ml_train_state` and `train_worker`; editable class
names and positive-class name.

**Chunk 3 — Prepare page: sensor configurations and study design**

*Tab 1 — Sensor configuration.* `modules/sensor_config.py` is the single
source of truth: a `SensorConfig`, the shipped `rapid` and `micro_eel`
configurations, a JSON store in `~/.strikeworks_sensors.json` (which only
holds a shipped configuration once it has actually been edited, so app
updates to the defaults are not shadowed), a `PARSERS` registry and a
`notifier` the pages follow. A sensor is a `SensorSource` per raw file
(extension, packet size, native rate, how it reaches the grid) plus two
rates that are deliberately separate:

  * `timebase_hz` — the counter clock the raw files are stamped from
  * `output_rate_hz` — the uniform grid the processed CSV is written on

RAPID is 2000/2000. `.imp` arrives at 100 Hz and is interpolated up. `.hig`
arrives at 2000 Hz but only in bursts around events (~29% of a run, gaps up
to 13 s), so it is *standardised*: every recorded sample keeps its own slot
and the gaps are filled with 0. Also on the tab: which three-axis sensors
get a magnitude channel (`higacc`/`inacc`/`rot`, all on by default) and the
nadir detection method — one method today, dispatched through
`rapid_functions.NADIR_METHODS` so a second is a function plus an entry.

The analysis window is *not* here — it is a downstream decision; the sensor
only answers what a window is worth in samples (`window_samples(seconds)`).

`modules/index_schema.py` holds the index's column list, transcribed from
the MVP's `config/index_config.txt` and verified column-for-column against
it. A library therefore needs no configuration at all to be processed, and
the parser no longer depends on the working directory (the `chdir` in the
processing thread is gone).

The hardcoding is ported: `page_process` scans the configured extensions,
parses names with the configured pattern and calls the registered parser;
`page_validate` takes its rate from the configuration and keeps its own
window; `page_dataset` derives target rows from its 200 ms window and the
sensor's rate; `rapid_functions` takes clock, packet sizes, output rate,
per-file method, magnitudes and nadir method as arguments. RAPID output is
byte-for-byte unchanged — including `higacc_mag_g`, which the reader
rounds to the device's precision and post-processing must therefore not
recompute.

*Tab 2 — Study design.* Plans a deployment: site, deployment ID, machine
and type, then one treatment per row (head, flow, BEP, RPM) with a run
count, each `+` copying the row above. Saving writes one row per treatment
*per run* into the library's `global_sensor_index.csv` with
`file = label_pad` (`modules/deployment_index.py`). A library holds as many
deployments as it needs: the deployment picker lists what it already has,
and saving replaces only the rows of the one being edited. A library filled
in before this existed has no plan rows, so deployments and treatments are
read back from the conditions on its processed sensors instead.

Process gained treatment and run pickers: pick what a batch was recorded
under, process, and every sensor in it is stamped with the conditions and
`deployment_info` flipped to Y. `sensor_rows()` keeps plan rows out of every
sensor listing (Process inventory and metadata, Validate progress, Dataset
extraction); the Metadata tab still edits individual sensors.

## Done (continued)

**Chunk 4, Stage 1 — Annotation & Video Analysis section**
A third top-level sidebar section, wired the same way Sensor Processing and
Machine Learning Analysis are (`main.py:_PANEL_SECTIONS`/`_configure_panel`/
`openPanel`, one shared `extraTopMenu` frame in `main.ui`). Dataset creation
relocated here from Sensor Processing (`btn_dataset` moved sub-menu group
and click handler; the page widget itself never needed to move - stacked-
widget children are flat, menu structure is a `main.py`-side concept).
`modules/page_annotate.py` added as the new page's controller.

**Chunk 4, Stage 2 — the Annotate page**
Built on Inspect's own shape (`ml_tab_inspect.py`): a fixed-width browser on
the left (library -> deployment -> treatment -> sensor, mirroring Inspect's
filter-combo pattern), a detail area filling the rest, itself split half
signal-plot / half annotation panel. Not a refactor of `page_validate.py`,
which stays under Sensor Processing untouched - it is the page slated to
grow into Delineation later, so the two temporarily overlap in what they
do. Reuses `page_validate.py`'s already-standalone `_CsvLoadThread`/
`_NavViewBox`/`_Spinner`/`_decimate` (the same reuse `ml_tab_inspect.py`
already makes) and its channel/exclusion constants, rather than
duplicating them.

A sensor's deployment and treatment are read from the folder tree, not the
index: `raw_sens_data/<deployment>/<treatment>/`, matched case-
insensitively for the `video`/`VIDEO`/etc. folder inside the treatment
folder (`<stem>_vid_*.mp4`). A deployment or treatment level that is
missing (raw files sitting one level higher than expected, or no
deployment folder at all) buckets under "(ungrouped)" rather than being
dropped. This is deliberately independent of `deployment_index`'s
index-based deployments/treatments (Prepare > Study design) - a recording
can be reviewed before any study-design plan exists for it.

The plot is the full nadir/ROI tool ported from `page_validate.py`: left
axis + optional right axis with a secondary view box, the ROI window
combo, the draggable nadir line. "Save + next" (not a separate "Set flag"
button - the flag and annotations commit together with the window) and
"Reset sensor" are the two actions, mirroring Validate's "save and next" /
"reset current".

Two checkboxes, Good and Bad, are mutually exclusive and reflect
`bad_sens` from the library's index (already an `index_schema.py` column);
changing which is ticked and pressing Save + next writes it back. A "No
annotations for this sensor" tick lets a sensor through with no annotation
values entered - without it, Save + next refuses if every annotation
field is blank, so a sensor is never silently skipped.

New modules:
- `modules/annotation_schema.py` - annotation variables (name, label, known
  values), JSON-stored like `sensor_config.py`, defaulting to the four
  columns the old `model_labels.csv` workflow used
  (`overall_passage_type`, `leading_edge_type`, `other_type`,
  `concentric_pump_region`), so nothing already reading them changes.
- `modules/annotation_widgets.py` - `AnnotationValueEditor` (a value combo
  + one "Edit…" button covering add/rename/remove of known values, all in
  one dialog) and `VariableListDialog` (add/rename-label/remove whole
  variables). Not `LevelGrouper` - that groups many observed levels into
  few classes for training; this is "pick or add one value for one
  recording," a different enough shape to warrant its own widget. The
  reused pattern is LevelGrouper's widget-dumb/state-computes split, not
  the class itself.
- `deployment_index.set_row_values(root, file, values)` - the generic form
  of `apply_treatment`'s write (mask by file, widen dtype, save), used for
  one recording's annotations and its manual `bad_sens` flag alike.

The saved window (nadir position + width) writes to the exact locations
`page_validate.py` already uses (`processed_sens_data/nadir_window/*.csv`,
the same index columns), so Dataset creation's segmented mode binds a
window produced by either page unchanged.

Dataset auto-build: "Save + next" also standardises the window (reusing
`page_dataset.py`'s own `_standardise`/`_META_COLS`, so the shape matches
what Dataset creation produces) and appends it to
`processed_sens_data/model_features.csv` - the first save creates the
file, a later save of the same sensor replaces its block rather than
duplicating it. Opening a library reads this file back to know which
sensors are already done (resume), and "next" skips them. Verified end to
end against a 2-deployment/2-treatment scratch library: deployment and
treatment filtering, video matching, dual-axis plotting, the annotation
gate, save/resume, and interoperation with Dataset creation's segmented
bind all pass.

The video button globs `<deployment>/<treatment>/<video-folder>/
<stem>_vid_*.mp4` and launches `exteneral_software/LosslessCut.exe` via
`subprocess.Popen` (disabled with no match; a chooser if more than one) -
no new dependency, no embedded player.

## Chunk 4 — Annotation & Video Analysis page tree (remaining)

### Page — Annotate
Done - see above. Superseded by Chunk 5: the Annotate page gains a
Reporting tab and Delineation/Misclassification are now tasks 6/3 below,
in the new section layout, not standalone additions to the old tree.

## Chunk 5 — app-wide restructure (in progress)

A full information-architecture pass: new top-level sections, several
current tabs promoted to their own sidebar entries, and a handful of
genuinely new pages (blade strike modelling, misclassification, export
animations, biological interpretation, final reporting, data analysis).
Agreed 2026-08-27; worked in the seven-task order below, checking in before
task 4 and wherever else a design call is needed.

**Navigation mechanics** - `main.ui`'s sidebar is one shared slide-out panel
(`extraLeftBox`/`extraTopMenu`) whose sub-button list swaps per section via
`main.py`'s `_PANEL_SECTIONS` dict, and every top-level page is a child of
one `stackedWidget`. Three of today's "pages" are actually a `QTabWidget`
wearing a page's clothes (`page_prepare`/`tabs_prepare`,
`page_ml_training`/`tabs_ml_training`, `page_ml_prediction`/
`tabs_ml_prediction`) - Prepare's two tabs, Train/Evaluate/Deploy, and
Predict/Inspect/Report. Promoting those tabs to sidebar entries does **not**
relocate their content frames (`frame_prepare_sensor`, `frame_train_evaluate`,
`frame_ml_inspect`, etc. all stay exactly where they are in `main.ui`, so
every existing controller keeps working unmodified) - instead each tab's
bar is hidden (`tabBar().hide()`) and a new sidebar sub-button drives
`setCurrentIndex()` on the same tab widget alongside the usual
`stackedWidget` switch. Cosmetic renames (Segmentation, Raw data
processing, Model reporting, ...) are text-only: `objectName`s are left
alone so no Python needs to change for a label change. The three
near-identical `sensorButtonClick`/`mlButtonClick`/`annotationButtonClick`
methods are collapsed into one data-driven dispatch, since six sections now
share the pattern instead of three. New empty pages share one stub-page
builder (title + "not built yet" body) rather than one file each.

**Target sidebar** (submenu order as given):
- Home - unchanged.
- **Mathematical Blade Strike Modelling** (new) - Calculator, Sensitivity
  analysis, Reporting (also writes a JSON of the blade strike calcs for
  Setup and deploy to read).
- **Setup and deploy** (new; absorbs Prepare) - order corrected 2026-08-27:
  Sensor configuration (unchanged content, relabelled), Study design (now a
  sampling-precision calculator - see the task 1 follow-up below), Create
  and edit deployment (renamed from "Initiate deployment" - now also owns
  the deployment/treatment plan itself, see the same follow-up). Open
  question, still unresolved: does the global index need a new flag marking
  which sensor configuration a deployment was locked to, so downstream
  stages can follow it automatically?
- **Sensor processing** (kept) - Raw data processing (current Process +
  Metadata tabs, unchanged), Segmentation (renamed from "Validate &
  segment"; this *is* the shelved Delineation tool - see task 6), Data
  analysis (new, empty until task 7 - passage duration, time-series
  normalisation, barotrauma metrics, acceleration peak finding, ported from
  the old Shiny app's framework).
- **Validate and annotate** (renamed from "Annotation & video analysis") -
  Annotate (gains a Reporting tab - annotation summary rebuilt live from
  what's on the page, becomes a dataset report once sensors are processed/
  validated/annotated), Export animations (new - see task 4), Advanced
  dataset options (renamed from "Dataset creation").
- **Model training** (new; replaces half of "Machine learning analysis") -
  Train, Evaluate, Deploy (promoted tabs, unchanged content), Misclassification
  analysis (new - see task 3), Model reporting (renamed from "Model
  performance", moved in from the old ML section unchanged).
- **Model prediction** (new; the other half of "Machine learning analysis")
  - Predict, Inspect, Report (promoted tabs, unchanged content), Biological
  interpretation (new - see task 5), Final Reporting (new).

Removed: the PyDracula template's dummy Widgets/New pages and the unwired
Save/Exit sidebar buttons (real save lives on each page already - "Save
sensor", "Save deployment plan", Annotate's "Save + next"; real exit is the
custom title bar's close button).

**Cross-app unification, applies throughout** - one save/export/report
pattern reused everywhere a page produces a report (BSM Reporting, Annotate
Reporting, deployment summary, model reporting, final reporting); one
metadata-card pattern (`MetaCard`, already shared); one plot-styling pass
across every live pyqtgraph/matplotlib panel (task 2) rather than
per-page tweaks.

**Task order:**
1. Page structure - done (commit pending). Every new section/button/page
   from the target sidebar above is wired and navigable: `main.ui` gained 4
   new top-level buttons, 14 new sub-menu buttons (8 reused with a text-only
   rename - `objectName`s untouched), and 9 new stub pages (via one script
   doing additive-only text surgery, anchored on a single unmodified read so
   line-number drift couldn't corrupt it - see
   `restructure_ui.py` in a past session's scratchpad if this needs
   repeating). Train/Evaluate/Deploy, Predict/Inspect/Report and Sensor
   configuration/Study design still live in their original `QTabWidget`s
   with content untouched; only their tab bars are hidden
   (`main.py`'s startup block) and new sidebar buttons drive
   `setCurrentIndex()` via `_SUBMENU_TARGETS`. The three old
   `sensorButtonClick`/`mlButtonClick`/`annotationButtonClick` methods
   collapsed into one `submenuButtonClick`/`navigate_to` dispatch keyed by
   `_SUBMENU_TARGETS`; cross-page callbacks (`goto_evaluate`, `goto_inspect`,
   `goto_report`) now go through `window.navigate_to(...)` instead of
   touching a tab widget directly. Found and fixed one navigation bug along
   the way: `navigate_to` needs to swap the *panel-ownership* highlight
   (`Settings.BTN_LEFT_BOX_COLOR`, applied outside `setSelected`/
   `resetStyle`) when it crosses sections, or the previous section's top
   button stays visually "stuck" selected - factored into
   `_swap_panel_ownership()`, shared with `openPanel`. New stub pages use
   one shared builder (`modules/page_stub.py`) rather than a file each.
   Removed the PyDracula template's dummy Widgets/New pages and dead Save/
   Exit buttons, including the now-orphaned `tableWidget` setup line in
   `main.py`. Verified headlessly: every button resolves, every
   `navigate_to`/`openPanel` call is error-free, and screenshots confirm
   correct submenu ordering and content in every section.

   Follow-up (2026-08-27): Model reporting was fully removed (button, page,
   `modules/page_ml_performance.py`, its `MLPerformancePage` wiring) - it
   was a thin, session-less wrapper around the same `EvaluateTab` class
   Model training's own Evaluate page already uses, so 100% redundant once
   Evaluate absorbed reporting duties. Model training's sub-menu is now
   Train, Evaluate and report, Misclassification analysis, Deploy (was
   Train/Evaluate/Deploy/Misclassification/Model reporting). Initiate
   deployment got a real controller
   (`modules/page_initiate_deployment.py`, `InitiateDeploymentPage`) instead
   of a stub: a "Choose library…" button opens a native folder dialog
   (create-or-select in one step, deliberately not the root+combo pattern
   other pages use, since this page's job is to *create* a library rather
   than pick among known ones), a deployment ID + treatment-name rows (read
   from `deployment_index.treatments()` when a plan already exists, editable
   free text otherwise), and "Build folder structure" creates
   `raw_sens_data/<deployment>/<treatment>/VIDEO/` for each - idempotent, so
   revisiting an existing deployment or adding a new one never disturbs
   files already dropped in. Writes a plain-text `deployment_summary.txt`
   into the deployment folder (to be unified with a shared reporting
   pattern once task 2 builds one). Nothing here touches
   `global_sensor_index.csv` - that stays Study design's job since it needs
   full treatment conditions this page doesn't collect - so
   `_load_deployments()` merges index-planned deployments with ones that
   only exist as a folder on disk, or a deployment built here and nowhere
   else would vanish from its own picker on next load (caught by an
   idempotency test, fixed).

   Follow-up (2026-08-27): Setup and deploy's page order and division of
   labour was corrected. Sidebar order is now Sensor configuration, Study
   design, Create and edit deployment - fixed by deleting a runtime
   reorder call added in task 1 (`main.py`'s `move_before("btn_study_design",
   "btn_prepare")`); removing it lets the buttons fall back to their natural
   layout position, which already matched the wanted order once
   `btn_initiate_deployment` and `btn_study_design` were both appended
   after `btn_prepare`. Study design's old deployment/treatment plan form
   moved wholesale to Create and edit deployment (`InitiateDeploymentPage`,
   `_TreatmentRow` moved in from the now-deleted `prepare_tab_study.py`):
   the deployment-fields form (site, pump/turbine model, type) plus full
   per-treatment conditions (head, flow, BEP, RPM, runs) sit alongside the
   library picker and folder-builder already there, and "Save deployment
   plan" now does both jobs in one action - `deployment_index.save_plan()`
   writes the index rows *and* the same call builds
   `raw_sens_data/<deployment>/<treatment>/VIDEO/`, idempotently. Study
   design itself was rebuilt as a small sampling-precision calculator
   (`modules/wilson_calc.py` + `modules/prepare_tab_precision.py`,
   `PrecisionCalcTab`): given a hypothesised strike rate and a planned
   sample size it shows the Wilson score interval that size would achieve
   (same formula the old MVP app's `bsm/core/model.py` uses for its
   observed-proportion CI, `wilson_lo`/`wilson_hi` - lifted out as a
   standalone function since planning uses a hypothesised rate rather than
   an observed one) plus a small table at half/double/quadruple that N, to
   make the sample-size-vs-precision tradeoff concrete without requiring
   the user to understand the statistics. Deliberately one simple tool for
   now, not a full planning suite; a later hook (not built) would let the
   expected rate come from a treatment's Blade Strike Modelling output
   instead of a typed guess, once task 5 exists. Verified end to end
   against a scratch library: saved a deployment with full treatment
   conditions, confirmed the index rows and folder tree both landed
   correctly, and confirmed re-selecting the deployment reads the same
   conditions back.
2. The smaller requested changes - done (2026-08-27).

   Live-plot margins + export: exactly three live pyqtgraph plots exist
   app-wide (Segmentation `page_validate.py`, Annotate `page_annotate.py`,
   Model prediction > Inspect `ml_tab_inspect.py`), each already sharing one
   construction pattern. New `modules/plot_style.py` is the one place that
   pattern's styling now lives: `reserve_top_margin()`/
   `set_right_axis_active()` fix the "top and right have no margin"
   complaint - pyqtgraph only reserves outer space on a side with a
   *visible* axis, so the fix keeps the right axis always shown (blank
   when no second channel is plotted, real values when one is) instead of
   the hideAxis()/showAxis() toggle each page did directly, and reserves a
   permanently-blank top strip the same way; both replace the matching
   hideAxis/showAxis call sites 1:1 in all three files. `add_export_button()`
   attaches a small "Export ▾" menu (PNG 300dpi / SVG) to each plot's
   toolbar row; `build_export_data()` is the shared shape every page's
   `_export_data()` callback returns (current view range, left channel
   black, right channel red); `render_export_figure()` redraws it with
   matplotlib for a fixed print style - white background, black axes -
   independent of the live dark-theme colours, at a user-chosen size in cm
   (default 16x10). Verified: rendered a real export at 300dpi and as SVG,
   confirmed the white/black/black/red styling visually, and screenshotted
   a live plot with real data loaded to confirm the margin fix (breathing
   room now visible at the top and right of the curve).

   Annotate's Reporting tab: `page_annotate.py`'s content is now a
   `QTabWidget` (Annotate / Reporting) - `_build_annotate_tab()` is the
   renamed original body, unchanged. Reporting shows a `MetaCard` summary
   (sensors in index, in dataset, not yet in dataset, flagged bad) and a
   by-annotation-variable value-count table, both scoped to the whole
   library rather than the browser's current deployment/treatment filter
   (a report should cover the library, not whatever happens to be filtered
   on screen) and refreshed every time `_populate_sensor_table()` runs -
   i.e. live, on every library/filter change and every save. "Generate
   dataset report" writes the same summary as Markdown to
   `processed_sens_data/annotation_report.md` - deliberately simple for
   now (plain file write, no shared framework yet); once a broader
   reporting pattern exists (BSM Reporting, deployment summary, Model
   reporting, Final Reporting all want one) this should move onto it
   rather than staying a one-off. Verified against the real "Library 1"
   working library (105 sensors, 2 flagged bad, 0 in dataset yet) - note
   this left a real `annotation_report.md` in that library as a
   side-effect of testing; harmless (it's exactly the file the feature is
   meant to produce) but flagged to the user rather than deleted.

   Sensor config global-index flag (from task 1's Setup and deploy note) is
   still an open question, deferred to whenever Setup and deploy's own
   build starts - not blocking anything so far.
3. Misclassification analysis (Model training) - done (2026-08-27),
   `modules/page_misclassification.py`. Built as planned in the old Chunk 4
   note: Inspect-based, `AnnotationValueEditor`/`VariableListDialog` reused
   verbatim for the Labels box, corrections written to a `_corrected` copy
   of the training dataset. The model-package misclassified/cv_predictions
   data existed already (`ml_model_library.discover_models()`); what didn't
   exist was a path to the actual *signal* for a misclassified file, since
   a deployed model ships no training data of its own - solved via
   `train_config.json` in the `BladeStrikeModel_v<v>/` package, which
   `ml_train_state.build_config()` already writes with the exact dataset
   path training used and `ml_model_library.export_model_report()` already
   copies into every deployment; a session-trained model reads
   `TrainingState.dataset_df` directly instead (no re-read needed). The
   long-format training CSV carries one row per (file, time_s), with every
   annotation column constant across a file's rows, so a correction is a
   masked update exactly like `deployment_index.set_row_values` - confirmed
   against the real 226k-row dataset before relying on it. Annotation
   columns are looked up under both StrikeWorks' own `annotation_schema`
   names and the MVP-legacy names the training pipeline also recognises
   (`overall_passage_type`/`passage_type`, `leading_edge_type`/
   `leading_type` - mirrors `ml_state.ANNOTATION_COLUMNS` and
   `ml_train_state.leading_type_column()`, centralised into one
   `_resolve_column()` rather than left as scattered tuples). Leaving the
   page after a correction - whichever button was actually clicked -
   is redirected by `MainWindow.navigate_to()` to Model training > Train
   with the corrected dataset already loaded, after a notice that the
   model should be retrained before its next deployment.  Verified against
   the real deployed models (multiclass1: 99 misclassified of 247; binary1:
   565 cv predictions) - model discovery, the misclassified list, signal
   loading with the model's actual channel set, and Labels reading the
   file's real annotation values (confirmed against
   `Pumpflow_2024_and_2026_datatset_.csv`) all check out; the save/
   leave-redirect path was verified against a small scratch dataset to
   avoid writing into real project data during testing.

   Follow-up (2026-08-27): Evaluate's per-recording error table
   (`tbl_err`) removed - `lbl_mis`'s summary line (total/FP/FN) stays, now
   with a one-line note pointing to Misclassification analysis for detail,
   since that table duplicated what this page already builds. Misclassification
   analysis's own table now takes half the page (`split.setSizes([1, 1])`,
   was `[1, 3]`) and gained a Video column: a `{stem: [paths]}` index built
   once per model switch (one recursive walk across every configured
   library's `raw_sens_data/`, matching on the same `<stem>_vid_*.mp4`
   pattern Annotate uses) rather than once per misclassified row, since a
   file's library isn't known up front and 99 separate walks would be slow.
   Double-clicking a Video cell opens it in LosslessCut, same chooser-on-
   multiple-matches behaviour as Annotate. Caught and fixed a real bug
   here: the double-click handler originally indexed `self._rows[item.
   row()]`, but the table is sortable, so a sorted visual row no longer
   lines up with that list's insertion order - fixed by reading the file
   stem from the clicked item's own `UserRole` data instead (the same safe
   pattern row-selection already used) and looking it up in a
   `{file: matches}` dict built alongside the table. "Generate
   misclassification report" writes the current table (including video
   presence) plus a "changes made this session" section to
   `<dataset>_misclassification_report.md` beside the training dataset -
   corrections are now tracked as `{file, variable, old, new, when}` as
   they're saved, not just a bare has-changed flag, specifically so the
   report can show a real diff; an empty session still produces a valid
   report ("no corrections made"), not an error. Verified end to end
   against the real deployed models and libraries: video index found 534
   videos, 49 of 99 misclassified files matched one, the double-click
   fix confirmed against a mismatched pre-fix row, and a real report
   generated correctly (then removed - it was a same-session test
   artifact, not requested output, and landed in the real `input_data`
   folder next to the training dataset).
4. Export animations page - done (2026-08-27),
   `modules/page_export_animations.py` (GUI) +
   `modules/video_sync.py` (pure logic, no Qt). Found the reference script
   at `Scripts/Time series video sync/video_sync.py` (431 lines) - a
   synced sensor-graph overlay (pressure black, accel magnitude red,
   scrolling window with a cursor line) burned frame-by-frame into
   high-speed video footage, plus a text overlay (pump, shaft speed,
   camera, sensor) and optional logo. Ported faithfully into
   `video_sync.py`'s `SyncOptions`/`build_cursor_arrays`/
   `make_graph_strip`/`build_text_lines`/`overlay_text`/`process_video`,
   every module-level constant the script hardcoded now a parameter driven
   by the page's Text inputs/Code options boxes. New runtime dependency:
   `opencv-python` (video read/write; not previously installed), added to
   `requirements.txt` - Pillow was already present transitively via
   matplotlib.

   Sync mechanics differ from the original by necessity: the script
   anchored on a `frames.txt`-supplied row index into an external combined
   dataset; here `nadir_time_s` comes straight from the sensor's own
   processed CSV (same `pres_min.time.` index column Annotate/Validate
   already read), so only the *video frame number* the nadir appears at
   needs entering by hand (Code options' "Sync frame") - no automatic
   video/sensor alignment exists or was asked for.

   Page skeleton matches Annotate as specified: same library/deployment/
   treatment/sensor+video browser (adapted rather than shared - see the
   docstring note on why Annotate wasn't refactored to share it), Text
   inputs in place of Annotations, Code options (sync frame, real fps,
   graph window, zoom, add-labels toggle) in place of Notes. The Signal
   container is a `QStackedWidget`: the plotted signal until a video's
   been processed, then a `QMediaPlayer`/`QVideoWidget` with play/pause
   for it. Processing runs on a `QThread` (`_VideoSyncWorker`) - a real
   clip's frame-by-frame matplotlib render is easily minutes of work, and
   a Cancel button (added once the worker's cancellation path was proven
   working) stops it cleanly. "Process" renders to
   `processed_video/<stem>_synced.mp4` and always saves its config
   alongside (`<stem>_sync_config.json` - text fields, sync frame, code
   options) so a re-render never drifts from what's shown; "Save" persists
   an edit without paying for a render. `processed_video/` is one
   app-root-relative folder, not per-library, matching how `models/`
   already works (`Path(__file__).parent.parent / "processed_video"`, not
   a bare relative path that would depend on the process's working
   directory) - the sensor list's "Synced" column reads it back so
   previously-exported sensors are visible without reprocessing.

   Verified in three tiers rather than only end-to-end, since a real
   clip's render is slow: `video_sync.process_video()` against a tiny
   synthetic video + sensor dataframe (confirmed frame count/dimensions,
   extracted a frame and visually confirmed the graph strip and text
   overlay render correctly); `_VideoSyncWorker` against the same
   synthetic inputs (progress signals, `finished_ok`, and the cancellation
   path all fire correctly); the page's browser/config/nadir-detection
   wiring against the real library set (257 sensors across 7 libraries,
   config save/reload round-trips correctly). Caught and fixed one bug in
   the process: `apply_section_defaults()` runs after `_build()` and
   force-shows every widget in an open Section, silently undoing the
   Cancel button's constructor-time `setVisible(False)` - fixed by
   reasserting it in `_set_loaded_enabled()`, which runs after that pass
   settles (and also correctly re-hides it when a new sensor loads while
   a previous run's Cancel button was still showing).

   Follow-up (2026-08-27), two Annotate fixes plus a substantial Export
   animations round:

   Annotate - the "show bad sensors" highlight interacting wrongly with
   the green/counter was real: a sensor that's both flagged bad *and*
   already saved to the dataset used to fall straight into the plain-green
   "done" bucket, losing its bad flag visually and in the "In dataset"
   count the moment it was saved - there was no way to tell a saved
   sensor was one that still needed attention. Fixed with a third state:
   saved+bad now renders amber (`WARN`), distinct from plain green
   (saved, not bad) and red (bad, not yet saved); the counter grew a
   "(N bad)" suffix when any saved sensor is flagged; both the colour and
   the suffix still respect the "Show bad sensors" toggle, so switching it
   off returns saved-bad sensors to plain green exactly as before. Traced
   this empirically against the real library (which only had one bad
   sensor at the time, not enough to reproduce the reported mismatch) by
   building a 3-sensor scratch library with a pre-flagged bad sensor and
   walking it through save/toggle/filter sequences.

   Also added a second save action: "Save annotations" writes the flag/
   annotation values/notes via the same `deployment_index.set_row_values`
   path `_save_and_next` already uses, but skips the ROI window extraction
   and dataset append and doesn't advance to the next sensor - for working
   through a library's annotations/notes in one pass without also
   finalising every window, or jotting a note mid-review without losing
   your place. Both save paths now share one gate (`_has_content_to_save`)
   that also accepts a note on its own as valid content to save, not just
   a formal annotation value or the "no annotations" tick.

   Export animations - the signal plot used to auto-range to the sensor's
   entire recording (hundreds of seconds), which is useless for finding a
   sync point: cropped it to nadir-centred, sized to the matched video's
   own duration (read from the video's own metadata via
   `cv2.VideoCapture`, no frames decoded) capped at 15s, with a shaded
   `LinearRegionItem` marking the assumed video span - shaded at the
   video's *true* duration even past the 15s view cap, since that's the
   thing being aligned, not the view. A "Video: N frames, D.DDDD s
   (fps)" label above the plot gives the frame-to-elapsed-time arithmetic
   needed to convert a moment spotted in LosslessCut into a frame number
   for the Sync frame field. Also added: Frame nudge (px) - the original
   script's `VIDEO_NUDGE_PX`, deliberately left out of the first pass, now
   exposed; an overlay-image picker (Browse…/Clear + opacity) for the
   original script's optional logo, wired into `SyncOptions.logo_path`/
   `logo_opacity` which already existed but had no UI; and Pump/Passive
   sensor now autofill the same way Shaft speed already did - Pump from
   the index's `pump_turbine`/`type` columns (the same fields Create and
   edit deployment writes), Passive sensor from `sensor_config.active()` -
   both stay plain editable text, and a value already saved to a sensor's
   `_sync_config.json` always wins over the autofill. Verified against a
   real sensor with a real video (709 frames, 11.8167s, 60fps): label,
   crop, and shading all matched expected math; separately forced a 30s
   synthetic duration to confirm the 15s view cap while the shading still
   showed the full 30s. One thing worth flagging: this testing produced
   two `processed_video/*_sync_config.json` files against real sensors
   (generic test values - blank pump, hardcoded default camera/sensor
   text) that got auto-committed at some point outside this session's
   control; both were removed as part of routine test cleanup once
   noticed, not left in place.
5. Blade strike modelling port, and finalise Model prediction - done
   (2026-08-27). Brought the mathematical model over from the old MVP/
   Shiny app (`old_bsm_app_mvp/bsm/`), then built Biological
   interpretation on top of it.

   `modules/bsm_model.py` is a faithful, unchanged-maths port of
   `core/model.py`'s `compute()`/`cen_regression()` (geometric/
   hydrodynamic collision-probability integral over 200 blade-radius
   points, mutilation-fraction regression by species/length-to-diameter
   regime) - the one deviation is the observed-strike confidence interval
   now goes through the shared `wilson_calc.wilson_interval()` (the same
   function Study design uses) instead of duplicated inline maths.
   `modules/bsm_state.py` is a `BSMState(QObject)` with a `calculated`
   signal, the same "one state object, several pages react to its signal"
   shape `PredictionState`/`TrainingState` already use, plus
   `LATEST_RESULT_PATH` - the well-known JSON location for the
   Setup-and-deploy handoff below. `modules/bsm_figures.py` ports
   `plotting.py`'s two bar charts and the sensitivity line+scatter plot,
   redrawn with the app's own dark theme (`ml_figures.py`'s
   `style_axes`/`fg_colour`/`_grid`/`_PALETTE`) rather than the old app's
   white-on-navy styling. `modules/bsm_io.py` ports `io.py`'s CSV/PNG
   export helpers unchanged.

   Three pages, one shared `BSMState` owned by `MainWindow`:
   - **Calculator** (`page_bsm_calculator.py`) - Fish/Pump/Blade profile
     (editable table, cubic-spline interpolated, minimum 2 rows)/Observed
     strike data groups as `Section` panels (replacing the old app's
     `QGroupBox`es), full-field validation before Calculate enables,
     results table (CEN row always, Observed row + Wilson CI line when
     included) and the two bar charts. Deliberately still starts blank
     (species unselected, no seeded numbers) - a faithful port, not a
     redesign.
   - **Sensitivity analysis** (`page_bsm_sensitivity.py`) - reacts to
     `BSMState.calculated` rather than being called directly by
     Calculator, so it is populated whether Calculator ran on this visit
     or the state already held a result from an earlier one; wf swept
     -3.5..+3.5 m/s in 0.1 m/s steps, cubic-spline fit, "Save sweep..."
     CSV+PNG export via `bsm_io.export_sensitivity`.
   - **Reporting** (`page_bsm_reporting.py`) - "Export report package..."
     writes CSV+PNGs (`bsm_io.export_results`) plus a self-contained
     HTML report. The report deliberately does NOT port the old app's
     `report/builder.py` (an elaborate MathJax-equation methodology
     document built from string Templates) - that would give BSM its own
     visual language; instead `modules/bsm_report.py` reuses
     `ml_report.py`'s generic building blocks (`_kv_table`/`_data_table`/
     `_img_tag`/`wrap_html_document`/`_DARK`) so a BSM report reads as
     the same family of document as a prediction report. On every new
     result the page also writes `bsm_state.LATEST_RESULT_PATH` - a
     small JSON (timestamp, species, CEN/observed Pco/Pm/S, Wilson CI) -
     automatically, no separate publish step.

   **Biological interpretation** (`page_bsm_biological.py`, promoted from
   its Chunk 5 stub) is three independent tools rather than one
   mega-table trying to do everything the roadmap asked for at once:
   per-treatment comparison (each treatment's data-driven strike rate
   from `PredictionState.summary`, reacting to `run_finished`, alongside
   the single mathematical Pco estimate for the same setup - shows
   over/under-prediction per treatment); a mortality/survival estimator
   built on a new `bsm_model.recompute_mortality(res, species,
   eel_vcrit=None, lf=None, threshold=None)` that re-runs the mortality
   integral from an existing `compute()` result under a different
   species/critical velocity/threshold while holding the hydrodynamic
   exposure (`Pco_arr`/`vstrike_arr`/`r_arr`) fixed - `threshold=None`
   reproduces `compute()`'s own continuous-fMR `Pm` exactly (verified:
   0.7177395399249237 both ways), a numeric threshold makes fMR binary
   (lethal iff the continuous fraction meets or exceeds it) so each
   species uses its own regression and critical velocity independently of
   the others; and a manual strike/no-strike proportion checker
   (`wilson_calc.wilson_interval`) for a quick count-based sanity check
   independent of both models.

   **Setup and deploy > Study design handoff**: `prepare_tab_precision.py`
   gained a "Load from Blade Strike Modelling" button next to the
   expected-strike-rate field that reads `LATEST_RESULT_PATH` and fills
   the field from the CEN Pco estimate (the a-priori planning figure, not
   an observed rate that does not exist yet before data collection) -
   deliberately reads the JSON rather than taking a live `BSMState`
   reference, so Study design stays decoupled from whether the BSM pages
   have even been visited this session.

   Verified end-to-end headlessly: `MainWindow()` construction (all four
   new page controllers plus every pre-existing page), a full Calculator
   run flowing through to Sensitivity/Reporting/Biological via
   `BSMState.calculated`, the Reporting page's JSON write, and the Study
   design "Load from Blade Strike Modelling" round trip pulling the CEN
   value into the precision calculator. `content_bsm_calculator`/
   `content_bsm_sensitivity`/`content_bsm_reporting`/`content_biological`
   removed from `main.py`'s `_stub_pages`; `content_data_analysis` (task
   7) and `content_final_report` (not part of task 5's scope) remain
   stubs.

   Longer-term (not this pass): replace the regression's assumed strike
   distribution with the concentric strike locations the blade-strike model
   predicts, for direct x%-mortality-from-x%-strikes-in-region-x estimates.

   Follow-up (2026-08-27): four fixes, none part of task 5/6/7 but raised
   while working nearby.

   `_min` files were appearing in Export animations' sensor list. Root
   cause: Export animations carried its own copy of Annotate's library/
   deployment/treatment-scan logic (copy-paste, not shared code), and its
   copy's exclusion list (`{"global_sensor_index.csv", "model_features.csv"}`
   / `("_nadir_window",)`) had silently drifted from the canonical one in
   `page_validate.py` (`_min`, `_delineated`) - both of Export's own
   exclusions were actually no-ops (`model_features.csv` and any
   `_nadir_window` file live outside the `processed_sens_data/csv/` folder
   the scan globs, so neither was ever reachable), while the exclusions
   that mattered were missing. Fixed at the root: new `modules/
   library_widgets.py` with a single `LibrarySelector(QWidget)` - the
   Library/Deployment/Treatment combo panel plus `list_sensor_csvs()`
   (canonical exclusions, now defined in `library_widgets.py` itself with
   `page_validate.py` importing them rather than the reverse, to avoid a
   page_process/page_validate/library_widgets import cycle) and
   `video_matches_for()`. Annotate and Export animations both now embed
   this one widget instead of their own copies; `page_misclassification.py`
   and `page_initiate_deployment.py`'s imports of the old `_RAW_DIR`/
   `_VIDEO_FOLDER_NAME` constants (previously re-exported from
   `page_annotate.py`) were repointed at `library_widgets.py`, their new
   home. Also caught and fixed while wiring this up: `LibrarySelector`'s
   deployment/treatment combos connected `currentIndexChanged` (which
   passes an int) directly to `filters_changed.emit` (a no-arg signal) -
   harmless while nothing but blockSignals-guarded repopulation touched
   the combos, but a `TypeError` the instant a user (or a test) actually
   picked a different deployment/treatment; fixed with a lambda that
   drops the index argument. Verified with a scratch library carrying
   `_min`/`_delineated` CSVs (both now excluded from `list_sensor_csvs()`)
   and by driving real combo selection changes (not just default state)
   through both pages. One transparency note: a scratch-library test run
   that hit the `filters_changed` bug above crashed before its cleanup
   step restored `settings.get_libraries_dir()`, leaving the persisted
   `~/.hifistrike_settings.json` pointed at the (now-deleted) scratch
   folder rather than the real RAPID_libraries path - caught immediately
   via a screenshot showing an empty Library combo, and restored by hand
   before finishing this pass.

   Per the same "one library style" request, Process (Sensor processing >
   Raw data processing) moved off its `QTreeView` file browser onto the
   same `LibrarySelector`. This one needed a `main.ui` edit - Designer's
   `grp_library` QGroupBox (`tree_library` + its own "Change libraries
   folder…" button) replaced with a bare `frame_process_library` at the
   same grid cell, `ui_main.py` regenerated via `build_ui.py --force` -
   plus adapting `page_process.py`'s scan target from "whatever tree node
   the user clicked" (arbitrary folder depth, `rglob`-scanned) to "the
   folder implied by the deployment/treatment combos" (`_scan_target_dir()`:
   raw root, or raw root/deployment, or raw root/deployment/treatment).
   Explicitly a narrowing of what was possible before (no more picking an
   arbitrary intermediate subfolder) - the user chose this over extending
   `LibrarySelector` with a folder-depth mode, given it matches Annotate/
   Export's shape and the tree never supported isolating an "(ungrouped)"
   top-level file from its siblings' subfolders either (rglob always
   recursed from wherever it was pointed). `_DirsOnlyProxy` (the dirs-only
   tree filter, shared with Validate's own file tree and Process's
   still-tree-based Metadata tab) also moved into `library_widgets.py` as
   part of untangling the import cycle. Verified with a scratch library
   spanning two deployments and two treatments: unfiltered scan found all
   three planted files, narrowing to one deployment found two, narrowing
   further to one treatment found one - and Process's `lib_selector` is
   confirmed the identical class Annotate/Export use.

   Predict (Model prediction) had three requested changes. (1) Switching
   between binary/multiclass model variants in the same folder (e.g.
   `binary1_1.joblib`, `binary1_2.joblib`, `binary1_3.joblib`) was not
   possible - `PredictionState.load_models_from_dir()` globbed for
   `binary*.joblib`/`multiclass*.joblib` and always silently took the
   alphabetically-first match, with no way to pick another. Fixed by
   splitting model loading into folder-discovery (`bin_candidates`/
   `mc_candidates` properties) and model-application
   (`select_bin_model()`/`select_mc_model()`, the latter accepting `None`
   for binary-only), and adding "Binary"/"Multiclass" combo pickers to the
   Model card in `ml_tab_predict.py` that list every discovered variant.
   Verified with a scratch models folder (3 binary + 2 multiclass
   variants): switching either combo updates `state.bin_model_path`/
   `mc_model_path` correctly, including switching multiclass back to
   "(none - binary only)". (2) The "Compatibility" checklist panel
   (`CheckList` widget, permanently visible under the Dataset card) is
   removed - `PredictionState.run_prediction()` already called
   `validate()` and refused to run when not ready, so the checks were
   already re-run at Run time; the panel was redundant, gating-only
   friction. `run_prediction()` now emits a "Checking model, dataset,
   channels, sequence length…" status message before validating, and on
   failure builds the status text from every failed check
   (`self.checks`) rather than one generic "not ready" line; the Run
   button itself is no longer gated on `state.ready` (only disabled while
   a run is actually in progress) so it is always available to press and
   find out why, rather than sitting disabled with no visible reason.
   `_on_run_failed` shows this itemised pre-flight message in full but
   keeps the old last-line-only condensing for genuine worker-subprocess
   tracebacks (still shown in a modal detail dialog, which the pre-flight
   case skips entirely - it's an expected, not exceptional, outcome).
   (3) The "Outputs: strike probability, confidence, predicted class;
   treatment summaries with Wilson 95% CIs." label under Prediction
   configuration is removed as redundant restating of what Results by
   treatment / Prediction figures already show.
6. Delineation tool (Segmentation page) - the design already agreed in the
   old Chunk 4 note: 7 windows covering the full time series, start/end
   trim handles placed first with everything else relative to them, nadir
   window fixed-width and centred, pre-/post-nadir windows fixed duration
   (default 300 ms), ROI 1/2 and 6/7 the remaining handles, same bad-sensor
   flag behaviour as Annotate, anticipates the old Shiny app's delineation
   and passage summary.
7. Data analysis page (Sensor processing) - passage durations, time-series
   normalisation, barotrauma metrics, acceleration peak finding, per the
   old Shiny app's framework.

## Deferred — multiple collision detection

Assessed, not implemented. The models are whole-window classifiers and
`predict_worker._pad()` truncates anything longer than
`max_sequence_length`, so a 1-minute file would be classified on its first
~200 ms only.

Proposed: sliding-window inference reusing the existing models unchanged.
Slide the 401-sample window at a hop (~100 samples / 50 ms), score each
position with the binary model to build a probability trace, peak-pick
above threshold with a refractory period of about one window to get
discrete events, then run the multiclass model on each detected event.
Add as `--mode scan --window --hop` in `predict_worker.py`, emitting the
trace plus an events CSV; Inspect can already plot the trace over the
signal.

Two calibration caveats: training windows were nadir-centred, so
off-centre positions are out of distribution and the trace will be noisy
between events; and the deployed `optimal_threshold` was tuned on roughly
balanced centred windows, whereas scanning is overwhelmingly negative, so
precision will drop and the threshold needs re-tuning against passages with
known multiple collisions.

## Future — end-to-end pipeline test bed

Not started. A repeatable full run through every stage, against the
"Testbed" dummy library (single treatment, small enough to reprocess from
raw on every run):

  build a fresh index (Prepare) -> process sensors -> validate and
  annotate sensors (Annotate) -> report -> train model -> evaluate ->
  misclassification analysis -> retrain -> report -> deploy -> predict ->
  report

The point is a single library that can be blown away and rebuilt from raw
files each time something upstream changes, so a change to (say) the
sensor parser or the index schema surfaces its downstream breakage
immediately rather than being caught later by hand. Likely shape: a script
or a "Run full pipeline" dev action that drives each page's existing
worker/state objects in sequence against the Testbed library, asserting
each stage's expected output exists before moving to the next - not a new
UI, mostly wiring together what already exists per page.
