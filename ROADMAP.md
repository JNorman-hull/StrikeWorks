# StrikeWorks roadmap

Open work only. Finished work is in the git history; the full log of what
was built up to 2026-09-25 is the ROADMAP.md in commit `a4fa30c`. The code
clean-up has its own plan, `REFACTOR_PLAN.md`.

The whole pipeline is exercised end to end by the two demos (Dev console,
`modules/dev_runner.py`, and `tests/test_demos.py`) from a demo pack
(`demo_data`, a library-shaped folder of recordings and annotations).

## Hidden for now

Built, just not offered in the UI. To bring one back, take it out of the
place named alongside it.

| Feature | Where it was | Hidden by | Why |
|---|---|---|---|
| Segmentation | Sensor processing | `MainWindow._HIDDEN_PAGES` (main.py) | Superseded by Validate and annotate's validation (Auto process all + Save + next) |
| Data analysis | Sensor processing | `MainWindow._HIDDEN_PAGES` | Still a stub (see below) |
| Advanced dataset options | Validate and annotate | `MainWindow._HIDDEN_PAGES` | Its one remaining tool, Bind training data, is in Model training > Train's Training dataset box (`modules/bind_datasets.py`) |
| Annotate > Reporting tab | Validate and annotate > Annotate | `AnnotationPage._build` (page_annotate.py) | Its summary is already in the central report (`report_center.annotation_section`) |
| Observed strike data | Mathematical blade strike modelling > Calculator | `CalculatorPage._build` (page_bsm_calculator.py) | Awaiting a decision on how to bring it back; `bsm_model.compute()` still accepts it |

## Open

**Delineation tool (Segmentation page).** Seven windows covering the full
time series: start/end trim handles placed first with everything else
relative to them, the nadir window fixed-width and centred, pre-/post-nadir
windows of fixed duration (default 300 ms), ROI 1/2 and 6/7 the remaining
handles, the same bad-sensor flag as Annotate. Anticipates the old Shiny
app's delineation and passage summary.

**Data analysis page (Sensor processing).** Passage durations, time-series
normalisation, barotrauma metrics and acceleration peak finding, following
the old Shiny app.

**Model comparison - two questions.** The bundled model and the manual
"Model 1" box share a name, so both can appear as "Model 1"; and the eel
bars' colour changed when mortality was added. Both want a decision.

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
