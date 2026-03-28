from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.errors import EmptyDataError

SPEED_TO_KMH = 3.6


class DataLoadError(ValueError):
    """Raised when exported ski data cannot be loaded safely."""


@dataclass
class SkiData:
    time: np.ndarray
    roll: np.ndarray
    pitch: np.ndarray
    yaw: np.ndarray
    acc: np.ndarray | None = None
    gyro: np.ndarray | None = None
    gyro_mag: np.ndarray | None = None
    speed: np.ndarray | None = None


@dataclass
class GpsTrackProfile:
    time: np.ndarray
    distance_km: np.ndarray
    altitude_m: np.ndarray
    gradient_pct: np.ndarray


@dataclass
class GpsPath:
    time: np.ndarray
    latitude: np.ndarray
    longitude: np.ndarray
    altitude_m: np.ndarray | None = None
    speed_kmh: np.ndarray | None = None
    accuracy_m: np.ndarray | None = None


@dataclass
class IntervalPeak:
    sample_index: int
    time: float
    value: float


@dataclass
class TurnInterval:
    interval_index: int
    idx_start: int
    idx_stop: int
    time_start: float
    time_stop: float
    stats: dict
    peaks: list[IntervalPeak]
    left_peaks: list[IntervalPeak]
    right_peaks: list[IntervalPeak]
    turn_bounds: list[tuple[float, float]]

@dataclass
class AverageTurnProfile:
    sample_count: int
    avg_peak_count: int
    euler_max_abs: dict[str, float]
    gyro_max_abs: dict[str, float]


@dataclass
class RunSegment:
    run_index: int
    idx_start: int
    idx_stop: int
    time_start: float
    time_stop: float
    distance_km: float
    altitude_drop_m: float


@dataclass
class TurnRadiusSegment:
    time_start: float
    time_stop: float
    radius_m: float
    valid: bool
    num_points: int


@dataclass
class TurnRadiusTimeSeries:
    time: np.ndarray
    radius_m: np.ndarray


def _read_csv_table(file: Path, required_columns: set[str]) -> pd.DataFrame:
    try:
        df = pd.read_csv(file)
    except FileNotFoundError:
        raise
    except EmptyDataError as exc:
        raise DataLoadError(f"Subor '{file.name}' je prazdny.") from exc
    except Exception as exc:
        raise DataLoadError(f"Subor '{file.name}' sa nepodarilo nacitat: {exc}") from exc

    if df.empty:
        raise DataLoadError(f"Subor '{file.name}' neobsahuje ziadne riadky.")

    missing = sorted(required_columns - set(df.columns))
    if missing:
        required_text = ", ".join(sorted(required_columns))
        missing_text = ", ".join(missing)
        raise DataLoadError(
            f"Subor '{file.name}' musi obsahovat stlpce [{required_text}]. "
            f"Chybaju: {missing_text}."
        )

    return df


def _invalid_row_numbers(series: pd.Series) -> str:
    rows = (series[series.isna()].index[:5] + 2).tolist()
    return ", ".join(str(row) for row in rows)


def _numeric_column(df: pd.DataFrame, file: Path, column: str) -> np.ndarray:
    numeric = pd.to_numeric(df[column], errors="coerce")

    if numeric.isna().any():
        rows = _invalid_row_numbers(numeric)
        raise DataLoadError(
            f"Subor '{file.name}', stlpec '{column}' obsahuje neplatne alebo prazdne "
            f"hodnoty. Problemove riadky: {rows}."
        )

    values = numeric.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise DataLoadError(
            f"Subor '{file.name}', stlpec '{column}' obsahuje neplatne hodnoty typu inf alebo nan."
        )

    return values


