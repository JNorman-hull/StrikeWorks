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


#: the two channels every export used before channels became
#: configurable - still the default so an old saved config (no
#: "channels" key) renders exactly as it always did
DEFAULT_CHANNELS = [
    {"column": "pressure_kpa", "label": "Pressure (kPa)", "color": "black"},
    {"column": "higacc_mag_g", "label": "Acceleration magnitude (g)",
     "color": "red"},
]

#: up to this many panels in one graph strip - past this a 150 dpi strip
#: has no room left to be readable
MAX_CHANNELS = 6


class SyncOptions:
    """Every tunable the original script hardcoded as a module constant."""

    def __init__(self, real_fps=1000, data_hz=2000, graph_window_s=0.3,
                zoom=1.0, pressure_row_offset=20, video_nudge_px=0,
                add_labels=True, logo_path=None, logo_opacity=1.0,
                channels=None, layout="row", no_video=False):
        self.real_fps = real_fps
        self.data_hz = data_hz
        self.graph_window_s = graph_window_s
        self.zoom = zoom
        self.pressure_row_offset = pressure_row_offset
        self.video_nudge_px = video_nudge_px
        self.add_labels = add_labels
        self.logo_path = logo_path
        self.logo_opacity = logo_opacity
        # which signal(s) the rolling graph strip plots, one panel each -
        # was hardcoded to pressure + acceleration magnitude; any numeric
        # column in the sensor's processed CSV works now (e.g. the raw
        # higacc_x/y/z axes instead of the combined magnitude)
        self.channels = channels or DEFAULT_CHANNELS
        # "row": panels side by side (the original layout, fits under a
        # video crop). "grid": up to 3 rows of 2 - only really usable
        # with no_video, where the panels get the whole frame to work
        # with instead of a quarter-height strip
        self.layout = layout
        # skip the video crop entirely and let the graph panels fill the
        # whole output frame - a pure sensor-signal animation rather than
        # a video overlay, for when there's no camera footage worth
        # keeping (or none at all)
        self.no_video = no_video


def build_cursor_arrays(nadir_time_s, df, nadir_frame, total_frames, opts,
                        columns=None):
    """{column: per-frame value array}, aligned 1-to-1 with encoded video
    frames - used only for the live cursor annotation value on each
    frame's panel. `columns` defaults to every channel in `opts.channels`.

    A pressure-named column gets the same row-offset correction the
    original script applied for every column (pressure and acceleration
    are logged a few rows apart on the same device) - every other column
    uses the acceleration-aligned time directly.
    """
    columns = columns or [c["column"] for c in opts.channels]
    times = df["time_s"].to_numpy(dtype=float)
    pres_offset_s = opts.pressure_row_offset / opts.data_hz
    f_idx = np.arange(total_frames)
    acc_times = nadir_time_s + (f_idx - nadir_frame) / opts.real_fps
    pres_times = acc_times - pres_offset_s

    def lookup(target_times):
        idx = np.searchsorted(times, target_times)
        idx = np.clip(idx, 0, len(times) - 1)
        valid = np.abs(times[idx] - target_times) < TIME_TOL
        return idx, valid

    out = {}
    for col in columns:
        if col not in df.columns or col in out:
            continue
        target_times = pres_times if "pres" in col.lower() else acc_times
        idx, valid = lookup(target_times)
        vals = df[col].to_numpy(dtype=float)
        out[col] = np.where(valid, vals[idx], 0.0)
    return out


