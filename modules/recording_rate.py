"""What a dataset's rows are: which sensor recorded them and at what rate,
read from the data itself rather than from the sensor selected in the app.

A model's input is a fixed number of samples from one device, so it only
means anything on data from that device at that rate. A dataset therefore
holds one sensor at one rate (`dataset_problem`), a model records both when
it's trained, and prediction refuses any other (`model_problem`).

The sensor is the `sensor_config` column dataset_build carries over from the
index. Datasets without it and models without these fields were all made from
RAPID at 2000 Hz, before any other device could reach a model.

No Qt and no package-relative imports needed: the workers import this both as
`modules.recording_rate` and, run as scripts, as `recording_rate`.
"""
import numpy as np
import pandas as pd

try:
    from .hig_peaks import sample_rate
except ImportError:          # run as a script from source (worker_launch.py)
    from hig_peaks import sample_rate

SENSOR_COL = "sensor_config"
RATE_FIELD = "sampling_rate_hz"
LEGACY_SENSOR = "rapid"
LEGACY_RATE = 2000
_SENSOR_NAMES = {"rapid": "RAPID", "micro_eel": "Micro-EEL"}
# enough rows for the median time step, without walking long recordings
_RATE_ROWS = 50


def read_dataset_csv(path):
    """A dataset CSV: (DataFrame, None), or (None, why it can't be used)."""
    try:
        peek = pd.read_csv(path, low_memory=False, nrows=5)
    except Exception as e:
        return None, f"Dataset load failed: {e}"
    for col in ("file", "time_s"):
        if col not in peek.columns:
            return None, f"CSV must have a '{col}' column."
    try:
        return pd.read_csv(path, low_memory=False), None
    except Exception as e:
        return None, f"Dataset load failed: {e}"


def sensor_name(key) -> str:
    return _SENSOR_NAMES.get(key, str(key))


def time_rate(time):
    """The rate of a run of time values, or None if there are too few."""
    values = np.asarray(time, dtype=float)[:_RATE_ROWS]
    return sample_rate(values) if len(values) >= 3 else None


def rates_by_file(df) -> dict:
    """{file: rate} from each recording's own time step."""
    if "file" not in df.columns or "time_s" not in df.columns:
        return {}
    rates = {}
    for file_id, time in df.groupby("file", sort=False)["time_s"]:
        rate = time_rate(time)
        if rate:
            rates[file_id] = rate
    return rates


def sensors_in(df) -> set:
    """The sensor keys a dataset's rows came from."""
    if SENSOR_COL not in df.columns:
        return {LEGACY_SENSOR}
    values = df[SENSOR_COL].fillna("").astype(str).str.strip().unique()
    return {v or LEGACY_SENSOR for v in values}


def _rates_text(rates) -> str:
    return ", ".join(f"{r:g} Hz" for r in sorted(rates))


def dataset_problem(df):
    """Why this dataset can't go to one model, or None."""
    sensors = sensors_in(df)
    if len(sensors) > 1:
        return ("This dataset mixes sensors ("
                + ", ".join(sorted(sensor_name(s) for s in sensors))
                + "). A model takes one sensor - use one at a time.")
    rates = set(rates_by_file(df).values())
    if len(rates) > 1:
        return (f"This dataset mixes frequencies ({_rates_text(rates)}). "
                "A model takes one frequency - use one at a time.")
    return None


def identity(df) -> dict:
    """{"sensor_config": key, "sampling_rate_hz": rate} for a dataset of one
    sensor at one rate, as a model records them. Rate None if unreadable."""
    rates = set(rates_by_file(df).values())
    return {SENSOR_COL: sorted(sensors_in(df))[0],
            RATE_FIELD: next(iter(rates)) if len(rates) == 1 else None}


def model_identity(metrics) -> tuple:
    """(sensor key, rate) a model was trained on, from its metrics."""
    metrics = metrics or {}
    return (metrics.get(SENSOR_COL) or LEGACY_SENSOR,
            metrics.get(RATE_FIELD) or LEGACY_RATE)


def describe(sensor, rate) -> str:
    return f"{sensor_name(sensor)} at {rate:g} Hz" if rate else sensor_name(sensor)


def model_problem(metrics, data_identity):
    """Why this model can't be used on a dataset (its `identity`), or None."""
    sensor, rate = model_identity(metrics)
    data_sensor, data_rate = data_identity[SENSOR_COL], data_identity[RATE_FIELD]
    if data_sensor == sensor and (data_rate is None or data_rate == rate):
        return None
    return (f"This model was trained on {describe(sensor, rate)}; this dataset "
            f"is {describe(data_sensor, data_rate)}. Use a model trained on "
            f"{describe(data_sensor, data_rate)}.")
