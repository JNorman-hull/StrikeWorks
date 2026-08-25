# StrikeWorks roadmap

Outstanding work, in the order agreed. Chunks 1 to 3 are done; 4 is not
started. Each chunk is independent enough to be picked up cold from this
file plus the code.

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

## Chunk 4 — Annotation & Video Analysis page tree

New top-level section mirroring Machine Learning Analysis.

### Page — Annotate
Built on the Inspect tab as its base (share the code, do not duplicate):
- half the width is the signal plot, the other half an annotation panel
- a button opens `LosslessCut.exe` from `exteneral_software/` (note the
  existing folder spelling) against the matching video in the library's
  `video/` folder, named `<sensor_file>_vid_*.mp4`
- the nadir validation / quick segmentation tool moves here from Sensor
  Processing, so a user can check the video, segment and validate the
  sensor file, and enter annotations in one pass
- annotation variables default to the current set but are user
  add/remove/rename — reuse `LevelGrouper` and the annotation editing
  built for the misclassification tool rather than a second implementation
- checkboxes "Show flags"; Bad unticked by default; "Set flag" writes
  `bad_sens` (default Good) back to the file
- dataset creation becomes largely redundant here: the global index already
  exists from Sensor Processing, and segmented windows can be bound as they
  are produced

### Page — Delineation (replaces Sensor Processing's segment page)
Full time-series delineation:
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

### Misclassification tool
Inspect used as the base again: list misclassified files, click through,
view the signal, change a file's classification. Collected changes are
written to a copy of the dataset in the input folder suffixed `_corrected`.
The same annotation-editing component serves the Labels box.

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
