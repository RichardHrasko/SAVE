import numpy as np
from matplotlib.colors import Normalize


SCALAR_CMAP = "turbo"
GPS_ACCURACY_CMAP = "RdYlGn_r"
ACC_SMOOTHING_S = 0.30
GYRO_SMOOTHING_S = 0.18
SPEED_COLOR_VMIN_KMH = 0.0
SPEED_COLOR_VMAX_KMH = 100.0


def smooth_time_series(time_values: np.ndarray, values: np.ndarray, smoothing_seconds: float):
    if len(values) < 3 or smoothing_seconds <= 0.0:
        return values

    time_values = np.asarray(time_values, dtype=float).reshape(-1)
    values = np.asarray(values, dtype=float).reshape(-1)
    if len(time_values) != len(values):
        return values

    dt = np.diff(time_values)
    dt = dt[np.isfinite(dt) & (dt > 0.0)]
    if dt.size == 0:
        return values

    median_dt = float(np.median(dt))
    if median_dt <= 0.0:
        return values

    window = max(3, int(round(smoothing_seconds / median_dt)))
    if window % 2 == 0:
        window += 1
    if window >= len(values):
        window = len(values) if len(values) % 2 == 1 else len(values) - 1
    if window < 3:
        return values

    pad = window // 2
    padded = np.pad(values, (pad, pad), mode="edge")
    kernel = np.ones(window, dtype=float) / float(window)
    return np.convolve(padded, kernel, mode="valid")


def get_scalar_data(ski, mode: str):
    if ski is None:
        return None

    if mode == "speed":
        if hasattr(ski, "speed") and ski.speed is not None:
            values = np.asarray(ski.speed, dtype=float).reshape(-1)
            if len(values) == len(ski.time):
                return values
        return None

    if mode == "acc":
        if hasattr(ski, "acc") and ski.acc is not None:
            acc = np.asarray(ski.acc, dtype=float)
            if acc.ndim == 2 and acc.shape[1] >= 3:
                values = np.linalg.norm(acc[:, :3], axis=1) / 9.80665
            else:
                values = np.abs(acc).reshape(-1) / 9.80665
            if len(values) == len(ski.time):
                return smooth_time_series(np.asarray(ski.time, dtype=float), values, ACC_SMOOTHING_S)
        return None

    if mode == "gyro":
        if hasattr(ski, "gyro_mag") and ski.gyro_mag is not None:
            values = np.asarray(ski.gyro_mag, dtype=float).reshape(-1)
            if len(values) == len(ski.time):
                return smooth_time_series(
                    np.asarray(ski.time, dtype=float),
                    values,
                    GYRO_SMOOTHING_S,
                )
        if hasattr(ski, "gyro") and ski.gyro is not None:
            gyro = np.asarray(ski.gyro, dtype=float)
            if gyro.ndim == 2 and gyro.shape[1] >= 3:
                values = np.degrees(np.linalg.norm(gyro[:, :3], axis=1))
            else:
                values = np.degrees(np.abs(gyro).reshape(-1))
            if len(values) == len(ski.time):
                return smooth_time_series(
                    np.asarray(ski.time, dtype=float),
                    values,
                    GYRO_SMOOTHING_S,
                )
        return None

    return None


def get_gps_accuracy_data(gps_path):
    if gps_path is None or getattr(gps_path, "accuracy_m", None) is None:
        return None

    values = np.asarray(gps_path.accuracy_m, dtype=float).reshape(-1)
    time_values = np.asarray(getattr(gps_path, "time", []), dtype=float).reshape(-1)
    if len(values) != len(time_values) or len(values) == 0:
        return None
    return values


def build_gps_accuracy_norm(gps_path):
    values = get_gps_accuracy_data(gps_path)
    if values is None:
        return None

    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return None

    vmax = max(float(np.percentile(finite, 95)), 8.0)
    if vmax <= 0.0:
        vmax = 1.0
    return Normalize(vmin=0.0, vmax=vmax)


def lookup_turn_radius_at_time(turn_radius_segments, time_value: float):
    if not turn_radius_segments or time_value is None:
        return None

    time_value = float(time_value)
    if not np.isfinite(time_value):
        return None

    for segment in turn_radius_segments:
        radius_m = float(getattr(segment, "radius_m", np.nan))
        if not getattr(segment, "valid", True) or not np.isfinite(radius_m):
            continue
        start_t = float(getattr(segment, "time_start", np.nan))
        stop_t = float(getattr(segment, "time_stop", np.nan))
        if not np.isfinite(start_t) or not np.isfinite(stop_t) or stop_t < start_t:
            continue
        if start_t <= time_value <= stop_t:
            return radius_m

    return None


def sample_turn_radius_segments(turn_radius_segments, target_time: np.ndarray):
    if not turn_radius_segments:
        return None

    target_time = np.asarray(target_time, dtype=float).reshape(-1)
    if target_time.size == 0:
        return None

    radius_series = np.full(target_time.shape, np.nan, dtype=float)
    for segment in turn_radius_segments:
        radius_m = float(getattr(segment, "radius_m", np.nan))
        if not getattr(segment, "valid", True) or not np.isfinite(radius_m):
            continue
        start_t = float(getattr(segment, "time_start", np.nan))
        stop_t = float(getattr(segment, "time_stop", np.nan))
        if not np.isfinite(start_t) or not np.isfinite(stop_t) or stop_t < start_t:
            continue
        mask = (target_time >= start_t) & (target_time <= stop_t)
        radius_series[mask] = radius_m

    if not np.isfinite(radius_series).any():
        return None

    return radius_series


