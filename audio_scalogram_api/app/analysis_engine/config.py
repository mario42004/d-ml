from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AudioEngineConfig:
    target_sample_rate: int = 16_000
    mono: bool = True
    dtype: str = "float32"
    normalize_amplitude: bool = True
    max_audio_duration_seconds: float = 20.0
    min_audio_duration_seconds: float = 0.1
    accepted_extensions: tuple[str, ...] = (
        ".wav",
        ".webm",
        ".mp3",
        ".m4a",
        ".ogg",
        ".flac",
        ".aac",
    )


@dataclass(frozen=True)
class FramingConfig:
    enabled: bool = True
    frame_duration_seconds: float = 5.0
    hop_duration_seconds: float = 5.0
    allow_overlap: bool = False
    auto_frame_duration: bool = False
    include_partial_last_frame: bool = True
    min_frame_duration_seconds: float = 0.1
    max_frame_duration_seconds: float = 5.0
    max_frames: int = 4
    expose_frame_features: bool = False


@dataclass(frozen=True)
class TemporalConfig:
    max_trend_points: int = 120
    peak_prominence_ratio: float = 0.10
    active_energy_ratio: float = 0.05


@dataclass(frozen=True)
class SpectralConfig:
    n_fft: int = 1024
    hop_length: int = 512
    rolloff_percentages: tuple[float, float] = (0.85, 0.95)
    frequency_bands: tuple[tuple[str, float, float], ...] = (
        ("low", 0.0, 300.0),
        ("mid", 300.0, 3000.0),
        ("high", 3000.0, 8000.0),
    )


@dataclass(frozen=True)
class CepstralConfig:
    num_mfcc: int = 13
    n_fft: int = 1024
    hop_length: int = 512
    n_mels: int = 40
    include_delta: bool = True
    voice_features_enabled: bool = False
    voice_fmin_hz: float = 70.0
    voice_fmax_hz: float = 500.0


@dataclass(frozen=True)
class TimeFrequencyConfig:
    enabled: bool = False
    wavelet: str = "morl"
    max_scales: int = 64
    reduced_bins: int = 16
    max_internal_sample_rate: int = 4_000
    max_samples: int = 80_000


@dataclass(frozen=True)
class AnalysisEngineConfig:
    version: str = "0.1.0"
    mode: str = "normal"
    audio: AudioEngineConfig = field(default_factory=AudioEngineConfig)
    framing: FramingConfig = field(default_factory=FramingConfig)
    temporal: TemporalConfig = field(default_factory=TemporalConfig)
    spectral: SpectralConfig = field(default_factory=SpectralConfig)
    cepstral: CepstralConfig = field(default_factory=CepstralConfig)
    time_frequency: TimeFrequencyConfig = field(default_factory=TimeFrequencyConfig)


DEFAULT_CONFIG = AnalysisEngineConfig()
