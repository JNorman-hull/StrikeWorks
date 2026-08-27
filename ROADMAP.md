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
- **Setup and deploy** (new; absorbs Prepare) - Study design (95% CI
  calculator, planned-sensor-count input, optional blade-strike-model
  result input - may cover only one treatment), Sensor configuration
  (unchanged content, relabelled), Initiate deployment (new - save the plan,
  write a basic summary report). Open question, revisit when this task
  starts: does the global index need a new flag marking which sensor
  configuration a deployment was locked to, so downstream stages can follow
  it automatically?
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
2. The smaller requested changes: *(next up)* Annotate's Reporting tab content, the
   live-plot margin fix + PNG(300dpi)/SVG export menu (size in cm, default
   16x10, white bg/black axis/black pressure/red higacc) applied to every
   live plot, and any other small items called out inline above.
3. Misclassification analysis (Model training) - see the old Chunk 4 note
   above for the approach (Inspect-based, `_corrected` dataset copy, reuses
   `AnnotationValueEditor`/`VariableListDialog`, model-package
   misclassified/cv_predictions CSVs already exist).
4. Export animations page - **check in before starting.** Same skeleton as
   Annotate (library, sensor/video list, Signal/Notes-shaped boxes) but the
   annotations box becomes the video-animator's text-field inputs and the
   notes box becomes its code/process options (frame sync, labels, ...);
   single sensor only for now; Process + Save buttons; processed video plays
   (play/pause) in the Signal container; output goes to a library-independent
   `processed_video/` folder that the page also reads to list what already
   exists. Ports `video_sync.py`.
5. Blade strike modelling port, and finalise Model prediction - bring the
   mathematical model over from the old MVP/Shiny app (Calculator,
   Sensitivity analysis, Reporting/JSON handoff), then Biological
   interpretation: compare data-driven vs. mathematical blade-strike
   predictions per treatment, generate mortality/survival estimates from
   the BSM output's empirical regressions with a user-adjustable critical
   mortality threshold, support multiple species (each its own regression +
   critical velocity), and the simple strike/no-strike proportion input.
   Longer-term (not this pass): replace the regression's assumed strike
   distribution with the concentric strike locations the blade-strike model
   predicts, for direct x%-mortality-from-x%-strikes-in-region-x estimates.
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
