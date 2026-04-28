from __future__ import annotations

import numpy as np

from app.analysis_engine.config import TemporalConfig

EPSILON = 1e-10


def _safe_float(value: float) -> float:
    if np.isfinite(value):
        return float(value)
    return 0.0


def _trend_points(frame_features: list[dict[str, object]], feature_key: str) -> list[dict[str, float]]:
    points: list[dict[str, float]] = []
    for frame in frame_features:
        basic = frame.get("basic_features", {})
        points.append(
            {
                "frame_index": int(frame["frame_index"]),
                "start_time": float(frame["start_time"]),
                "end_time": float(frame["end_time"]),
                "time_seconds": float((float(frame["start_time"]) + float(frame["end_time"])) / 2),
                "value": float(basic.get(feature_key, 0.0)),
            }
        )
    return points


def reduce_trend(points: list[dict[str, float]], max_points: int) -> list[dict[str, float]]:
    if max_points <= 0 or len(points) <= max_points:
        return points

    selected_indices = np.linspace(0, len(points) - 1, max_points)
    unique_indices = sorted({int(round(index)) for index in selected_indices})
    return [points[index] for index in unique_indices]


def _linear_regression(times: np.ndarray, values: np.ndarray) -> tuple[float, float, float]:
    if times.size < 2 or values.size < 2:
        intercept = float(values[0]) if values.size else 0.0
        return 0.0, intercept, 0.0

    slope, intercept = np.polyfit(times, values, 1)
    if abs(float(slope)) < EPSILON:
        slope = 0.0
    if abs(float(intercept)) < EPSILON:
        intercept = 0.0
    predicted = slope * times + intercept
    residual_sum = float(np.sum((values - predicted) ** 2))
    total_sum = float(np.sum((values - np.mean(values)) ** 2))
    r2 = 0.0 if total_sum <= EPSILON else 1.0 - (residual_sum / total_sum)
    return _safe_float(float(slope)), _safe_float(float(intercept)), _safe_float(float(max(0.0, min(1.0, r2))))


def _detect_peaks(values: np.ndarray, config: TemporalConfig) -> list[int]:
    if values.size < 3:
        return []

    value_range = float(np.max(values) - np.min(values))
    if value_range <= EPSILON:
        return []

    threshold = float(np.min(values) + value_range * config.peak_prominence_ratio)
    peaks: list[int] = []
    for index in range(1, values.size - 1):
        if values[index] >= values[index - 1] and values[index] > values[index + 1] and values[index] >= threshold:
            peaks.append(index)
    return peaks


def _energy_ratios(values: np.ndarray) -> tuple[float, float, float]:
    if values.size == 0:
        return 0.0, 0.0, 0.0

    thirds = np.array_split(values, 3)
    total = float(np.sum(values))
    if total <= EPSILON:
        return 0.0, 0.0, 0.0

    return tuple(_safe_float(float(np.sum(part) / total)) for part in thirds)


def compute_temporal_summary(
    frame_features: list[dict[str, object]],
    *,
    config: TemporalConfig,
) -> dict[str, object]:
    rms_trend = _trend_points(frame_features, "rms_mean")
    energy_trend = _trend_points(frame_features, "short_time_energy_mean")
    rms_reduced = reduce_trend(rms_trend, config.max_trend_points)
    energy_reduced = reduce_trend(energy_trend, config.max_trend_points)

    times = np.asarray([point["time_seconds"] for point in energy_trend], dtype=float)
    energy = np.asarray([point["value"] for point in energy_trend], dtype=float)
    rms = np.asarray([point["value"] for point in rms_trend], dtype=float)

    slope, intercept, r2 = _linear_regression(times, energy)
    peak_indices = _detect_peaks(energy, config)
    peak_times = [float(times[index]) for index in peak_indices]

    peak_index = int(np.argmax(energy)) if energy.size else 0
    time_to_peak = float(times[peak_index]) if times.size else 0.0
    attack_time = time_to_peak - float(times[0]) if times.size else 0.0
    decay_time = float(times[-1]) - time_to_peak if times.size else 0.0

    mean_energy = float(np.mean(energy)) if energy.size else 0.0
    std_energy = float(np.std(energy)) if energy.size else 0.0
    coefficient_of_variation = 0.0 if mean_energy <= EPSILON else std_energy / (mean_energy + EPSILON)
    stability_index = 1.0 / (1.0 + coefficient_of_variation)
    variability_index = coefficient_of_variation

    max_energy = float(np.max(energy)) if energy.size else 0.0
    active_threshold = max_energy * config.active_energy_ratio
    active_mask = energy > active_threshold if max_energy > EPSILON else np.zeros_like(energy, dtype=bool)
    active_frame_ratio = float(np.mean(active_mask)) if active_mask.size else 0.0
    silence_frame_ratio = 1.0 - active_frame_ratio if active_mask.size else 0.0

    early_ratio, middle_ratio, late_ratio = _energy_ratios(energy)
    temporal_asymmetry = 0.0
    if early_ratio + late_ratio > EPSILON:
        temporal_asymmetry = (late_ratio - early_ratio) / (late_ratio + early_ratio + EPSILON)

    return {
        "rms_trend_reduced": rms_reduced,
        "energy_trend_reduced": energy_reduced,
        "power_slope": slope,
        "power_intercept": intercept,
        "power_r2": r2,
        "num_energy_peaks": len(peak_indices),
        "peak_frame_indices": [int(index) for index in peak_indices],
        "peak_times_seconds": peak_times,
        "time_to_peak_seconds": _safe_float(time_to_peak),
        "attack_time_seconds": _safe_float(attack_time),
        "decay_time_seconds": _safe_float(decay_time),
        "stability_index": _safe_float(float(stability_index)),
        "variability_index": _safe_float(float(variability_index)),
        "coefficient_of_variation": _safe_float(float(coefficient_of_variation)),
        "active_frame_ratio": _safe_float(active_frame_ratio),
        "silence_frame_ratio": _safe_float(silence_frame_ratio),
        "temporal_asymmetry": _safe_float(float(temporal_asymmetry)),
        "early_energy_ratio": _safe_float(float(early_ratio)),
        "middle_energy_ratio": _safe_float(float(middle_ratio)),
        "late_energy_ratio": _safe_float(float(late_ratio)),
    }
