# StrikeWorks roadmap

Open work only. Finished work is in the git history; the full log of what
was built up to 2026-09-25 is the ROADMAP.md in commit `a4fa30c`. The code
clean-up of September 2026 is recorded in `REFACTOR_PLAN.md` (finished; its
conventions apply to new code).

The whole pipeline is exercised end to end by the two demos (Settings >
Console, `modules/dev_runner.py`, and `tests/test_demos.py`) from a demo pack
(`demo_data`, a library-shaped folder of recordings and annotations).

## Hidden for now

Built, just not offered in the UI. To bring one back, take it out of the
place named alongside it.

| Feature | Where it was | Hidden by | Why |
|---|---|---|---|
| Data analysis | Sensor processing | `MainWindow._HIDDEN_PAGES` | Still a stub (see below) |
| Advanced dataset options | Validate and annotate | `MainWindow._HIDDEN_PAGES` | Its one remaining tool, Bind training data, is in Model training > Train's Training dataset box (`modules/bind_datasets.py`) |
| Annotate > Reporting tab | Validate and annotate > Annotate | `AnnotationPage._build` (page_annotate.py) | Its summary is already in the central report (`report_center.annotation_section`) |
| Observed strike data | Blade strike calculator > Calculator | `CalculatorPage._build` (page_bsm_calculator.py) | Awaiting a decision on how to bring it back; `bsm_model.compute()` still accepts it |

## Open

**Editable HIG bands.** Predict's Advanced features lets HIG peak analysis's
detection settings be changed (peak height, prominence, minimum gap, the
shear rule), but shows the event bands (95, 200, 400 g) and the collision /
severe value (400 g) greyed out. They come from RAPID at 2000 Hz, so the EEL
tag - at other rates and filters - may want different ones. Making them
editable means everything named after them follows the run's own values
instead of fixed numbers: the `n_events_<g>g` and `n_over_<g>g` columns,
severity's bands and table headers, the Collisions card, the HIG figures'
labels and the report text (`hig_peaks.py`, `predict_worker.py`,
`ml_figures.py`, `ml_report.py`, `ml_tab_predict.py`). The bands are one
set already, `hig_peaks.THRESHOLDS_G`.

**Low-magnitude contacts called strikes.** On the Pentair dataset (66
recordings, different pump conditions from the training data; on OneDrive,
`RAPID_libraries\Pentair\StrikeWorks_user_output\Pentair__20260930_134246.csv`)
the binary model calls 64 strikes, but only 1 recording's HIG peak passes
400 g (16 pass 200 g, 41 pass 95 g). The HIG peak analysis
(`modules/hig_peaks.py`, on by default in Predict) puts the same data as
111 acceleration events of at least 95 g, 25 of at least 200 g and 1 of
at least 400 g: 1 collision in 66 recordings, 1.5 % (95 % CI 0.3-8.1 %).
Strike severity (`modules/hig_peaks.py`) still reports the per-recording
peak where the peak analysis is off; the model itself is unchanged. Wants
a decision: report the collision probability as the headline figure;
retrain with labels that separate light contacts from strikes (Annotate's
`overall_passage_type` already records contact types), or with
Pentair-like conditions in the training data; or re-tune the threshold.

**Build tooling.** `build.py --zip` refuses when the folder holds anything
made by using the built app. It should zip a clean copy instead (what
ships only), leaving the user's own libraries, outputs and settings in
place - the 30 September zips were made that way by hand.
`tools\smoke_test.ps1 -Demos` now leaves `settings.json` out of its copy
(so the demos can't write into the user's real libraries), but still
copies the user's own data; it should copy only what ships.

**Bundle size** (`REFACTOR_PLAN.md`, Still open). `_internal` is 539 MB.
Candidates, each needing a build and a smoke test: exclude PySide6's
unused Qt parts (`Qt6Quick`, `Qt6Qml`, `Qt6Pdf`, `opengl32sw.dll`, ~30
MB); `opencv-python-headless` instead of `opencv-python` (a package
change).

**Delineation and full sensor segmentation.** Planned in
`SEGMENTATION_PLAN.md`: a nadir detector based on the pump's pressure step
(76 of 76 Testbed recordings against the current 55), the seven regions of
the old Shiny app found from pressure, a Full passage mode on the
validation screen to check them, and a per-region summary.

**Code review, November 2026.** `CODE_REVIEW.md`: duplicated and unused
code, three small merges and the shared signal plot, as batches to approve.

**Data analysis page (Sensor processing).** Passage durations, time-series
normalisation and barotrauma metrics, following the old Shiny app.
Acceleration peak finding exists already, on datasets (Predict's HIG peak
analysis, `modules/hig_peaks.py`); this page would run it on whole
recordings and other regions of interest.

**Model comparison - one question.** The eel bars' colour changed when
mortality was added; it wants a decision. (The manual box is now "Model
comparison", so it no longer shares the bundled model's "Model 1".)

**Raw data processing "Selection information".** The four summary cards
should come from a JSON file the page writes for the current selection,
part of moving the app towards consistent JSON outputs. Not started.

**Home resume summary, phase 2.** A fuller view of what has been done in
the library, once it's clear what else is worth showing.

**Report generation package.** Evaluate a standard package (for example
https://github.com/svanirudh1809/ReportGenerator) against the hand-built
`ml_report.py` / `report_center.py` before deciding either way.

**Demos as a test bed.** The demos cover deployment > processing >
validation and annotation > training > deployment > prediction > report.
Not yet covered: misclassification analysis and retraining, checks beyond
"each step produced its output", and a fresh library on every run.

## Deferred - multiple collision detection

Assessed, not implemented. The models classify a whole window, and
`predict_worker._pad()` truncates anything longer than
`max_sequence_length`, so a 1-minute file would be classified on its first
~200 ms only.

Proposed: sliding-window inference with the existing models. Slide the
401-sample window at a hop (~100 samples / 50 ms), score each position
with the binary model to build a probability trace, pick peaks above the
threshold with a refractory period of about one window to get discrete
events, then run the multiclass model on each event. Add as
`--mode scan --window --hop` in `predict_worker.py`, writing the trace and
an events CSV; Inspect can already plot the trace over the signal.

Two calibration caveats: training windows were nadir-centred, so
off-centre positions are out of distribution and the trace will be noisy
between events; and the deployed `optimal_threshold` was tuned on roughly
balanced centred windows, whereas scanning is overwhelmingly negative, so
precision will drop and the threshold needs re-tuning against passages
with known multiple collisions.
