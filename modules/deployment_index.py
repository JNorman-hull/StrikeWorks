# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""The deployment plan, and the treatment rows it puts in the sensor index.

A study is planned before any sensor is wetted: the site, the deployment,
the machine, and then one set of conditions per treatment (head, flow, BEP,
RPM and how many runs). The Prepare page's Study design tab collects that
and writes it into the library's ``global_sensor_index.csv`` - one row per
treatment, so processing can stamp sensors with a treatment rather than
having deployment metadata typed in per file.

Plan rows and sensor rows share one file
----------------------------------------
A plan row is a real row of the index with ``file`` set to ``label_pad``.
Nothing else in the app ever produces a sensor called that, so plan rows are
easy to keep out of the way: ``sensor_rows()`` drops them and every page
that lists or counts sensors uses it. They are deliberately *not* dropped
when a page rewrites the whole index - that would delete the plan.

The columns come from the library's own ``config/index_config.txt``, the
same list ``rapid_functions.append_to_sensor_index`` builds a processed
sensor's row from, so plan rows and sensor rows always align.
"""
from pathlib import Path

import pandas as pd

from PySide6.QtCore import QObject, Signal

INDEX_REL = Path("processed_sens_data") / "index" / "global_sensor_index.csv"
INDEX_CONFIG_REL = Path("config") / "index_config.txt"

#: value in the `file` column that marks a row as plan, not sensor
PAD_FILE = "label_pad"

FILE_COL = "file"
TREATMENT_COL = "treatment"

# what the Study design tab collects, and the index column each lands in
DEPLOYMENT_FIELDS = [
    ("site", "Site"),
    ("deployment_id", "Deployment ID"),
    ("pump_turbine", "Pump / turbine model"),
    ("type", "Pump / turbine type"),
]

TREATMENT_FIELDS = [
    ("treatment", "Treatment"),
    ("head", "Head"),
    ("flow", "Flow"),
    ("point_bep", "BEP (%)"),
    ("rpm", "RPM"),
    ("run", "Runs"),
]

#: every column a treatment carries onto a sensor when one is assigned
STAMPED_COLUMNS = ([c for c, _ in DEPLOYMENT_FIELDS]
                   + [c for c, _ in TREATMENT_FIELDS])

# used when a library has no config/index_config.txt to take columns from
_FALLBACK_COLUMNS = [FILE_COL, "sensor", "date_deploy"] + STAMPED_COLUMNS


class _Notifier(QObject):
    """Emits when a library's plan is written, so pages can re-read it."""
    plan_saved = Signal(str)       # library root


notifier = _Notifier()


# ── reading ──────────────────────────────────────────────────────────────────
def index_path(root) -> Path:
    return Path(root) / INDEX_REL


def read_index(root):
    """The whole index - plan rows included. None when there is not one."""
    path = index_path(root)
    if not path.exists():
        return None
    try:
        return pd.read_csv(path, low_memory=False)
    except Exception:
        return None


def is_plan_row(df):
    """Boolean mask of the plan rows in `df`."""
    if df is None or FILE_COL not in df.columns:
        return None
    return df[FILE_COL].astype(str).str.strip().str.lower() == PAD_FILE


def sensor_rows(df):
    """`df` without its plan rows - what every sensor listing wants."""
    mask = is_plan_row(df)
    if mask is None:
        return df
    return df[~mask].copy()


def plan_rows(df):
    """Just the plan rows."""
    mask = is_plan_row(df)
    if mask is None:
        return df.iloc[0:0].copy() if df is not None else None
    return df[mask].copy()


def treatments(root):
    """The planned treatments in a library, newest plan last.

    Returns [{column: value}] with one entry per treatment row, ready to be
    stamped onto a sensor. Empty when the library has no plan.
    """
    df = read_index(root)
    if df is None:
        return []
    rows = plan_rows(df)
    if rows is None or rows.empty:
        return []
    out = []
    for _, row in rows.iterrows():
        entry = {c: ("" if pd.isna(row.get(c, "")) else str(row.get(c, "")))
                 for c in STAMPED_COLUMNS if c in rows.columns}
        if entry.get(TREATMENT_COL, "").strip():
            out.append(entry)
    return out


def describe(treatment) -> str:
    """One-line label for a treatment, for a picker or a log."""
    name = treatment.get(TREATMENT_COL, "").strip() or "(unnamed)"
    bits = []
    for col, label in TREATMENT_FIELDS:
        if col == TREATMENT_COL:
            continue
        val = str(treatment.get(col, "")).strip()
        if val:
            bits.append(f"{label} {val}")
    return f"{name} — {', '.join(bits)}" if bits else name


# ── columns ──────────────────────────────────────────────────────────────────
def index_columns(root):
    """The index's column list, from the library's index_config.txt.

    Falls back to whatever an existing index already has, then to a minimal
    set, so a plan can still be written into a library that is not fully
    configured.
    """
    cfg = Path(root) / INDEX_CONFIG_REL
    if cfg.exists():
        try:
            cols = []
            for line in cfg.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                name = line.split("=", 1)[0].strip() if "=" in line else line
                if name and name not in cols:
                    cols.append(name)
            if cols:
                return cols
        except Exception:
            pass

    existing = read_index(root)
    if existing is not None and len(existing.columns):
        return list(existing.columns)
    return list(_FALLBACK_COLUMNS)


# ── writing ──────────────────────────────────────────────────────────────────
def save_plan(root, deployment, treatments_in, replace_existing=True):
    """Write the plan into the library's index, one row per treatment.

    `deployment` is {column: value} for the whole deployment; `treatments_in`
    is a list of the same for each treatment. Sensor rows already in the
    index are left exactly as they are; only plan rows are rewritten (unless
    `replace_existing` is False, in which case the new ones are appended).

    Returns (path, n_written).
    """
    root = Path(root)
    path = index_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)

    columns = index_columns(root)
    existing = read_index(root)

    rows = []
    for treatment in treatments_in:
        row = {c: "" for c in columns}
        row[FILE_COL] = PAD_FILE
        for col, value in {**deployment, **treatment}.items():
            if col in row:
                row[col] = value
        rows.append(row)
    new = pd.DataFrame(rows, columns=columns)

    if existing is None:
        out = new
    else:
        keep = sensor_rows(existing) if replace_existing else existing
        out = pd.concat([new, keep], ignore_index=True)
        # a library configured after its first plan may have gained columns
        for col in columns:
            if col not in out.columns:
                out[col] = ""

    out.to_csv(path, index=False)
    notifier.plan_saved.emit(str(root))
    return path, len(new)


def apply_treatment(root, files, treatment):
    """Stamp a treatment's values onto the index rows of `files`.

    Called after processing so a batch of sensors carries the conditions it
    was run under. Returns the number of rows changed; 0 when there is no
    index yet or none of the files are in it.
    """
    df = read_index(root)
    if df is None or FILE_COL not in df.columns or not files:
        return 0

    wanted = {str(f) for f in files}
    mask = df[FILE_COL].astype(str).isin(wanted)
    n = int(mask.sum())
    if not n:
        return 0

    for col in STAMPED_COLUMNS:
        value = str(treatment.get(col, "")).strip()
        if not value:
            continue
        if col not in df.columns:
            df[col] = ""
        # a column read back as float (head, flow, rpm...) will not take a
        # string in place, so widen it first rather than lose the value
        df[col] = df[col].astype(object)
        df.loc[mask, col] = value

    df.to_csv(index_path(root), index=False)
    return n
