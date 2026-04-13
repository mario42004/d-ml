from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
from io import BytesIO

import librosa
import matplotlib
import numpy as np
import pywt
from scipy.signal import find_peaks

from app.core.config import settings


matplotlib.use("Agg")
import matplotlib.pyplot as plt


EPSILON = 1e-10
ANALYSIS_FRAME_LENGTH = 2048
ANALYSIS_HOP_LENGTH = 512
ANALYSIS_VERSION = "2.1"


@dataclass
class SummaryStats:
    mean: float
    std: float
    min: float
    max: float
    p05: float
    median: float
    p95: float


@dataclass
class TemporalAnalysis:
    rms: SummaryStats
    zero_crossing_rate: SummaryStats
    amplitude_envelope: SummaryStats
    peak_amplitude: float
    peak_to_peak_amplitude: float
    crest_factor: float
    silence_ratio: float
    dynamic_range_db: float
    dc_offset: float
    clipping_ratio: float


@dataclass
class SpectralPeak:
    rank: int
    frequency_hz: float
    magnitude: float


@dataclass
class SpectralAnalysis:
    centroid_hz: SummaryStats
    bandwidth_hz: SummaryStats
    rolloff_hz: SummaryStats
    flatness: SummaryStats
    contrast_db_by_band: list[float]
    dominant_frequency_hz: float
    dominant_frequency_magnitude: float
    spectral_flux: SummaryStats
    top_spectral_peaks: list[SpectralPeak]


@dataclass
class AutocorrelationAnalysis:
    strongest_peak_lag_samples: int | None
    strongest_peak_lag_seconds: float | None
    strongest_peak_value: float | None
    second_peak_lag_samples: int | None
    second_peak_lag_seconds: float | None
    second_peak_value: float | None
    peak_distance_samples: int | None
    peak_distance_seconds: float | None
    peak_count: int


@dataclass
class AudioMetadata:
    sample_rate: int
    original_sample_rate: int
    duration_seconds: float
    sample_count: int
    channel_count: int
    file_size_bytes: int
    analyzed_frame_length: int
    analyzed_hop_length: int
    nyquist_hz: float


@dataclass
class ScalogramConfig:
    wavelet: str
    width_min: int
    width_max: int
    colormap: str


@dataclass
class PlotImage:
    key: str
    title: str
    description: str
    media_type: str
    image_bytes: bytes

    def as_dict(self) -> dict[str, str]:
        return {
            "title": self.title,
            "description": self.description,
            "media_type": self.media_type,
            "image_base64": base64.b64encode(self.image_bytes).decode("ascii"),
            "encoding": "base64",
        }


@dataclass
class ScalogramResult:
    primary_image: PlotImage
    plots: dict[str, PlotImage]
    metadata: AudioMetadata
    scalogram_config: ScalogramConfig
    temporal_analysis: TemporalAnalysis
    spectral_analysis: SpectralAnalysis
    autocorrelation_analysis: AutocorrelationAnalysis
    analysis_version: str


def _summarize(values: np.ndarray) -> SummaryStats:
    flattened = np.asarray(values, dtype=float).reshape(-1)
    return SummaryStats(
        mean=float(np.mean(flattened)),
        std=float(np.std(flattened)),
        min=float(np.min(flattened)),
        max=float(np.max(flattened)),
        p05=float(np.percentile(flattened, 5)),
        median=float(np.percentile(flattened, 50)),
        p95=float(np.percentile(flattened, 95)),
    )


def _render_figure(figure: plt.Figure) -> bytes:
    buffer = BytesIO()
    figure.tight_layout()
    figure.savefig(buffer, format="png", bbox_inches="tight")
    plt.close(figure)
    return buffer.getvalue()


def _seconds_axis(frame_count: int, sample_rate: int, hop_length: int) -> np.ndarray:
    return librosa.frames_to_time(np.arange(frame_count), sr=sample_rate, hop_length=hop_length)


