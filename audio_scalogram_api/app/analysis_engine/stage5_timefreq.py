from __future__ import annotations

import librosa
import numpy as np
import pywt

from app.analysis_engine.config import TimeFrequencyConfig

EPSILON = 1e-10


def _safe_float(value: float) -> float:
    if np.isfinite(value):
        return float(value)
    return 0.0


def _entropy(values: np.ndarray) -> float:
    total = float(np.sum(values))
    if total <= EPSILON:
        return 0.0
    probabilities = values / total
    return _safe_float(float(-np.sum(probabilities * np.log2(probabilities + EPSILON))))


def _reduce_distribution(values: np.ndarray, bins: int) -> list[float]:
    if values.size == 0:
        return []
    bins = max(1, min(int(bins), int(values.size)))
    parts = np.array_split(values, bins)
    reduced = np.asarray([float(np.sum(part)) for part in parts], dtype=float)
    total = float(np.sum(reduced))
    if total <= EPSILON:
        return [0.0 for _ in range(bins)]
    return [_safe_float(float(value / total)) for value in reduced]


def _prepare_signal(waveform: np.ndarray, sample_rate: int, config: TimeFrequencyConfig) -> tuple[np.ndarray, int]:
    signal = waveform.astype(np.float32, copy=False).reshape(-1)
    effective_rate = int(sample_rate)
    if signal.size == 0:
        return signal, effective_rate

    if sample_rate > config.max_internal_sample_rate:
        signal = librosa.resample(
            signal,
            orig_sr=sample_rate,
            target_sr=config.max_internal_sample_rate,
        ).astype(np.float32, copy=False)
        effective_rate = config.max_internal_sample_rate

    if signal.size > config.max_samples:
        indices = np.linspace(0, signal.size - 1, config.max_samples)
        signal = signal[np.round(indices).astype(int)].astype(np.float32, copy=False)

    return signal, effective_rate


def compute_time_frequency_summary(
    waveform: np.ndarray,
    *,
    sample_rate: int,
    config: TimeFrequencyConfig,
) -> dict[str, object]:
    if not config.enabled:
        return {
            "enabled": False,
            "status": "skipped",
            "reason": "time_frequency_features_disabled",
        }

    if config.max_scales < 1:
        raise ValueError("Time-frequency max_scales must be at least 1.")

    signal, effective_rate = _prepare_signal(waveform, sample_rate, config)
    if signal.size == 0 or float(np.max(np.abs(signal))) <= EPSILON:
        return {
            "enabled": True,
            "status": "success",
            "wavelet": config.wavelet,
            "internal_sample_rate": effective_rate,
            "num_scales": min(config.max_scales, 1),
            "wavelet_entropy": 0.0,
            "dominant_scale": 0,
            "scale_energy_distribution_reduced": [0.0],
            "time_frequency_concentration": 0.0,
            "frequency_centroid_timefreq": 0.0,
            "frequency_spread_timefreq": 0.0,
            "transient_index": 0.0,
            "modulation_energy_summary": {"mean": 0.0, "std": 0.0, "max": 0.0},
        }

    scale_count = min(config.max_scales, 64)
    scales = np.arange(1, scale_count + 1, dtype=np.float32)
    coefficients, frequencies = pywt.cwt(
        signal,
        scales,
        config.wavelet,
        sampling_period=1 / effective_rate,
    )
    power = np.abs(coefficients).astype(np.float32) ** 2
    total_power = float(np.sum(power))
    if total_power <= EPSILON:
        scale_energy = np.zeros(scale_count, dtype=float)
    else:
        scale_energy = np.sum(power, axis=1).astype(float)

    dominant_index = int(np.argmax(scale_energy)) if scale_energy.size else 0
    energy_distribution = scale_energy / (float(np.sum(scale_energy)) + EPSILON)
    wavelet_entropy = _entropy(scale_energy)

    flattened = power.reshape(-1)
    if total_power <= EPSILON:
        concentration = 0.0
    else:
        top_count = max(1, int(round(flattened.size * 0.10)))
        top_energy = float(np.sum(np.partition(flattened, -top_count)[-top_count:]))
        concentration = top_energy / (total_power + EPSILON)

    frequencies = np.asarray(frequencies, dtype=float)
    frequency_centroid = float(np.sum(frequencies * energy_distribution)) if frequencies.size else 0.0
    frequency_spread = float(
        np.sqrt(np.sum(energy_distribution * (frequencies - frequency_centroid) ** 2))
    ) if frequencies.size else 0.0

    temporal_energy = np.sum(power, axis=0).astype(float)
    transient_index = float(np.std(temporal_energy) / (np.mean(temporal_energy) + EPSILON)) if temporal_energy.size else 0.0
    modulation = np.abs(np.diff(temporal_energy))

    return {
        "enabled": True,
        "status": "success",
        "wavelet": config.wavelet,
        "internal_sample_rate": effective_rate,
        "num_scales": int(scale_count),
        "wavelet_entropy": _safe_float(wavelet_entropy),
        "dominant_scale": int(scales[dominant_index]) if scales.size else 0,
        "scale_energy_distribution_reduced": _reduce_distribution(scale_energy, config.reduced_bins),
        "time_frequency_concentration": _safe_float(float(concentration)),
        "frequency_centroid_timefreq": _safe_float(frequency_centroid),
        "frequency_spread_timefreq": _safe_float(frequency_spread),
        "transient_index": _safe_float(transient_index),
        "modulation_energy_summary": {
            "mean": _safe_float(float(np.mean(modulation))) if modulation.size else 0.0,
            "std": _safe_float(float(np.std(modulation))) if modulation.size else 0.0,
            "max": _safe_float(float(np.max(modulation))) if modulation.size else 0.0,
        },
    }
