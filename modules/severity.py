# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Strike severity: how hard each recording was hit, measured rather than
predicted - the peak high-g acceleration magnitude (HIG) over the
recording's window, banded at 95, 200 and 400 g. Only a peak over 400 g is
a severe strike; the model flags contacts of any size.

predict_worker.py computes it (hig_peak_g / severity / severe_strike per
recording, n_over_<g>g and severe_rate per treatment, severity_summary.csv);
this module presents it. The thresholds here must match the worker's
(tests/test_rules.py checks).
"""
THRESHOLDS_G = (95, 200, 400)
SEVERE_G = 400
BANDS = ("<=95 g", "95-200 g", "200-400 g", ">400 g")
BAND_LABELS = ("≤ 95 g", "95–200 g", "200–400 g", "> 400 g (severe)")

TABLE_HEADERS = ["> 95 g", "> 200 g", "> 400 g (severe)", "Severe 95% CI",
                 "Strikes > 400 g"]


def available(summary):
    """True when the run measured severity (the dataset had HIG)."""
    return summary is not None and f"n_over_{SEVERE_G}g" in summary.columns


def table_values(row):
    """The treatment table's severity cells, for one summary row."""
    n = int(row["n"])
    cells = []
    for g in THRESHOLDS_G:
        k = int(row[f"n_over_{g}g"])
        cells.append(f"{k} ({k / n * 100:.0f}%)" if n else "0")
    cells.append(f"{row['severe_ci_lo'] * 100:.1f}% – "
                 f"{row['severe_ci_hi'] * 100:.1f}%")
    n_strike = int(row["n_strike"])
    k = int(row["n_strike_severe"])
    cells.append(f"{k} of {n_strike}")
    return cells


def band_rows(predictions):
    """[(band label, "count (share)")] for a MetaCard."""
    bands = band_counts(predictions)
    total = sum(c for _l, c in bands) or 1
    return [(label, f"{c} ({c / total * 100:.0f}%)") for label, c in bands]


def band_counts(predictions):
    """[(band label, count)] over every recording, in band order."""
    if predictions is None or "severity" not in predictions.columns:
        return []
    counts = predictions["severity"].value_counts()
    return [(label, int(counts.get(band, 0)))
            for band, label in zip(BANDS, BAND_LABELS)]