def _build_scalogram_plot(
    power: np.ndarray,
    frequencies: np.ndarray,
    duration_seconds: float,
    colormap: str,
) -> PlotImage:
    figure, axis = plt.subplots(figsize=(12, 5), dpi=160)
    extent = [0, duration_seconds, float(frequencies[-1]), float(frequencies[0])]
    axis.imshow(
        power,
        extent=extent,
        cmap=colormap,
        aspect="auto",
        origin="upper",
    )
    axis.set_title("Scalogram")
    axis.set_xlabel("Time (s)")
    axis.set_ylabel("Frequency (Hz)")
    axis.set_ylim(float(frequencies[-1]), float(frequencies[0]))
    axis.grid(False)
    return PlotImage(
        key="scalogram",
        title="Scalogram",
        description="Continuous wavelet transform power over time and frequency.",
        media_type="image/png",
        image_bytes=_render_figure(figure),
    )


def _build_waveform_plot(waveform: np.ndarray, sample_rate: int) -> PlotImage:
    times = np.arange(len(waveform)) / sample_rate
    figure, axis = plt.subplots(figsize=(12, 3.5), dpi=160)
    axis.plot(times, waveform, color="#0f766e", linewidth=0.8)
    axis.set_title("Waveform")
    axis.set_xlabel("Time (s)")
    axis.set_ylabel("Amplitude")
    axis.set_xlim(0, times[-1] if len(times) else 0)
    axis.grid(alpha=0.2)
    return PlotImage(
        key="waveform",
        title="Waveform",
        description="Signal amplitude across time, useful for transients and clipping.",
        media_type="image/png",
        image_bytes=_render_figure(figure),
    )


def _build_rms_plot(times: np.ndarray, rms: np.ndarray) -> PlotImage:
    figure, axis = plt.subplots(figsize=(12, 3.5), dpi=160)
    axis.plot(times, rms, color="#b45309", linewidth=1.0)
    axis.fill_between(times, rms, color="#f59e0b", alpha=0.25)
    axis.set_title("Energy Envelope (RMS)")
    axis.set_xlabel("Time (s)")
    axis.set_ylabel("RMS")
    axis.set_xlim(0, times[-1] if len(times) else 0)
    axis.grid(alpha=0.2)
    return PlotImage(
        key="rms_energy",
        title="RMS Energy",
        description="Frame-by-frame energy envelope to detect bursts, fades and silence.",
        media_type="image/png",
        image_bytes=_render_figure(figure),
    )


def _build_spectrum_plot(frequencies: np.ndarray, magnitude: np.ndarray) -> PlotImage:
    figure, axis = plt.subplots(figsize=(12, 3.5), dpi=160)
    axis.plot(frequencies, magnitude, color="#1d4ed8", linewidth=1.0)
    axis.set_title("Average Spectrum")
    axis.set_xlabel("Frequency (Hz)")
    axis.set_ylabel("Magnitude")
    axis.set_xlim(0, float(frequencies[-1]) if len(frequencies) else 0)
    axis.grid(alpha=0.2)
    return PlotImage(
        key="spectrum",
        title="Average Spectrum",
        description="Averaged frequency content, useful to track shifts in dominant bands.",
        media_type="image/png",
        image_bytes=_render_figure(figure),
    )


def _build_mel_plot(mel_db: np.ndarray, sample_rate: int, hop_length: int) -> PlotImage:
    figure, axis = plt.subplots(figsize=(12, 4.5), dpi=160)
    time_axis = _seconds_axis(mel_db.shape[1], sample_rate, hop_length)
    mel_frequencies = librosa.mel_frequencies(n_mels=mel_db.shape[0], fmax=sample_rate / 2)
    mesh = axis.pcolormesh(time_axis, mel_frequencies, mel_db, shading="auto", cmap="magma")
    figure.colorbar(mesh, ax=axis, format="%+2.0f dB")
    axis.set_title("Mel Spectrogram")
    axis.set_xlabel("Time (s)")
    axis.set_ylabel("Frequency (Hz)")
    return PlotImage(
        key="mel_spectrogram",
        title="Mel Spectrogram",
        description="Time-frequency map closer to perceptual energy distribution than a scalogram.",
        media_type="image/png",
        image_bytes=_render_figure(figure),
    )


