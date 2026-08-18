import struct
import os
import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
from pathlib import Path
from datetime import datetime

# Enable NumPy multi-threading
os.environ["OMP_NUM_THREADS"] = str(os.cpu_count())
os.environ["OPENBLAS_NUM_THREADS"] = str(os.cpu_count())
os.environ["MKL_NUM_THREADS"] = str(os.cpu_count())

def read_imp_raw(filename):
    """Optimized version of read_imp_raw with performance improvements"""
    filename = Path(filename)
    packetSize = 29
    FS = 2000
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
    ts = TimeRaw / FS
    
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

def read_hig_raw(filename):
    filename = Path(filename)
    packetSize = 11
    FS = 2000
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
    ts = TimeRaw / FS
    ax = np.round(DataRaw[:, 0] * gain_hig, HIG_PREC)
    ay = np.round(DataRaw[:, 1] * gain_hig, HIG_PREC)
    az = np.round(DataRaw[:, 2] * gain_hig, HIG_PREC)
    aMag = np.round(np.sqrt(ax ** 2 + ay ** 2 + az ** 2), HIG_PREC)
    
    column_names_raw = [
        'time_s', 'higacc_x_g', 'higacc_y_g', 'higacc_z_g', 'higacc_mag_g'
    ]
    
    dataExportCSV = np.column_stack((ts, ax, ay, az, aMag))
    
    return pd.DataFrame(dataExportCSV, columns=column_names_raw)

def process_imp_hig_direct(imp_filename, hig_filename, output_dir):
    imp_data = read_imp_raw(imp_filename)
    hig_data = read_hig_raw(hig_filename)
    
    base_filename = Path(imp_filename).stem
    
    file_info = parse_filename_info(base_filename)
    
    # Create a uniform 2000Hz time series
    start_time = imp_data["time_s"].min()
    end_time = imp_data["time_s"].max()
    time_step = 1.0 / 2000  # 0.0005 seconds
    times = np.arange(start_time, end_time + time_step, time_step)
    
    # Create combined dataset with the high-resolution time series
    combined_data = pd.DataFrame({"time_s": times})
    
    # Add HIG data - vectorized mapping
    for col in hig_data.columns:
        if col != "time_s":
            combined_data[col] = 0.0
    
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
    
    imp_cols = [col for col in imp_data.columns if col != "time_s"]

    for col in imp_cols:
        interp_func = interp1d(
            imp_data["time_s"],
            imp_data[col],
            kind='linear',
            bounds_error=False,
            fill_value="extrapolate"
        )
        combined_data[col] = interp_func(combined_data["time_s"])
    
    # Apply post-processing (pressure conversion, etc.)
    combined_data, summary_info = post_process_combined(combined_data)
    
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
    """Add or replace sensor in the persistent index file."""
    index_file = Path(output_dir) / "index" / "global_sensor_index.csv"
    index_config_file = Path("config") / "index_config.txt"
    
    # Load sensor config
    with open(index_config_file, 'r') as f:
        config_lines = [line.strip() for line in f if line.strip()]
    
    # Build new row data
    new_row_data = {}
    for line in config_lines:
        if '=' in line:
            col_name, default_value = [x.strip() for x in line.split('=', 1)]
            new_row_data[col_name] = default_value
        else:
            col_name = line.strip()
            key_mapping = {
                'duration.mm.ss.': 'duration[mm:ss]',
                'pres_min.kPa.': 'pres_min[kPa]',
                'pres_min.time.': 'pres_min[time]',
                'HIG_max.g.': 'HIG_max[g]',
                'HIG_max.time.': 'HIG_max[time]'
            }
            key = key_mapping.get(col_name, col_name)
            value = sensor_info.get(key, '')
            new_row_data[col_name] = str(value) if value is not None else ''
    
    # Handle the index file
    if index_file.exists():
        existing_df = pd.read_csv(index_file)
        sensor_file = sensor_info.get('file', '')
        if sensor_file and sensor_file in existing_df['file'].values:
            existing_df = existing_df[existing_df['file'] != sensor_file]
        new_row = pd.DataFrame([new_row_data])
        updated_df = pd.concat([existing_df, new_row], ignore_index=True)
        updated_df.to_csv(index_file, index=False)
    else:
        new_df = pd.DataFrame([new_row_data])
        new_df.to_csv(index_file, index=False)

def parse_filename_info(filename):
    """Extract sensor name, date, and time from the filename."""
    if isinstance(filename, Path):
        filename = filename.stem
    elif '.' in filename:
        filename = Path(filename).stem
    
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

def post_process_combined(data):
    """Apply post-processing to the combined dataset."""
    # Calculate acceleration magnitude for IMP data
    data["inacc_mag_ms"] = np.sqrt(
        data["inacc_x_ms"]**2 + 
        data["inacc_y_ms"]**2 + 
        data["inacc_z_ms"]**2
    ) - 9.81
    
    # Calculate rotational magnitude
    data["rot_mag_degs"] = np.sqrt(
        data["rot_x_degs"]**2 + 
        data["rot_y_degs"]**2 + 
        data["rot_z_degs"]**2
    )
    
    # Calculate duration
    num_seconds = len(data) / 2000
    minutes, seconds = divmod(num_seconds, 60)
    duration = f"{int(minutes):02}:{int(seconds):02}"
    
    # Find max acceleration time
    acc_max_index = data["higacc_mag_g"].idxmax()
    acc_max_time = data["time_s"][acc_max_index]
    max_acc_g_force = data["higacc_mag_g"].iloc[acc_max_index]
    
    warnings = []
    
    # Find pressure nadir around acceleration maxima
    if "pressure_kpa" not in data.columns or data["pressure_kpa"].isna().all():
        data["pressure_kpa"] = 0.0
        warnings.append("PRES: No pressure data available")
        pres_min_value = 0.0
        pres_min_time = acc_max_time
    else:
        window_start = max(0, acc_max_index - 3000)
        window_end = min(len(data) - 1, acc_max_index + 3000)
        pressure_window = data["pressure_kpa"].iloc[window_start:window_end]
        pres_min_local_index = pressure_window.idxmin()
        pres_min_time = data["time_s"][pres_min_local_index]
        pres_min_value = data["pressure_kpa"].iloc[pres_min_local_index]
        
        if pressure_window.nunique() <= 1:
            warnings.append("PRES: Pressure fault identified (unchanging values)")
    
    if data["time_s"].max() >= 5000:
        warnings.append("TIME: Time series incorrect")
    
    if max_acc_g_force >= 400:
        warnings.append("HIG: High impact event >= 400g found")
    
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
    minimal_cols = ["time_s", "pressure_kpa", "higacc_mag_g", "inacc_mag_ms", "rot_mag_degs"]
    minimal_data = data[minimal_cols].copy()
    
    output_path = Path(output_dir) / "csv"
    output_path.mkdir(parents=True, exist_ok=True)
    
    output_file = output_path / f"{filename}_min.csv"
    minimal_data.to_csv(output_file, index=False)
    
    return minimal_data
