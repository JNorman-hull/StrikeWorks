# Full sensor segmentation - plan

Status, 13 November 2026: the design below is agreed (Josh's regions and
screen, section 2-4). Phase 1, the nadir detector, is built. The rest is
not. Open questions are in section 7.

## 1. What the recordings look like

Two rigs, checked on copies outside the repo.

**Testbed** (RAPID, 76 recordings, 60 s each): in air at 100 kPa; released
about 5 s in, with a HIG knock; a pressurised stage at 130-150 kPa for about
2 s; a fall of about 46 kPa to a low-pressure approach that creeps up from
80 to 97 kPa; a short dip, then a rise of 35-53 kPa within 0.3 s at the
pump, 17-57 s in; a decay over about 4 s to 105 kPa; then 100-110 kPa to
the end.

**EEL, Run 3 of `400_eel_1`** (12 recordings, 2500 Hz, one 2000 Hz): flat
at 100 kPa (the tag's datum); into the water about 7 s in, rising to
110-120 kPa within a second or two; a slow drift; a dip, then a rise of
13-35 kPa at the pump, 12-17 s in; either a decay to 105-110 kPa over 5-10
s, or (four recordings) the sensor stays at 120-150 kPa with pressure and
HIG noise to the end of the file. Two recordings have a pressure trace that
never leaves 100-102 kPa.

So there is no pressurised stage on the EEL rig, and a boundary rule tuned
to one rig will not hold on the other. Only the pump's pressure step is
common to both.

## 2. The regions

Josh's definitions; the labels are the old Shiny app's, as the R analysis
reads them (question 1).

| ROI | Label | What it marks |
|---|---|---|
| 1 | `roi1_sens_ingress` | Sensor ingress: the sensor enters the system from atmospheric pressure or another landmark (an injection pipe, say) |
| 2 | `roi2_inflow_passage` | Intake passage: through the intake structures and pipework leading towards the impeller |
| 3 | `roi3_prenadir` | Pre-nadir: just before the impeller, where pressure differentials and swirl are most likely |
| 4 | `roi4_nadir` | Nadir: passage through the impeller - the hydraulic pinch point where maximum acceleration and rotation and minimum pressure are likely |
| 5 | `roi5_postnadir` | Post-nadir: just after the impeller, where guide vane and other collisions, residual turbulence and pressure recovery are most likely |
| 6 | `roi6_outflow_passage` | Outflow passage: through the outflow pipework and structures towards sensor outgress; velocity falling, pressure returning towards atmospheric |
| 7 | `roi7_sens_outgress` | Sensor outgress: the sensor leaves the system, at atmospheric pressure or another landmark (stable flow in the tailwater, say) |
| | start and end trim | From the start of the data to the start of ROI 1, and from the end of ROI 7 to the end of the data. Worked out, not placed; removed afterwards with the trim tool |

Four boundaries are dragged: the start of ROI 1, ROI 1/2, ROI 6/7 and the
end of ROI 7. ROI 3, 4 and 5 are fixed lengths around the nadir (300, 200
and 300 ms by default; ROI 4 is the model's window) and move with it.

## 3. The screen

On the validation screen (Validate and annotate), as in the mock-up:

- **Enable full segmentation**, a button beside Open video. Off, the screen
  is as it is now.
- **Three window lengths** where "ROI window" is now: ROI 3, ROI 4 and ROI
  5. ROI 4 is today's box. The other two are greyed out unless full
  segmentation is on.
- **On the plot:** a line at each region boundary, the regions numbered 1-7
  along the top, drag handles on the four placed boundaries, and the two
  trim sections marked from the ends of the data. The nadir stays the
  yellow line; moving it moves ROI 3-5. Lines snap to a sample and can't
  cross.
- **Save + Next** saves the nadir as now and, with full segmentation on,
  the four boundaries and the three lengths to the sensor index.
- **Save and export** still binds the nadir windows into the model dataset
  and nothing else goes into it. With full segmentation on, it also writes
  a `roi` column into each listed sensor's processed CSV
  (`processed_sens_data/csv/<stem>.csv`): one of the seven labels, or
  `trim_start` / `trim_end`.
- Each region's description above is its tooltip.

When full segmentation is switched on for a sensor with nothing saved, the
four boundaries start from a suggestion (section 5) for the user to
correct.

## 4. What is stored

- **Sensor index**, on Save + Next: `roi1_start_s`, `roi12_s`, `roi67_s`,
  `roi7_end_s`; the lengths in `roi_config` (`300/200/300`); `delineated`
  Y. The nadir is `pres_min.time.` as now. That is everything needed to
  redraw the lines.
- **Processed CSV**, on Save and export: the `roi` column. The nadir
  window files and the dataset never carry it.
- **Trim tool** (later): removes the `trim_start` / `trim_end` rows
  (question 2).

This replaces the earlier plan's region table as the first output. The
per-region analyses read the `roi` column: durations (whole passage and
each region), collision classification (HIG peak analysis per region),
and pressure analysis (rate, ratio, nadir) - the last becoming StrikeWorks's
barotrauma analysis, following the old Shiny code (question 3).

## 5. Automatic parts

**Nadir (built).** `rapid_functions.nadir_pressure_step`, the default in
Sensor configuration > Nadir detection, with the earlier method as its
fallback and as a choice of its own:

1. Pressure at 100 Hz.
2. At each instant, the step: the median of the 0.5 s after it (past a 0.1
   s gap) minus the median of the 0.5 s before. Medians, so spikes don't
   count.
3. Candidates: steps of at least 5 kPa after which pressure stays above
   where it started for 4 s.
4. The pump is the largest candidate - unless pressure then falls back
   below where that one started and steps up again by at least 60 % as
   much (the Testbed's pressurised stage); then the later one.
5. The nadir is the lowest pressure from 0.6 s before the step to 0.2 s
   after.
6. No candidate: the lowest pressure within 1.5 s of the largest
   acceleration, as before, and the index message says so.

Against validated nadirs, through the app's own readers:

| | Recordings | Earlier method | Pressure step |
|---|---|---|---|
| Testbed (RAPID) | 76 | 55 within 20 ms; 21 over a second out | 76 within 20 ms |
| EEL Run 3 | 12 | 9 accepted as found, 3 moved by hand | 10 within 20 ms; 2 on the fallback |

The two on the fallback are the flat-pressure recordings, where the nadir
was put by hand at the acceleration spike (question 4). One of the three
moved by hand, `EEL_010-1110144657`, has its largest acceleration 90 s
after the pump; the step finds its nadir.

Not proven beyond these two rigs. A turbine, where pressure steps down
through the machine, needs its own method.

**Boundary suggestions (not built).** Starting points only, for the user to
drag:

- start of ROI 1: pressure leaves its level at the start of the file by
  0.5 kPa;
- end of ROI 7: the mirror - pressure joins its level at the end of the
  file;
- ROI 6/7: after ROI 5, pressure is within 2 kPa of that final level and
  stays there;
- ROI 1/2: a large sustained fall between the start of ROI 1 and ROI 3
  where there is one (the Testbed's pressurised stage ending); otherwise
  where the first rise after entry levels off.

On the Testbed, rough versions of these gave an ingress of about 7 s, 13 s
from ROI 1/2 to the nadir, 4.3 s from the nadir to ROI 6/7 and 30 s to the
end of the file, with ROI 6/7 found in 74 of 76. They are unchecked beyond
plots: there is no delineated recording on this machine to compare with.

## 6. Phases

1. **Nadir detector.** Done: `rapid_functions.py`, `sensor_config.py`,
   `setup_sensor.py`, `tests/test_nadir.py`.
2. **Shared signal plot** (`plot_widgets.SignalPlot`, `CODE_REVIEW.md`
   batch E), so the region lines are an overlay on one plot and not a fifth
   copy of it.
3. **`modules/delineation.py`**, no Qt: the boundaries (order, clamping,
   the label of each sample), the suggestions, and tests.
4. **The screen** (section 3) and the index columns.
5. **Save and export** writing the `roi` column.
6. **Trim tool.**
7. **Per-region analysis**: durations, HIG peak analysis by region, then
   the barotrauma analysis.

## 7. Questions

1. The labels in the `roi` column: the old app's (`roi1_sens_ingress` ...
   `roi7_sens_outgress`), so the R scripts and the Shiny code read the
   files as they are? And `trim_start` / `trim_end` for the trim rows?
2. The trim tool: remove the rows from the processed CSV itself (it can be
   processed again from the raw files, but the validated nadir would need
   keeping), or write a trimmed copy?
3. Where is the old Shiny code? It isn't on this machine outside OneDrive
   (the R analysis points at `RAPID_processing\shiny\`), and it has the
   pressure-change definitions the barotrauma analysis needs.
4. For a recording with no pressure step, should the fallback be the time
   of the largest acceleration itself? In both flat-pressure EEL recordings
   that is within 40 ms of where the nadir was put by hand; the lowest
   pressure near it, in a trace that is only noise, is 0.7 and 1.5 s away.
5. Full segmentation in the Development toolkit only, or in StrikeWorks's
   Validate step too?
6. Are boundary suggestions wanted (section 5), or should the four lines
   start at fixed places for the user to drag?
