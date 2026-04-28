from app.routers.scalogram import build_coherent_metrics


def test_coherent_metrics_prefers_engine_context() -> None:
    legacy_payload = {
        "audio_metadata": {
            "sample_rate": 22050,
            "original_sample_rate": 24000,
            "duration_seconds": 2.0,
        },
        "autocorrelation_analysis": {
            "peak_count": 2,
            "strongest_peak_lag_seconds": 0.01,
            "second_peak_lag_seconds": 0.02,
            "peak_distance_seconds": 0.01,
            "peak_distance_samples": 160,
        },
    }
    engine_payload = {
        "input_audio": {
            "duration_seconds": 2.0,
            "internal_sample_rate": 16000,
            "channels_original": 1,
        },
        "framing": {
            "frame_count": 1,
            "frame_duration_seconds": 5,
        },
        "quality": {
            "valid_audio": True,
            "quality_flag": "good",
            "duration_seconds": 2.0,
            "sample_rate_original": 24000,
            "sample_rate_internal": 16000,
            "channels_original": 1,
            "silence_ratio": 0.1,
            "clipping_ratio": 0.0,
        },
        "global_features": {
            "basic_features": {
                "rms_mean": 0.2,
                "peak_amplitude": 0.4,
            },
        },
        "temporal_summary": {
            "silence_frame_ratio": 0.0,
            "stability_index": 1.0,
        },
        "spectral_summary": {
            "dominant_frequency": 390.625,
            "spectral_flatness_mean": 0.2,
        },
        "cepstral_summary": {
            "mfcc_mean": [1.0, 2.0],
        },
        "time_frequency_summary": {
            "enabled": False,
            "status": "skipped",
        },
    }

    metrics = build_coherent_metrics(
        legacy_payload=legacy_payload,
        engine_payload=engine_payload,
    )

    assert metrics["schema_version"] == "1.0"
    assert metrics["policy"] == "canonical_analysis_engine_first"
    assert metrics["measurement_context"]["sample_rate_analysis_hz"] == 16000
    assert metrics["measurement_context"]["sample_rate_original_hz"] == 24000

    rows = [
        metric
        for group in metrics["groups"]
        for metric in group["metrics"]
    ]
    by_key = {metric["key"]: metric for metric in rows}

    assert by_key["sample_rate_analysis_hz"]["source"] == "analysis_engine.input_audio.internal_sample_rate"
    assert by_key["sample_rate_original_hz"]["source"] == "analysis_engine.quality.sample_rate_original"
    assert by_key["silence_sample_ratio"]["source"] == "analysis_engine.quality.silence_ratio"
    assert by_key["silence_frame_ratio"]["source"] == "analysis_engine.temporal_summary.silence_frame_ratio"
    assert by_key["peak_distance_seconds"]["source"] == "autocorrelation_analysis.peak_distance_seconds"
