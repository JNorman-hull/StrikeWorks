# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""HTML report builder for a Blade Strike Modelling result.

Deliberately does NOT adopt the old MVP app's `bsm/report/builder.py`
wholesale (a MathJax-rendered document, its own external CDN dependency
and visual language) - this reuses `ml_report.py`'s generic HTML building
blocks (`_kv_table`/`_data_table`/`_img_tag`/`wrap_html_document`/`_DARK`)
so a BSM report still looks like the same family of document as a
prediction report, with every equation shown as plain substituted-numbers
text rather than typeset LaTeX. What DID change (2026-09-01, in response
to "not fully featured... include more of the actual methodology, like
the previous html reporter"): every derivation step the old reporter
showed is here now, not just the tip-point summary - blade profile,
effective fish length (both species' own derivation), pump kinematics,
strike velocity/collision probability/mortality integrand at hub/mid-
span/tip, the full mutilation-ratio regime table, and the empirical/
observed comparison section. `build_bsm_report_html()` also now takes an
optional second species' result and reports both scaly and eel in one
document (dual-species default, ROADMAP.md item 15) rather than whichever
one happened to be primary.
"""
import numpy as np
from datetime import datetime

from .ml_report import _DARK, _MUTED, _BORD, _data_table, _img_tag, _kv_table

_EPS = 1e-9

# Table 3 (EVS-EN 18110:2025) - the same regression constants
# bsm_model.cen_regression() applies, shown here as reference documentation
_SCALY_REGIME_TABLE = [
    ("0-1",   "0.1008",  "0.0370"),
    ("1-2",   "0.0289",  "0.0370"),
    ("2-10",  "0.0829",  "-0.0021"),
    ("10-25", "0.0327",  "0.1146"),
]


def _equation_block(title, lines):
    body = "<br>".join(lines)
    return (f"<p style='margin:10px 0 2px;font-weight:bold;'>{title}</p>"
            f"<div style='font-family:Consolas,\"Courier New\",monospace;"
            f"font-size:12px;background:#f1f5f9;border-radius:4px;"
            f"padding:8px 12px;white-space:pre-wrap;'>{body}</div>")


def _result_box(text):
    return (f"<div style='display:inline-block;padding:6px 14px;"
            f"background:#f0fdf4;border:1px solid #86efac;border-radius:4px;"
            f"font-weight:bold;color:#065f46;margin:8px 0;'>{text}</div>")


def _species_label(species):
    return "Eel" if species == "eel" else "Scaly fish"


def _blade_profile_table(p):
    headers = ["r/Tr", "d (mm)", "β (°)", "δ (°)"]
    rows = [[f"{rt:.3f}", f"{d:.2f}", f"{b:.3f}", f"{dl:.3f}"]
            for rt, d, b, dl in zip(p["rttr"], p["d_vals"], p["beta_vals"],
                                    p["delta_vals"])]
    return _data_table(headers, rows)


def _effective_length_section(res):
    p = res["params"]
    if p["species"] == "eel":
        return _equation_block(
            "Eq 15 - Eel effective length (slender-body assumption, body "
            "height ignored)", [
                "Leff,m = 0.8 x Lf,   Leff,t = 0",
                f"Leff,m = 0.8 x {p['lf']:.4f} = {res['Leff_m']:.6f} m",
            ])
    return "".join([
        _equation_block("Eq 11 - Body diagonal", [
            "Lmax = sqrt(Lf^2 + Bf^2)",
            f"Lmax = sqrt({p['lf']:.4f}^2 + {p['bf']:.4f}^2) "
            f"= {res['Lmax']:.6f} m",
        ]),
        _equation_block("Eq 12 - Base angle", [
            "theta0 = arctan(Bf / Lf)",
            f"theta0 = arctan({p['bf']:.4f} / {p['lf']:.4f}) "
            f"= {res['theta0']:.6f} rad",
        ]),
        _equation_block("Eq 9 - Meridional effective length", [
            "Leff,m = Lmax . cos(|theta| - theta0)",
            f"Leff,m = {res['Lmax']:.6f} . cos(|{p['alpha']:.4f}| - "
            f"{res['theta0']:.6f}) = {res['Leff_m']:.6f} m",
        ]),
        _equation_block("Eq 10 - Tangential effective length", [
            "Leff,t = Lmax . sin(theta + theta0)",
            f"Leff,t = {res['Lmax']:.6f} . sin({p['alpha']:.4f} + "
            f"{res['theta0']:.6f}) = {res['Leff_t']:.6f} m",
        ]),
    ])


def _pump_kinematics_section(res):
    p = res["params"]
    return "".join([
        _equation_block("Eq 6 - Angular velocity", [
            "Omega = 2.pi.N / 60",
            f"Omega = 2.pi x {p['N']:.0f} / 60 = {res['Omega']:.4f} rad/s",
        ]),
        _equation_block("Annular through-flow area", [
            "A = pi(r^2 - bh^2)",
            f"A = pi({p['r']:.4f}^2 - {p['bh']:.4f}^2) = {res['A']:.6f} m^2",
        ]),
        _equation_block("Eq 7 - Meridional velocity", [
            "vm = Q / A",
            f"vm = {p['Q']:.4f} / {res['A']:.6f} = {res['vm']:.4f} m/s",
        ]),
    ])


def _hub_mid_tip(res):
    n = len(res["f_arr"])
    return [("Hub", 0), ("Mid-span", n // 2), ("Tip", n - 1)]


def _strike_velocity_table(res):
    p = res["params"]

    def row(label, i):
        vm_cb = ((res["vm"] + p["wf"] * np.cos(p["alpha"]))
                 * np.cos(res["beta_arr"][i]))
        circ_i = (res["Omega"] * res["r_arr"][i]
                 - res["vm"] * np.tan(p["alpha"])
                 - p["wf"] * np.sin(p["alpha"]))
        circ_cd = circ_i * np.cos(res["delta_arr"][i])
        return [label, f"{res['r_arr'][i]:.4f}",
                f"{np.degrees(res['beta_arr'][i]):.3f}",
                f"{np.degrees(res['delta_arr'][i]):.3f}",
                f"{vm_cb:.4f}", f"{circ_cd:.4f}",
                f"{res['vstrike_arr'][i]:.4f}"]

    headers = ["Position", "r (m)", "b (deg)", "d (deg)",
              "(vm+wf.cosa).cosb", "(Wr-...).cosd", "vstrike (m/s)"]
    rows = [row(label, i) for label, i in _hub_mid_tip(res)]
    return _data_table(headers, rows)


def _mortality_integrand_table(res):
    def row(label, i):
        val = res["fMR_arr"][i] * res["Pco_arr"][i] * res["r_arr"][i]
        return [label, f"{res['r_arr'][i]:.4f}", f"{res['d_arr'][i] * 1000:.2f}",
                f"{res['Pco_arr'][i]:.6f}", f"{res['vstrike_arr'][i]:.4f}",
                f"{res['fMR_arr'][i]:.6f}", f"{val:.8f}"]

    headers = ["Position", "r (m)", "d (mm)", "Pco", "vstrike (m/s)",
              "fMR", "fMR.Pco.r"]
    rows = [row(label, i) for label, i in _hub_mid_tip(res)]
    return _data_table(headers, rows)


def _mutilation_regime_table(res):
    p = res["params"]
    rows = [["Scaly", rng, a, b, "max(4.8, -2.8.Lf/d + 10.3)"]
            for rng, a, b in _SCALY_REGIME_TABLE]
    rows.append(["Eel", "1-30", "0.0024", "-", f"{p['eel_vcrit']:.4f} m/s"])
    headers = ["Species", "Lf/d range", "a", "b", "vcrit"]
    return _data_table(headers, rows)


def _collision_probability_section(res):
    circ_abs = abs(res["circ_tip"])
    denom_v = max(abs(res["vm"] + res["params"]["wf"]
                      * np.cos(res["params"]["alpha"])), _EPS)
    return "".join([
        _equation_block("Eq 5 - Collision probability", [
            "Pco = Leff,m . |Wr - vm.tan(a) - wf.sin(a)| / "
            "[max(2.pi.r/Nr - Leff,t, eps) . |vm + wf.cos(a)|]",
            f"Pco (tip) = {res['Leff_m']:.4f} x {circ_abs:.4f} / "
            f"[max({res['chan_tip']:.4f} - {res['Leff_t']:.4f}, eps) x "
            f"{denom_v:.4f}]",
            f"          = {res['Pco_tip']:.6f}  ({res['Pco_tip'] * 100:.4f} %)",
        ]),
        _result_box(f"Pco (tip) = {res['Pco_tip'] * 100:.4f}%"),
        "<p style='color:#64748b;font-size:11px;'>Pco is bounded to "
        "[0, 1] and varies along the radial coordinate - see the "
        "strike-velocity/mortality-integrand tables above for the "
        "hub/mid-span/tip values actually used in the integral below.</p>",
    ])


def _mutilation_section(res):
    p = res["params"]
    if p["species"] == "eel":
        fmr_eq = "fMR = max[0, a . (Lf/d) . (vstrike - vcrit)]"
        eq_num, eq_sub = "17", (
            f"fMR (tip) = max[0, {res['a_tip']:.4f} x {res['Lf_d_tip']:.2f} "
            f"x ({res['vstrike_tip']:.4f} - {res['vcrit_tip']:.4f})] "
            f"= {res['fMR_tip']:.6f}")
    else:
        fmr_eq = "fMR = max[0, (a.ln(Lf/d) + b) . (vstrike - vcrit)]"
        eq_num, eq_sub = "16", (
            f"fMR (tip) = max[0, ({res['a_tip']:.4f} x "
            f"ln({res['Lf_d_tip']:.2f}) + {res['b_tip']:.4f}) x "
            f"({res['vstrike_tip']:.4f} - {res['vcrit_tip']:.4f})] "
            f"= {res['fMR_tip']:.6f}")
    b_disp = f"{res['b_tip']:.4f}" if res["b_tip"] is not None else "- (eel)"
    return "".join([
        f"<p style='color:{_MUTED};font-size:11px;'>Tip Lf/d = "
        f"{res['Lf_d_tip']:.2f} &rarr; regime <b>{res['regime_tip']}</b>, "
        f"a = {res['a_tip']:.4f}, b = {b_disp}, "
        f"vcrit = {res['vcrit_tip']:.4f} m/s</p>",
        _equation_block(f"Eq {eq_num} - Mutilation ratio", [fmr_eq, eq_sub]),
        _result_box(f"fMR (tip) = {res['fMR_tip']:.6f}"),
    ])


def _mortality_section(res):
    p = res["params"]
    return "".join([
        _equation_block("Eq 20 - Mortality integral", [
            "Pm = 2/(r + bh) . integral[0,1] fMR(f).Pco(f).r(f) df",
            f"Pm = 2/({p['r']:.4f} + {p['bh']:.4f}) x {res['integral']:.6f} "
            f"= {res['Pm']:.6f}",
        ]),
        "<p style='margin:6px 0;'>Integrand evaluated at hub, mid-span "
        "and tip:</p>",
        _mortality_integrand_table(res),
        _result_box(f"Pm = {res['Pm'] * 100:.4f}%"),
        _equation_block("Eq 4 - Passage survival rate", [
            "S = 1 - Pm",
            f"S = 1 - {res['Pm']:.6f} = {res['S']:.6f}",
        ]),
        _result_box(f"S = {res['S'] * 100:.4f}%"),
    ])


def _empirical_section(res):
    if "Pco_obs" not in res:
        return ""
    p = res["params"]
    return "".join([
        f"<h3 style='color:{_DARK};'>Empirical comparison</h3>",
        "<p>Observed strike counts replace the per-strip Pco with a "
        "constant empirical estimate:</p>",
        _equation_block("Empirical collision probability", [
            "Pco,obs = k / n",
            f"Pco,obs = {p['strike']} / {p['total']} = {res['Pco_obs']:.6f}",
        ]),
        _result_box(
            f"95% CI: [{res['wilson_lo'] * 100:.4f}%, "
            f"{res['wilson_hi'] * 100:.4f}%]"),
        "<p>Mortality from the empirical encounter rate (Eq 20 with "
        "constant Pco):</p>",
        _equation_block("Mortality from observed Pco", [
            "Pm,obs = 2/(r + bh) . Pco,obs . integral[0,1] fMR(f).r(f) df",
            f"Pm,obs = 2/({p['r']:.4f} + {p['bh']:.4f}) x "
            f"{res['Pco_obs']:.6f} x integral = {res['Pm_obs']:.6f}",
        ]),
        _result_box(
            f"Pm,obs = {res['Pm_obs'] * 100:.4f}% | "
            f"S,obs = {res['S_obs'] * 100:.4f}%"),
    ])


def _species_section(res):
    """One species' full methodology walkthrough - every step the old
    MVP reporter showed, in the app's own (non-MathJax) HTML style."""
    p = res["params"]
    h = [f"<h2 style='color:{_DARK};'>{_species_label(p['species'])}</h2>"]

    h.append(f"<h3 style='color:{_DARK};'>Inputs</h3>")
    h.append(_kv_table([
        ("Species",                    p["species"]),
        ("Fish body length Lf (m)",    f"{p['lf']:g}"),
        ("Fish body height Bf (m)",    f"{p['bf']:g}"),
        ("Relative fish velocity wf (m/s)", f"{p['wf']:g}"),
        ("Pre-rotation angle alpha (rad)", f"{p['alpha']:g}"),
        ("Eel critical velocity (m/s)", f"{p['eel_vcrit']:g}"),
        ("Number of blades n",         p["n"]),
        ("Shaft speed N (rpm)",        f"{p['N']:g}"),
        ("Flow rate Q (m3/s)",         f"{p['Q']:g}"),
        ("Tip radius r (m)",           f"{p['r']:g}"),
        ("Hub radius bh (m)",          f"{p['bh']:g}"),
    ]))

    h.append(f"<h3 style='color:{_DARK};'>Blade profile</h3>")
    h.append("<p>Measurement positions along the leading edge, "
             "interpolated by natural cubic spline:</p>")
    h.append(_blade_profile_table(p))

    h.append(f"<h3 style='color:{_DARK};'>Effective fish length</h3>")
    h.append(_effective_length_section(res))
    h.append(_result_box(
        f"Leff,m = {res['Leff_m']:.6f} m | Leff,t = {res['Leff_t']:.6f} m"))

    h.append(f"<h3 style='color:{_DARK};'>Pump kinematics</h3>")
    h.append(_pump_kinematics_section(res))

    h.append(f"<h3 style='color:{_DARK};'>Strike velocity</h3>")
    h.append("<p>Strike velocity combines axial and tangential relative "
             "motion, modulated by leading-edge angles &beta; and "
             "&delta; (Eq 19):</p>")
    h.append(_strike_velocity_table(res))

    h.append(f"<h3 style='color:{_DARK};'>Collision probability</h3>")
    h.append(_collision_probability_section(res))

    h.append(f"<h3 style='color:{_DARK};'>Mutilation ratio</h3>")
    h.append("<p>Table 3 parameters (EVS-EN 18110:2025):</p>")
    h.append(_mutilation_regime_table(res))
    h.append(_mutilation_section(res))

    h.append(f"<h3 style='color:{_DARK};'>Blade strike mortality</h3>")
    h.append("<p>Pco and fMR vary along the leading edge - total "
             "mortality is a flow-weighted integral:</p>")
    h.append(_mortality_section(res))

    h.append(_empirical_section(res))
    return "".join(h)


def build_bsm_report_html(res, res_other=None, image_paths=None,
                          embed_images=True):
    """Full methodology report for one BSM result, or both species in one
    document when `res_other` (the other species' own independent
    `bsm_model.compute()` result - dual-species default, ROADMAP.md item
    15) is supplied. `image_paths` - figures (e.g. the Sensitivity page's
    Pco/Pm bars) embedded at the end, shared across both species since
    they aren't species-specific themselves."""
    h = ["<div style='font-family:Segoe UI, Arial, sans-serif;"
         "color:#1e293b;font-size:13px;'>"]
    h.append(f"<h1 style='color:{_DARK};'>Blade Strike Modelling Report</h1>")
    h.append(f"<p style='color:{_MUTED};font-size:11px;'>Generated by "
             f"StrikeWorks on {datetime.now().strftime('%Y-%m-%d %H:%M')}."
             "</p>")

    h.append(_species_section(res))
    if res_other is not None:
        h.append("<hr style='margin:24px 0;border:none;"
                 f"border-top:1px solid {_BORD};'/>")
        h.append(_species_section(res_other))

    image_paths = image_paths or {}
    figs = [f for f in image_paths.values() if f]
    if figs:
        h.append(f"<h2 style='color:{_DARK};'>Figures</h2>")
        for f in figs:
            h.append(_img_tag(f, embed_images))

    h.append("</div>")
    return "".join(h)
