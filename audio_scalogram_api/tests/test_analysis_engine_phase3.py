from __future__ import annotations

import json
from io import BytesIO

import numpy as np
import soundfile as sf

from app.analysis_engine.config import DEFAULT_CONFIG
from app.analysis_engine.orchestrator import run_analysis_engine
from app.analysis_engine.stage3_spectral import compute_spectral_features


def _wav_bytes(waveform: np.ndarray, sample_rate: int = 16_000) -> bytes:
    buffer = BytesIO()
    sf.write(buffer, waveform.astype(np.float32), sample_rate, format="WAV")
    return buffer.getvalue()


def _sine_wave(frequency: float, duration_seconds: float = 5.0, sample_rate: int = 16_000) -> np.ndarray:
    times = np.linspace(0, duration_seconds, int(sample_rate * duration_seconds), endpoint=False)
    return (0.25 * np.sin(2 * np.pi * frequency * times)).astype(np.float32)


def test_sinusoidal_signal_known_dominant_frequency() -> None:
    features = compute_spectral_features(
        _sine_wave(440.0),
        sample_rate=16_000,
        config=DEFAULT_CONFIG.spectral,
    )

    assert abs(features["dominant_frequency"] - 440.0) <= 20.0


def test_broadband_noise_has_high_band_energy() -> None:
    rng = np.random.default_rng(42)
    noise = rng.normal(0, 0.1, 16_000).astype(np.float32)
    features = compute_spectral_features(noise, sample_rate=16_000, config=DEFAULT_CONFIG.spectral)

    assert features["spectral_flatness_mean"] > 0.1
    assert features["high_band_energy_ratio"] > 0.1


def test_silent_audio_is_safe() -> None:
    features = compute_spectral_features(
        np.zeros(16_000, dtype=np.float32),
        sample_rate=16_000,
        config=DEFAULT_CONFIG.spectral,
    )

    assert features["dominant_frequency"] == 0.0
    assert features["band_energy_entropy"] == 0.0
    assert features["power_spectral_density_summary"]["total_power"] == 0.0


def test_band_energy_ratios_sum_to_one_for_active_audio() -> None:
    features = compute_spectral_features(
        _sine_wave(440.0),
        sample_rate=16_000,
        config=DEFAULT_CONFIG.spectral,
    )
    total = sum(features["energy_bands"].values())

    assert abs(total - 1.0) <= 0.01


def test_orchestrator_spectral_summary_is_global_and_json_serializable() -> None:
    payload = run_analysis_engine(
        audio_input=_wav_bytes(_sine_wave(440.0, duration_seconds=12.0)),
        original_format=".wav",
        filename="spectral.wav",
    )

    assert payload["status"] == "success"
    assert payload["frame_features"] == []
    assert abs(payload["spectral_summary"]["dominant_frequency"] - 440.0) <= 20.0
    assert "power_spectral_density_summary" in payload["spectral_summary"]
    json.dumps(payload)
