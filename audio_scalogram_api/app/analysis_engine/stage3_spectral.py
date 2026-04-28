from __future__ import annotations

import numpy as np

from app.analysis_engine.config import SpectralConfig

EPSILON = 1e-10


def _safe_float(value: float) -> float:
    if np.isfinite(value):
        return float(value)
    return 0.0


def _windowed_spectra(waveform: np.ndarray, config: SpectralConfig) -> np.ndarray:
    signal = waveform.astype(np.float32, copy=False)
    if signal.size == 0:
        return np.zeros((1, config.n_fft // 2 + 1), dtype=np.float32)

    n_fft = min(config.n_fft, max(2, int(signal.size)))
    hop_length = min(config.hop_length, n_fft)
    if signal.size <= n_fft:
        frames = [np.pad(signal, (0, n_fft - signal.size))]
    else:
        frames = []
        for start in range(0, signal.size - n_fft + 1, hop_length):
            frames.append(signal[start : start + n_fft])
        if not frames:
            frames = [np.pad(signal, (0, n_fft - signal.size))]

    window = np.hanning(n_fft).astype(np.float32)
    spectra = [np.abs(np.fft.rfft(frame * window, n=n_fft)).astype(np.float32) for frame in frames]
    return np.asarray(spectra, dtype=np.float32)


def _rolloff_frequency(frequencies: np.ndarray, power: np.ndarray, percentage: float) -> float:
    total_power = float(np.sum(power))
    if total_power <= EPSILON:
        return 0.0
    cumulative = np.cumsum(power)
    index = int(np.searchsorted(cumulative, total_power * percentage, side="left"))
    index = min(index, frequencies.size - 1)
    return _safe_float(float(frequencies[index]))


def _spectral_contrast_mean(frequencies: np.ndarray, mean_magnitude: np.ndarray, config: SpectralConfig) -> float:
    contrasts: list[float] = []
    for _, low_hz, high_hz in config.frequency_bands:
        mask = (frequencies >= low_hz) & (frequencies < high_hz)
        values = mean_magnitude[mask]
        if values.size < 2:
            continue
        high = float(np.percentile(values, 95))
        low = float(np.percentile(values, 5))
        contrasts.append(20 * np.log10((high + EPSILON) / (low + EPSILON)))
    return _safe_float(float(np.mean(contrasts))) if contrasts else 0.0


def _band_energy_ratios(frequencies: np.ndarray, power: np.ndarray, config: SpectralConfig) -> dict[str, float]:
    total_power = float(np.sum(power))
    ratios: dict[str, float] = {}
    for name, low_hz, high_hz in config.frequency_bands:
        mask = (frequencies >= low_hz) & (frequencies < high_hz)
        band_power = float(np.sum(power[mask])) if np.any(mask) else 0.0
        ratios[name] = _safe_float(band_power / (total_power + EPSILON)) if total_power > EPSILON else 0.0
    return ratios


def _entropy(values: np.ndarray) -> float:
    total = float(np.sum(values))
    if total <= EPSILON:
        return 0.0
    probabilities = values / total
    return _safe_float(float(-np.sum(probabilities * np.log2(probabilities + EPSILON))))


def compute_spectral_features(
    waveform: np.ndarray,
    *,
    sample_rate: int,
    config: SpectralConfig,
) -> dict[str, object]:
    spectra = _windowed_spectra(waveform, config)
    n_fft = (spectra.shape[1] - 1) * 2
    frequencies = np.fft.rfftfreq(n_fft, d=1.0 / sample_rate).astype(np.float32)
    magnitude = spectra.astype(float)
    power_by_frame = magnitude**2
    frame_power = np.sum(power_by_frame, axis=1)
    total_frame_power = frame_power + EPSILON

    centroid = np.sum(power_by_frame * frequencies, axis=1) / total_frame_power
    bandwidth = np.sqrt(
        np.sum(power_by_frame * (frequencies.reshape(1, -1) - centroid.reshape(-1, 1)) ** 2, axis=1)
        / total_frame_power
    )
    flatness = np.exp(np.mean(np.log(magnitude + EPSILON), axis=1)) / (np.mean(magnitude + EPSILON, axis=1))

    mean_power = np.mean(power_by_frame, axis=0)
    mean_magnitude = np.mean(magnitude, axis=0)
    rolloff_85 = _rolloff_frequency(frequencies, mean_power, 0.85)
    rolloff_95 = _rolloff_frequency(frequencies, mean_power, 0.95)

    normalized_power = power_by_frame / (np.sum(power_by_frame, axis=1, keepdims=True) + EPSILON)
    flux_values = np.sqrt(np.sum(np.diff(normalized_power, axis=0) ** 2, axis=1))
    flux_mean = float(np.mean(flux_values)) if flux_values.size else 0.0

    dominant_index = int(np.argmax(mean_power)) if mean_power.size else 0
    dominant_frequency = float(frequencies[dominant_index]) if frequencies.size else 0.0
    dominant_power = float(mean_power[dominant_index]) if mean_power.size else 0.0
    energy_bands = _band_energy_ratios(frequencies, mean_power, config)
    band_energy_entropy = _entropy(np.asarray(list(energy_bands.values()), dtype=float))

    total_power = float(np.sum(mean_power))
    psd_summary = {
        "total_power": _safe_float(total_power),
        "mean_power": _safe_float(float(np.mean(mean_power))) if mean_power.size else 0.0,
        "max_power": _safe_float(dominant_power),
        "max_power_frequency": _safe_float(dominant_frequency),
    }

    return {
        "spectral_centroid_mean": _safe_float(float(np.mean(centroid))) if centroid.size else 0.0,
        "spectral_centroid_std": _safe_float(float(np.std(centroid))) if centroid.size else 0.0,
        "spectral_bandwidth_mean": _safe_float(float(np.mean(bandwidth))) if bandwidth.size else 0.0,
        "spectral_bandwidth_std": _safe_float(float(np.std(bandwidth))) if bandwidth.size else 0.0,
        "spectral_rolloff_85_mean": rolloff_85,
        "spectral_rolloff_95_mean": rolloff_95,
        "spectral_flatness_mean": _safe_float(float(np.mean(flatness))) if flatness.size else 0.0,
        "spectral_contrast_mean": _spectral_contrast_mean(frequencies, mean_magnitude, config),
        "spectral_flux_mean": _safe_float(float(flux_mean)),
        "dominant_frequency": _safe_float(dominant_frequency),
        "dominant_power": _safe_float(dominant_power),
        "low_band_energy_ratio": energy_bands.get("low", 0.0),
        "mid_band_energy_ratio": energy_bands.get("mid", 0.0),
        "high_band_energy_ratio": energy_bands.get("high", 0.0),
        "energy_bands": energy_bands,
        "band_energy_entropy": band_energy_entropy,
        "power_spectral_density_summary": psd_summary,
    }


def compute_frame_spectral_features(
    frames: list[np.ndarray],
    *,
    sample_rate: int,
    config: SpectralConfig,
) -> list[dict[str, object]]:
    return [
        {
            "frame_index": index,
            "spectral_features": compute_spectral_features(frame, sample_rate=sample_rate, config=config),
        }
        for index, frame in enumerate(frames)
    ]


def aggregate_frame_spectral_features(
    frame_spectral_features: list[dict[str, object]],
    *,
    frame_durations: list[float],
) -> dict[str, object]:
    if not frame_spectral_features:
        return {}

    durations = np.asarray(frame_durations, dtype=float)
    if float(np.sum(durations)) <= EPSILON:
        durations = np.ones(len(frame_spectral_features), dtype=float)
    weights = durations / np.sum(durations)
    features = [frame["spectral_features"] for frame in frame_spectral_features]

    def weighted(key: str) -> float:
        values = np.asarray([float(feature.get(key, 0.0)) for feature in features], dtype=float)
        return _safe_float(float(np.sum(values * weights)))

    dominant_index = int(
        np.argmax([float(feature.get("dominant_power", 0.0)) for feature in features])
    )
    band_names = tuple(features[0].get("energy_bands", {}).keys())
    energy_bands = {
        name: _safe_float(
            float(np.sum([float(feature.get("energy_bands", {}).get(name, 0.0)) * weight for feature, weight in zip(features, weights)]))
        )
        for name in band_names
    }
    band_total = sum(energy_bands.values())
    if band_total > EPSILON:
        energy_bands = {name: _safe_float(value / band_total) for name, value in energy_bands.items()}

    psd_total_power = _safe_float(
        float(np.sum([float(feature["power_spectral_density_summary"]["total_power"]) * weight for feature, weight in zip(features, weights)]))
    )
    psd_mean_power = _safe_float(
        float(np.sum([float(feature["power_spectral_density_summary"]["mean_power"]) * weight for feature, weight in zip(features, weights)]))
    )
    dominant_feature = features[dominant_index]

    return {
        "spectral_centroid_mean": weighted("spectral_centroid_mean"),
        "spectral_centroid_std": weighted("spectral_centroid_std"),
        "spectral_bandwidth_mean": weighted("spectral_bandwidth_mean"),
        "spectral_bandwidth_std": weighted("spectral_bandwidth_std"),
        "spectral_rolloff_85_mean": weighted("spectral_rolloff_85_mean"),
        "spectral_rolloff_95_mean": weighted("spectral_rolloff_95_mean"),
        "spectral_flatness_mean": weighted("spectral_flatness_mean"),
        "spectral_contrast_mean": weighted("spectral_contrast_mean"),
        "spectral_flux_mean": weighted("spectral_flux_mean"),
        "dominant_frequency": _safe_float(float(dominant_feature.get("dominant_frequency", 0.0))),
        "low_band_energy_ratio": energy_bands.get("low", 0.0),
        "mid_band_energy_ratio": energy_bands.get("mid", 0.0),
        "high_band_energy_ratio": energy_bands.get("high", 0.0),
        "energy_bands": energy_bands,
        "band_energy_entropy": _entropy(np.asarray(list(energy_bands.values()), dtype=float)),
        "power_spectral_density_summary": {
            "total_power": psd_total_power,
            "mean_power": psd_mean_power,
            "max_power": _safe_float(float(dominant_feature["power_spectral_density_summary"]["max_power"])),
            "max_power_frequency": _safe_float(
                float(dominant_feature["power_spectral_density_summary"]["max_power_frequency"])
            ),
        },
    }
