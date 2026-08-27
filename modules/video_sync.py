# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Pure video/sensor sync logic - port of `video_sync.py` (Scripts/Time
series video sync), adapted for Export animations (ROADMAP.md Chunk 5
task 4).

Sync logic (unchanged from the original script)
-------------------------------------------------
  nadir_frame : encoded video frame number of the sync point (typed in by
                the user - StrikeWorks has no automatic video/sensor
                alignment, the same as the original script's `frames.txt`).
  nadir_time_s: the sensor time (seconds) the sync point corresponds to -
                read straight from the processed sensor CSV's pressure
                minimum, rather than an external `labeled_data_with_types`
                row index the way the original script needed.

  For any encoded frame N: current_t = nadir_time_s + (N - nadir_frame) / real_fps

Differences from the original script
-------------------------------------
- No `frames.txt`/external combined dataset: the nadir time comes directly
  from the sensor's own processed CSV, matching how Annotate and Validate
  already find a nadir.
- Every constant the script hardcoded (real_fps, data_hz, graph window,
  zoom, pressure row offset, whether to draw the text overlay, an optional
  logo) is a parameter here, driven by Export animations' Code options box
  instead of editing the script.
- GUI-free: `process_video()` takes an optional `progress_cb(frame, total)`
  so a QThread worker (`page_export_animations.py`'s `_VideoSyncWorker`)
  can report progress without this module depending on Qt at all.
"""
import os
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg
from PIL import Image, ImageDraw, ImageFont

TEXT_FONT = "C:/Windows/Fonts/arial.ttf"
TEXT_SIZE = 28
TEXT_COLOUR = (255, 255, 255)
TEXT_PADDING = 20

# tolerance for a time_s nearest-neighbour match; ~1 sample at 2000 Hz
TIME_TOL = 0.001


class SyncOptions:
    """Every tunable the original script hardcoded as a module constant."""

    def __init__(self, real_fps=1000, data_hz=2000, graph_window_s=0.3,
                zoom=1.0, pressure_row_offset=20, video_nudge_px=0,
                add_labels=True, logo_path=None, logo_opacity=1.0):
        self.real_fps = real_fps
        self.data_hz = data_hz
        self.graph_window_s = graph_window_s
        self.zoom = zoom
        self.pressure_row_offset = pressure_row_offset
        self.video_nudge_px = video_nudge_px
        self.add_labels = add_labels
        self.logo_path = logo_path
        self.logo_opacity = logo_opacity


def build_cursor_arrays(nadir_time_s, df, nadir_frame, total_frames, opts):
    """Pressure/accmag arrays aligned 1-to-1 with encoded video frames -
    used only for the live cursor annotation value on each frame."""
    times = df["time_s"].to_numpy(dtype=float)
    pres_vals = df["pressure_kpa"].to_numpy(dtype=float)
    acc_vals = df["higacc_mag_g"].to_numpy(dtype=float)

    pres_offset_s = opts.pressure_row_offset / opts.data_hz
    f_idx = np.arange(total_frames)
    acc_times = nadir_time_s + (f_idx - nadir_frame) / opts.real_fps
    pres_times = acc_times - pres_offset_s

    def lookup(target_times):
        idx = np.searchsorted(times, target_times)
        idx = np.clip(idx, 0, len(times) - 1)
        valid = np.abs(times[idx] - target_times) < TIME_TOL
        return idx, valid

    acc_idx, acc_valid = lookup(acc_times)
    pres_idx, pres_valid = lookup(pres_times)
    accmag = np.where(acc_valid, acc_vals[acc_idx], 0.0)
    pres = np.where(pres_valid, pres_vals[pres_idx], 0.0)
    return pres, accmag


def make_graph_strip(df, pres_cursor, accmag_cursor, frame_idx, nadir_time_s,
                     nadir_frame, strip_width, strip_height, opts):
    """Two-panel scrolling graph (pressure black, accel magnitude red) for
    the current frame - full processed signal as backdrop so data is
    always visible on both sides of the cursor."""
    time_axis = df["time_s"].to_numpy(dtype=float)
    pres_plot = df["pressure_kpa"].to_numpy(dtype=float)
    acc_plot = df["higacc_mag_g"].to_numpy(dtype=float)

    current_t = nadir_time_s + (frame_idx - nadir_frame) / opts.real_fps
    window = opts.graph_window_s / max(opts.zoom, 1e-6)
    t_lo, t_hi = current_t - window, current_t + window

    p_min, p_max = np.nanmin(pres_plot), np.nanmax(pres_plot)
    a_min, a_max = np.nanmin(acc_plot), np.nanmax(acc_plot)

    def pad_range(lo, hi, frac=0.08):
        r = (hi - lo) if hi != lo else 1.0
        return lo - frac * r, hi + frac * r

    dpi = 150
    fig_w, fig_h = strip_width / dpi, strip_height / dpi
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(fig_w, fig_h), dpi=dpi)
    fig.patch.set_facecolor("white")

    ax1.plot(time_axis, pres_plot, color="black", linewidth=0.8)
    ax1.set_xlim(t_lo, t_hi)
    ax1.set_ylim(*pad_range(p_min, p_max))
    ax1.axvline(x=current_t, color="#00cc44", linestyle="--", linewidth=1.0)
    ax1.set_ylabel("Pressure (kPa)", fontsize=8)
    ax1.set_xticks([])
    ax1.tick_params(axis="y", labelsize=7)
    ax1.text(current_t, pres_cursor[frame_idx], f" {pres_cursor[frame_idx]:.2f}",
             va="center", ha="left", fontsize=8, color="black")

    ax2.plot(time_axis, acc_plot, color="red", linewidth=0.8)
    ax2.set_xlim(t_lo, t_hi)
    ax2.set_ylim(*pad_range(a_min, a_max))
    ax2.axvline(x=current_t, color="#00cc44", linestyle="--", linewidth=1.0)
    ax2.set_ylabel("Acceleration magnitude (g)", fontsize=8)
    ax2.set_xticks([])
    ax2.tick_params(axis="y", labelsize=7)
    ax2.text(current_t, accmag_cursor[frame_idx],
             f" {accmag_cursor[frame_idx]:.2f}",
             va="center", ha="left", fontsize=8, color="red")

    fig.subplots_adjust(left=0.06, right=0.99, top=0.95, bottom=0.08,
                        wspace=0.12)

    canvas = FigureCanvasAgg(fig)
    canvas.draw()
    buf = np.frombuffer(canvas.buffer_rgba(), dtype=np.uint8)
    buf = buf.reshape(canvas.get_width_height()[::-1] + (4,))[:, :, :3]
    plt.close(fig)

    strip_bgr = cv2.cvtColor(buf, cv2.COLOR_RGB2BGR)
    return cv2.resize(strip_bgr, (strip_width, strip_height))


def build_text_lines(fields, frame_idx, opts):
    """`fields`: {pump, shaft_speed, camera, sensor} - Export animations'
    Text inputs box, in place of the original script's hardcoded lines."""
    elapsed_ms = frame_idx / opts.real_fps * 1000
    info_lines = [l for l in [
        f"Pump: {fields.get('pump', '')}".strip(),
        f"Shaft speed: {fields.get('shaft_speed', '')}".strip(),
        f"Video camera: {fields.get('camera', '')}".strip(),
        f"Passive sensor: {fields.get('sensor', '')}".strip(),
    ] if l and not l.endswith(":")]
    realtime_line = f"Real-time: {elapsed_ms:.1f} ms"
    return info_lines, realtime_line


def overlay_text(frame_bgr, lines, realtime_line, video_h):
    img = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(TEXT_FONT, TEXT_SIZE)
        font_rt = ImageFont.truetype(TEXT_FONT, TEXT_SIZE + 4)
    except (IOError, OSError):
        font = ImageFont.load_default()
        font_rt = font

    if lines:
        max_w = max(draw.textlength(l, font=font) for l in lines)
        x = img.width - max_w - TEXT_PADDING
        y = TEXT_PADDING
        for line in lines:
            draw.text((x, y), line, font=font, fill=TEXT_COLOUR)
            y += TEXT_SIZE + 4

    rt_w = draw.textlength(realtime_line, font=font_rt)
    x_rt = img.width - rt_w - TEXT_PADDING
    y_rt = video_h - (TEXT_SIZE + 4) - TEXT_PADDING
    draw.text((x_rt, y_rt), realtime_line, font=font_rt, fill=TEXT_COLOUR)
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def load_logo(path, width, height):
    if not path or not os.path.exists(path):
        return None
    logo = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if logo is None:
        return None
    return cv2.resize(logo, (width, height))


def overlay_logo(frame, logo, opacity):
    if logo is None:
        return frame
    if logo.shape[2] == 4:
        alpha = (logo[:, :, 3] / 255.0) * opacity
        for c in range(3):
            frame[:, :, c] = (
                frame[:, :, c] * (1 - alpha) + logo[:, :, c] * alpha
            ).astype(np.uint8)
    return frame


def process_video(video_path, df, nadir_time_s, nadir_frame, fields,
                  output_path, opts: SyncOptions, progress_cb=None):
    """Renders the synced+overlaid video to `output_path`. `df` is the
    sensor's full processed CSV (time_s, pressure_kpa, higacc_mag_g).
    `progress_cb(frame_index, total_frames)`, called every frame, may
    raise `InterruptedError` to cancel."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise IOError(f"Cannot open: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    enc_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    strip_h = frame_height // 4
    video_h = frame_height - strip_h

    pres_cursor, accmag_cursor = build_cursor_arrays(
        nadir_time_s, df, nadir_frame, total_frames, opts)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(output_path), fourcc, enc_fps,
                          (frame_width, frame_height))
    logo = load_logo(opts.logo_path, frame_width, frame_height)

    try:
        for f in range(total_frames):
            ret, frame = cap.read()
            if not ret:
                break

            video_crop = frame[opts.video_nudge_px:video_h + opts.video_nudge_px, :]
            graph_strip = make_graph_strip(
                df, pres_cursor, accmag_cursor, f, nadir_time_s, nadir_frame,
                frame_width, strip_h, opts)
            combined = np.vstack([video_crop, graph_strip])
            combined = overlay_logo(combined, logo, opts.logo_opacity)
            if opts.add_labels:
                lines, realtime_line = build_text_lines(fields, f, opts)
                combined = overlay_text(combined, lines, realtime_line, video_h)
            out.write(combined)

            if progress_cb is not None:
                progress_cb(f, total_frames)
    finally:
        cap.release()
        out.release()

    return output_path