def _build_dashboard_plot(
    waveform: np.ndarray,
    sample_rate: int,
    rms_times: np.ndarray,
    rms: np.ndarray,
    spectrum_frequencies: np.ndarray,
    average_spectrum: np.ndarray,
    mel_db: np.ndarray,
    hop_length: int,
) -> PlotImage:
    figure, axes = plt.subplots(2, 2, figsize=(14, 8), dpi=160)

    waveform_times = np.arange(len(waveform)) / sample_rate
    axes[0, 0].plot(waveform_times, waveform, color="#0f766e", linewidth=0.7)
    axes[0, 0].set_title("Waveform")
    axes[0, 0].set_xlabel("Time (s)")
    axes[0, 0].set_ylabel("Amplitude")
    axes[0, 0].grid(alpha=0.2)

    axes[0, 1].plot(rms_times, rms, color="#b45309", linewidth=1.0)
    axes[0, 1].fill_between(rms_times, rms, color="#f59e0b", alpha=0.25)
    axes[0, 1].set_title("RMS Energy")
    axes[0, 1].set_xlabel("Time (s)")
    axes[0, 1].set_ylabel("RMS")
    axes[0, 1].grid(alpha=0.2)

    axes[1, 0].plot(spectrum_frequencies, average_spectrum, color="#1d4ed8", linewidth=1.0)
    axes[1, 0].set_title("Average Spectrum")
    axes[1, 0].set_xlabel("Frequency (Hz)")
    axes[1, 0].set_ylabel("Magnitude")
    axes[1, 0].grid(alpha=0.2)

    mel_times = _seconds_axis(mel_db.shape[1], sample_rate, hop_length)
    mel_frequencies = librosa.mel_frequencies(n_mels=mel_db.shape[0], fmax=sample_rate / 2)
    mesh = axes[1, 1].pcolormesh(mel_times, mel_frequencies, mel_db, shading="auto", cmap="magma")
    axes[1, 1].set_title("Mel Spectrogram")
    axes[1, 1].set_xlabel("Time (s)")
    axes[1, 1].set_ylabel("Frequency (Hz)")
    figure.colorbar(mesh, ax=axes[1, 1], format="%+2.0f dB")

    figure.suptitle("Audio Analysis Dashboard", fontsize=16)

    return PlotImage(
        key="dashboard",
        title="Analysis Dashboard",
        description="Combined waveform, energy, average spectrum and mel spectrogram view.",
        media_type="image/png",
        image_bytes=_render_figure(figure),
    )


def _build_autocorrelation_plot(
    lag_seconds: np.ndarray,
    autocorrelation: np.ndarray,
    peak_indices: list[int],
) -> PlotImage:
    figure, axis = plt.subplots(figsize=(12, 3.8), dpi=160)
    axis.plot(lag_seconds, autocorrelation, color="#8b5cf6", linewidth=1.2)
    if peak_indices:
        peak_x = lag_seconds[peak_indices]
        peak_y = autocorrelation[peak_indices]
        axis.scatter(peak_x, peak_y, color="#f97316", s=28, zorder=3)
    axis.set_title("Autocorrelation")
    axis.set_xlabel("Lag (s)")
    axis.set_ylabel("Correlation")
    axis.set_xlim(0, float(lag_seconds[-1]) if len(lag_seconds) else 0)
    axis.grid(alpha=0.2)
    return PlotImage(
        key="autocorrelation",
        title="Autocorrelation",
        description="Self-similarity across lags, useful for periodicity and spacing between repeated patterns.",
        media_type="image/png",
        image_bytes=_render_figure(figure),
    )


def _serialize_temporal_analysis(analysis: TemporalAnalysis) -> dict[str, object]:
    return {
        "rms": asdict(analysis.rms),
        "zero_crossing_rate": asdict(analysis.zero_crossing_rate),
        "amplitude_envelope": asdict(analysis.amplitude_envelope),
        "peak_amplitude": analysis.peak_amplitude,
        "peak_to_peak_amplitude": analysis.peak_to_peak_amplitude,
        "crest_factor": analysis.crest_factor,
        "silence_ratio": analysis.silence_ratio,
        "dynamic_range_db": analysis.dynamic_range_db,
        "dc_offset": analysis.dc_offset,
        "clipping_ratio": analysis.clipping_ratio,
    }


