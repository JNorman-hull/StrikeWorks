# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""CSV and PNG export for blade strike modelling results, shared by
Analysis and reporting and the central report (report_center.py),
including the two fixed-size report figures.
"""
import csv
from pathlib import Path

CM_PER_INCH = 2.54


def export_results(results, out_dir):
    """bsm_results.csv - one row per species and method (CEN, and
    Observed when observed counts were entered). `results`: {"scaly":
    res, "eel": res}."""
    out = Path(out_dir)
    with open(out / "bsm_results.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["species", "method", "Pco", "fMR", "Pm", "S"])
        for species, res in results.items():
            if res is None:
                continue
            w.writerow([species, "CEN", f"{res['Pco_tip']:.6f}",
                        f"{res['fMR_tip']:.6f}", f"{res['Pm']:.6f}",
                        f"{res['S']:.6f}"])
            if "Pco_obs" in res:
                w.writerow([species, "observed", f"{res['Pco_obs']:.6f}",
                            f"{res['fMR_tip']:.6f}", f"{res['Pm_obs']:.6f}",
                            f"{res['S_obs']:.6f}"])
    return out


def export_sweeps_csv(sweeps, out_dir, stem):
    """Long-format export of `bsm_model.sensitivity_sweeps()` - one row per
    (quantity, x, flow) point, matching the standalone Mathematical BSM
    scripts' `*_sensitivity_wf_q.csv` convention."""
    names = {"pco_n": ("collision_probability", "N_rpm"),
             "pco_wf": ("collision_probability", "wf_m_per_s"),
             "pm_n": ("mortality_probability", "N_rpm"),
             "pm_wf": ("mortality_probability", "wf_m_per_s")}
    out = Path(out_dir)
    with open(out / f"{stem}.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["quantity", "x_variable", "x", "flow", "percent"])
        for key, (quantity, x_name) in names.items():
            for label, (x_arr, y_arr) in sweeps[key].items():
                for xi, yi in zip(x_arr, y_arr):
                    w.writerow([quantity, x_name, f"{xi:g}", label,
                                f"{yi:.6f}"])
    return out / f"{stem}.csv"


def save_fixed(fig, base_path, formats=("png",), dpi=300):
    """Saves `fig` at exactly its own figure size (no tight bounding box,
    which would crop it to a different size) once per format. Returns the
    .png path if one was written, else the first path written."""
    png, first = None, None
    for fmt in formats or ("png",):
        path = Path(base_path).with_suffix(f".{fmt}")
        try:
            fig.savefig(path, dpi=dpi, facecolor="white")
        except (OSError, ValueError) as e:
            print(f"Could not save {path.name}: {e}")
            continue
        first = first or path
        if fmt == "png":
            png = path
    return png or first


def sized_figure(size_cm):
    from matplotlib.figure import Figure
    w, h = size_cm
    return Figure(figsize=(w / CM_PER_INCH, h / CM_PER_INCH), dpi=100)


def save_results_panels(results, base_path, formats=("png",), dpi=300):
    """The 4-panel headline results figure (12 x 12 cm), report styling."""
    from . import bsm_figures
    fig = sized_figure(bsm_figures.RESULTS_PANELS_CM)
    bsm_figures.draw_results_panels(fig, results, dark=False)
    return save_fixed(fig, base_path, formats, dpi)


def save_sweep_panels(sweeps, species, params, base_path, formats=("png",),
                      dpi=300):
    """The 4-panel sensitivity figure (20 x 16 cm), report styling."""
    from . import bsm_figures
    fig = sized_figure(bsm_figures.SWEEP_PANELS_CM)
    bsm_figures.draw_sweep_panels(
        fig, sweeps, dark=False,
        title=bsm_figures.sweep_panels_title(species, params))
    return save_fixed(fig, base_path, formats, dpi)