def _sorted_unique_time_data(
    file: Path, time: np.ndarray, *value_arrays: np.ndarray
) -> tuple[np.ndarray, ...]:
    if len(time) < 2:
        raise DataLoadError(
            f"Subor '{file.name}' musi obsahovat aspon 2 riadky s platnym casom."
        )

    order = np.argsort(time)
    time_sorted = time[order]
    values_sorted = [values[order] for values in value_arrays]

    unique_time, unique_indices = np.unique(time_sorted, return_index=True)
    duplicate_count = len(time_sorted) - len(unique_time)
    if duplicate_count:
        time_sorted = unique_time
        values_sorted = [values[unique_indices] for values in values_sorted]

    if len(time_sorted) < 2:
        raise DataLoadError(
            f"Subor '{file.name}' neobsahuje dostatok unikatnych casovych znaciek."
        )

    return (time_sorted, *values_sorted)


def _wrap_angle_deg(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    wrapped = (values + 180.0) % 360.0 - 180.0
    wrapped[np.isclose(wrapped, -180.0)] = 180.0
    return wrapped


def interp_to_base_time(base_t, src_t, src_values):
    base_t = np.asarray(base_t, dtype=float).reshape(-1)
    src_t = np.asarray(src_t, dtype=float).reshape(-1)
    src_values = np.asarray(src_values, dtype=float)

    valid = np.isfinite(src_t)
    if src_values.ndim == 1:
        valid = valid & np.isfinite(src_values)
    else:
        valid = valid & np.all(np.isfinite(src_values), axis=1)

    src_t = src_t[valid]
    src_values = src_values[valid]

    if len(src_t) < 2:
        return None

    order = np.argsort(src_t)
    src_t = src_t[order]
    src_values = src_values[order]

    src_t_unique, unique_idx = np.unique(src_t, return_index=True)
    src_t = src_t_unique
    src_values = src_values[unique_idx]

    if len(src_t) < 2:
        return None

    if src_values.ndim == 1:
        return np.interp(base_t, src_t, src_values)

    out = np.empty((len(base_t), src_values.shape[1]), dtype=float)
    for i in range(src_values.shape[1]):
        out[:, i] = np.interp(base_t, src_t, src_values[:, i])
    return out


def read_euler_csv(file: Path):
    if not file.exists():
        return None

    df = _read_csv_table(file, {"time", "roll_deg", "pitch_deg", "yaw_deg"})
    time = _numeric_column(df, file, "time")
    roll = _numeric_column(df, file, "roll_deg")
    pitch = _numeric_column(df, file, "pitch_deg")
    yaw = _numeric_column(df, file, "yaw_deg")
    time, roll, pitch, yaw = _sorted_unique_time_data(file, time, roll, pitch, yaw)

    return {
        "time": time,
        "roll": roll,
        "pitch": pitch,
        "yaw": yaw,
    }


def read_acc_csv(file: Path):
    if not file.exists():
        return None

    df = _read_csv_table(file, {"time", "acc_x", "acc_y", "acc_z"})
    time = _numeric_column(df, file, "time")
    acc_x = _numeric_column(df, file, "acc_x")
    acc_y = _numeric_column(df, file, "acc_y")
    acc_z = _numeric_column(df, file, "acc_z")

    time, acc_x, acc_y, acc_z = _sorted_unique_time_data(file, time, acc_x, acc_y, acc_z)

    return {
        "time": time,
        "acc": np.column_stack((acc_x, acc_y, acc_z)),
    }


def read_gyro_csv(file: Path):
    if not file.exists():
        return None

    df = _read_csv_table(file, {"time", "gyro_x", "gyro_y", "gyro_z"})
    time = _numeric_column(df, file, "time")
    gyro_x = _numeric_column(df, file, "gyro_x")
    gyro_y = _numeric_column(df, file, "gyro_y")
    gyro_z = _numeric_column(df, file, "gyro_z")

    time, gyro_x, gyro_y, gyro_z = _sorted_unique_time_data(
        file, time, gyro_x, gyro_y, gyro_z
    )

    return {
        "time": time,
        "gyro": np.column_stack((gyro_x, gyro_y, gyro_z)),
    }


def read_gps_csv(file: Path):
    if not file.exists():
        return None

    df = _read_csv_table(file, {"time", "speed"})
    time = _numeric_column(df, file, "time")
    speed = _numeric_column(df, file, "speed") * SPEED_TO_KMH

    time, speed = _sorted_unique_time_data(file, time, speed)

    return {
        "time": time,
        "speed": speed,
    }


def _haversine_step_distance_m(
    latitude_deg: np.ndarray, longitude_deg: np.ndarray
) -> np.ndarray:
    lat_rad = np.radians(latitude_deg)
    lon_rad = np.radians(longitude_deg)

    dlat = np.diff(lat_rad)
    dlon = np.diff(lon_rad)

    a = (
        np.sin(dlat / 2.0) ** 2
        + np.cos(lat_rad[:-1]) * np.cos(lat_rad[1:]) * np.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))
    earth_radius_m = 6_371_000.0
    return earth_radius_m * c


