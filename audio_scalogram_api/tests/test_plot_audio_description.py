import numpy as np

from app.services import scalogram


def test_plot_titles_include_normalized_audio_description(monkeypatch) -> None:
    monkeypatch.setattr(scalogram, "_render_figure", lambda figure: b"png-bytes")

    raw_description = "  Motor   bomba   turno manana con vibracion persistente extra  "
    expected_description = "Motor bomba turno manana con vibracion persistente"

    dashboard = scalogram._build_dashboard_plot(
        waveform=np.sin(np.linspace(0, 1, 128)),
        sample_rate=1000,
        rms_times=np.linspace(0, 1, 4),
        rms=np.array([0.1, 0.2, 0.15, 0.12]),
        spectrum_frequencies=np.linspace(0, 500, 8),
        average_spectrum=np.linspace(0.2, 0.8, 8),
        mel_db=np.ones((4, 4)),
        hop_length=32,
        audio_description=raw_description,
    )
    autocorrelation = scalogram._build_autocorrelation_plot(
        lag_seconds=np.linspace(0, 0.1, 8),
        autocorrelation=np.linspace(1.0, 0.1, 8),
        peak_indices=[2],
        audio_description=raw_description,
    )

    assert dashboard.title == f"Audio Analysis Dashboard: {expected_description}"
    assert autocorrelation.title == f"Autocorrelation: {expected_description}"
