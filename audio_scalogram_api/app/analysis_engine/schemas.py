from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class LoadedAudio:
    waveform: np.ndarray
    original_sample_rate: int
    internal_sample_rate: int
    channels_original: int
    duration_seconds: float
    normalization_applied: bool
    original_format: str
