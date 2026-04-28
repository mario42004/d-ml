from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.analysis_engine.config import FramingConfig


@dataclass(frozen=True)
class FramePlan:
    enabled: bool
    frame_duration_seconds: float
    hop_duration_seconds: float
    frame_length_samples: int
    hop_length_samples: int
    frame_count: int
    max_frames: int
    include_partial_last_frame: bool
    exposed_in_response: bool


def select_frame_timing(duration_seconds: float, config: FramingConfig) -> tuple[float, float]:
    if not config.auto_frame_duration:
        return config.frame_duration_seconds, config.hop_duration_seconds
    if duration_seconds <= 15:
        return 1.0, 0.5
    if duration_seconds <= 60:
        return 2.0, 1.0
    return 3.0, 1.5


def split_frames(waveform: np.ndarray, sample_rate: int, config: FramingConfig) -> tuple[list[np.ndarray], FramePlan]:
    if not config.enabled:
        plan = FramePlan(False, 0.0, 0.0, 0, 0, 0, config.max_frames, False, False)
        return [], plan

    duration_seconds = float(len(waveform) / sample_rate) if sample_rate else 0.0
    frame_seconds, hop_seconds = select_frame_timing(duration_seconds, config)
    frame_seconds = min(max(frame_seconds, config.min_frame_duration_seconds), config.max_frame_duration_seconds)
    hop_seconds = min(hop_seconds, frame_seconds) if config.allow_overlap else frame_seconds

    frame_length = max(1, int(round(frame_seconds * sample_rate)))
    hop_length = max(1, int(round(hop_seconds * sample_rate)))

    frames: list[np.ndarray] = []
    if len(waveform) <= frame_length:
        frames.append(waveform.astype(np.float32, copy=False))
    else:
        for start in range(0, len(waveform), hop_length):
            frame = waveform[start : start + frame_length]
            if frame.size < frame_length and not config.include_partial_last_frame:
                break
            if frame.size == 0:
                break
            frames.append(frame.astype(np.float32, copy=False))
            if len(frames) >= config.max_frames:
                break

    plan = FramePlan(
        enabled=True,
        frame_duration_seconds=float(frame_seconds),
        hop_duration_seconds=float(hop_seconds),
        frame_length_samples=int(frame_length),
        hop_length_samples=int(hop_length),
        frame_count=len(frames),
        max_frames=config.max_frames,
        include_partial_last_frame=config.include_partial_last_frame,
        exposed_in_response=config.expose_frame_features,
    )
    return frames, plan
