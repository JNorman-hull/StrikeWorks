# StrikeWorks roadmap

Outstanding work, in the order agreed. Chunks 1 to 3 are done. Chunk 4's
sidebar section and its Annotate page are done; Delineation is shelved and
the Misclassification tool is not started. Each chunk is independent enough
to be picked up cold from this file plus the code.

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
Half signal plot / half annotation panel, per the roadmap spec below, built
fresh (not a refactor of `page_validate.py`, which stays under Sensor
Processing untouched - it is the page slated to grow into Delineation
later, so the two temporarily overlap in what they do). Reuses
`page_validate.py`'s already-standalone `_CsvLoadThread`/`_NavViewBox`/
`_Spinner` (the same reuse `ml_tab_inspect.py` already makes) and its
channel/exclusion constants, rather than duplicating them.

New modules:
- `modules/annotation_schema.py` - annotation variables (name, label, known
  values), JSON-stored like `sensor_config.py`, defaulting to the four
  columns the old `model_labels.csv` workflow used
  (`overall_passage_type`, `leading_edge_type`, `other_type`,
  `concentric_pump_region`), so nothing already reading them changes.
- `modules/annotation_widgets.py` - `AnnotationValueEditor` (a combo of
  known values + add-new + a rename/remove dialog) and
  `VariableListDialog` (add/rename-label/remove whole variables). Not
  `LevelGrouper` - that groups many observed levels into few classes for
  training; this is "pick or add one value for one recording," a different
  enough shape to warrant its own widget. The reused pattern is
  LevelGrouper's widget-dumb/state-computes split, not the class itself.
- `deployment_index.set_row_values(root, file, values)` - the generic form
  of `apply_treatment`'s write (mask by file, widen dtype, save), used for
  one recording's annotations and its manual `bad_sens` flag alike.

The saved window (nadir position + width) writes to the exact locations
`page_validate.py` already uses (`processed_sens_data/nadir_window/*.csv`,
the same index columns), so Dataset creation's segmented mode binds a
window produced by either page with no changes to `page_dataset.py` -
verified end to end against the Chunk 3 scratch library.

The video button globs `<library>/video/<stem>_vid_*.mp4` and launches
`exteneral_software/LosslessCut.exe` via `subprocess.Popen` (disabled with
no match; a chooser if more than one) - no new dependency, no embedded
player.

## Chunk 4 — Annotation & Video Analysis page tree (remaining)

### Page — Annotate
Done - see above.

### Page — Delineation (shelved)
`page_validate.py` ("Validate & segment") stays under Sensor Processing,
unchanged, until this is picked up. Full time-series delineation:
- 7 windows covering 100% of the time series
- the start/end grab handles are the trim markers; the user places these
  first and everything else moves relative to them, staying inside the trim
- the nadir window is always centred on the nadir and keeps its fixed-width
  behaviour
- pre- and post-nadir windows are fixed durations, default 300 ms, same
  options as the nadir window
- the remaining handles move ROI 1/2 and 6/7
- same "Show flags" / `bad_sens` behaviour as Annotate
- anticipate the delineation and passage summary from the old Shiny app

### Misclassification tool (not started)
Inspect used as the base again: list misclassified files, click through,
view the signal, change a file's classification. Collected changes are
written to a copy of the dataset in the input folder suffixed `_corrected`.
Reuses Annotate's `AnnotationValueEditor`/`VariableListDialog` for the
Labels box - already shaped for this, not a second implementation. The
misclassified-file list and its columns already exist in every deployed
model package (`BladeStrikeModel_v<v>/{kind}_misclassified.csv`,
`{kind}_cv_predictions.csv` - see `modules/ml_model_library.py`), so this is
mostly wiring, not new data plumbing.

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
