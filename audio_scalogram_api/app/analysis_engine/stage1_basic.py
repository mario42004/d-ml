from __future__ import annotations

import numpy as np

EPSILON = 1e-10
SHORT_WINDOW_SECONDS = 0.05
SHORT_HOP_SECONDS = 0.025


def _safe_float(value: float) -> float:
    if np.isfinite(value):
        return float(value)
    return 0.0


def _short_windows(waveform: np.ndarray, sample_rate: int) -> list[np.ndarray]:
    window_length = max(1, int(round(SHORT_WINDOW_SECONDS * sample_rate)))
    hop_length = max(1, int(round(SHORT_HOP_SECONDS * sample_rate)))

    if waveform.size <= window_length:
        return [waveform.astype(np.float32, copy=False)]

    return [
        waveform[start : start + window_length].astype(np.float32, copy=False)
        for start in range(0, waveform.size - window_length + 1, hop_length)
    ]


def _rms_series(waveform: np.ndarray, sample_rate: int) -> np.ndarray:
    windows = _short_windows(waveform, sample_rate)
    return np.asarray(
        [np.sqrt(np.mean(window.astype(float) ** 2)) if window.size else 0.0 for window in windows],
        dtype=float,
    )


def _short_time_energy_series(waveform: np.ndarray, sample_rate: int) -> np.ndarray:
    windows = _short_windows(waveform, sample_rate)
    return np.asarray(
        [np.mean(window.astype(float) ** 2) if window.size else 0.0 for window in windows],
        dtype=float,
    )


def _zero_crossing_rate_series(waveform: np.ndarray, sample_rate: int) -> np.ndarray:
    windows = _short_windows(waveform, sample_rate)
    rates: list[float] = []
    for window in windows:
        if window.size < 2:
            rates.append(0.0)
            continue
        signs = np.signbit(window)
        rates.append(float(np.mean(signs[1:] != signs[:-1])))
    return np.asarray(rates, dtype=float)


def _peak_count(waveform: np.ndarray) -> int:
    if waveform.size < 3:
        return 0

    envelope = np.abs(waveform)
    threshold = max(float(np.percentile(envelope, 75)), EPSILON)
    local_maxima = (envelope[1:-1] > envelope[:-2]) & (envelope[1:-1] >= envelope[2:])
    return int(np.sum(local_maxima & (envelope[1:-1] >= threshold)))


def _energy_entropy(energy: np.ndarray) -> float:
    if energy.size == 0:
        return 0.0

    total_energy = float(np.sum(energy))
    if total_energy <= EPSILON:
        return 0.0

    probabilities = energy / total_energy
    entropy = -np.sum(probabilities * np.log2(probabilities + EPSILON))
    return _safe_float(float(entropy))


def compute_basic_features(
    waveform: np.ndarray,
    *,
    sample_rate: int,
    active_threshold: float | None = None,
) -> dict[str, object]:
    signal = waveform.astype(float, copy=False)
    envelope = np.abs(signal)
    rms = _rms_series(waveform, sample_rate)
    energy = _short_time_energy_series(waveform, sample_rate)
    zcr = _zero_crossing_rate_series(waveform, sample_rate)

    peak_amplitude = float(np.max(envelope)) if envelope.size else 0.0
    rms_mean = float(np.mean(rms)) if rms.size else 0.0
    threshold = active_threshold
    if threshold is None:
        threshold = max(peak_amplitude * 0.03, EPSILON)

    active_duration_seconds = float(np.sum(envelope >= threshold) / sample_rate) if sample_rate else 0.0
    crest_factor = peak_amplitude / (rms_mean + EPSILON)
    dynamic_range_db = 20 * np.log10(
        (float(np.percentile(rms, 95)) + EPSILON) / (float(np.percentile(rms, 5)) + EPSILON)
    ) if rms.size else 0.0

    return {
        "rms_mean": _safe_float(float(np.mean(rms))) if rms.size else 0.0,
        "rms_std": _safe_float(float(np.std(rms))) if rms.size else 0.0,
        "rms_min": _safe_float(float(np.min(rms))) if rms.size else 0.0,
        "rms_max": _safe_float(float(np.max(rms))) if rms.size else 0.0,
        "rms_median": _safe_float(float(np.median(rms))) if rms.size else 0.0,
        "short_time_energy_mean": _safe_float(float(np.mean(energy))) if energy.size else 0.0,
        "short_time_energy_std": _safe_float(float(np.std(energy))) if energy.size else 0.0,
        "zero_crossing_rate_mean": _safe_float(float(np.mean(zcr))) if zcr.size else 0.0,
        "zero_crossing_rate_std": _safe_float(float(np.std(zcr))) if zcr.size else 0.0,
        "peak_count": _peak_count(waveform),
        "crest_factor": _safe_float(float(crest_factor)),
        "dynamic_range_db": _safe_float(float(dynamic_range_db)),
        "energy_entropy": _energy_entropy(energy),
        "active_duration_seconds": _safe_float(active_duration_seconds),
    }


