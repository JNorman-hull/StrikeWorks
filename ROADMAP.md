# StrikeWorks roadmap

Outstanding work, in the order agreed. Chunks 1 and 2 are done and
committed; 3 and 4 are not started. Each chunk is independent enough to be
picked up cold from this file plus the code.

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

## Chunk 3 — Prepare page: sensor configurations

New content on the existing `page_prepare` (currently an empty placeholder
in `main.ui`). Two tabs.

### Tab 1 — Sensor configuration

Select the session's sensor type; the choice drives raw import and
processing. Ship two configurations and make adding a third a data edit,
not a code change.

`rapid` (the current setup — derive the values from
`modules/rapid_functions.py`, which currently hardcodes them):
- sampling rate 2000 Hz
- two input files per recording: `.imp` and `.hig`, paired by stem
- filename pattern `SENSOR-MMDDHHMMSS` (`_FNAME_RE` in `page_process.py`)
- channel set = `DEFAULT_CHANNELS` in `ml_train_state.py`

`micro_eel` (anticipated, not yet real):
- sampling rate ~6000 Hz
- likely a single file per recording rather than a pair
- file extension(s) TBD
- packet size / parser differences TBD

Expose now: sensor name, sampling rate, files-per-recording, file
extensions, channel list, filename pattern, packet size. Leave a clear
code point for the per-sensor parser; `rapid` keeps calling
`rapid_functions.process_imp_hig_direct`.

Also expose interpolation: resample a lower-rate sensor up to a target rate
(e.g. 100 Hz to 6000 Hz), since model input length depends on rate.

Where the current hardcoding lives, for the port:
- `modules/rapid_functions.py` — the RAPID parser and its constants
- `modules/page_process.py` — `_FNAME_RE`, `_RAW_REL`, `_CSV_DIR`, the
  imp/hig pairing in `ProcessPage`
- `modules/page_validate.py` — `_FS = 2000`, `_WIN_SEC = 0.2`
- `modules/page_dataset.py` — `_TARGET_ROWS = 400`, `_NADIR_WIN_SUFFIX`

### Tab 2 — Study design tools

Placeholder page for study-design helpers. Structure only for now.

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