def _serialize_spectral_analysis(analysis: SpectralAnalysis) -> dict[str, object]:
    return {
        "centroid_hz": asdict(analysis.centroid_hz),
        "bandwidth_hz": asdict(analysis.bandwidth_hz),
        "rolloff_hz": asdict(analysis.rolloff_hz),
        "flatness": asdict(analysis.flatness),
        "contrast_db_by_band": analysis.contrast_db_by_band,
        "dominant_frequency_hz": analysis.dominant_frequency_hz,
        "dominant_frequency_magnitude": analysis.dominant_frequency_magnitude,
        "spectral_flux": asdict(analysis.spectral_flux),
        "top_spectral_peaks": [asdict(peak) for peak in analysis.top_spectral_peaks],
    }


def _serialize_autocorrelation_analysis(analysis: AutocorrelationAnalysis) -> dict[str, object]:
    return asdict(analysis)


def serialize_result(result: ScalogramResult, *, include_images: bool = True) -> dict[str, object]:
    payload: dict[str, object] = {
        "analysis_version": result.analysis_version,
        "primary_visualization": result.primary_image.key,
        "audio_metadata": asdict(result.metadata),
        "scalogram_config": asdict(result.scalogram_config),
        "temporal_analysis": _serialize_temporal_analysis(result.temporal_analysis),
        "spectral_analysis": _serialize_spectral_analysis(result.spectral_analysis),
        "autocorrelation_analysis": _serialize_autocorrelation_analysis(result.autocorrelation_analysis),
    }

    if include_images:
        payload["plots"] = {key: plot.as_dict() for key, plot in result.plots.items()}

    return payload


