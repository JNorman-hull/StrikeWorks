"""RAPID sensor parser: paired .imp / .hig files merged onto one time base.

Three rates are involved and they are not the same number:

  * the counter clock both files are stamped from (2000 Hz) - the `fs`
    argument of the two readers, which turns the raw counter into seconds;
  * each file's own rate - .imp is 100 Hz, .hig is 2000 Hz but recorded
    only around events, so it is sparse;
  * the output grid the combined CSV is written on (2000 Hz).

Getting from the second to the third is the interpolation this parser has
always done: the 100 Hz .imp channels are interpolated up onto the grid,
and each sparse .hig sample is written to its nearest grid point (gaps stay
at zero rather than having signal invented across them).

All of it arrives as arguments from the sensor configuration, so the same
reader serves any RAPID-family device defined on the Prepare page. The
defaults are the values this file used to hardcode, so calling it without a
config behaves exactly as before - verified byte-for-byte against the
pre-configuration version.
"""
import struct
import os
import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
from pathlib import Path
from datetime import datetime

from . import index_schema

# defaults, used when no SensorConfig is supplied
FS = 2000
IMP_PACKET_SIZE = 29
HIG_PACKET_SIZE = 11
NADIR_SEARCH_SEC = 1.5


# ── nadir detection ─────────────────────────────────────────────────────────
# The passage nadir is the moment every downstream window is cut around, so
# how it is found is a real choice. One method exists - the MVP's - but it
# is dispatched through a registry, so a second (a pressure gradient, a
# model-scored trace) is a function plus an entry here rather than surgery
# on the parser. A method takes the combined frame, the peak-acceleration
# index and the output rate, and returns (index, time, value, warnings).

def nadir_pressure_min_near_peak(data, acc_max_index, fs):
    """Lowest pressure within 1.5 s of the acceleration peak (the MVP's)."""
    warnings = []
    half = int(round(NADIR_SEARCH_SEC * float(fs)))
    window_start = max(0, acc_max_index - half)
    window_end = min(len(data) - 1, acc_max_index + half)
    pressure_window = data["pressure_kpa"].iloc[window_start:window_end]
    idx = pressure_window.idxmin()
    if pressure_window.nunique() <= 1:
        warnings.append("PRES: Pressure fault identified (unchanging values)")
    return idx, data["time_s"][idx], data["pressure_kpa"].iloc[idx], warnings


#: method name -> callable(data, acc_max_index, fs)
NADIR_METHODS = {
    "pressure_min_near_peak": nadir_pressure_min_near_peak,
}

DEFAULT_NADIR_METHOD = "pressure_min_near_peak"


# ── computed channels ───────────────────────────────────────────────────────
# Magnitude of each three-axis sensor. Which ones are written is a sensor
# setting (Prepare > Sensor configuration); the maths lives here.
#   key -> (output column, axis columns, offset subtracted)
MAGNITUDES = {
    "higacc": ("higacc_mag_g",
               ("higacc_x_g", "higacc_y_g", "higacc_z_g"), 0.0),
    "inacc": ("inacc_mag_ms",
              ("inacc_x_ms", "inacc_y_ms", "inacc_z_ms"), 9.81),
    "rot": ("rot_mag_degs",
            ("rot_x_degs", "rot_y_degs", "rot_z_degs"), 0.0),
}


def magnitude(data, key):
    """The magnitude series for one three-axis sensor, or None.

    inacc subtracts g, as the MVP did, so the channel reads as acceleration
    above rest rather than including gravity.
    """
    _name, axes, offset = MAGNITUDES[key]
    if any(a not in data.columns for a in axes):
        return None
    total = sum(data[a] ** 2 for a in axes)
    return np.sqrt(total) - offset

# Enable NumPy multi-threading
os.environ["OMP_NUM_THREADS"] = str(os.cpu_count())
os.environ["OPENBLAS_NUM_THREADS"] = str(os.cpu_count())
os.environ["MKL_NUM_THREADS"] = str(os.cpu_count())

