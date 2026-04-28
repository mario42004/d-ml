from __future__ import annotations

from io import BytesIO

import numpy as np
import soundfile as sf

from app.analysis_engine.orchestrator import run_analysis_engine


def _wav_bytes(duration_seconds: float = 1.2, sample_rate: int = 8_000, amplitude: float = 0.2) -> bytes:
    times = np.linspace(0, duration_seconds, int(sample_rate * duration_seconds), endpoint=False)
    waveform = (amplitude * np.sin(2 * np.pi * 440 * times)).astype(np.float32)
    buffer = BytesIO()
    sf.write(buffer, waveform, sample_rate, format="WAV")
    return buffer.getvalue()


def _silent_wav_bytes(duration_seconds: float = 1.2, sample_rate: int = 8_000) -> bytes:
    waveform = np.zeros(int(sample_rate * duration_seconds), dtype=np.float32)
    buffer = BytesIO()
    sf.write(buffer, waveform, sample_rate, format="WAV")
    return buffer.getvalue()


def test_phase1_normal_audio_global_schema() -> None:
    payload = run_analysis_engine(
        audio_input=_wav_bytes(),
        original_format=".wav",
        filename="normal.wav",
    )

    features = payload["global_features"]["basic_features"]
    assert payload["status"] == "success"
    assert features["rms_mean"] > 0
    assert features["short_time_energy_mean"] > 0
    assert features["peak_count"] > 0
    assert "active_duration_seconds" in features


def test_phase1_silent_audio_is_safe() -> None:
    payload = run_analysis_engine(
        audio_input=_silent_wav_bytes(),
        original_format=".wav",
        filename="silent.wav",
    )

    features = payload["global_features"]["basic_features"]
    assert payload["status"] == "success"
    assert features["rms_mean"] == 0.0
    assert features["energy_entropy"] == 0.0
    assert features["crest_factor"] == 0.0


def test_phase1_short_audio_schema() -> None:
    payload = run_analysis_engine(
        audio_input=_wav_bytes(duration_seconds=0.2),
        original_format=".wav",
        filename="short.wav",
    )

    assert payload["status"] == "success"
    assert payload["framing"]["frame_count"] == 1
    assert payload["frame_features"] == []
    assert payload["global_features"]["basic_features"]["rms_mean"] > 0


def test_phase1_frame_features_are_internal_and_global_features_are_aggregated() -> None:
    payload = run_analysis_engine(
        audio_input=_wav_bytes(duration_seconds=12.0),
        original_format=".wav",
        filename="frames.wav",
    )

    assert payload["framing"]["frame_count"] == 3
    assert payload["frame_features"] == []
    assert "basic_features" in payload["global_features"]
    assert "summary" in payload["dashboard_ready"]
    assert "rms_trend" not in payload["dashboard_ready"]