def _moving_average(values: np.ndarray, window: int) -> np.ndarray:
    if window <= 1 or len(values) < 3:
        return values

    pad = window // 2
    padded = np.pad(values, (pad, pad), mode="edge")
    kernel = np.ones(window, dtype=float) / float(window)
    return np.convolve(padded, kernel, mode="valid")


def load_gps_track_profile(folder: Path) -> GpsTrackProfile | None:
    gps_file = folder / "gps.csv"
    if not gps_file.exists():
        return None

    df = _read_csv_table(gps_file, {"time", "latitude", "longitude", "altitude"})
    time = _numeric_column(df, gps_file, "time")
    latitude = _numeric_column(df, gps_file, "latitude")
    longitude = _numeric_column(df, gps_file, "longitude")
    altitude = _numeric_column(df, gps_file, "altitude")

    time, latitude, longitude, altitude = _sorted_unique_time_data(
        gps_file, time, latitude, longitude, altitude
    )

    if len(time) < 3:
        return None

    step_distance_m = _haversine_step_distance_m(latitude, longitude)
    cumulative_distance_m = np.concatenate(([0.0], np.cumsum(step_distance_m)))

    if not np.isfinite(cumulative_distance_m).all() or cumulative_distance_m[-1] <= 0.0:
        return None

    # Regular distance spacing makes the profile much more stable and easier to read.
    spacing_m = 5.0
    sample_distance_m = np.arange(0.0, cumulative_distance_m[-1] + spacing_m, spacing_m)
    if len(sample_distance_m) < 3:
        sample_distance_m = cumulative_distance_m

    sample_time = np.interp(sample_distance_m, cumulative_distance_m, time)
    sample_altitude = np.interp(sample_distance_m, cumulative_distance_m, altitude)
    sample_altitude = _moving_average(sample_altitude, window=9)

    gradient_pct = np.zeros_like(sample_altitude)
    if len(sample_altitude) >= 2:
        altitude_delta = np.diff(sample_altitude)
        distance_delta = np.diff(sample_distance_m)
        valid = distance_delta > 0.0
        gradient_step = np.zeros_like(altitude_delta)
        gradient_step[valid] = (altitude_delta[valid] / distance_delta[valid]) * 100.0
        gradient_step = _moving_average(gradient_step, window=7)
        gradient_pct[1:] = gradient_step
        gradient_pct[0] = gradient_pct[1]

    gradient_pct = np.clip(gradient_pct, -60.0, 60.0)

    return GpsTrackProfile(
        time=sample_time,
        distance_km=sample_distance_m / 1000.0,
        altitude_m=sample_altitude,
        gradient_pct=gradient_pct,
    )


