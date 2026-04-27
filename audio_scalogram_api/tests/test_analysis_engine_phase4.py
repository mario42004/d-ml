from __future__ import annotations

import json
from dataclasses import replace
from io import BytesIO

import numpy as np
import soundfile as sf

from app.analysis_engine.config import DEFAULT_CONFIG, AnalysisEngineConfig
from app.analysis_engine.orchestrator import run_analysis_engine
from app.analysis_engine.stage4_cepstral import compute_cepstral_features


def _sine_wave(duration_seconds: float = 5.0, sample_rate: int = 16_000) -> np.ndarray:
    times = np.linspace(0, duration_seconds, int(sample_rate * duration_seconds), endpoint=False)
    return (0.25 * np.sin(2 * np.pi * 440 * times)).astype(np.float32)


def _wav_bytes(waveform: np.ndarray, sample_rate: int = 16_000) -> bytes:
    buffer = BytesIO()
    sf.write(buffer, waveform.astype(np.float32), sample_rate, format="WAV")
    return buffer.getvalue()


def test_mfcc_output_length() -> None:
    features = compute_cepstral_features(
        _sine_wave(),
        sample_rate=16_000,
        config=DEFAULT_CONFIG.cepstral,
    )

    assert len(features["mfcc_mean"]) == 13
    assert len(features["mfcc_std"]) == 13
    assert features["num_mfcc"] == 13


def test_voice_features_disabled_by_default() -> None:
    features = compute_cepstral_features(
        _sine_wave(),
        sample_rate=16_000,
        config=DEFAULT_CONFIG.cepstral,
    )

    assert features["voice_features_enabled"] is False
    assert "voice_features" not in features


def test_short_audio_is_safe() -> None:
    features = compute_cepstral_features(
        _sine_wave(duration_seconds=0.2),
        sample_rate=16_000,
        config=DEFAULT_CONFIG.cepstral,
    )

    assert len(features["mfcc_mean"]) == 13
    assert "spectral_envelope_summary" in features


def test_silent_audio_is_safe() -> None:
    features = compute_cepstral_features(
        np.zeros(16_000, dtype=np.float32),
        sample_rate=16_000,
        config=DEFAULT_CONFIG.cepstral,
    )

    assert features["mfcc_mean"] == [0.0] * 13
    assert features["mfcc_std"] == [0.0] * 13


def test_stable_feature_names_and_json_serialization() -> None:
    payload = run_analysis_engine(
        audio_input=_wav_bytes(_sine_wave(duration_seconds=12.0)),
        original_format=".wav",
        filename="cepstral.wav",
    )

    summary = payload["cepstral_summary"]
    assert set(summary) == {
        "mfcc_mean",
        "mfcc_std",
        "delta_mfcc_mean",
        "delta_mfcc_std",
        "num_mfcc",
        "voice_features_enabled",
        "spectral_envelope_summary",
    }
    assert payload["frame_features"] == []
    json.dumps(payload)


def test_voice_features_can_be_enabled_and_marked_as_proxies() -> None:
    config = replace(
        DEFAULT_CONFIG,
        cepstral=replace(DEFAULT_CONFIG.cepstral, voice_features_enabled=True),
    )
    payload = run_analysis_engine(
        audio_input=_wav_bytes(_sine_wave(duration_seconds=5.0)),
        original_format=".wav",
        filename="voice.wav",
        config=config,
    )

    voice = payload["cepstral_summary"]["voice_features"]
    assert payload["cepstral_summary"]["voice_features_enabled"] is True
    assert "jitter_proxy" in voice
    assert "shimmer_proxy" in voice
    assert "proxy_notice" in voice
