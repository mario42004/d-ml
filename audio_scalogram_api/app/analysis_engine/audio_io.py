from __future__ import annotations

from io import BytesIO

import librosa
import numpy as np
import soundfile as sf

from app.analysis_engine.config import AudioEngineConfig
from app.analysis_engine.schemas import LoadedAudio
from app.analysis_engine.validation import validate_duration


def _channel_count(audio: np.ndarray) -> int:
    if audio.ndim == 1:
        return 1
    return int(audio.shape[1])


def _load_audio_bytes(audio_input: bytes) -> tuple[np.ndarray, int, int]:
    try:
        data, sample_rate = sf.read(BytesIO(audio_input), always_2d=False, dtype="float32")
    except Exception:
        data, sample_rate = librosa.load(BytesIO(audio_input), sr=None, mono=False)
        if np.asarray(data).ndim > 1:
            data = np.asarray(data).T
    return np.asarray(data, dtype=np.float32), int(sample_rate), _channel_count(np.asarray(data))


def load_and_normalize_audio(
    audio_input: bytes,
    *,
    original_format: str,
    config: AudioEngineConfig,
) -> LoadedAudio:
    if not audio_input:
        raise ValueError("Audio input is empty.")

    audio, original_sample_rate, channels_original = _load_audio_bytes(audio_input)
    if audio.size == 0:
        raise ValueError("Audio input is empty.")

    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)

    if original_sample_rate != config.target_sample_rate:
        audio = librosa.resample(
            audio,
            orig_sr=original_sample_rate,
            target_sr=config.target_sample_rate,
        ).astype(np.float32, copy=False)

    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    normalization_applied = False
    if config.normalize_amplitude and peak > 1.0:
        audio = (audio / peak).astype(np.float32, copy=False)
        normalization_applied = True

    audio = np.clip(audio, -1.0, 1.0).astype(np.float32, copy=False)
    duration_seconds = float(audio.size / config.target_sample_rate)
    validate_duration(duration_seconds, config)

    return LoadedAudio(
        waveform=audio,
        original_sample_rate=original_sample_rate,
        internal_sample_rate=config.target_sample_rate,
        channels_original=channels_original,
        duration_seconds=duration_seconds,
        normalization_applied=normalization_applied,
        original_format=original_format.lstrip("."),
    )