def _grid_shape(n, layout):
    if layout == "grid":
        cols = 2 if n > 1 else 1
        rows = -(-n // cols)   # ceil
        return rows, cols
    return 1, n


def make_graph_strip(df, cursor_values, frame_idx, nadir_time_s,
                     nadir_frame, strip_width, strip_height, opts):
    """Scrolling graph, one panel per `opts.channels` entry (up to
    `MAX_CHANNELS`), arranged per `opts.layout` - the current frame's
    slice of every configured signal, full processed signal as backdrop
    so data is always visible on both sides of the cursor.

    `cursor_values`: {column: array} from `build_cursor_arrays`.
    """
    channels = opts.channels[:MAX_CHANNELS]
    time_axis = df["time_s"].to_numpy(dtype=float)
    current_t = nadir_time_s + (frame_idx - nadir_frame) / opts.real_fps
    window = opts.graph_window_s / max(opts.zoom, 1e-6)
    t_lo, t_hi = current_t - window, current_t + window

    def pad_range(lo, hi, frac=0.08):
        r = (hi - lo) if hi != lo else 1.0
        return lo - frac * r, hi + frac * r

    dpi = 150
    fig_w, fig_h = strip_width / dpi, strip_height / dpi
    rows, cols = _grid_shape(len(channels), opts.layout)
    fig, axes = plt.subplots(rows, cols, figsize=(fig_w, fig_h), dpi=dpi,
                             squeeze=False)
    fig.patch.set_facecolor("white")
    flat_axes = [ax for row in axes for ax in row]

    for ax, ch in zip(flat_axes, channels):
        col = ch["column"]
        if col not in df.columns:
            ax.axis("off")
            continue
        y = df[col].to_numpy(dtype=float)
        color = ch.get("color", "black")
        ax.plot(time_axis, y, color=color, linewidth=0.8)
        ax.set_xlim(t_lo, t_hi)
        ax.set_ylim(*pad_range(np.nanmin(y), np.nanmax(y)))
        ax.axvline(x=current_t, color="#00cc44", linestyle="--", linewidth=1.0)
        ax.set_ylabel(ch.get("label", col), fontsize=8)
        ax.set_xticks([])
        ax.tick_params(axis="y", labelsize=7)
        cur = cursor_values.get(col)
        if cur is not None:
            val = cur[frame_idx]
            ax.text(current_t, val, f" {val:.2f}", va="center", ha="left",
                    fontsize=8, color=color)
    # unused cells in a grid layout that doesn't fill evenly (e.g. 5
    # channels in a 2x3 grid) stay blank rather than showing empty axes
    for ax in flat_axes[len(channels):]:
        ax.axis("off")

    fig.subplots_adjust(left=0.06, right=0.99, top=0.95, bottom=0.08,
                        wspace=0.12, hspace=0.3)

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


def render_preview_frame(video_path, df, nadir_time_s, nadir_frame, fields,
                         opts: SyncOptions, frame_idx):
    """Composite exactly one frame - the same video crop + graph strip +
    overlays `process_video` burns into every frame of the export - without
    rendering the whole clip. Lets Export animations' "Generate preview
    frame" sanity-check the sync frame/graph window/overlay settings
    before committing to a full (slow) render.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise IOError(f"Cannot open: {video_path}")
    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_idx = max(0, min(int(frame_idx), max(total_frames - 1, 0)))
        frame = None
        if not opts.no_video:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                raise IOError(f"Could not read frame {frame_idx} of {video_path}")
    finally:
        cap.release()

    # cursor arrays are cheap (numpy, no per-frame decode) even built out
    # to frame_idx + 1 just to read the last value - no need for a
    # separate single-value code path
    cursor_values = build_cursor_arrays(
        nadir_time_s, df, nadir_frame, frame_idx + 1, opts)

    if opts.no_video:
        # pure sensor-signal animation - no camera footage, so the graph
        # panels get the whole frame instead of a quarter-height strip
        combined = make_graph_strip(
            df, cursor_values, frame_idx, nadir_time_s, nadir_frame,
            frame_width, frame_height, opts)
        video_h = frame_height
    else:
        strip_h = frame_height // 4
        video_h = frame_height - strip_h
        video_crop = frame[opts.video_nudge_px:video_h + opts.video_nudge_px, :]
        graph_strip = make_graph_strip(
            df, cursor_values, frame_idx, nadir_time_s,
            nadir_frame, frame_width, strip_h, opts)
        combined = np.vstack([video_crop, graph_strip])

    logo = load_logo(opts.logo_path, frame_width, frame_height)
    combined = overlay_logo(combined, logo, opts.logo_opacity)
    if opts.add_labels:
        lines, realtime_line = build_text_lines(fields, frame_idx, opts)
        combined = overlay_text(combined, lines, realtime_line, video_h)
    return combined


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

    if opts.no_video:
        strip_h = video_h = frame_height
    else:
        strip_h = frame_height // 4
        video_h = frame_height - strip_h

    cursor_values = build_cursor_arrays(
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

            graph_strip = make_graph_strip(
                df, cursor_values, f, nadir_time_s, nadir_frame,
                frame_width, strip_h, opts)
            if opts.no_video:
                combined = graph_strip
            else:
                video_crop = frame[opts.video_nudge_px:video_h + opts.video_nudge_px, :]
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
