from __future__ import annotations

from app.analysis_engine.audio_io import load_and_normalize_audio
from app.analysis_engine.config import AnalysisEngineConfig, DEFAULT_CONFIG
from app.analysis_engine.framing import split_frames
from app.analysis_engine.serialization import to_jsonable
from app.analysis_engine.stage0_quality import compute_quality_metrics
from app.analysis_engine.stage1_basic import (
    aggregate_frame_basic_features,
    build_dashboard_ready,
    compute_frame_basic_features,
)
from app.analysis_engine.stage2_temporal import compute_temporal_summary
from app.analysis_engine.stage3_spectral import (
    aggregate_frame_spectral_features,
    compute_frame_spectral_features,
)
from app.analysis_engine.stage4_cepstral import (
    aggregate_frame_cepstral_features,
    compute_frame_cepstral_features,
)
from app.analysis_engine.stage5_timefreq import compute_time_frequency_summary
from app.analysis_engine.validation import normalize_extension, validate_audio_extension


def _empty_result(config: AnalysisEngineConfig, *, status: str = "success") -> dict[str, object]:
    return {
        "version": config.version,
        "status": status,
        "mode": config.mode,
        "input_audio": {},
        "framing": {},
        "quality": {},
        "global_features": {},
        "frame_features": [],
        "temporal_summary": {},
        "spectral_summary": {},
        "cepstral_summary": {},
        "time_frequency_summary": {},
        "ml_ready": {},
        "dashboard_ready": {},
        "exports": {},
        "errors": [],
    }


def run_analysis_engine(
    *,
    audio_input: bytes,
    sample_rate: int | None = None,
    original_format: str | None = None,
    filename: str | None = None,
    config: AnalysisEngineConfig | None = None,
) -> dict[str, object]:
    engine_config = config or DEFAULT_CONFIG
    result = _empty_result(engine_config)

    try:
        extension = normalize_extension(original_format, filename)
        validate_audio_extension(extension, engine_config.audio)

        loaded_audio = load_and_normalize_audio(
            audio_input,
            original_format=extension,
            config=engine_config.audio,
        )
        frames, frame_plan = split_frames(
            loaded_audio.waveform,
            loaded_audio.internal_sample_rate,
            engine_config.framing,
        )
        quality = compute_quality_metrics(
            loaded_audio,
            max_duration_seconds=engine_config.audio.max_audio_duration_seconds,
        )

        result["input_audio"] = {
            "original_format": loaded_audio.original_format,
            "internal_sample_rate": loaded_audio.internal_sample_rate,
            "channels": 1,
            "channels_original": loaded_audio.channels_original,
            "duration_seconds": loaded_audio.duration_seconds,
            "normalization_applied": loaded_audio.normalization_applied,
            "requested_sample_rate": sample_rate,
        }
        result["framing"] = frame_plan
        result["quality"] = quality
        internal_frame_features = compute_frame_basic_features(
            frames,
            sample_rate=loaded_audio.internal_sample_rate,
            hop_length_samples=frame_plan.hop_length_samples,
        )
        result["global_features"] = {
            "duration_seconds": loaded_audio.duration_seconds,
            "sample_count": int(loaded_audio.waveform.size),
            "basic_features": aggregate_frame_basic_features(internal_frame_features),
        }
        internal_spectral_features = compute_frame_spectral_features(
            frames,
            sample_rate=loaded_audio.internal_sample_rate,
            config=engine_config.spectral,
        )
        frame_durations = [
            float(frame["end_time"]) - float(frame["start_time"])
            for frame in internal_frame_features
        ]
        result["spectral_summary"] = aggregate_frame_spectral_features(
            internal_spectral_features,
            frame_durations=frame_durations,
        )
        internal_cepstral_features = compute_frame_cepstral_features(
            frames,
            sample_rate=loaded_audio.internal_sample_rate,
            config=engine_config.cepstral,
        )
        result["cepstral_summary"] = aggregate_frame_cepstral_features(
            internal_cepstral_features,
            frame_durations=frame_durations,
            config=engine_config.cepstral,
        )
        try:
            result["time_frequency_summary"] = compute_time_frequency_summary(
                loaded_audio.waveform,
                sample_rate=loaded_audio.internal_sample_rate,
                config=engine_config.time_frequency,
            )
        except Exception as exc:
            result["status"] = "partial_success"
            result["time_frequency_summary"] = {
                "enabled": engine_config.time_frequency.enabled,
                "status": "failed",
            }
            result["errors"].append({"stage": "stage5_timefreq", "message": str(exc)})
        if engine_config.framing.expose_frame_features:
            for frame_feature, spectral_feature, cepstral_feature in zip(
                internal_frame_features,
                internal_spectral_features,
                internal_cepstral_features,
            ):
                frame_feature["spectral_features"] = spectral_feature["spectral_features"]
                frame_feature["cepstral_features"] = cepstral_feature["cepstral_features"]
        result["frame_features"] = internal_frame_features if engine_config.framing.expose_frame_features else []
        result["temporal_summary"] = compute_temporal_summary(
            internal_frame_features,
            config=engine_config.temporal,
        )
        if not engine_config.framing.expose_frame_features:
            result["temporal_summary"].pop("rms_trend_reduced", None)
            result["temporal_summary"].pop("energy_trend_reduced", None)
            result["temporal_summary"].pop("peak_frame_indices", None)
        result["dashboard_ready"] = {
            "summary": {
                "rms_mean": result["global_features"]["basic_features"].get("rms_mean", 0.0),
                "short_time_energy_mean": result["global_features"]["basic_features"].get(
                    "short_time_energy_mean", 0.0
                ),
                "active_duration_seconds": result["global_features"]["basic_features"].get(
                    "active_duration_seconds", 0.0
                ),
                "stability_index": result["temporal_summary"].get("stability_index", 0.0),
                "variability_index": result["temporal_summary"].get("variability_index", 0.0),
                "dominant_frequency": result["spectral_summary"].get("dominant_frequency", 0.0),
                "spectral_centroid_mean": result["spectral_summary"].get("spectral_centroid_mean", 0.0),
                "mfcc_1_mean": (
                    result["cepstral_summary"].get("mfcc_mean", [0.0])[0]
                    if result["cepstral_summary"].get("mfcc_mean")
                    else 0.0
                ),
            }
        }
        if engine_config.framing.expose_frame_features:
            result["dashboard_ready"].update(build_dashboard_ready(internal_frame_features))
    except Exception as exc:
        result["status"] = "failed"
        result["errors"] = [{"stage": "stage0_quality", "message": str(exc)}]

    return to_jsonable(result)
