from __future__ import annotations

import json
from dataclasses import replace
from io import BytesIO

import numpy as np
import soundfile as sf

from app.analysis_engine.config import DEFAULT_CONFIG
from app.analysis_engine.orchestrator import run_analysis_engine
from app.analysis_engine.stage5_timefreq import compute_time_frequency_summary


def _sine_wave(duration_seconds: float = 5.0, sample_rate: int = 16_000) -> np.ndarray:
    times = np.linspace(0, duration_seconds, int(sample_rate * duration_seconds), endpoint=False)
    return (0.25 * np.sin(2 * np.pi * 440 * times)).astype(np.float32)


def _audio_bytes(waveform: np.ndarray, sample_rate: int = 16_000) -> bytes:
    buffer = BytesIO()
    sf.write(buffer, waveform.astype(np.float32), sample_rate, format="WAV")
    return buffer.getvalue()


def test_disabled_by_default() -> None:
    summary = compute_time_frequency_summary(
        _sine_wave(),
        sample_rate=16_000,
        config=DEFAULT_CONFIG.time_frequency,
    )

    assert summary["enabled"] is False
    assert summary["status"] == "skipped"


def test_compact_output_and_no_large_arrays() -> None:
    config = replace(
        DEFAULT_CONFIG.time_frequency,
        enabled=True,
        max_scales=16,
        reduced_bins=4,
    )
    summary = compute_time_frequency_summary(_sine_wave(), sample_rate=16_000, config=config)

    assert summary["enabled"] is True
    assert summary["status"] == "success"
    assert summary["num_scales"] == 16
    assert len(summary["scale_energy_distribution_reduced"]) == 4
    assert all(not isinstance(value, list) for key, value in summary.items() if key != "scale_energy_distribution_reduced")


def test_failure_handled_as_partial_success() -> None:
    config = replace(
        DEFAULT_CONFIG,
        time_frequency=replace(DEFAULT_CONFIG.time_frequency, enabled=True, max_scales=0),
    )
    payload = run_analysis_engine(
        audio_input=_audio_bytes(_sine_wave()),
        original_format=".wav",
        filename="bad-timefreq.wav",
        config=config,
    )

    assert payload["status"] == "partial_success"
    assert payload["time_frequency_summary"]["status"] == "failed"
    assert payload["errors"][0]["stage"] == "stage5_timefreq"


def test_json_serialization() -> None:
    config = replace(
        DEFAULT_CONFIG,
        time_frequency=replace(DEFAULT_CONFIG.time_frequency, enabled=True, max_scales=8, reduced_bins=4),
    )
    payload = run_analysis_engine(
        audio_input=_audio_bytes(_sine_wave(duration_seconds=5.0)),
        original_format=".wav",
        filename="timefreq.wav",
        config=config,
    )

    assert payload["time_frequency_summary"]["enabled"] is True
    json.dumps(payload)
