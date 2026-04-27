from __future__ import annotations

from pathlib import Path

from app.analysis_engine.config import AudioEngineConfig


def normalize_extension(original_format: str | None = None, filename: str | None = None) -> str:
    if original_format:
        value = original_format.strip().lower()
        if not value.startswith("."):
            value = f".{value}"
        return value

    if filename:
        return Path(filename).suffix.lower()

    return ""


def validate_audio_extension(extension: str, config: AudioEngineConfig) -> None:
    if not extension:
        raise ValueError("Audio format is required.")
    if extension not in config.accepted_extensions:
        accepted = ", ".join(config.accepted_extensions)
        raise ValueError(f"Unsupported audio format '{extension}'. Accepted formats: {accepted}.")


def validate_duration(duration_seconds: float, config: AudioEngineConfig) -> None:
    if duration_seconds < config.min_audio_duration_seconds:
        raise ValueError("Audio is too short for analysis.")
    if duration_seconds > config.max_audio_duration_seconds:
        raise ValueError(
            f"Audio is too long. Max duration is {config.max_audio_duration_seconds:g} seconds."
        )
