from __future__ import annotations

import librosa
import numpy as np

from app.analysis_engine.config import CepstralConfig

EPSILON = 1e-10


def _safe_float(value: float) -> float:
    if np.isfinite(value):
        return float(value)
    return 0.0


def _zeros(config: CepstralConfig) -> dict[str, object]:
    zeros = [0.0 for _ in range(config.num_mfcc)]
    return {
        "mfcc_mean": zeros,
        "mfcc_std": zeros,
        "delta_mfcc_mean": zeros if config.include_delta else [],
        "delta_mfcc_std": zeros if config.include_delta else [],
        "num_mfcc": config.num_mfcc,
        "voice_features_enabled": config.voice_features_enabled,
        "spectral_envelope_summary": {
            "mean_log_energy": 0.0,
            "std_log_energy": 0.0,
            "min_log_energy": 0.0,
            "max_log_energy": 0.0,
        },
    }


def _safe_n_fft(waveform: np.ndarray, config: CepstralConfig) -> int:
    if waveform.size <= 1:
        return 2
    return min(config.n_fft, int(waveform.size))


def _compute_voice_features(
    waveform: np.ndarray,
    *,
    sample_rate: int,
    config: CepstralConfig,
) -> dict[str, object]:
    if waveform.size < 3 or float(np.max(np.abs(waveform))) <= EPSILON:
        return {
            "estimated_f0_mean": 0.0,
            "estimated_f0_std": 0.0,
            "estimated_f0_min": 0.0,
            "estimated_f0_max": 0.0,
            "voiced_ratio": 0.0,
            "jitter_proxy": 0.0,
            "shimmer_proxy": 0.0,
            "proxy_notice": "jitter_proxy and shimmer_proxy are approximate, non-clinical signal descriptors.",
        }

    try:
        f0 = librosa.yin(
            waveform.astype(np.float32, copy=False),
            fmin=config.voice_fmin_hz,
            fmax=config.voice_fmax_hz,
            sr=sample_rate,
            frame_length=_safe_n_fft(waveform, config),
            hop_length=min(config.hop_length, max(1, waveform.size // 2)),
        )
    except Exception:
        f0 = np.asarray([], dtype=float)

    valid_f0 = f0[np.isfinite(f0)]
    if valid_f0.size == 0:
        f0_mean = f0_std = f0_min = f0_max = voiced_ratio = jitter_proxy = 0.0
    else:
        f0_mean = float(np.mean(valid_f0))
        f0_std = float(np.std(valid_f0))
        f0_min = float(np.min(valid_f0))
        f0_max = float(np.max(valid_f0))
        voiced_ratio = float(valid_f0.size / max(1, f0.size))
        jitter_proxy = (
            float(np.mean(np.abs(np.diff(valid_f0))) / (abs(f0_mean) + EPSILON))
            if valid_f0.size > 1
            else 0.0
        )

    frame_length = _safe_n_fft(waveform, config)
    hop_length = min(config.hop_length, frame_length)
    rms = librosa.feature.rms(
        y=waveform.astype(np.float32, copy=False),
        frame_length=frame_length,
        hop_length=hop_length,
    )[0]
    shimmer_proxy = float(np.std(rms) / (np.mean(rms) + EPSILON)) if rms.size else 0.0

    return {
        "estimated_f0_mean": _safe_float(f0_mean),
        "estimated_f0_std": _safe_float(f0_std),
        "estimated_f0_min": _safe_float(f0_min),
        "estimated_f0_max": _safe_float(f0_max),
        "voiced_ratio": _safe_float(voiced_ratio),
        "jitter_proxy": _safe_float(jitter_proxy),
        "shimmer_proxy": _safe_float(shimmer_proxy),
        "proxy_notice": "jitter_proxy and shimmer_proxy are approximate, non-clinical signal descriptors.",
    }


def compute_cepstral_features(
    waveform: np.ndarray,
    *,
    sample_rate: int,
    config: CepstralConfig,
) -> dict[str, object]:
    signal = waveform.astype(np.float32, copy=False)
    if signal.size == 0 or float(np.max(np.abs(signal))) <= EPSILON:
        result = _zeros(config)
        if config.voice_features_enabled:
            result["voice_features"] = _compute_voice_features(signal, sample_rate=sample_rate, config=config)
        return result

    n_fft = _safe_n_fft(signal, config)
    hop_length = min(config.hop_length, n_fft)
    mfcc = librosa.feature.mfcc(
        y=signal,
        sr=sample_rate,
        n_mfcc=config.num_mfcc,
        n_fft=n_fft,
        hop_length=hop_length,
        n_mels=config.n_mels,
    )
    mfcc_mean = [_safe_float(float(value)) for value in np.mean(mfcc, axis=1)]
    mfcc_std = [_safe_float(float(value)) for value in np.std(mfcc, axis=1)]

    delta_mean: list[float] = []
    delta_std: list[float] = []
    if config.include_delta:
        if mfcc.shape[1] >= 3:
            delta = librosa.feature.delta(mfcc, width=min(9, mfcc.shape[1] if mfcc.shape[1] % 2 else mfcc.shape[1] - 1))
        else:
            delta = np.zeros_like(mfcc)
        delta_mean = [_safe_float(float(value)) for value in np.mean(delta, axis=1)]
        delta_std = [_safe_float(float(value)) for value in np.std(delta, axis=1)]

    mel = librosa.feature.melspectrogram(
        y=signal,
        sr=sample_rate,
        n_fft=n_fft,
        hop_length=hop_length,
        n_mels=config.n_mels,
        power=2.0,
    )
    log_energy = librosa.power_to_db(mel + EPSILON, ref=1.0)

    result: dict[str, object] = {
        "mfcc_mean": mfcc_mean,
        "mfcc_std": mfcc_std,
        "delta_mfcc_mean": delta_mean,
        "delta_mfcc_std": delta_std,
        "num_mfcc": config.num_mfcc,
        "voice_features_enabled": config.voice_features_enabled,
        "spectral_envelope_summary": {
            "mean_log_energy": _safe_float(float(np.mean(log_energy))),
            "std_log_energy": _safe_float(float(np.std(log_energy))),
            "min_log_energy": _safe_float(float(np.min(log_energy))),
            "max_log_energy": _safe_float(float(np.max(log_energy))),
        },
    }

    if config.voice_features_enabled:
        result["voice_features"] = _compute_voice_features(signal, sample_rate=sample_rate, config=config)

    return result


def compute_frame_cepstral_features(
    frames: list[np.ndarray],
    *,
    sample_rate: int,
    config: CepstralConfig,
) -> list[dict[str, object]]:
    return [
        {
            "frame_index": index,
            "cepstral_features": compute_cepstral_features(frame, sample_rate=sample_rate, config=config),
        }
        for index, frame in enumerate(frames)
    ]


def aggregate_frame_cepstral_features(
    frame_cepstral_features: list[dict[str, object]],
    *,
    frame_durations: list[float],
    config: CepstralConfig,
) -> dict[str, object]:
    if not frame_cepstral_features:
        return _zeros(config)

    durations = np.asarray(frame_durations, dtype=float)
    if float(np.sum(durations)) <= EPSILON:
        durations = np.ones(len(frame_cepstral_features), dtype=float)
    weights = durations / np.sum(durations)
    features = [frame["cepstral_features"] for frame in frame_cepstral_features]

    def weighted_vector(key: str) -> list[float]:
        values = np.asarray([feature.get(key, [0.0] * config.num_mfcc) for feature in features], dtype=float)
        if values.size == 0:
            return [0.0 for _ in range(config.num_mfcc)]
        return [_safe_float(float(value)) for value in np.sum(values * weights.reshape(-1, 1), axis=0)]

    def weighted_scalar(path: tuple[str, str]) -> float:
        values = np.asarray([float(feature[path[0]][path[1]]) for feature in features], dtype=float)
        return _safe_float(float(np.sum(values * weights)))

    result: dict[str, object] = {
        "mfcc_mean": weighted_vector("mfcc_mean"),
        "mfcc_std": weighted_vector("mfcc_std"),
        "delta_mfcc_mean": weighted_vector("delta_mfcc_mean") if config.include_delta else [],
        "delta_mfcc_std": weighted_vector("delta_mfcc_std") if config.include_delta else [],
        "num_mfcc": config.num_mfcc,
        "voice_features_enabled": config.voice_features_enabled,
        "spectral_envelope_summary": {
            "mean_log_energy": weighted_scalar(("spectral_envelope_summary", "mean_log_energy")),
            "std_log_energy": weighted_scalar(("spectral_envelope_summary", "std_log_energy")),
            "min_log_energy": _safe_float(
                float(min(feature["spectral_envelope_summary"]["min_log_energy"] for feature in features))
            ),
            "max_log_energy": _safe_float(
                float(max(feature["spectral_envelope_summary"]["max_log_energy"] for feature in features))
            ),
        },
    }

    if config.voice_features_enabled:
        voice_keys = (
            "estimated_f0_mean",
            "estimated_f0_std",
            "estimated_f0_min",
            "estimated_f0_max",
            "voiced_ratio",
            "jitter_proxy",
            "shimmer_proxy",
        )
        result["voice_features"] = {
            key: _safe_float(
                float(
                    np.sum(
                        [
                            float(feature.get("voice_features", {}).get(key, 0.0)) * weight
                            for feature, weight in zip(features, weights)
                        ]
                    )
                )
            )
            for key in voice_keys
        }
        result["voice_features"]["proxy_notice"] = (
            "jitter_proxy and shimmer_proxy are approximate, non-clinical signal descriptors."
        )

    return result