def load_gps_path(folder: Path) -> GpsPath | None:
    gps_file = folder / "gps.csv"
    if not gps_file.exists():
        return None

    df = _read_csv_table(gps_file, {"time", "latitude", "longitude", "speed"})
    time = _numeric_column(df, gps_file, "time")
    latitude = _numeric_column(df, gps_file, "latitude")
    longitude = _numeric_column(df, gps_file, "longitude")
    altitude_m = (
        _numeric_column(df, gps_file, "altitude")
        if "altitude" in df.columns
        else None
    )
    accuracy_m = (
        _numeric_column(df, gps_file, "accuracy")
        if "accuracy" in df.columns
        else None
    )
    speed_kmh = _numeric_column(df, gps_file, "speed") * SPEED_TO_KMH

    value_arrays = [latitude, longitude]
    if altitude_m is not None:
        value_arrays.append(altitude_m)
    value_arrays.append(speed_kmh)
    if accuracy_m is not None:
        value_arrays.append(accuracy_m)

    sorted_values = _sorted_unique_time_data(gps_file, time, *value_arrays)
    time = sorted_values[0]
    next_idx = 1
    latitude = sorted_values[next_idx]
    next_idx += 1
    longitude = sorted_values[next_idx]
    next_idx += 1
    if altitude_m is not None:
        altitude_m = sorted_values[next_idx]
        next_idx += 1
    speed_kmh = sorted_values[next_idx]
    next_idx += 1
    if accuracy_m is not None:
        accuracy_m = sorted_values[next_idx]

    if len(time) < 2:
        return None

    return GpsPath(
        time=time,
        latitude=latitude,
        longitude=longitude,
        altitude_m=altitude_m,
        speed_kmh=speed_kmh,
        accuracy_m=accuracy_m,
    )


def load_one_ski(folder: Path, tag: str, gps_data=None) -> SkiData | None:
    euler_file = folder / f"{tag}_euler.csv"
    acc_file = folder / f"{tag}_acc.csv"
    gyro_file = folder / f"{tag}_gyro.csv"

    euler = read_euler_csv(euler_file)
    if euler is None:
        return None

    time = euler["time"]

    acc = None
    acc_data = read_acc_csv(acc_file)
    if acc_data is not None:
        acc = interp_to_base_time(time, acc_data["time"], acc_data["acc"])

    gyro = None
    gyro_mag = None
    gyro_data = read_gyro_csv(gyro_file)
    if gyro_data is not None:
        gyro = interp_to_base_time(time, gyro_data["time"], gyro_data["gyro"])
        if gyro is not None:
            gyro_mag = np.degrees(np.linalg.norm(np.asarray(gyro, dtype=float), axis=1))

    speed = None
    if gps_data is not None:
        speed = interp_to_base_time(time, gps_data["time"], gps_data["speed"])

    return SkiData(
        time=time,
        roll=euler["roll"],
        pitch=euler["pitch"],
        yaw=euler["yaw"],
        acc=acc,
        gyro=gyro,
        gyro_mag=gyro_mag,
        speed=speed,
    )


def load_exported_ski_folder(folder: Path) -> tuple[SkiData | None, SkiData | None]:
    if not folder.exists():
        raise DataLoadError(f"Priecinok '{folder}' neexistuje.")

    if not folder.is_dir():
        raise DataLoadError(f"Cesta '{folder}' nie je priecinok.")

    gps_file = folder / "gps.csv"
    gps_data = read_gps_csv(gps_file)

    right = load_one_ski(folder, "right_ski", gps_data=gps_data)
    left = load_one_ski(folder, "left_ski", gps_data=gps_data)

    if right is None and left is None:
        raise DataLoadError(
            "V priecinku sa nenasiel ani 'right_ski_euler.csv' ani 'left_ski_euler.csv'."
        )

    return right, left


def is_export_session_folder(folder: Path) -> bool:
    if not folder.exists() or not folder.is_dir():
        return False

    required_any = [
        folder / "right_ski_euler.csv",
        folder / "left_ski_euler.csv",
    ]
    return any(file.exists() for file in required_any)


def list_export_sessions(root: Path) -> list[Path]:
    if not root.exists():
        return []
    if not root.is_dir():
        return []

    sessions = [child for child in root.iterdir() if is_export_session_folder(child)]
    return sorted(sessions, key=lambda path: path.name.lower())


def _coerce_scalar(value):
    if pd.isna(value):
        return None
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value)
    return value


def normalize_stats_fields(stats: dict) -> dict:
    normalized = dict(stats)

    elevation_loss = normalized.get("elevationloss")
    typo_elevation_loss = normalized.get("elevatioloss")

    if elevation_loss in (None, 0, 0.0) and typo_elevation_loss not in (None, 0, 0.0):
        normalized["elevationloss"] = typo_elevation_loss

    if "avgTurnRadius_m" in normalized and "averageTurnRadius_m" not in normalized:
        normalized["averageTurnRadius_m"] = normalized["avgTurnRadius_m"]

    return normalized