def build_turn_radius_norm(turn_radius_segments):
    if not turn_radius_segments:
        return None

    values = [
        float(getattr(segment, "radius_m", np.nan))
        for segment in turn_radius_segments
        if getattr(segment, "valid", True) and np.isfinite(getattr(segment, "radius_m", np.nan))
    ]
    if not values:
        return None

    merged = np.asarray(values, dtype=float)
    vmin = float(np.percentile(merged, 5))
    vmax = float(np.percentile(merged, 95))

    if np.isclose(vmin, vmax):
        vmin = float(np.min(merged))
        vmax = float(np.max(merged))
    if np.isclose(vmin, vmax):
        vmax = vmin + 1e-9

    return Normalize(vmin=vmin, vmax=vmax)


def lookup_turn_radius_series_at_time(turn_radius_series, time_value: float):
    if turn_radius_series is None or time_value is None:
        return None

    src_time = np.asarray(getattr(turn_radius_series, "time", []), dtype=float).reshape(-1)
    values = np.asarray(getattr(turn_radius_series, "radius_m", []), dtype=float).reshape(-1)
    if len(src_time) == 0 or len(src_time) != len(values):
        return None

    idx = int(np.searchsorted(src_time, float(time_value), side="left"))
    if idx <= 0:
        nearest = 0
    elif idx >= len(src_time):
        nearest = len(src_time) - 1
    else:
        prev_idx = idx - 1
        nearest = idx if abs(src_time[idx] - time_value) < abs(time_value - src_time[prev_idx]) else prev_idx

    value = float(values[nearest])
    return value if np.isfinite(value) else None


def sample_turn_radius_series(turn_radius_series, target_time: np.ndarray):
    if turn_radius_series is None:
        return None

    target_time = np.asarray(target_time, dtype=float).reshape(-1)
    src_time = np.asarray(getattr(turn_radius_series, "time", []), dtype=float).reshape(-1)
    values = np.asarray(getattr(turn_radius_series, "radius_m", []), dtype=float).reshape(-1)
    if target_time.size == 0 or len(src_time) == 0 or len(src_time) != len(values):
        return None

    idx = np.searchsorted(src_time, target_time, side="left")
    idx = np.clip(idx, 0, len(src_time) - 1)
    prev_idx = np.clip(idx - 1, 0, len(src_time) - 1)
    choose_prev = np.abs(target_time - src_time[prev_idx]) <= np.abs(src_time[idx] - target_time)
    nearest_idx = np.where(choose_prev, prev_idx, idx)
    sampled = values[nearest_idx].astype(float, copy=True)
    if not np.isfinite(sampled).any():
        return None
    return sampled


def build_turn_radius_series_norm(turn_radius_series):
    if turn_radius_series is None:
        return None

    values = np.asarray(getattr(turn_radius_series, "radius_m", []), dtype=float).reshape(-1)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return None

    vmin = float(np.percentile(finite, 5))
    vmax = float(np.percentile(finite, 95))
    if np.isclose(vmin, vmax):
        vmin = float(np.min(finite))
        vmax = float(np.max(finite))
    if np.isclose(vmin, vmax):
        vmax = vmin + 1e-9
    return Normalize(vmin=vmin, vmax=vmax)


def interpolate_scalar_to_time(ski, mode: str, target_time: np.ndarray):
    if ski is None:
        return None

    values = get_scalar_data(ski, mode)
    if values is None:
        return None

    src_time = np.asarray(getattr(ski, "time", []), dtype=float).reshape(-1)
    values = np.asarray(values, dtype=float).reshape(-1)
    target_time = np.asarray(target_time, dtype=float).reshape(-1)

    if len(src_time) != len(values) or len(src_time) < 2 or len(target_time) == 0:
        return None

    valid = np.isfinite(src_time) & np.isfinite(values)
    src_time = src_time[valid]
    values = values[valid]
    if len(src_time) < 2:
        return None

    order = np.argsort(src_time)
    src_time = src_time[order]
    values = values[order]

    src_time, unique_idx = np.unique(src_time, return_index=True)
    values = values[unique_idx]
    if len(src_time) < 2:
        return None

    return np.interp(target_time, src_time, values)


def combine_scalar_series(series_list: list[np.ndarray | None]):
    arrays = [np.asarray(series, dtype=float).reshape(-1) for series in series_list if series is not None]
    if not arrays:
        return None

    length = len(arrays[0])
    arrays = [series for series in arrays if len(series) == length]
    if not arrays:
        return None

    if len(arrays) == 1:
        return arrays[0]

    stacked = np.vstack(arrays)
    return np.nanmean(stacked, axis=0)


def build_shared_scalar_norm(skis, mode: str):
    if mode == "fixed":
        return None

    values = []
    for ski in skis:
        series = get_scalar_data(ski, mode)
        if series is not None and len(series) > 0:
            values.append(np.asarray(series, dtype=float))

    if not values:
        return None

    merged = np.concatenate(values)
    merged = merged[np.isfinite(merged)]
    if merged.size == 0:
        return None

    if mode == "speed":
        return Normalize(vmin=SPEED_COLOR_VMIN_KMH, vmax=SPEED_COLOR_VMAX_KMH)

    vmin = float(np.percentile(merged, 5))
    vmax = float(np.percentile(merged, 95))

    if np.isclose(vmin, vmax):
        vmin = float(np.min(merged))
        vmax = float(np.max(merged))

    if np.isclose(vmin, vmax):
        vmax = vmin + 1e-9

    return Normalize(vmin=vmin, vmax=vmax)
