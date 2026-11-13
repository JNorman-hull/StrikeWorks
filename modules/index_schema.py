"""The columns of ``global_sensor_index.csv``, in the order indexes have
always been written. Each entry is (column, default); a default of None
takes the value from the parser's summary, under ``source`` where the
parser's name differs. Everything reads and writes the index through
``columns()`` and ``row_for()``.
"""

# (column, default, source-key-in-summary)
#   default None  -> filled from the parser summary
#   source None   -> the summary key is the column name
SCHEMA = [
    ("file", None, "file"),
    ("sensor", None, "sensor"),
    ("date_deploy", None, "date_deploy"),
    ("duration.mm.ss.", None, "duration[mm:ss]"),
    ("bad_sens", "N", None),

    # deployment - written by Create and edit deployment and processing
    ("site", "NA", None),
    ("deployment_id", "NA", None),
    ("pump_turbine", "NA", None),
    ("type", "NA", None),
    ("rpm", "NA", None),
    ("head", "NA", None),
    ("flow", "NA", None),
    ("point_bep", "NA", None),
    ("treatment", "NA", None),
    ("run", "NA", None),
    ("deployment_info", "N", None),
    ("deployment_config", "NA", None),

    # delineation / normalisation
    ("roi_config", "NA", None),
    ("delineated", "N", None),
    ("trimmed", "N", None),
    ("normalized", "N", None),
    ("passage_times", "N", None),
    ("passage_duration.mm.ss.", "NA", None),
    ("ingress_nadir_duration.mm.ss.", "NA", None),
    ("nadir_outgress_duration.mm.ss.", "NA", None),

    # per-signal processing flags
    ("pres_config", "NA", None),
    ("all_pres_processed", "N", None),
    ("pres_sum_processed", "N", None),
    ("pres_rpc_processed", "N", None),
    ("pres_lrpc_processed", "N", None),
    ("acc_config", "NA", None),
    ("all_acc_processed", "N", None),
    ("acc_sum_processed", "N", None),
    ("acc_hig_peaks_processed", "N", None),
    ("acc_strike_processed", "N", None),
    ("acc_collision_processed", "N", None),
    ("rot_config", "NA", None),
    ("all_rot_processed", "N", None),
    ("rot_sum_processed", "N", None),

    # summary values from the parser
    ("pres_min.kPa.", None, "pres_min[kPa]"),
    ("pres_min.time.", None, "pres_min[time]"),
    ("HIG_max.g.", None, "HIG_max[g]"),
    ("HIG_max.time.", None, "HIG_max[time]"),
    ("sampling_rate_hz", None, "sampling_rate_hz"),
    ("messages", None, "messages"),
]


def columns():
    """Every column, in order."""
    return [c for c, _d, _s in SCHEMA]


def defaults():
    """{column: default} for the columns that have one."""
    return {c: d for c, d, _s in SCHEMA if d is not None}


def row_for(info):
    """Build one index row from a parser's summary.

    Columns the summary does not carry take their default (or "" when they
    have none), so the row always has the full column set.
    """
    row = {}
    for column, default, source in SCHEMA:
        if default is not None:
            row[column] = default
            continue
        value = info.get(source or column, "")
        row[column] = "" if value is None else str(value)
    return row