def load_interval_stats_file(file: Path) -> dict:
    if not file.exists():
        return {}

    df = _read_csv_table(file, set())
    first_row = df.iloc[0]
    stats = {column: _coerce_scalar(first_row[column]) for column in df.columns}
    return normalize_stats_fields(stats)


def _load_peak_file(file: Path) -> list[IntervalPeak]:
    if not file.exists():
        return []

    df = _read_csv_table(file, {"idx", "tPeaks", "values"})
    peak_indices = _numeric_column(df, file, "idx").astype(int)
    peak_times = _numeric_column(df, file, "tPeaks")
    peak_values = _numeric_column(df, file, "values")

    return [
        IntervalPeak(
            sample_index=int(peak_idx),
            time=float(peak_time),
            value=float(peak_value),
        )
        for peak_idx, peak_time, peak_value in zip(peak_indices, peak_times, peak_values)
    ]


def _group_peaks_by_intervals(
    time_start: np.ndarray, time_stop: np.ndarray, peaks: list[IntervalPeak]
) -> list[list[IntervalPeak]]:
    peaks_by_interval: list[list[IntervalPeak]] = [[] for _ in range(len(time_start))]

    for peak in peaks:
        for interval_pos, (start_t, stop_t) in enumerate(zip(time_start, time_stop)):
            if start_t <= peak.time <= stop_t:
                peaks_by_interval[interval_pos].append(peak)
                break

    return peaks_by_interval


def _load_turn_bounds_file(file: Path) -> np.ndarray:
    if not file.exists():
        return np.empty((0, 2), dtype=float)

    try:
        df = _read_csv_table(file, {"tLeft", "tRight"})
    except DataLoadError:
        return np.empty((0, 2), dtype=float)

    # Peak bounds are optional viewer hints. Invalid rows should be ignored,
    # not treated as a fatal load error for the whole session.
    t_left = pd.to_numeric(df["tLeft"], errors="coerce").to_numpy(dtype=float)
    t_right = pd.to_numeric(df["tRight"], errors="coerce").to_numpy(dtype=float)

    valid = np.isfinite(t_left) & np.isfinite(t_right) & (t_right > t_left)
    t_left = t_left[valid]
    t_right = t_right[valid]

    if len(t_left) == 0:
        return np.empty((0, 2), dtype=float)

    return np.column_stack((t_left, t_right))


def _group_turn_bounds_by_intervals(
    time_start: np.ndarray, time_stop: np.ndarray, turn_bounds: np.ndarray
) -> list[list[tuple[float, float]]]:
    bounds_by_interval: list[list[tuple[float, float]]] = [[] for _ in range(len(time_start))]

    for bound_start, bound_stop in turn_bounds:
        for interval_pos, (start_t, stop_t) in enumerate(zip(time_start, time_stop)):
            clipped_start = max(float(bound_start), float(start_t))
            clipped_stop = min(float(bound_stop), float(stop_t))
            if clipped_start < clipped_stop:
                bounds_by_interval[interval_pos].append((clipped_start, clipped_stop))
                break

    return bounds_by_interval


def _load_turn_radius_segments_file(file: Path) -> list[TurnRadiusSegment]:
    if not file.exists():
        return []

    radius_column = "radiusFinal_m" if "combined" in file.stem else "radius_m"
    valid_column = "validFinal" if "combined" in file.stem else "valid"
    df = _read_csv_table(file, {"tStart", "tStop", radius_column})
    t_start = _numeric_column(df, file, "tStart")
    t_stop = _numeric_column(df, file, "tStop")
    radius = _numeric_column(df, file, radius_column)
    valid_raw = (
        _numeric_column(df, file, valid_column)
        if valid_column in df.columns
        else np.ones(len(t_start), dtype=float)
    )
    num_points = (
        _numeric_column(df, file, "numPoints").astype(int)
        if "numPoints" in df.columns
        else np.zeros(len(t_start), dtype=int)
    )

    segments: list[TurnRadiusSegment] = []
    for start_t, stop_t, radius_m, valid_value, points in zip(
        t_start, t_stop, radius, valid_raw, num_points
    ):
        is_valid = bool(valid_value >= 0.5) and np.isfinite(radius_m) and float(stop_t) > float(start_t)
        segments.append(
            TurnRadiusSegment(
                time_start=float(start_t),
                time_stop=float(stop_t),
                radius_m=float(radius_m),
                valid=is_valid,
                num_points=int(points),
            )
        )

    return segments