def compute_frame_basic_features(
    frames: list[np.ndarray],
    *,
    sample_rate: int,
    hop_length_samples: int,
    active_threshold: float | None = None,
) -> list[dict[str, object]]:
    frame_features: list[dict[str, object]] = []
    for index, frame in enumerate(frames):
        start_time = float((index * hop_length_samples) / sample_rate) if sample_rate else 0.0
        end_time = start_time + (float(len(frame) / sample_rate) if sample_rate else 0.0)
        frame_features.append(
            {
                "frame_index": index,
                "start_time": start_time,
                "end_time": end_time,
                "basic_features": compute_basic_features(
                    frame,
                    sample_rate=sample_rate,
                    active_threshold=active_threshold,
                ),
            }
        )
    return frame_features


def aggregate_frame_basic_features(frame_features: list[dict[str, object]]) -> dict[str, object]:
    if not frame_features:
        return {}

    durations = np.asarray(
        [float(frame["end_time"]) - float(frame["start_time"]) for frame in frame_features],
        dtype=float,
    )
    if float(np.sum(durations)) <= EPSILON:
        durations = np.ones(len(frame_features), dtype=float)
    weights = durations / np.sum(durations)
    features = [frame["basic_features"] for frame in frame_features]

    def weighted_mean(key: str) -> float:
        values = np.asarray([float(feature[key]) for feature in features], dtype=float)
        return _safe_float(float(np.sum(values * weights)))

    def weighted_std(key: str) -> float:
        values = np.asarray([float(feature[key]) for feature in features], dtype=float)
        mean = float(np.sum(values * weights))
        return _safe_float(float(np.sqrt(np.sum(weights * (values - mean) ** 2))))

    rms_means = np.asarray([float(feature["rms_mean"]) for feature in features], dtype=float)
    energy_means = np.asarray([float(feature["short_time_energy_mean"]) for feature in features], dtype=float)
    total_energy = float(np.sum(energy_means * durations))
    energy_entropy = 0.0
    if total_energy > EPSILON:
        probabilities = (energy_means * durations) / total_energy
        energy_entropy = _safe_float(float(-np.sum(probabilities * np.log2(probabilities + EPSILON))))

    dynamic_range_db = 0.0
    if rms_means.size:
        dynamic_range_db = 20 * np.log10(
            (float(np.percentile(rms_means, 95)) + EPSILON)
            / (float(np.percentile(rms_means, 5)) + EPSILON)
        )

    return {
        "rms_mean": weighted_mean("rms_mean"),
        "rms_std": weighted_std("rms_mean"),
        "rms_min": _safe_float(float(min(float(feature["rms_min"]) for feature in features))),
        "rms_max": _safe_float(float(max(float(feature["rms_max"]) for feature in features))),
        "rms_median": _safe_float(float(np.median(rms_means))) if rms_means.size else 0.0,
        "short_time_energy_mean": weighted_mean("short_time_energy_mean"),
        "short_time_energy_std": weighted_std("short_time_energy_mean"),
        "zero_crossing_rate_mean": weighted_mean("zero_crossing_rate_mean"),
        "zero_crossing_rate_std": weighted_std("zero_crossing_rate_mean"),
        "peak_count": int(sum(int(feature["peak_count"]) for feature in features)),
        "crest_factor": weighted_mean("crest_factor"),
        "dynamic_range_db": _safe_float(float(dynamic_range_db)),
        "energy_entropy": energy_entropy,
        "active_duration_seconds": _safe_float(
            float(sum(float(feature["active_duration_seconds"]) for feature in features))
        ),
    }


def build_dashboard_ready(frame_features: list[dict[str, object]]) -> dict[str, object]:
    return {
        "rms_trend": [
            {
                "frame_index": frame["frame_index"],
                "start_time": frame["start_time"],
                "end_time": frame["end_time"],
                "value": frame["basic_features"]["rms_mean"],
            }
            for frame in frame_features
        ],
        "energy_trend": [
            {
                "frame_index": frame["frame_index"],
                "start_time": frame["start_time"],
                "end_time": frame["end_time"],
                "value": frame["basic_features"]["short_time_energy_mean"],
            }
            for frame in frame_features
        ],
    }
