# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""HIG peak analysis: acceleration events in each recording's high-g
magnitude (higacc_mag_g), counted around the pressure nadir.

Peak finding follows the original R analysis:
  1. local maxima (a strict rise then fall) of at least HEIGHT_G;
  2. prominence: the peak stands PROMINENCE_G above the higher of the two
     minima within INTERPEAK_S either side of it;
  3. inter-peak distance: of peaks within INTERPEAK_S of each other, the
     highest is kept (scanning forward from the earliest);
  4. type: above 70 % of its height for less than SHEAR_S it is a
     collision, otherwise a shear.

Dataset windows are 200 ms centred on the validated nadir, so the nadir is
each window's centre sample and the region of interest, nadir +/- 0.1 s,
is the whole window. A recording has a collision when one of its events
reaches COLLISION_G there. Collision probability is the share of
recordings with at least one, with a Wilson 95 % interval.

No Qt and no package-relative imports: the prediction worker imports this
module both as `modules.hig_peaks` and, run as a script, as `hig_peaks`.
"""
import math

import numpy as np
import pandas as pd

HEIGHT_G = 95.0
PROMINENCE_G = 25.0
INTERPEAK_S = 0.002
SHEAR_S = 0.0075          # 15 samples at 2000 Hz
SHEAR_FRACTION = 0.7
THRESHOLDS_G = (95, 200, 400)
COLLISION_G = 400
NADIR_WINDOW_S = 0.1
ROI_LABEL = "nadir (±0.1 s)"
ALL_LABEL = "All recordings"
CHANNEL = "higacc_mag_g"

PEAK_COLUMNS = ["file", "peak_number", "peak_time_s", "time_from_nadir_s",
                "peak_g", "peak_type", "duration_samples", "in_roi"]

# per-recording columns added to predictions.csv
FILE_COLUMNS = ["n_events"] + [f"n_events_{g}g" for g in THRESHOLDS_G[1:]] + [
    "max_event_g", "collision", "collision_g", "collision_time_s"]


def parameters():
    """The analysis settings, for run_meta.json and the report."""
    return {"channel": CHANNEL, "height_g": HEIGHT_G,
            "prominence_g": PROMINENCE_G, "interpeak_s": INTERPEAK_S,
            "shear_s": SHEAR_S, "thresholds_g": list(THRESHOLDS_G),
            "collision_g": COLLISION_G, "nadir_window_s": NADIR_WINDOW_S}


def sample_rate(time):
    """Samples per second from the median time step (rounded, as the R
    analysis did)."""
    step = np.nanmedian(np.diff(np.asarray(time, dtype=float)))
    return round(1 / step) if step > 0 else None


def find_peaks(acc, time, height=HEIGHT_G, prominence=PROMINENCE_G,
               interpeak_s=INTERPEAK_S, shear_s=SHEAR_S):
    """The acceleration events in one recording, as a DataFrame of
    peak_number, peak_index, peak_time_s, peak_g, peak_type ("collision" /
    "shear") and duration_samples, in time order."""
    acc = np.nan_to_num(np.asarray(acc, dtype=float))
    time = np.asarray(time, dtype=float)
    empty = pd.DataFrame(columns=["peak_number", "peak_index", "peak_time_s",
                                  "peak_g", "peak_type", "duration_samples"])
    fs = sample_rate(time) if len(acc) >= 3 else None
    if not fs:
        return empty
    gap = int(round(interpeak_s * fs))
    shear_samples = int(round(shear_s * fs))
    n = len(acc)

    # 1. strict local maxima at or above the height
    peaks = np.where(np.diff(np.sign(np.diff(acc))) == -2)[0] + 1
    peaks = peaks[acc[peaks] >= height]

    # 2. prominence against the minima within `gap` samples either side
    def prominent(p):
        left = acc[max(0, p - gap):p + 1].min()
        right = acc[p:min(n, p + gap + 1)].min()
        return acc[p] - max(left, right) >= prominence
    peaks = [int(p) for p in peaks if prominent(p)]

    # 3. one peak per `gap` samples: the highest of each run
    kept, i = [], 0
    while i < len(peaks):
        j = i
        while j + 1 < len(peaks) and peaks[j + 1] <= peaks[i] + gap:
            j += 1
        run = peaks[i:j + 1]
        kept.append(run[int(np.argmax(acc[run]))])
        i = j + 1
    if not kept:
        return empty

    # 4. how long it stays above 70 % of its height
    rows = []
    for number, p in enumerate(kept, start=1):
        level = SHEAR_FRACTION * acc[p]
        left = p
        while left > 0 and acc[left] >= level:
            left -= 1
        right = p
        while right < n - 1 and acc[right] >= level:
            right += 1
        duration = right - left
        rows.append({"peak_number": number, "peak_index": p,
                     "peak_time_s": time[p],
                     # the sensor's 0.1 g resolution
                     "peak_g": round(float(acc[p]), 1),
                     "peak_type": ("collision" if duration < shear_samples
                                   else "shear"),
                     "duration_samples": duration})
    return pd.DataFrame(rows)


def hig_magnitude(df):
    """The HIG magnitude series (g) for a dataset, or None without HIG."""
    if CHANNEL in df.columns:
        return df[CHANNEL].astype(float)
    axes = ("higacc_x_g", "higacc_y_g", "higacc_z_g")
    if all(c in df.columns for c in axes):
        return np.sqrt(sum(df[c].astype(float) ** 2 for c in axes))
    return None


def analyse(df, files=None):
    """Peak events and per-recording results for a dataset.

    Returns (events, per_file): `events` has PEAK_COLUMNS, one row per
    event; `per_file` is indexed by file (in `files` order when given) with
    FILE_COLUMNS - counts and the largest event within the region of
    interest, and the collision (1/0) with its size and time, the one
    closest to the nadir. (None, None) when the dataset has no HIG."""
    mag = hig_magnitude(df)
    if mag is None:
        return None, None
    data = pd.DataFrame({"file": df["file"].values,
                         "time_s": df["time_s"].astype(float).values,
                         "acc": mag.values})
    order = list(files) if files is not None else list(
        dict.fromkeys(data["file"]))
    event_parts, results = [], {}
    for file_id, rec in data.groupby("file", sort=False):
        rec = rec.sort_values("time_s", kind="stable")
        time = rec["time_s"].values
        nadir_t = time[len(time) // 2]
        peaks = find_peaks(rec["acc"].values, time)
        if len(peaks):
            peaks.insert(0, "file", file_id)
            peaks["time_from_nadir_s"] = peaks["peak_time_s"] - nadir_t
            peaks["in_roi"] = (peaks["time_from_nadir_s"].abs()
                               <= NADIR_WINDOW_S + 1e-9)
            event_parts.append(peaks)
        results[file_id] = _file_result(peaks)
    events = (pd.concat(event_parts, ignore_index=True)[PEAK_COLUMNS]
              if event_parts else pd.DataFrame(columns=PEAK_COLUMNS))
    per_file = pd.DataFrame.from_dict(results, orient="index",
                                      columns=FILE_COLUMNS)
    per_file = per_file.reindex(order)
    per_file.index.name = "file"
    return events, per_file


def _file_result(peaks):
    roi = peaks[peaks["in_roi"]] if len(peaks) else peaks
    out = {"n_events": int(len(roi))}
    for g in THRESHOLDS_G[1:]:
        out[f"n_events_{g}g"] = int((roi["peak_g"] >= g).sum()) if len(roi) else 0
    out["max_event_g"] = float(roi["peak_g"].max()) if len(roi) else np.nan
    hits = roi[roi["peak_g"] >= COLLISION_G] if len(roi) else roi
    if len(hits):
        closest = hits.loc[hits["time_from_nadir_s"].abs().idxmin()]
        out.update(collision=1, collision_g=float(closest["peak_g"]),
                   collision_time_s=round(float(closest["peak_time_s"]), 4))
    else:
        out.update(collision=0, collision_g=np.nan, collision_time_s=np.nan)
    return out


def wilson_ci(k, n, z=1.96):
    """(proportion, lower, upper) - the Wilson score interval."""
    if n == 0:
        return 0.0, 0.0, 0.0
    p = k / n
    denom = 1 + z ** 2 / n
    centre = (p + z ** 2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z ** 2 / (4 * n ** 2)) / denom
    return p, max(0.0, centre - half), min(1.0, centre + half)


def summary(events, per_file, treatments=None):
    """The acceleration table: one row per treatment (in name order, as
    the prediction summary), and an "All recordings" row when there is
    more than one. `treatments` maps file ->
    treatment (a Series indexed by file); without it every recording is one
    group.

    Columns: treatment, roi, n_events_<g>g for each threshold, n_sensors,
    n_collision, collision_rate, ci_lo, ci_hi, and acc_min_g, acc_q1_g,
    acc_median_g, acc_q3_g, acc_max_g over the events in the region of
    interest."""
    if treatments is None:
        groups = pd.Series(ALL_LABEL, index=per_file.index)
    else:
        groups = treatments.reindex(per_file.index).fillna("").astype(str)
    roi_events = events[events["in_roi"].astype(bool)] if len(events) else events

    def row(label, files):
        ev = roi_events[roi_events["file"].isin(files)] if len(roi_events) else roi_events
        sub = per_file.loc[files]
        n = len(sub)
        k = int(sub["collision"].sum())
        rate, lo, hi = wilson_ci(k, n)
        out = {"treatment": label, "roi": ROI_LABEL}
        for g in THRESHOLDS_G:
            out[f"n_events_{g}g"] = int((ev["peak_g"] >= g).sum()) if len(ev) else 0
        out.update(n_sensors=n, n_collision=k, collision_rate=round(rate, 6),
                   ci_lo=round(lo, 6), ci_hi=round(hi, 6))
        values = ev["peak_g"].astype(float).values if len(ev) else np.array([])
        stats = (np.min(values), *np.percentile(values, [25, 50, 75]),
                 np.max(values)) if len(values) else (np.nan,) * 5
        for name, value in zip(("acc_min_g", "acc_q1_g", "acc_median_g",
                                "acc_q3_g", "acc_max_g"), stats):
            out[name] = round(float(value), 1) if np.isfinite(value) else np.nan
        return out

    rows = [row(label, list(files.index))
            for label, files in groups.groupby(groups, sort=True)]
    if len(rows) > 1:
        rows.append(row(ALL_LABEL, list(per_file.index)))
    return pd.DataFrame(rows)


# ── the acceleration table, as the report template lays it out ─────────────
TABLE_GROUPS = (("Event count", 3), ("Collision probability", 3),
                ("Acceleration (g)", 3))
TABLE_COLUMNS = ("≥95 g", "≥200 g", "≥400 g", "Total sensors",
                 "Total ≥ 1 collision ‡", "Probability [95% CI]",
                 "Minimum", "Maximum", "IQR")
TABLE_NOTES = (
    "† A collision detected within ±0.1 s of the nadir.",
    f"‡ ≥{COLLISION_G} g used as the threshold for a collision.",
    f"Events: HIG peaks of at least {HEIGHT_G:.0f} g (prominence "
    f"{PROMINENCE_G:.0f} g, at least {INTERPEAK_S * 1000:g} ms apart). "
    "Acceleration is over those events; IQR is the 25th-75th percentile. "
    "95% CI: Wilson score interval.",
)


def _g(value):
    return "-" if pd.isna(value) else f"{value:.1f}"


def table_rows(acc_summary):
    """[(treatment, roi, [cell, ...])] for the acceleration table, the
    cells in TABLE_COLUMNS order."""
    out = []
    for _, r in acc_summary.iterrows():
        cells = [str(int(r[f"n_events_{g}g"])) for g in THRESHOLDS_G]
        cells += [str(int(r["n_sensors"])), str(int(r["n_collision"])),
                  f"{r['collision_rate'] * 100:.1f}% "
                  f"[{r['ci_lo'] * 100:.1f} - {r['ci_hi'] * 100:.1f}] †",
                  _g(r["acc_min_g"]), _g(r["acc_max_g"]),
                  "-" if pd.isna(r["acc_q1_g"]) else
                  f"{r['acc_q1_g']:.1f} - {r['acc_q3_g']:.1f}"]
        out.append((str(r["treatment"]), str(r["roi"]), cells))
    return out


def show_treatment(acc_summary):
    """Whether the table needs a Treatment column (more than one group)."""
    return acc_summary is not None and len(acc_summary) > 1


# ── acceleration-centred traces ──────────────────────────────────────────────
MEDIAN_BIN = 0.0025


def centred_traces(df, files, facet_col=None):
    """Each recording's HIG magnitude on two normalised time axes, as in
    the R figures: `time_norm_acc` puts the recording's peak acceleration
    at 0.5 and `time_norm_nadir` the nadir (the window centre), each side
    stretched to fill 0-0.5 and 0.5-1. Columns: file, facet, time_s,
    higacc_mag_g, time_norm_acc, time_norm_nadir."""
    mag = hig_magnitude(df)
    if mag is None or not len(files):
        return pd.DataFrame(columns=["file", "facet", "time_s", CHANNEL,
                                     "time_norm_acc", "time_norm_nadir"])
    data = pd.DataFrame({"file": df["file"].values,
                         "time_s": df["time_s"].astype(float).values,
                         CHANNEL: mag.values})
    data["facet"] = (df[facet_col].astype(str).values
                     if facet_col and facet_col in df.columns else ALL_LABEL)
    data = data[data["file"].isin(set(files))]
    parts = []
    for _file_id, rec in data.groupby("file", sort=False):
        rec = rec.sort_values("time_s", kind="stable").copy()
        t = rec["time_s"].values
        start, end = t.min(), t.max()
        peak_t = t[int(np.nanargmax(rec[CHANNEL].values))]
        nadir_t = t[len(t) // 2]
        rec["time_norm_acc"] = _normalise(t, start, peak_t, end)
        rec["time_norm_nadir"] = _normalise(t, start, nadir_t, end)
        parts.append(rec)
    out = pd.concat(parts, ignore_index=True)
    ok = out["time_norm_acc"].between(0, 1) & out["time_norm_nadir"].between(0, 1)
    return out[ok].reset_index(drop=True)


def _normalise(t, start, mid, end):
    with np.errstate(divide="ignore", invalid="ignore"):
        before = (t - start) / (2 * (mid - start))
        after = 0.5 + (t - mid) / (2 * (end - mid))
    return np.where(t <= mid, before, after)


def median_trace(traces, x_col):
    """The median HIG per facet in MEDIAN_BIN bins of `x_col`: columns
    facet, time_bin, median_g."""
    if not len(traces):
        return pd.DataFrame(columns=["facet", "time_bin", "median_g"])
    binned = traces.assign(
        time_bin=(traces[x_col] / MEDIAN_BIN).round() * MEDIAN_BIN)
    return (binned.groupby(["facet", "time_bin"], sort=True)[CHANNEL]
            .median().rename("median_g").reset_index())