def build_scalogram(
    audio_bytes: bytes,
    *,
    sample_rate: int | None = None,
    wavelet: str | None = None,
    width_min: int | None = None,
    width_max: int | None = None,
    colormap: str | None = None,
    visualization: str = "dashboard",
) -> ScalogramResult:
    target_sample_rate = sample_rate or settings.default_sample_rate
    selected_wavelet = wavelet or settings.default_wavelet
    selected_width_min = width_min or settings.default_width_min
    selected_width_max = width_max or settings.default_width_max
    selected_colormap = colormap or settings.default_colormap

    if selected_width_min < 1 or selected_width_max <= selected_width_min:
        raise ValueError("Invalid wavelet width range.")

    waveform, original_sample_rate = librosa.load(
        BytesIO(audio_bytes),
        sr=None,
        mono=True,
    )

    if waveform.size == 0:
        raise ValueError("Audio file is empty.")

    if original_sample_rate != target_sample_rate:
        waveform = librosa.resample(
            waveform,
            orig_sr=original_sample_rate,
            target_sr=target_sample_rate,
        )

    effective_sample_rate = target_sample_rate
    duration_seconds = float(len(waveform) / effective_sample_rate)

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

    rms = librosa.feature.rms(
        y=waveform,
        frame_length=ANALYSIS_FRAME_LENGTH,
        hop_length=ANALYSIS_HOP_LENGTH,
    )[0]
    zcr = librosa.feature.zero_crossing_rate(
        y=waveform,
        frame_length=ANALYSIS_FRAME_LENGTH,
        hop_length=ANALYSIS_HOP_LENGTH,
    )[0]
    envelope = np.abs(waveform)
    silence_threshold = max(float(np.max(envelope)) * 0.05, EPSILON)
    silence_ratio = float(np.mean(envelope < silence_threshold))
    peak_amplitude = float(np.max(envelope))
    peak_to_peak_amplitude = float(np.max(waveform) - np.min(waveform))
    rms_mean = float(np.mean(rms))
    crest_factor = float(peak_amplitude / (rms_mean + EPSILON))
    dynamic_range_db = float(
        20 * np.log10((np.percentile(rms, 95) + EPSILON) / (np.percentile(rms, 5) + EPSILON))
    )
    clipping_ratio = float(np.mean(envelope >= 0.999))
    dc_offset = float(np.mean(waveform))

    stft = librosa.stft(
        waveform,
        n_fft=ANALYSIS_FRAME_LENGTH,
        hop_length=ANALYSIS_HOP_LENGTH,
    )
    stft_magnitude = np.abs(stft)
    average_spectrum = np.mean(stft_magnitude, axis=1)
    spectrum_frequencies = librosa.fft_frequencies(sr=effective_sample_rate, n_fft=ANALYSIS_FRAME_LENGTH)

    centroid = librosa.feature.spectral_centroid(S=stft_magnitude, sr=effective_sample_rate)[0]
    bandwidth = librosa.feature.spectral_bandwidth(S=stft_magnitude, sr=effective_sample_rate)[0]
    rolloff = librosa.feature.spectral_rolloff(S=stft_magnitude, sr=effective_sample_rate)[0]
    flatness = librosa.feature.spectral_flatness(S=stft_magnitude + EPSILON)[0]
    contrast = librosa.feature.spectral_contrast(S=stft_magnitude + EPSILON, sr=effective_sample_rate)

    normalized_spectrum = stft_magnitude / (np.sum(stft_magnitude, axis=0, keepdims=True) + EPSILON)
    spectral_flux_series = np.sqrt(np.sum(np.diff(normalized_spectrum, axis=1) ** 2, axis=0))
    spectral_flux = (
        spectral_flux_series if spectral_flux_series.size else np.array([0.0], dtype=float)
    )

    dominant_index = int(np.argmax(average_spectrum))
    dominant_frequency_hz = float(spectrum_frequencies[dominant_index])
    dominant_frequency_magnitude = float(average_spectrum[dominant_index])

    sorted_indices = np.argsort(average_spectrum)[::-1]
    top_spectral_peaks = [
        SpectralPeak(
            rank=rank,
            frequency_hz=float(spectrum_frequencies[index]),
            magnitude=float(average_spectrum[index]),
        )
        for rank, index in enumerate(sorted_indices[:5], start=1)
    ]

    mel_spectrogram = librosa.feature.melspectrogram(
        y=waveform,
        sr=effective_sample_rate,
        n_fft=ANALYSIS_FRAME_LENGTH,
        hop_length=ANALYSIS_HOP_LENGTH,
        n_mels=128,
    )
    mel_db = librosa.power_to_db(mel_spectrogram, ref=np.max)
    rms_times = _seconds_axis(len(rms), effective_sample_rate, ANALYSIS_HOP_LENGTH)

    autocorrelation = librosa.autocorrelate(waveform)
    autocorrelation = autocorrelation[: min(len(autocorrelation), effective_sample_rate * 2)]
    if autocorrelation.size == 0:
        autocorrelation = np.array([1.0], dtype=float)
    autocorrelation = autocorrelation / (np.max(np.abs(autocorrelation)) + EPSILON)
    autocorrelation_lags = np.arange(len(autocorrelation))
    autocorrelation_seconds = autocorrelation_lags / effective_sample_rate

    positive_autocorrelation = autocorrelation[1:] if autocorrelation.size > 1 else np.array([], dtype=float)
    detected_peaks = np.array([], dtype=int)
    if positive_autocorrelation.size > 2:
        detected_peaks, _ = find_peaks(
            positive_autocorrelation,
            prominence=0.05,
            distance=max(1, int(effective_sample_rate * 0.005)),
        )
    detected_peaks = detected_peaks + 1 if detected_peaks.size else detected_peaks
    strongest_peak_indices = sorted(
        detected_peaks.tolist(),
        key=lambda idx: float(autocorrelation[idx]),
        reverse=True,
    )[:2]

    strongest_peak_lag_samples = strongest_peak_indices[0] if len(strongest_peak_indices) >= 1 else None
    second_peak_lag_samples = strongest_peak_indices[1] if len(strongest_peak_indices) >= 2 else None

    peak_distance_samples = None
    peak_distance_seconds = None
    if strongest_peak_lag_samples is not None and second_peak_lag_samples is not None:
        peak_distance_samples = abs(second_peak_lag_samples - strongest_peak_lag_samples)
        peak_distance_seconds = float(peak_distance_samples / effective_sample_rate)

    plots = {
        "dashboard": _build_dashboard_plot(
            waveform,
            effective_sample_rate,
            rms_times,
            rms,
            spectrum_frequencies,
            average_spectrum,
            mel_db,
            ANALYSIS_HOP_LENGTH,
        ),
        "waveform": _build_waveform_plot(waveform, effective_sample_rate),
        "rms_energy": _build_rms_plot(rms_times, rms),
        "spectrum": _build_spectrum_plot(spectrum_frequencies, average_spectrum),
        "mel_spectrogram": _build_mel_plot(mel_db, effective_sample_rate, ANALYSIS_HOP_LENGTH),
        "scalogram": _build_scalogram_plot(power, frequencies, duration_seconds, selected_colormap),
        "autocorrelation": _build_autocorrelation_plot(
            autocorrelation_seconds,
            autocorrelation,
            strongest_peak_indices,
        ),
    }

    if visualization not in plots:
        raise ValueError(
            "Invalid visualization. Use one of: dashboard, waveform, rms_energy, spectrum, mel_spectrogram, scalogram, autocorrelation."
        )

    temporal_analysis = TemporalAnalysis(
        rms=_summarize(rms),
        zero_crossing_rate=_summarize(zcr),
        amplitude_envelope=_summarize(envelope),
        peak_amplitude=peak_amplitude,
        peak_to_peak_amplitude=peak_to_peak_amplitude,
        crest_factor=crest_factor,
        silence_ratio=silence_ratio,
        dynamic_range_db=dynamic_range_db,
        dc_offset=dc_offset,
        clipping_ratio=clipping_ratio,
    )

    spectral_analysis = SpectralAnalysis(
        centroid_hz=_summarize(centroid),
        bandwidth_hz=_summarize(bandwidth),
        rolloff_hz=_summarize(rolloff),
        flatness=_summarize(flatness),
        contrast_db_by_band=[float(value) for value in np.mean(contrast, axis=1)],
        dominant_frequency_hz=dominant_frequency_hz,
        dominant_frequency_magnitude=dominant_frequency_magnitude,
        spectral_flux=_summarize(spectral_flux),
        top_spectral_peaks=top_spectral_peaks,
    )

    autocorrelation_analysis = AutocorrelationAnalysis(
        strongest_peak_lag_samples=int(strongest_peak_lag_samples) if strongest_peak_lag_samples is not None else None,
        strongest_peak_lag_seconds=(
            float(strongest_peak_lag_samples / effective_sample_rate)
            if strongest_peak_lag_samples is not None
            else None
        ),
        strongest_peak_value=(
            float(autocorrelation[strongest_peak_lag_samples])
            if strongest_peak_lag_samples is not None
            else None
        ),
        second_peak_lag_samples=int(second_peak_lag_samples) if second_peak_lag_samples is not None else None,
        second_peak_lag_seconds=(
            float(second_peak_lag_samples / effective_sample_rate)
            if second_peak_lag_samples is not None
            else None
        ),
        second_peak_value=(
            float(autocorrelation[second_peak_lag_samples])
            if second_peak_lag_samples is not None
            else None
        ),
        peak_distance_samples=int(peak_distance_samples) if peak_distance_samples is not None else None,
        peak_distance_seconds=peak_distance_seconds,
        peak_count=int(detected_peaks.size),
    )

    metadata = AudioMetadata(
        sample_rate=int(effective_sample_rate),
        original_sample_rate=int(original_sample_rate),
        duration_seconds=duration_seconds,
        sample_count=int(len(waveform)),
        channel_count=1,
        file_size_bytes=len(audio_bytes),
        analyzed_frame_length=ANALYSIS_FRAME_LENGTH,
        analyzed_hop_length=ANALYSIS_HOP_LENGTH,
        nyquist_hz=float(effective_sample_rate / 2),
    )

    return ScalogramResult(
        primary_image=plots[visualization],
        plots=plots,
        metadata=metadata,
        scalogram_config=ScalogramConfig(
            wavelet=selected_wavelet,
            width_min=selected_width_min,
            width_max=selected_width_max,
            colormap=selected_colormap,
        ),
        temporal_analysis=temporal_analysis,
        spectral_analysis=spectral_analysis,
        autocorrelation_analysis=autocorrelation_analysis,
        analysis_version=ANALYSIS_VERSION,
    )
