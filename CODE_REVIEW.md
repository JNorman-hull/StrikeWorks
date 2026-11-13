# Code review, November 2026

A review of the hand-written code (86 modules in `modules/`, about 34,000
lines with the tests; `ui_main.py` and `modules/resources_rc.py` are
generated) for redundant modules, modules split too far, duplicated code
and AI-style writing.

**Done, uncommitted:** batch A on 9 November (comments and docstrings
only, checked against `4c97e55`), and batches B, C, D and F on 13 November
once approved - see "Batches" at the end for what each did. Still open:
batch E (the shared signal plot), the custom title bar, the two hidden
pages, the two retired buttons in `main.ui`, and the large classes.

## Verdict

The structure is sound and better than the module count suggests. The
Qt-free cores (`hig_peaks`, `bsm_model`, `raw_layout`, `recording_rate`,
`eel_format`, `rapid_functions`, `video_sync`, `wilson_calc`) are cleanly
separated from the pages, the model stack stays in the two workers, shared
state objects carry the signals, and 61 of the 62 catch-all `except
Exception` handlers report what they caught (the other is the cosmetic
taskbar call).

The module split is mostly not the problem: the small modules are
single-purpose, and one module per sidebar page is the convention
`REFACTOR_PLAN.md` set. Three merges are worth making (batch D). What does
need work is code written out more than once, a handful of unused
functions, two very large classes, and reports reaching into pages'
private attributes.

## Found on the way

Decided on 13 November: 1 - the pressure-step detector is the default,
with the earlier method as its fallback (README, "Sensor configurations");
2 - fixed, a dragged column keeps its width until the table gets new
columns; 3 - z is 1.96 everywhere, one function (`wilson_calc.py`); 4 -
reworded.

1. **The automatic nadir is wrong in 21 of the 76 Testbed recordings.**
   `rapid_functions.nadir_pressure_min_near_peak` looks within 1.5 s of
   the largest HIG value, and in those 21 the largest HIG value is the
   knock when the sensor is released, about 5 s in. A detector that looks
   for the pump's pressure step instead matched the validated nadir in
   76 of 76. Details and how to bring it in: `SEGMENTATION_PLAN.md`.
2. **Dragged column widths don't survive leaving a page.**
   `tables.fill_table_width` (tables.py:125) runs every time a table is
   shown and starts with `resizeColumnsToContents()`, so a column dragged
   to 400 px is back at its fitted width after a page switch (checked
   off-screen). Its docstring said the opposite; it now says what the code
   does. Fix: fill once per table, or only while no column has been
   dragged.
3. **Three values of z for the 95 % Wilson interval:** 1.96 (`hig_peaks`,
   `ml_report`, `predict_worker`), 1.959964 (`train_worker.py:338`) and
   1.959963984540054 (`wilson_calc.py:8`). The intervals differ from the
   fifth significant figure. One function for all of them changes some
   reported digits, so it needs your say on which z.
4. **A message names a page that no longer exists:**
   `dataset_build.py:204`, "Run the Validate & segment page first."

## Written more than once

