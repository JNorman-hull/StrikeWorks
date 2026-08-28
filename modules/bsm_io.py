# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""CSV/PNG export helpers for blade strike modelling results - port of the
old MVP app's `bsm/io.py`, unchanged. Shared by Sensitivity (wf sweep) and
Reporting (headline results) so there is one export routine per shape
rather than one per page.
"""
import csv
from pathlib import Path


def export_results(res, fig_pco, fig_pm, out_dir):
    out = Path(out_dir)
    with open(out / "bsm_results.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["method", "Pco", "fMR", "Pm", "S"])
        w.writerow(["CEN", f"{res['Pco_tip']:.6f}", f"{res['fMR_tip']:.6f}",
                    f"{res['Pm']:.6f}", f"{res['S']:.6f}"])
        if "Pco_obs" in res:
            w.writerow(["observed", f"{res['Pco_obs']:.6f}", f"{res['fMR_tip']:.6f}",
                        f"{res['Pm_obs']:.6f}", f"{res['S_obs']:.6f}"])
    fig_pco.savefig(out / "barplot_pco.png", dpi=300, bbox_inches="tight")
    fig_pm.savefig(out / "barplot_pm.png", dpi=300, bbox_inches="tight")
    return out


def export_sensitivity(x, y, fig, out_dir, stem, x_header):
    out = Path(out_dir)
    with open(out / f"{stem}.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([x_header, "Pco_percent"])
        for xi, yi in zip(x, y):
            w.writerow([f"{xi:g}", f"{yi:.6f}"])
    fig.savefig(out / f"{stem}.png", dpi=300, bbox_inches="tight")
    return out