def read_imp_raw(filename, fs=FS, packet_size=IMP_PACKET_SIZE):
    """Read an .imp file (IMU, pressure, temperature, battery) at ~100 Hz.

    `fs` is the counter clock the timestamps are stamped from, not the rate
    the channels arrive at.
    """
    filename = Path(filename)
    packetSize = int(packet_size) or IMP_PACKET_SIZE
    fs = float(fs) or FS
    IMU_PREC = 3
    P_PREC = 1
    T_BAT_PREC = 2
    gain_ac = 0.005 
    gain_gy = 0.1
    gain_mg = 0.1
    gain_pr = 0.1
    gain_t = 0.01
    gain_bt = 0.01
    
    with open(filename, 'rb') as file_ID:
        fstat = os.stat(filename)
        flen = (fstat.st_size // packetSize) - 1

        TimeRaw = []
        TimeSpot = []

        # Read time data first (matching original logic exactly)
        for _ in range(flen):
            time_raw = struct.unpack('>i', file_ID.read(4))[0]
            TimeRaw.append(time_raw)
            TimeSpot.append(file_ID.tell())
            file_ID.seek(25, 1)

        DataRaw = np.zeros((flen, 12), dtype=np.int16)
        DataRawP = np.zeros(flen, dtype=np.uint16)

        # Read data packets (matching original structure)
        for it in range(flen):
            if it == 0:
                file_ID.seek(4, 0)
            else:
                DataRaw[it, 0] = struct.unpack('>h', file_ID.read(2))[0]
                DataRaw[it, 1] = struct.unpack('>h', file_ID.read(2))[0]
                DataRaw[it, 2] = struct.unpack('>h', file_ID.read(2))[0]
                DataRaw[it, 3] = struct.unpack('>h', file_ID.read(2))[0]
                DataRaw[it, 4] = struct.unpack('>h', file_ID.read(2))[0]
                DataRaw[it, 5] = struct.unpack('>h', file_ID.read(2))[0]
                DataRaw[it, 6] = struct.unpack('>h', file_ID.read(2))[0]
                DataRaw[it, 7] = struct.unpack('>h', file_ID.read(2))[0]
                DataRaw[it, 8] = struct.unpack('>h', file_ID.read(2))[0]
                file_ID.seek(2, 1)
                DataRaw[it, 9] = struct.unpack('>h', file_ID.read(2))[0]
                DataRaw[it, 10] = struct.unpack('>h', file_ID.read(2))[0]
                file_ID.seek(5, 1)

        DataRaw[0, :] = DataRaw[1, :]

        # Read pressure data (matching original structure)
        for it in range(flen):
            if it == 0:
                file_ID.seek(TimeSpot[0] + 4 + (2 * 7), 0)
            else:
                DataRawP[it] = struct.unpack('>H', file_ID.read(2))[0]
                file_ID.seek(27, 1)

        DataRawP[0] = DataRawP[1]
    
    # Use numba-accelerated processing on correctly parsed data
    TimeRaw = np.array(TimeRaw, dtype=np.float64)
    ts = TimeRaw / fs
    
    # Apply gains using numba (but keep the original data structure)
    ax = np.round(DataRaw[:, 0] * gain_ac, IMU_PREC)
    ay = np.round(DataRaw[:, 1] * gain_ac, IMU_PREC)
    az = np.round(DataRaw[:, 2] * gain_ac, IMU_PREC)
    gx = np.round(DataRaw[:, 3] * gain_gy, IMU_PREC)
    gy = np.round(DataRaw[:, 4] * gain_gy, IMU_PREC)
    gz = np.round(DataRaw[:, 5] * gain_gy, IMU_PREC)
    mx = np.round(DataRaw[:, 6] * gain_mg, IMU_PREC)
    my = np.round(DataRaw[:, 7] * gain_mg, IMU_PREC)
    mz = np.round(DataRaw[:, 8] * gain_mg, IMU_PREC)
    p = np.round(DataRawP * gain_pr, P_PREC)
    t = np.round(DataRaw[:, 9] * gain_t, T_BAT_PREC)
    b = np.round(DataRaw[:, 10] * gain_bt, T_BAT_PREC)
    
    # Create output dataframe
    column_names_raw = [
        'time_s', 'inacc_x_ms', 'inacc_y_ms', 'inacc_z_ms',
        'rot_x_degs', 'rot_y_degs', 'rot_z_degs', 'mag_x_mt',
        'mag_y_mt', 'mag_z_mt', 'pressure_kpa', 'temp_c', 'battery_v'
    ]
    
    # Convert pressure from mbar to kPa during export
    dataExportCSV = np.column_stack((
        ts, ax, ay, az, gx, gy, gz, mx, my, mz, p / 10.0, t, b
    ))
    return pd.DataFrame(dataExportCSV, columns=column_names_raw)

def read_hig_raw(filename, fs=FS, packet_size=HIG_PACKET_SIZE):
    """Read a .hig file (high-g accelerometer), sampled around events.

    `fs` is the counter clock, as for read_imp_raw.
    """
    filename = Path(filename)
    packetSize = int(packet_size) or HIG_PACKET_SIZE
    fs = float(fs) or FS
    HIG_PREC = 1
    gain_hig = 0.1
    
    with open(filename, 'rb') as file_ID:
        fstat = os.stat(filename)
        flen = fstat.st_size // packetSize

        TimeRaw = []
        DataRaw = np.zeros((flen, 3), dtype=np.int16)
        
        for it in range(flen):
            packet = file_ID.read(packetSize)
            
            time_raw = struct.unpack('>I', packet[:4])[0]
            TimeRaw.append(time_raw)

            DataRaw[it, 0] = struct.unpack('>h', packet[4:6])[0]  # acc X
            DataRaw[it, 1] = struct.unpack('>h', packet[6:8])[0]  # acc Y
            DataRaw[it, 2] = struct.unpack('>h', packet[8:10])[0]  # acc Z
    
    # Use optimized numpy processing 
    TimeRaw = np.array(TimeRaw, dtype=np.float64)
    ts = TimeRaw / fs
    ax = np.round(DataRaw[:, 0] * gain_hig, HIG_PREC)
    ay = np.round(DataRaw[:, 1] * gain_hig, HIG_PREC)
    az = np.round(DataRaw[:, 2] * gain_hig, HIG_PREC)
    aMag = np.round(np.sqrt(ax ** 2 + ay ** 2 + az ** 2), HIG_PREC)
    
    column_names_raw = [
        'time_s', 'higacc_x_g', 'higacc_y_g', 'higacc_z_g', 'higacc_mag_g'
    ]
    
    dataExportCSV = np.column_stack((ts, ax, ay, az, aMag))
    
    return pd.DataFrame(dataExportCSV, columns=column_names_raw)

def process_imp_hig_direct(imp_filename, hig_filename, output_dir, config=None):
    """Parse one .imp/.hig pair and write the combined CSV.

    `config` is the SensorConfig selected on Prepare. Without one the RAPID
    defaults apply, which is what the MVP did.
    """
    if config is not None:
        clock = float(config.timebase_hz) or FS
        out_rate = float(config.output_rate_hz) or clock
        imp_packet = config.packet_size(".imp") or IMP_PACKET_SIZE
        hig_packet = config.packet_size(".hig") or HIG_PACKET_SIZE
        imp_method = config.method(".imp", "linear")
        hig_method = config.method(".hig", "nearest")
    else:
        clock = out_rate = FS
        imp_packet, hig_packet = IMP_PACKET_SIZE, HIG_PACKET_SIZE
        imp_method, hig_method = "linear", "nearest"

    # `clock` is the counter tick rate both files are stamped from, NOT the
    # rate their channels arrive at: .imp is 100 Hz and .hig is 2000 Hz but
    # event-triggered. Each file's own timestamps carry that.
    imp_data = read_imp_raw(imp_filename, fs=clock, packet_size=imp_packet)
    hig_data = read_hig_raw(hig_filename, fs=clock, packet_size=hig_packet)
    
    base_filename = Path(imp_filename).stem
    
    file_info = parse_filename_info(base_filename, config=config)
    
    # Uniform output grid. Every channel is brought onto this, whatever
    # rate it arrived at.
    start_time = imp_data["time_s"].min()
    end_time = imp_data["time_s"].max()
    time_step = 1.0 / out_rate
    times = np.arange(start_time, end_time + time_step, time_step)
    
    # Create combined dataset with the high-resolution time series
    combined_data = pd.DataFrame({"time_s": times})
    
    # HIG onto the grid. Its samples are sparse (recorded around events),
    # so by default each one is written to its nearest grid point and the
    # rest stay zero - interpolating across the gaps would invent signal.
    for col in hig_data.columns:
        if col != "time_s":
            combined_data[col] = 0.0

    if hig_method == "nearest":
        # vectorized approach
        hig_indices = np.searchsorted(combined_data["time_s"], hig_data["time_s"], side='left')
        hig_indices = np.clip(hig_indices, 0, len(combined_data) - 1)

        # Vectorized nearest neighbor selection
        valid_left = hig_indices > 0
        left_indices = np.maximum(hig_indices - 1, 0)

        left_diffs = np.where(valid_left,
                             np.abs(combined_data["time_s"].iloc[left_indices].values - hig_data["time_s"].values),
                             np.inf)
        right_diffs = np.abs(combined_data["time_s"].iloc[hig_indices].values - hig_data["time_s"].values)

        use_left = left_diffs < right_diffs
        final_indices = np.where(use_left, left_indices, hig_indices)

        for col in hig_data.columns:
            if col != "time_s":
                combined_data.loc[final_indices, col] = hig_data[col].values
    else:
        # a configuration that asks for interpolation instead gets it
        for col in hig_data.columns:
            if col == "time_s":
                continue
            f = interp1d(hig_data["time_s"], hig_data[col],
                         kind=hig_method, bounds_error=False,
                         fill_value="extrapolate")
            combined_data[col] = f(combined_data["time_s"])

    imp_cols = [col for col in imp_data.columns if col != "time_s"]

    for col in imp_cols:
        interp_func = interp1d(
            imp_data["time_s"],
            imp_data[col],
            kind=imp_method,
            bounds_error=False,
            fill_value="extrapolate"
        )
        combined_data[col] = interp_func(combined_data["time_s"])
    
    # Apply post-processing (pressure conversion, etc.)
    combined_data, summary_info = post_process_combined(
        combined_data, fs=out_rate,
        magnitudes=(config.magnitudes if config is not None else None),
        nadir_method=(config.nadir_method if config is not None else None))
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Create CSV subdirectory
    csv_dir = output_path / "csv"
    csv_dir.mkdir(parents=True, exist_ok=True)
    
    # Save the combined data to CSV directory
    output_file = csv_dir / f"{base_filename}.csv"
    combined_data.to_csv(output_file, index=False)
    
    all_info = {**file_info, **summary_info, 'file': base_filename}
    append_to_sensor_index(all_info, output_dir)

    # Create and save minimal CSV
    minimal_data = create_minimal_csv(combined_data, base_filename, output_path)
    
    return combined_data, {**file_info, **summary_info}

def append_to_sensor_index(sensor_info, output_dir):
    """Add or replace this sensor's row in the library's index.

    The column list is the app's (``index_schema``), not the library's - a
    library needs no config/index_config.txt to be processed, and nothing
    here depends on the working directory.
    """
    index_file = Path(output_dir) / "index" / "global_sensor_index.csv"
    index_file.parent.mkdir(parents=True, exist_ok=True)

    new_row_data = index_schema.row_for(sensor_info)

    if index_file.exists():
        existing_df = pd.read_csv(index_file)
        sensor_file = sensor_info.get('file', '')
        if sensor_file and sensor_file in existing_df['file'].values:
            existing_df = existing_df[existing_df['file'] != sensor_file]
        # a column the index has never carried (an older library, or one
        # written before the schema gained a column) is added, not dropped
        for col in index_schema.columns():
            if col not in existing_df.columns:
                existing_df[col] = index_schema.defaults().get(col, "")
        new_row = pd.DataFrame([new_row_data])
        updated_df = pd.concat([existing_df, new_row], ignore_index=True)
        updated_df.to_csv(index_file, index=False)
    else:
        new_df = pd.DataFrame([new_row_data], columns=index_schema.columns())
        new_df.to_csv(index_file, index=False)

def parse_filename_info(filename, config=None):
    """Extract sensor name, date, and time from the filename.

    A configuration's filename pattern wins when it matches; the original
    split-on-dash rule is the fallback, so names the pattern does not cover
    still yield a sensor and a deployment time.
    """
    if isinstance(filename, Path):
        filename = filename.stem
    elif '.' in filename:
        filename = Path(filename).stem

    if config is not None:
        try:
            sensor, date_deploy, time_deploy = config.parse_stem(filename)
            if date_deploy and time_deploy:
                return {
                    'sensor': sensor,
                    'date_deploy': date_deploy,
                    'time_deploy': time_deploy
                }
        except Exception:
            pass

    if '-' in filename:
        sensor, date_time = filename.split('-')
    else:
        sensor = filename[:3]
        date_time = filename[3:]
    
    date_str = date_time[:4]
    time_str = date_time[4:]
    
    date_deploy = datetime.strptime(date_str, "%m%d").strftime("%d/%m")
    time_deploy = f"{time_str[:2]}:{time_str[2:4]}:{time_str[4:]}"
    
    return {
        'sensor': sensor,
        'date_deploy': date_deploy,
        'time_deploy': time_deploy
    }

def post_process_combined(data, fs=FS, magnitudes=None, nadir_method=None):
    """Apply post-processing to the combined dataset.

    `fs` is the rate of the combined series, used for the duration and by
    the nadir method. `magnitudes` selects which three-axis magnitudes are
    written (all of them by default); `nadir_method` names an entry in
    NADIR_METHODS.
    """
    wanted = set(MAGNITUDES) if magnitudes is None else set(magnitudes)

    for key in MAGNITUDES:
        name = MAGNITUDES[key][0]
        if key not in wanted:
            if name in data.columns and key != "higacc":
                del data[name]
            continue
        # A reader may already have produced the magnitude - read_hig_raw
        # does, rounded to the device's precision. Recomputing it from the
        # merged columns would silently change those values, so a magnitude
        # is only calculated where one is missing.
        if name not in data.columns:
            series = magnitude(data, key)
            if series is not None:
                data[name] = series

    # Peak acceleration anchors the nadir search, so higacc magnitude is
    # computed for that even when it is not wanted as an output column -
    # and dropped again below, once the summary has been taken.
    peak_name = MAGNITUDES["higacc"][0]
    keep_peak = "higacc" in wanted
    if peak_name not in data.columns:
        series = magnitude(data, "higacc")
        if series is not None:
            data[peak_name] = series

    # Calculate duration
    num_seconds = len(data) / float(fs)
    minutes, seconds = divmod(num_seconds, 60)
    duration = f"{int(minutes):02}:{int(seconds):02}"
    
    # Find max acceleration time
    acc_max_index = data[peak_name].idxmax()
    acc_max_time = data["time_s"][acc_max_index]
    max_acc_g_force = data[peak_name].iloc[acc_max_index]
    
    warnings = []
    
    # Find the nadir with whichever method the configuration names
    if "pressure_kpa" not in data.columns or data["pressure_kpa"].isna().all():
        data["pressure_kpa"] = 0.0
        warnings.append("PRES: No pressure data available")
        pres_min_value = 0.0
        pres_min_time = acc_max_time
    else:
        find = NADIR_METHODS.get(nadir_method or DEFAULT_NADIR_METHOD,
                                 nadir_pressure_min_near_peak)
        _idx, pres_min_time, pres_min_value, found = find(
            data, acc_max_index, fs)
        warnings.extend(found)
    
    if data["time_s"].max() >= 5000:
        warnings.append("TIME: Time series incorrect")
    
    if max_acc_g_force >= 400:
        warnings.append("HIG: High impact event >= 400g found")
    
    if not keep_peak and peak_name in data.columns:
        del data[peak_name]

    warning_message = "; ".join(warnings) if warnings else "No warnings"
    
    bad_sens = "Y" if ("TIME:" in warning_message or "PRES:" in warning_message) else "N"
    
    summary_info = {
        "duration[mm:ss]": duration,
        "pres_min[kPa]": pres_min_value,
        "pres_min[time]": pres_min_time,
        "HIG_max[g]": max_acc_g_force,
        "HIG_max[time]": acc_max_time,
        "messages": warning_message,
        "bad_sens": bad_sens
    }
    
    return data, summary_info

def create_minimal_csv(data, filename, output_dir):
    """Create a minimal CSV with only selected columns."""
    minimal_cols = [c for c in ["time_s", "pressure_kpa",
                                "higacc_mag_g", "inacc_mag_ms",
                                "rot_mag_degs"] if c in data.columns]
    minimal_data = data[minimal_cols].copy()
    
    output_path = Path(output_dir) / "csv"
    output_path.mkdir(parents=True, exist_ok=True)
    
    output_file = output_path / f"{filename}_min.csv"
    minimal_data.to_csv(output_file, index=False)
    
    return minimal_data
