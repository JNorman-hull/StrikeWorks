# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""CEN 2025 blade strike mortality calculation - pure port of the old MVP
app's `bsm/core/model.py` (ROADMAP.md Chunk 5 task 5). NumPy/SciPy only, no
GUI deps, unchanged maths - every formula, constant and regime break is as
found there.

The one change: the observed-strike confidence interval used to be
computed inline; it's now `wilson_calc.wilson_interval()`, the same
function Setup and deploy > Study design uses for sample-size planning -
one Wilson-interval implementation for the app rather than two.
"""
import numpy as np
from scipy.interpolate import CubicSpline

from .wilson_calc import wilson_interval

N_INTEGRATION_POINTS = 200


def cen_regression(species, Lf_d, eel_vcrit):
    """(a, b, vcrit, regime label) for the mutilation-fraction regression
    at this length-to-diameter ratio. `b` is None for eels (single-term
    regression, no intercept)."""
    if species == "eel":
        return 0.0024, None, eel_vcrit, "Eel"
    vcrit = max(4.8, -2.8 * Lf_d + 10.3)
    if Lf_d <= 1:
        return 0.1008, 0.0370, vcrit, "0-1"
    elif Lf_d <= 2:
        return 0.0289, 0.0370, vcrit, "1-2"
    elif Lf_d <= 10:
        return 0.0829, -0.0021, vcrit, "2-10"
    else:
        return 0.0327, 0.1146, vcrit, "10-25"


def compute(p):
    """`p`: species, lf, bf, wf, alpha, eel_vcrit, n, N, Q, r, bh, rttr,
    d_vals, beta_vals, delta_vals, use_observed, total, strike.
    Returns a result dict - see the field names used throughout this
    module and `ml_report`-style consumers below."""
    species = p["species"]
    lf, bf = p["lf"], p["bf"]
    wf, alpha = p["wf"], p["alpha"]
    eel_vcrit = p["eel_vcrit"]
    n, N, Q = p["n"], p["N"], p["Q"]
    r, bh = p["r"], p["bh"]
    rttr = p["rttr"]
    d_vals, beta_vals, delta_vals = p["d_vals"], p["beta_vals"], p["delta_vals"]
    n_int = N_INTEGRATION_POINTS

    Lmax = np.sqrt(lf**2 + bf**2)
    theta0 = np.arctan(bf / lf)
    theta = alpha
    if species == "eel":
        Leff_m, Leff_t = 0.8 * lf, 0.0
    else:
        Leff_m = Lmax * np.cos(abs(theta) - theta0)
        Leff_t = Lmax * np.sin(theta + theta0)

    Omega = 2 * np.pi * N / 60
    A = np.pi * (r**2 - bh**2)
    vm = Q / A

    d_spl = CubicSpline(rttr, np.array(d_vals) / 1000.0, bc_type="natural")
    beta_spl = CubicSpline(rttr, np.deg2rad(beta_vals), bc_type="natural")
    delta_spl = CubicSpline(rttr, np.deg2rad(delta_vals), bc_type="natural")

    eps = 1e-9
    f_arr = np.linspace(0.0, 1.0, n_int)
    r_arr = bh + f_arr * (r - bh)
    rtr = r_arr / r
    d_arr = np.maximum(d_spl(rtr), 1e-4).astype(float)
    beta_arr = beta_spl(rtr).astype(float)
    delta_arr = delta_spl(rtr).astype(float)

    Pco_arr = np.zeros(n_int)
    fMR_arr = np.zeros(n_int)
    vstrike_arr = np.zeros(n_int)

    for i in range(n_int):
        r_f, d_f = r_arr[i], d_arr[i]
        beta_f, delta_f = beta_arr[i], delta_arr[i]
        Lf_d = lf / d_f
        a_c, b_c, vcrit, _ = cen_regression(species, Lf_d, eel_vcrit)

        circ = Omega * r_f - vm * np.tan(alpha) - wf * np.sin(alpha)
        chan = 2 * np.pi * r_f / n

        Pco = min(1.0, max(0.0,
            Leff_m * abs(circ) /
            (max(chan - Leff_t, eps) * max(abs(vm + wf * np.cos(alpha)), eps))))

        vstrike = np.sqrt(
            ((vm + wf * np.cos(alpha)) * np.cos(beta_f))**2 +
            (circ * np.cos(delta_f))**2)

        if species == "eel":
            fMR = min(1.0, max(0.0, a_c * Lf_d * (vstrike - vcrit)))
        else:
            fMR = min(1.0, max(0.0, (a_c * np.log(Lf_d) + b_c) * (vstrike - vcrit)))

        Pco_arr[i], fMR_arr[i], vstrike_arr[i] = Pco, fMR, vstrike

    integrand = fMR_arr * Pco_arr * r_arr
    integral = np.sum(np.diff(f_arr) * (integrand[:-1] + integrand[1:]) / 2)
    Pm = min(1.0, max(0.0, 2 / (r + bh) * integral))
    S = 1 - Pm

    Lf_d_tip = lf / d_arr[-1]
    a_tip, b_tip, vcrit_tip, regime_tip = cen_regression(species, Lf_d_tip, eel_vcrit)
    circ_tip = Omega * r - vm * np.tan(alpha) - wf * np.sin(alpha)
    chan_tip = 2 * np.pi * r / n

    res = {
        "params": p,
        "Lmax": Lmax, "theta0": theta0, "theta": theta,
        "Leff_m": Leff_m, "Leff_t": Leff_t,
        "Omega": Omega, "A": A, "vm": vm,
        "f_arr": f_arr, "r_arr": r_arr,
        "d_arr": d_arr, "beta_arr": beta_arr, "delta_arr": delta_arr,
        "Pco_arr": Pco_arr, "fMR_arr": fMR_arr, "vstrike_arr": vstrike_arr,
        "Pco_tip": Pco_arr[-1], "fMR_tip": fMR_arr[-1], "vstrike_tip": vstrike_arr[-1],
        "Lf_d_tip": Lf_d_tip, "regime_tip": regime_tip,
        "a_tip": a_tip, "b_tip": b_tip, "vcrit_tip": vcrit_tip,
        "circ_tip": circ_tip, "chan_tip": chan_tip,
        "integral": integral,
        "Pm": Pm, "S": S,
    }

    if p["use_observed"]:
        total, strike = p["total"], p["strike"]
        Pco_obs = min(1.0, strike / total) if total else 0.0
        integrand_obs = fMR_arr * Pco_obs * r_arr
        integral_obs = np.sum(np.diff(f_arr) * (integrand_obs[:-1] + integrand_obs[1:]) / 2)
        Pm_obs = min(1.0, max(0.0, 2 / (r + bh) * integral_obs))
        S_obs = 1 - Pm_obs

        wilson = wilson_interval(Pco_obs, total, confidence=95) if total else None
        wilson_lo, wilson_hi = wilson[:2] if wilson else (Pco_obs, Pco_obs)

        res.update({
            "Pco_obs": Pco_obs, "Pm_obs": Pm_obs, "S_obs": S_obs,
            "wilson_lo": wilson_lo, "wilson_hi": wilson_hi,
            "integral_obs": integral_obs,
        })

    return res


def recompute_mortality(res, species, eel_vcrit=None, lf=None, threshold=None):
    """Re-run the mortality integral from an existing `compute()` result
    under a different species / eel critical velocity / mortality
    threshold, holding the hydrodynamic exposure (Pco_arr, vstrike_arr,
    r_arr - i.e. the fish's actual passage through the blade sweep) fixed.

    This is the "what if these fish were a different species, or death is
    any strike whose injury fraction meets a threshold rather than the
    continuous fMR itself" question Biological interpretation answers,
    without re-running the geometric/hydrodynamic half of the model.

    threshold=None keeps the continuous fMR (identical maths to
    `compute()`); a threshold in [0, 1] makes fMR binary: 1.0 where the
    continuous fraction meets or exceeds it, else 0.0.
    """
    p = res["params"]
    lf = lf if lf is not None else p["lf"]
    eel_vcrit = eel_vcrit if eel_vcrit is not None else p["eel_vcrit"]
    r, bh = p["r"], p["bh"]
    f_arr = res["f_arr"]
    r_arr, d_arr = res["r_arr"], res["d_arr"]
    vstrike_arr, Pco_arr = res["vstrike_arr"], res["Pco_arr"]

    fMR_arr = np.zeros_like(r_arr)
    for i in range(len(r_arr)):
        Lf_d = lf / d_arr[i]
        a_c, b_c, vcrit, _ = cen_regression(species, Lf_d, eel_vcrit)
        if species == "eel":
            fMR_arr[i] = min(1.0, max(0.0, a_c * Lf_d * (vstrike_arr[i] - vcrit)))
        else:
            fMR_arr[i] = min(1.0, max(0.0,
                (a_c * np.log(Lf_d) + b_c) * (vstrike_arr[i] - vcrit)))

    fMR_eff = fMR_arr if threshold is None else (fMR_arr >= threshold).astype(float)
    integrand = fMR_eff * Pco_arr * r_arr
    integral = np.sum(np.diff(f_arr) * (integrand[:-1] + integrand[1:]) / 2)
    Pm = min(1.0, max(0.0, 2 / (r + bh) * integral))

    return {"species": species, "eel_vcrit": eel_vcrit, "lf": lf,
            "threshold": threshold, "fMR_arr": fMR_arr, "Pm": Pm, "S": 1 - Pm}
