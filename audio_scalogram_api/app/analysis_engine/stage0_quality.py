from __future__ import annotations

import numpy as np

from app.analysis_engine.schemas import LoadedAudio

EPSILON = 1e-10


def _quality_flag(
    *,
    duration_seconds: float,
    max_duration_seconds: float,
    clipping_ratio: float,
    silence_ratio: float,
    snr_estimate: float,
) -> str:
    if duration_seconds < 0.1:
        return "too_short"
    if duration_seconds > max_duration_seconds:
        return "too_long"
    if clipping_ratio > 0.01:
        return "clipped"
    if silence_ratio > 0.8:
        return "mostly_silent"
    if snr_estimate < 10:
        return "low_snr"
    return "good"


def compute_quality_metrics(audio: LoadedAudio, *, max_duration_seconds: float) -> dict[str, object]:
    waveform = audio.waveform.astype(float, copy=False)
    envelope = np.abs(waveform)
    peak_amplitude = float(np.max(envelope)) if envelope.size else 0.0
    mean_amplitude = float(np.mean(envelope)) if envelope.size else 0.0
    dc_offset = float(np.mean(waveform)) if waveform.size else 0.0
    clipping_ratio = float(np.mean(envelope >= 0.999)) if envelope.size else 0.0

    silence_threshold = max(peak_amplitude * 0.03, EPSILON)
    silence_mask = envelope < silence_threshold
    silence_ratio = float(np.mean(silence_mask)) if envelope.size else 1.0
    active_ratio = float(1.0 - silence_ratio)

    noise_floor = float(np.percentile(envelope, 10)) if envelope.size else 0.0
    active_level = float(np.percentile(envelope, 90)) if envelope.size else 0.0
    snr_estimate = float(20 * np.log10((active_level + EPSILON) / (noise_floor + EPSILON)))

    quality_flag = _quality_flag(
        duration_seconds=audio.duration_seconds,
        max_duration_seconds=max_duration_seconds,
        clipping_ratio=clipping_ratio,
        silence_ratio=silence_ratio,
        snr_estimate=snr_estimate,
    )

    return {
        "valid_audio": quality_flag not in {"invalid", "too_short", "too_long"},
        "quality_flag": quality_flag,
        "duration_seconds": audio.duration_seconds,
        "sample_rate_original": audio.original_sample_rate,
        "sample_rate_internal": audio.internal_sample_rate,
        "channels_original": audio.channels_original,
        "is_mono_internal": True,
        "clipping_ratio": clipping_ratio,
        "silence_ratio": silence_ratio,
        "active_ratio": active_ratio,
        "estimated_noise_floor": noise_floor,
        "snr_estimate": snr_estimate,
        "peak_amplitude": peak_amplitude,
        "mean_amplitude": mean_amplitude,
        "dc_offset": dc_offset,
    }