| What | Where | Proposal |
|---|---|---|
| Wilson interval, 5 copies | `wilson_calc.wilson_interval`, `hig_peaks.wilson_ci`, `ml_report._wilson_ci`, `predict_worker._wilson_ci`, `train_worker.wilson_ci` | `ml_report` and `predict_worker` use `hig_peaks.wilson_ci` now (same z, same result). The rest wait on decision 3 |
| HIG bands 95 / 200 / 400 g, 3 copies | `hig_peaks.py:32`, `severity.py:11`, `predict_worker.py:94` | One set in `hig_peaks` (also what ROADMAP's "Editable HIG bands" needs first) |
| The dual-axis signal plot, 4 copies (about 450 lines) | `sensor_validation`, `ml_tab_inspect`, `page_misclassification`, `page_export_animations` - channel pickers, right-axis view box, decimated overlay, view limits, Export; `_sync_vb2` is identical in all four | One `plot_widgets.SignalPlot`. Phase 0 of the segmentation plan, which would otherwise add a fifth copy |
| Pop-up window that hides with its page, 5 copies | `bring_up` in `dev_console`, `ml_tab_predict`, `ml_tab_train_configure`, `ml_tab_train_deploy`, `page_annotate`; the same `eventFilter` in four of them | One `layout.ToolWindow` base class |
| `level_key`, 3 copies | `model_labels.py:17`, `ml_train_state.py:58`, `train_worker.py:58` | Keep `model_labels`'s; the other two import it |
| Reading and checking a dataset CSV, 2 copies | `ml_state.py:380`, `ml_train_state.py:200` | One `read_dataset_csv(path)` |
| `_run_sort_key`, 2 copies | `deployment_index.py:260`, `library_widgets.py:57` | One in `raw_layout`, which both import |

`_softmax` and `_package_versions` are also in both workers (15 lines).
Left alone: sharing them needs another module, which costs more than it
saves.

## Unused

No references anywhere in the app or the tests:
`ml_model_library.export_model_report` (its button went on 29 October),
`PredictionState.select_treatment`, `sensor_config.register_parser` and
`_INTERP_KIND`, `ValidationView.set_video_lookup` and `window_df`,
`severity.band_rows`, `ml_train_figures.BINARY_FIGURES` /
`MULTICLASS_FIGURES`. Used only by a test:
`validation_core.processed_sensor_files`, `RangeSlider.setValues`.

Left over from earlier designs:

- `HomePage._go_advanced` (page_home.py:184) only calls
  `main_window.expand_sidebar()`; Home has no mode buttons now. Its two
  callers can call `expand_sidebar()` themselves.
- The custom title bar: `ENABLE_CUSTOM_TITLE_BAR` has been False since 7
  October. Behind it are three branches of `ui_functions.py`, the
  `widgets/custom_grips` package (224 lines) and `MainWindow`'s
  `mousePressEvent` / `resizeEvent`. Delete, or keep the switch - your
  call.
- `MainWindow._RETIRED_BUTTONS`: two buttons still in `main.ui` and hidden
  at start-up. Remove them from `main.ui`.
- The hidden `page_dataset.py` (574 lines) and `page_stub.py`:
  `REFACTOR_PLAN.md` decided hidden pages stay. Still the decision?

## Modules

Merge:

- `edition.py` (10 lines, one function) into `startup.py`.
- `ui_config.py` (14 lines, five constants) into `ui_functions.py`, its
  only user besides `main.py`.
- `severity.py` (53 lines) into `hig_peaks.py`: the same bands, and
  both describe HIG magnitude.

Leave: the page wrappers (`page_setup`, `page_deployment`, `page_bsm`,
`page_ml_training`, `page_ml_prediction` - one module per sidebar page);
`processing.py`, `dataset_build.py` and `plot_widgets.py` (taken out of
pages on purpose in September); `wilson_calc`, `canvas`, `range_slider`,
`frequency_dialog`, `session_state`, `worker_launch`, `model_labels`
(small, one job each).

Names that no longer say what the module is, should you want to rename:
`page_simple_mode.py` is the StrikeWorks window (kept on 21 October);
`rapid_functions.py` is RAPID's reader, as `eel_format.py` is the EEL
tag's; `ml_tab_train_configure.py` is the Train tab.

## Too large

- `TrainTab` (ml_tab_train_configure.py): about 1,100 lines, 59 methods. The
  Labelling row and the Model box could each be a widget of their own, as
  `DeploymentPanel` already is.
- `ExportAnimationsPage`: about 1,100 lines, 63 methods. The frame scrubber
  window and the channels table are separable.
- `predict_worker.main` (208 lines) and `ml_report.build_report_html`
  (217): one function per stage or section.

No rush on these; worth doing when one is next changed.

## Reaching into private parts

- `report_center` reads seven private attributes and methods of the
  Annotate and Misclassification pages (`_dataset_stems`, `_load_index`,
  `_variable_value_counts`, `_corrections`, `_video_index`, ...). The
  report should call a public method on each page.
- `ml_report`'s HTML helpers (`_esc`, `_kv_table`, `_data_table`,
  `_img_tag`) are used by `report_center`, `ml_model_library` and
  `bsm_report`. They are the app's report HTML and should lose the
  underscore.
- `dev_runner` calls 14 private page methods. Acceptable for the demo
  driver, but each rename in a page has to be followed there.

## Batches

One commit each, in this order. Tests: `test_lint` plus those named.
A to D and F are done; E is not.

| | What | Output changes | Tests |
|---|---|---|---|
| A | Comments and docstrings (done, uncommitted): file banners, section rulers, long docstrings, change history, stale names | None (checked) | `test_lint` |
| B | One of each: the Wilson interval (`wilson_calc.wilson_ci` / `wilson_interval`), HIG bands (`hig_peaks.THRESHOLDS_G`), `model_labels.level_key`, `raw_layout.run_sort_key`, `recording_rate.read_dataset_csv`, `layout.ToolWindow`, public report helpers (`ml_report.esc`, `kv_table`, `data_table`, `img_tag`), `_go_advanced` gone; the stale message | None but z (F) | `test_rules`, `test_severity`, `test_hig_peaks`, `test_model_labels`, `test_training_labels`, `test_reports`, `test_predict_pages`, `test_app` |
| C | Unused functions and constants listed above, and the treatment-selection signal nothing emitted (`PredictionState.treatment_selected`) | None | `test_app`, `test_validation_view`, `test_evaluate` |
| D | The three merges: `edition.py`, `ui_config.py` and `severity.py` are gone | None | `test_severity`, `test_hig_peaks`, `test_app` |
| E | `SignalPlot` for the four signal plots | None intended; one page at a time | `test_validation_view`, `test_predict_pages`, `test_plot_export`, `test_app` |
| F | Table widths kept once dragged; z = 1.96 (Study design, Model comparison, the BSM's observed interval and the training metrics move in the fifth significant figure) | Yes | `test_tables`, `test_bsm_model`, `test_hig_peaks` |

`HANDOVER.md`'s "Where things stand" is 300 lines of dated change notes.
Not code, so untouched, but it would read better cut to the current state
with the history left to git.