def load_turn_radius_segments(folder: Path) -> list[TurnRadiusSegment]:
    for name in ("turn_radius_combined.csv", "turn_radius_by_interval.csv"):
        file = folder / name
        if file.exists():
            return _load_turn_radius_segments_file(file)
    return []


def load_turn_radius_summary(folder: Path) -> dict:
    for name in ("turn_radius_combined_summary.csv", "turn_radius_summary.csv"):
        file = folder / name
        if file.exists():
            return load_interval_stats_file(file)
    return {}


def load_turn_radius_timeseries(folder: Path) -> TurnRadiusTimeSeries | None:
    file = folder / "turn_radius_timeseries.csv"
    if not file.exists():
        return None

    df = _read_csv_table(file, {"time", "radius_m"})
    time = _numeric_column(df, file, "time")
    radius = pd.to_numeric(df["radius_m"], errors="coerce").to_numpy(dtype=float)
    time, radius = _sorted_unique_time_data(file, time, radius)
    if len(time) < 2:
        return None

    return TurnRadiusTimeSeries(time=time, radius_m=radius)


def _group_turn_radius_stats_by_intervals(
    time_start: np.ndarray,
    time_stop: np.ndarray,
    radius_segments: list[TurnRadiusSegment],
) -> list[dict]:
    stats_by_interval: list[dict] = [{} for _ in range(len(time_start))]

    for interval_pos, (start_t, stop_t) in enumerate(zip(time_start, time_stop)):
        radii = [
            float(segment.radius_m)
            for segment in radius_segments
            if segment.valid
            and np.isfinite(segment.radius_m)
            and float(segment.time_stop) > float(start_t)
            and float(segment.time_start) < float(stop_t)
        ]

        if not radii:
            continue

        radius_arr = np.asarray(radii, dtype=float)
        stats_by_interval[interval_pos] = {
            "averageTurnRadius_m": float(np.mean(radius_arr)),
            "minTurnRadius_m": float(np.min(radius_arr)),
            "maxTurnRadius_m": float(np.max(radius_arr)),
            "numValidTurnsRadius": int(len(radius_arr)),
        }

    return stats_by_interval


def load_turn_intervals(folder: Path) -> list[TurnInterval]:
    intervals_file = folder / "turnDetection_intervals.csv"
    if not intervals_file.exists():
        return []

    df = _read_csv_table(intervals_file, {"idxStart", "idxStop", "tStart", "tStop"})
    idx_start = _numeric_column(df, intervals_file, "idxStart").astype(int)
    idx_stop = _numeric_column(df, intervals_file, "idxStop").astype(int)
    time_start = _numeric_column(df, intervals_file, "tStart")
    time_stop = _numeric_column(df, intervals_file, "tStop")

    peaks_by_interval = _group_peaks_by_intervals(
        time_start,
        time_stop,
        _load_peak_file(folder / "turnDetection_peaks.csv"),
    )
    left_peaks_by_interval = _group_peaks_by_intervals(
        time_start,
        time_stop,
        _load_peak_file(folder / "turnDetection_left_peaks.csv"),
    )
    right_peaks_by_interval = _group_peaks_by_intervals(
        time_start,
        time_stop,
        _load_peak_file(folder / "turnDetection_right_peaks.csv"),
    )
    turn_bounds_by_interval = _group_turn_bounds_by_intervals(
        time_start,
        time_stop,
        _load_turn_bounds_file(folder / "peak_bounds.csv"),
    )
    radius_stats_by_interval = _group_turn_radius_stats_by_intervals(
        time_start,
        time_stop,
        load_turn_radius_segments(folder),
    )
    intervals: list[TurnInterval] = []
    for interval_pos, (start_idx, stop_idx, start_t, stop_t) in enumerate(
        zip(idx_start, idx_stop, time_start, time_stop),
        start=1,
    ):
        stats_file = folder / f"interval_{interval_pos:02d}_stats.csv"
        interval_stats = load_interval_stats_file(stats_file)
        interval_stats.update(radius_stats_by_interval[interval_pos - 1])
        intervals.append(
            TurnInterval(
                interval_index=interval_pos,
                idx_start=int(start_idx),
                idx_stop=int(stop_idx),
                time_start=float(start_t),
                time_stop=float(stop_t),
                stats=interval_stats,
                peaks=peaks_by_interval[interval_pos - 1],
                left_peaks=left_peaks_by_interval[interval_pos - 1],
                right_peaks=right_peaks_by_interval[interval_pos - 1],
                turn_bounds=turn_bounds_by_interval[interval_pos - 1],
            )
        )

    return intervals


