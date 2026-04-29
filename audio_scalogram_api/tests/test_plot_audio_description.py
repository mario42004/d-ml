import numpy as np

from app.services import scalogram


def _dashboard_fixture(**overrides):
    data = {
        "waveform": np.sin(np.linspace(0, 12, 3000)),
        "sample_rate": 1000,
        "rms_times": np.linspace(0, 3, 6),
        "rms": np.array([0.1, 0.2, 0.15, 0.12, 0.18, 0.14]),
        "spectrum_frequencies": np.linspace(0, 500, 8),
        "average_spectrum": np.linspace(0.2, 0.8, 8),
        "mel_db": np.ones((4, 4)),
        "hop_length": 32,
    }
    data.update(overrides)
    return data


def test_plot_titles_include_normalized_audio_description(monkeypatch) -> None:
    monkeypatch.setattr(scalogram, "_render_figure", lambda figure: b"png-bytes")

    raw_description = "  Motor   bomba   turno manana con vibracion persistente extra  "
    expected_description = "Motor bomba turno manana con vibracion persistente"

    dashboard = scalogram._build_dashboard_plot(**_dashboard_fixture(audio_description=raw_description))
    autocorrelation = scalogram._build_autocorrelation_plot(
        lag_seconds=np.linspace(0, 0.1, 8),
        autocorrelation=np.linspace(1.0, 0.1, 8),
        peak_indices=[2],
        audio_description=raw_description,
    )

    assert dashboard.title == f"Audio Analysis Dashboard: {expected_description}"
    assert autocorrelation.title == f"Autocorrelation: {expected_description}"


def test_dashboard_replaces_rms_panel_with_zoomed_envelope(monkeypatch) -> None:
    captured_figures = []

    def capture_figure(figure):
        captured_figures.append(figure)
        return b"png-bytes"

    monkeypatch.setattr(scalogram, "_render_figure", capture_figure)

    plot = scalogram._build_dashboard_plot(**_dashboard_fixture())

    assert plot.description == "Combined waveform, zoomed envelope, average spectrum and mel spectrogram view."
    assert captured_figures
    axes = captured_figures[0].axes
    assert axes[1].get_title() == "Waveform Zoom + Envelope"
    assert axes[1].get_xlabel() == "Time (s)"
    assert axes[1].get_ylabel() == "Amplitude"
    assert axes[1].get_xlim()[1] <= 1.6
