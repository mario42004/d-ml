from __future__ import annotations

from app.analysis_engine.config import TemporalConfig
from app.analysis_engine.orchestrator import run_analysis_engine
from app.analysis_engine.stage2_temporal import compute_temporal_summary

import numpy as np
import soundfile as sf
from io import BytesIO


def _frames(values: list[float]) -> list[dict[str, object]]:
    return [
        {
            "frame_index": index,
            "start_time": float(index),
            "end_time": float(index + 1),
            "basic_features": {
                "rms_mean": value**0.5,
                "short_time_energy_mean": value,
            },
        }
        for index, value in enumerate(values)
    ]


def _wav_bytes(duration_seconds: float = 12.0, sample_rate: int = 8_000) -> bytes:
    times = np.linspace(0, duration_seconds, int(sample_rate * duration_seconds), endpoint=False)
    envelope = np.linspace(0.1, 0.6, times.size)
    waveform = (envelope * np.sin(2 * np.pi * 440 * times)).astype(np.float32)
    buffer = BytesIO()
    sf.write(buffer, waveform, sample_rate, format="WAV")
    return buffer.getvalue()


def test_increasing_energy_trend() -> None:
    summary = compute_temporal_summary(_frames([0.1, 0.2, 0.4, 0.8]), config=TemporalConfig())
    assert summary["power_slope"] > 0
    assert summary["late_energy_ratio"] > summary["early_energy_ratio"]


def test_decreasing_energy_trend() -> None:
    summary = compute_temporal_summary(_frames([0.8, 0.4, 0.2, 0.1]), config=TemporalConfig())
    assert summary["power_slope"] < 0
    assert summary["early_energy_ratio"] > summary["late_energy_ratio"]


def test_flat_signal() -> None:
    summary = compute_temporal_summary(_frames([0.3, 0.3, 0.3, 0.3]), config=TemporalConfig())
    assert summary["power_slope"] == 0.0
    assert summary["num_energy_peaks"] == 0
    assert summary["stability_index"] == 1.0


def test_silent_signal() -> None:
    summary = compute_temporal_summary(_frames([0.0, 0.0, 0.0]), config=TemporalConfig())
    assert summary["active_frame_ratio"] == 0.0
    assert summary["silence_frame_ratio"] == 1.0
    assert summary["early_energy_ratio"] == 0.0


def test_peak_detection() -> None:
    summary = compute_temporal_summary(_frames([0.1, 1.0, 0.1, 0.8, 0.1]), config=TemporalConfig())
    assert summary["num_energy_peaks"] == 2
    assert summary["peak_frame_indices"] == [1, 3]


def test_trend_length_limits() -> None:
    summary = compute_temporal_summary(
        _frames([float(index) for index in range(20)]),
        config=TemporalConfig(max_trend_points=5),
    )
    assert len(summary["rms_trend_reduced"]) <= 5
    assert len(summary["energy_trend_reduced"]) <= 5


def test_normal_response_keeps_phase2_global_only() -> None:
    payload = run_analysis_engine(
        audio_input=_wav_bytes(),
        original_format=".wav",
        filename="temporal.wav",
    )

    temporal = payload["temporal_summary"]
    assert payload["status"] == "success"
    assert payload["frame_features"] == []
    assert "rms_trend_reduced" not in temporal
    assert "energy_trend_reduced" not in temporal
    assert "peak_frame_indices" not in temporal
    assert "power_slope" in temporal
    assert "stability_index" in temporal