def load_average_turn_profile(folder: Path) -> AverageTurnProfile | None:
    euler_file = folder / "turnDetection_average_euler.csv"
    gyro_file = folder / "turnDetection_average_gyro.csv"
    avg_peaks_file = folder / "turnDetection_avg_peaks.csv"

    has_any = euler_file.exists() or gyro_file.exists() or avg_peaks_file.exists()
    if not has_any:
        return None

    euler_max_abs = {"roll_deg": 0.0, "pitch_deg": 0.0, "yaw_deg": 0.0}
    gyro_max_abs = {"gyroX": 0.0, "gyroY": 0.0, "gyroZ": 0.0}
    sample_count = 0

    if euler_file.exists():
        euler_df = _read_csv_table(euler_file, {"roll_deg", "pitch_deg", "yaw_deg"})
        for column in euler_max_abs:
            values = _numeric_column(euler_df, euler_file, column)
            euler_max_abs[column] = float(np.max(np.abs(values))) if len(values) else 0.0
        sample_count = max(sample_count, len(euler_df))

    if gyro_file.exists():
        gyro_df = _read_csv_table(gyro_file, {"gyroX", "gyroY", "gyroZ"})
        for column in gyro_max_abs:
            values = _numeric_column(gyro_df, gyro_file, column)
            gyro_max_abs[column] = float(np.max(np.abs(values))) if len(values) else 0.0
        sample_count = max(sample_count, len(gyro_df))

    avg_peak_count = len(_load_peak_file(avg_peaks_file))

    return AverageTurnProfile(
        sample_count=sample_count,
        avg_peak_count=avg_peak_count,
        euler_max_abs=euler_max_abs,
        gyro_max_abs=gyro_max_abs,
    )


def slice_ski_data_to_interval(
    ski: SkiData | None, time_start: float, time_stop: float
) -> SkiData | None:
    if ski is None:
        return None

    time = np.asarray(ski.time, dtype=float)
    mask = (time >= time_start) & (time <= time_stop)
    if int(np.count_nonzero(mask)) < 2:
        return None

    def maybe_slice(values):
        if values is None:
            return None
        array = np.asarray(values)
        if len(array) != len(mask):
            return None
        return array[mask]

    return SkiData(
        time=time[mask],
        roll=np.asarray(ski.roll, dtype=float)[mask],
        pitch=np.asarray(ski.pitch, dtype=float)[mask],
        yaw=np.asarray(ski.yaw, dtype=float)[mask],
        acc=maybe_slice(ski.acc),
        gyro=maybe_slice(ski.gyro),
        gyro_mag=maybe_slice(ski.gyro_mag),
        speed=maybe_slice(ski.speed),
    )


