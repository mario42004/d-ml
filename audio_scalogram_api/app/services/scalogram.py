from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

import librosa
import matplotlib
import numpy as np
import pywt

from app.core.config import settings


matplotlib.use("Agg")
import matplotlib.pyplot as plt


@dataclass
class ScalogramResult:
    image_bytes: bytes
    sample_rate: int
    duration_seconds: float
    sample_count: int
    width_min: int
    width_max: int
    wavelet: str
    colormap: str


def build_scalogram(
    audio_bytes: bytes,
    *,
    sample_rate: int | None = None,
    wavelet: str | None = None,
    width_min: int | None = None,
    width_max: int | None = None,
    colormap: str | None = None,
) -> ScalogramResult:
    target_sample_rate = sample_rate or settings.default_sample_rate
    selected_wavelet = wavelet or settings.default_wavelet
    selected_width_min = width_min or settings.default_width_min
    selected_width_max = width_max or settings.default_width_max
    selected_colormap = colormap or settings.default_colormap

    if selected_width_min < 1 or selected_width_max <= selected_width_min:
        raise ValueError("Invalid wavelet width range.")

    waveform, effective_sample_rate = librosa.load(
        BytesIO(audio_bytes),
        sr=target_sample_rate,
        mono=True,
    )
    duration_seconds = float(len(waveform) / effective_sample_rate)

    if duration_seconds == 0:
        raise ValueError("Audio file is empty.")

    if duration_seconds > settings.max_audio_duration_seconds:
        raise ValueError(
            f"Audio is too long. Max duration is {settings.max_audio_duration_seconds} seconds."
        )

    widths = np.arange(selected_width_min, selected_width_max + 1)
    coefficients, frequencies = pywt.cwt(
        waveform,
        widths,
        selected_wavelet,
        sampling_period=1 / effective_sample_rate,
    )
    power = np.abs(coefficients)

    figure, axis = plt.subplots(figsize=(12, 5), dpi=160)
    extent = [0, duration_seconds, float(frequencies[-1]), float(frequencies[0])]
    axis.imshow(
        power,
        extent=extent,
        cmap=selected_colormap,
        aspect="auto",
        origin="upper",
    )
    axis.set_title("Scalogram")
    axis.set_xlabel("Time (s)")
    axis.set_ylabel("Frequency (Hz)")
    axis.set_ylim(float(frequencies[-1]), float(frequencies[0]))
    axis.grid(False)
    figure.tight_layout()

    buffer = BytesIO()
    figure.savefig(buffer, format="png", bbox_inches="tight")
    plt.close(figure)

    return ScalogramResult(
        image_bytes=buffer.getvalue(),
        sample_rate=int(effective_sample_rate),
        duration_seconds=duration_seconds,
        sample_count=int(len(waveform)),
        width_min=selected_width_min,
        width_max=selected_width_max,
        wavelet=selected_wavelet,
        colormap=selected_colormap,
    )
