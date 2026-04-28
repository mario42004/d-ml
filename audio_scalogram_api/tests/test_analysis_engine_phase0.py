from __future__ import annotations

import json
from io import BytesIO

import numpy as np
import soundfile as sf

from app.analysis_engine.audio_io import load_and_normalize_audio
from app.analysis_engine.config import DEFAULT_CONFIG
from app.analysis_engine.framing import split_frames
from app.analysis_engine.orchestrator import run_analysis_engine
from app.analysis_engine.validation import validate_audio_extension


def _wav_bytes(duration_seconds: float = 1.2, sample_rate: int = 8_000, amplitude: float = 0.2) -> bytes:
    times = np.linspace(0, duration_seconds, int(sample_rate * duration_seconds), endpoint=False)
    waveform = (amplitude * np.sin(2 * np.pi * 440 * times)).astype(np.float32)
    buffer = BytesIO()
    sf.write(buffer, waveform, sample_rate, format="WAV")
    return buffer.getvalue()


def test_accepts_configured_formats() -> None:
    for extension in DEFAULT_CONFIG.audio.accepted_extensions:
        validate_audio_extension(extension, DEFAULT_CONFIG.audio)


def test_rejects_unsupported_formats() -> None:
    try:
        validate_audio_extension(".txt", DEFAULT_CONFIG.audio)
    except ValueError as exc:
        assert "Unsupported audio format" in str(exc)
    else:
        raise AssertionError("Unsupported extension should raise ValueError")


def test_normalization_output_dtype() -> None:
    loaded = load_and_normalize_audio(
        _wav_bytes(),
        original_format=".wav",
        config=DEFAULT_CONFIG.audio,
    )

    assert loaded.waveform.dtype == np.float32
    assert loaded.internal_sample_rate == 16_000
    assert loaded.channels_original == 1


def test_frame_splitting() -> None:
    loaded = load_and_normalize_audio(
        _wav_bytes(duration_seconds=12.0),
        original_format=".wav",
        config=DEFAULT_CONFIG.audio,
    )
    frames, plan = split_frames(loaded.waveform, loaded.internal_sample_rate, DEFAULT_CONFIG.framing)

    assert plan.frame_duration_seconds == 5.0
    assert plan.hop_duration_seconds == 5.0
    assert plan.frame_count == len(frames)
    assert len(frames) == 3
    assert len(frames[-1]) == 2 * loaded.internal_sample_rate


def test_rejects_audio_longer_than_twenty_seconds() -> None:
    payload = run_analysis_engine(
        audio_input=_wav_bytes(duration_seconds=21.0),
        original_format=".wav",
        filename="too-long.wav",
    )

    assert payload["status"] == "failed"
    assert "Max duration is 20" in payload["errors"][0]["message"]


def test_quality_flags_and_json_serializability() -> None:
    payload = run_analysis_engine(
        audio_input=_wav_bytes(amplitude=0.25),
        original_format=".wav",
        filename="sample.wav",
    )

    assert payload["status"] == "success"
    assert payload["quality"]["quality_flag"] == "good"
    json.dumps(payload)