def slice_gps_path_to_interval(
    gps_path: GpsPath | None, time_start: float, time_stop: float
) -> GpsPath | None:
    if gps_path is None:
        return None

    time = np.asarray(gps_path.time, dtype=float)
    mask = (time >= time_start) & (time <= time_stop)
    if int(np.count_nonzero(mask)) < 2:
        return None

    return GpsPath(
        time=time[mask],
        latitude=np.asarray(gps_path.latitude, dtype=float)[mask],
        longitude=np.asarray(gps_path.longitude, dtype=float)[mask],
        altitude_m=(
            None
            if gps_path.altitude_m is None
            else np.asarray(gps_path.altitude_m, dtype=float)[mask]
        ),
        speed_kmh=(
            None
            if gps_path.speed_kmh is None
            else np.asarray(gps_path.speed_kmh, dtype=float)[mask]
        ),
        accuracy_m=(
            None
            if gps_path.accuracy_m is None
            else np.asarray(gps_path.accuracy_m, dtype=float)[mask]
        ),
    )


def detect_gps_runs(gps_path: GpsPath | None) -> list[RunSegment]:
    if gps_path is None or gps_path.altitude_m is None or gps_path.speed_kmh is None:
        return []

    time = np.asarray(gps_path.time, dtype=float)
    latitude = np.asarray(gps_path.latitude, dtype=float)
    longitude = np.asarray(gps_path.longitude, dtype=float)
    altitude = np.asarray(gps_path.altitude_m, dtype=float)
    speed_kmh = np.asarray(gps_path.speed_kmh, dtype=float)

    if len(time) < 10:
        return []

    positive_dt = np.diff(time)
    positive_dt = positive_dt[np.isfinite(positive_dt) & (positive_dt > 0.0)]
    if positive_dt.size == 0:
        return []

    dt = float(np.median(positive_dt))
    if dt <= 0.0:
        return []

    smooth_window = max(5, int(round(3.0 / dt)))
    if smooth_window % 2 == 0:
        smooth_window += 1
    if smooth_window >= len(altitude):
        smooth_window = len(altitude) - 1 if len(altitude) % 2 == 0 else len(altitude)
    if smooth_window < 3:
        smooth_window = 3

    altitude_smooth = _moving_average(altitude, smooth_window)
    slope_mps = np.gradient(altitude_smooth, time)

    fast_enough = speed_kmh >= 8.0
    descending = slope_mps <= -0.12
    run_mask = fast_enough & descending

    gap_samples = max(1, int(round(3.0 / dt)))
    true_indices = np.flatnonzero(run_mask)
    if true_indices.size >= 2:
        for left_idx, right_idx in zip(true_indices[:-1], true_indices[1:]):
            gap = right_idx - left_idx - 1
            if 0 < gap <= gap_samples:
                run_mask[left_idx + 1 : right_idx] = True

    segments: list[tuple[int, int]] = []
    start_idx = None
    for idx, is_run in enumerate(run_mask):
        if is_run and start_idx is None:
            start_idx = idx
        elif not is_run and start_idx is not None:
            segments.append((start_idx, idx - 1))
            start_idx = None
    if start_idx is not None:
        segments.append((start_idx, len(run_mask) - 1))

    runs: list[RunSegment] = []
    for start_idx, stop_idx in segments:
        while start_idx > 0 and speed_kmh[start_idx - 1] >= 4.0:
            start_idx -= 1
            if altitude_smooth[start_idx] >= altitude_smooth[start_idx + 1]:
                break

        while stop_idx < len(time) - 1 and speed_kmh[stop_idx + 1] >= 4.0:
            stop_idx += 1
            if altitude_smooth[stop_idx] <= altitude_smooth[stop_idx - 1]:
                break

        duration_s = float(time[stop_idx] - time[start_idx])
        altitude_drop_m = float(altitude_smooth[start_idx] - altitude_smooth[stop_idx])
        if duration_s < 20.0 or altitude_drop_m < 10.0:
            continue

        distance_steps = _haversine_step_distance_m(
            latitude[start_idx : stop_idx + 1],
            longitude[start_idx : stop_idx + 1],
        )
        distance_km = float(np.sum(distance_steps) / 1000.0)
        if distance_km < 0.15:
            continue

        runs.append(
            RunSegment(
                run_index=len(runs) + 1,
                idx_start=int(start_idx),
                idx_stop=int(stop_idx),
                time_start=float(time[start_idx]),
                time_stop=float(time[stop_idx]),
                distance_km=distance_km,
                altitude_drop_m=altitude_drop_m,
            )
        )

    return runs
