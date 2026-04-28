from types import SimpleNamespace

from app.routers.scalogram import build_json_payload, build_metricas


def test_metricas_exposes_rich_canonical_features_without_metadata() -> None:
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
            "active_ratio": 0.9,
            "clipping_ratio": 0.0,
            "snr_estimate": 42.0,
        },
        "global_features": {
            "basic_features": {
                "rms_mean": 0.2,
                "short_time_energy_mean": 0.04,
                "zero_crossing_rate_mean": 0.03,
                "peak_amplitude": 0.4,
                "energy_entropy": 0.8,
            },
        },
        "temporal_summary": {
            "silence_frame_ratio": 0.0,
            "stability_index": 1.0,
        },
        "spectral_summary": {
            "dominant_frequency": 390.625,
            "spectral_flatness_mean": 0.2,
            "spectral_contrast_mean": 12.5,
            "power_spectral_density_summary": {
                "total_power": 2.0,
                "mean_power": 0.2,
                "max_power": 1.0,
                "max_power_frequency": 390.625,
            },
        },
        "cepstral_summary": {
            "mfcc_mean": [1.0, 2.0],
            "mfcc_std": [0.1, 0.2],
            "delta_mfcc_mean": [0.01, 0.02],
            "delta_mfcc_std": [0.001, 0.002],
            "spectral_envelope_summary": {
                "mean_log_energy": -12.0,
                "std_log_energy": 2.0,
                "min_log_energy": -20.0,
                "max_log_energy": -5.0,
            },
        },
        "time_frequency_summary": {
            "enabled": False,
            "status": "skipped",
        },
    }

    metricas = build_metricas(
        legacy_payload=legacy_payload,
        engine_payload=engine_payload,
    )

    assert metricas["version_esquema"] == "1.0"
    assert metricas["politica"] == "metricas_canonicas_unificadas"
    assert "contexto_medicion" not in metricas

    rows = [
        metric
        for group in metricas["grupos"]
        for metric in group["metricas"]
    ]
    by_key = {metric["clave"]: metric for metric in rows}

    assert "duration_seconds" not in by_key
    assert "sample_rate_analysis_hz" not in by_key
    assert "sample_rate_original_hz" not in by_key
    assert "channels_original" not in by_key
    assert "frame_count" not in by_key
    assert by_key["silence_sample_ratio"]["fuente"] == "analysis_engine.quality.silence_ratio"
    assert by_key["active_ratio"]["fuente"] == "analysis_engine.quality.active_ratio"
    assert by_key["snr_estimate"]["fuente"] == "analysis_engine.quality.snr_estimate"
    assert by_key["short_time_energy_mean"]["fuente"] == "analysis_engine.global_features.basic_features.short_time_energy_mean"
    assert by_key["zero_crossing_rate_mean"]["fuente"] == "analysis_engine.global_features.basic_features.zero_crossing_rate_mean"
    assert by_key["energy_entropy"]["fuente"] == "analysis_engine.global_features.basic_features.energy_entropy"
    assert by_key["silence_frame_ratio"]["fuente"] == "analysis_engine.temporal_summary.silence_frame_ratio"
    assert by_key["peak_distance_seconds"]["fuente"] == "autocorrelation_analysis.peak_distance_seconds"
    assert by_key["spectral_contrast_mean"]["fuente"] == "analysis_engine.spectral_summary.spectral_contrast_mean"
    assert by_key["psd_total_power"]["fuente"] == "analysis_engine.spectral_summary.power_spectral_density_summary.total_power"
    assert by_key["mfcc_0_mean"]["fuente"] == "analysis_engine.cepstral_summary.mfcc_mean.0"
    assert by_key["delta_mfcc_0_std"]["fuente"] == "analysis_engine.cepstral_summary.delta_mfcc_std.0"
    assert by_key["spectral_envelope_mean_log_energy"]["fuente"] == (
        "analysis_engine.cepstral_summary.spectral_envelope_summary.mean_log_energy"
    )


def test_json_payload_exposes_only_canonical_metricas() -> None:
    result = SimpleNamespace(
        analysis_version="2.1",
        primary_image=SimpleNamespace(key="dashboard", image_bytes=b"png-bytes"),
    )
    legacy_payload = {
        "audio_metadata": {"sample_rate": 22050},
        "temporal_analysis": {"rms": {"mean": 0.1}},
        "spectral_analysis": {"dominant_frequency_hz": 440},
        "plots": {"dashboard": {"title": "Dashboard"}},
    }
    engine_payload = {
        "input_audio": {"duration_seconds": 1.0, "internal_sample_rate": 16000},
        "framing": {"frame_count": 1, "frame_duration_seconds": 5},
        "quality": {"sample_rate_original": 22050, "max_allowed_duration_seconds": 20},
        "global_features": {"basic_features": {"rms_mean": 0.1}},
        "temporal_summary": {},
        "spectral_summary": {"dominant_frequency": 440},
        "cepstral_summary": {},
        "time_frequency_summary": {},
    }

    payload = build_json_payload(
        result=result,
        legacy_payload=legacy_payload,
        analysis_engine_payload=engine_payload,
        filename="sample.wav",
    )

    assert payload["analysis_version"] == "2.1"
    assert payload["primary_visualization"] == "dashboard"
    assert payload["metricas"]["version_esquema"] == "1.0"
    assert payload["plots"] == legacy_payload["plots"]
    assert payload["filename"] == "sample.wav.png"
    assert payload["image_base64"] == "cG5nLWJ5dGVz"
    assert "analysis_engine" not in payload
    assert "audio_metadata" not in payload
    assert "temporal_analysis" not in payload
    assert "spectral_analysis" not in payload
