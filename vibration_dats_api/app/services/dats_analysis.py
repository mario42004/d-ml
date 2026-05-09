from __future__ import annotations

import base64
import csv
import io
import math
from dataclasses import dataclass
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


EXPECTED_COLUMNS = [
    "session_start_wall_time_ms",
    "wall_time_ms",
    "sensor_time_ns",
    "sensor",
    "accuracy",
    "x",
    "y",
    "z",
]


class DatsAnalysisError(ValueError):
    pass


@dataclass(frozen=True)
class SensorSeries:
    name: str
    t: np.ndarray
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    accuracy: np.ndarray


def analyze_dats_bytes(
    raw: bytes,
    *,
    filename: str,
    window_ms: int = 500,
    max_duration_seconds: int = 180,
    min_window_ms: int = 100,
    max_window_ms: int = 5000,
) -> dict[str, object]:
    if not min_window_ms <= window_ms <= max_window_ms:
        raise DatsAnalysisError(f"window_ms debe estar entre {min_window_ms} y {max_window_ms}.")

    text = _decode_dat(raw)
    metadata, rows = _parse_dat_text(text)
    if not rows:
        raise DatsAnalysisError("El archivo no contiene filas de datos validas.")

    series = _build_sensor_series(rows)
    if not series:
        raise DatsAnalysisError("No se encontraron muestras de acelerometro o giroscopio.")

    capture_start_ns = min(float(item.t[0]) for item in series.values())
    capture_end_ns = max(float(item.t[-1]) for item in series.values())
    duration_seconds = (capture_end_ns - capture_start_ns) / 1e9
    if duration_seconds > max_duration_seconds:
        raise DatsAnalysisError(
            f"La captura dura {duration_seconds:.2f} s y supera el limite de {max_duration_seconds} s."
        )

    relative_series = {
        name: SensorSeries(
            name=item.name,
            t=(item.t - capture_start_ns) / 1e9,
            x=item.x,
            y=item.y,
            z=item.z,
            accuracy=item.accuracy,
        )
        for name, item in series.items()
    }

    window_seconds = window_ms / 1000.0
    sensor_summaries = {
        name: _sensor_summary(item, window_seconds=window_seconds)
        for name, item in relative_series.items()
    }
    windows = _window_summaries(relative_series.values(), duration_seconds, window_seconds)
    _add_window_change_scores(windows)
    plots = _build_plots(relative_series, windows)

    return {
        "analysis_version": "1.1",
        "file": {
            "filename": filename,
            "metadata": metadata,
            "declared_columns": _metadata_value(metadata, "columns"),
            "declared_target_sample_rate_hz": _metadata_number(metadata, "target_sample_rate_hz"),
            "declared_sensor_period_us": _metadata_number(metadata, "sensor_period_us"),
        },
        "capture": {
            "duration_seconds": _round(duration_seconds),
            "max_duration_seconds": max_duration_seconds,
            "window_ms": window_ms,
            "window_count": len(windows),
            "sensors": sorted(relative_series),
        },
        "sensor_summaries": sensor_summaries,
        "windows": windows,
        "metricas": _build_metricas(sensor_summaries),
        "plots": plots,
    }


def _decode_dat(raw: bytes) -> str:
    if not raw:
        raise DatsAnalysisError("El archivo esta vacio.")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DatsAnalysisError("El archivo debe estar codificado en UTF-8.") from exc


def _parse_dat_text(text: str) -> tuple[dict[str, str], list[dict[str, object]]]:
    metadata: dict[str, str] = {}
    data_lines: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            key, value = _parse_metadata_line(line)
            if key:
                metadata[key] = value
            continue
        data_lines.append(line)

    rows: list[dict[str, object]] = []
    reader = csv.reader(data_lines)
    for line_number, row in enumerate(reader, start=1):
        if len(row) != len(EXPECTED_COLUMNS):
            raise DatsAnalysisError(f"Fila {line_number} invalida: se esperaban 8 columnas.")
        try:
            rows.append(
                {
                    "session_start_wall_time_ms": int(row[0]),
                    "wall_time_ms": int(row[1]),
                    "sensor_time_ns": int(row[2]),
                    "sensor": row[3].strip().lower(),
                    "accuracy": int(row[4]),
                    "x": float(row[5]),
                    "y": float(row[6]),
                    "z": float(row[7]),
                }
            )
        except ValueError as exc:
            raise DatsAnalysisError(f"Fila {line_number} contiene valores no numericos.") from exc
    return metadata, rows


def _parse_metadata_line(line: str) -> tuple[str, str]:
    clean = line.lstrip("#").strip()
    if "=" not in clean:
        return "", clean
    key, value = clean.split("=", 1)
    return key.strip(), value.strip()


def _build_sensor_series(rows: list[dict[str, object]]) -> dict[str, SensorSeries]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        sensor = str(row["sensor"])
        if sensor not in {"accelerometer", "gyroscope"}:
            continue
        grouped.setdefault(sensor, []).append(row)

    result: dict[str, SensorSeries] = {}
    for sensor, sensor_rows in grouped.items():
        sensor_rows.sort(key=lambda item: int(item["sensor_time_ns"]))
        result[sensor] = SensorSeries(
            name=sensor,
            t=np.array([row["sensor_time_ns"] for row in sensor_rows], dtype=np.float64),
            x=np.array([row["x"] for row in sensor_rows], dtype=np.float64),
            y=np.array([row["y"] for row in sensor_rows], dtype=np.float64),
            z=np.array([row["z"] for row in sensor_rows], dtype=np.float64),
            accuracy=np.array([row["accuracy"] for row in sensor_rows], dtype=np.int32),
        )
    return result


def _sensor_summary(series: SensorSeries, *, window_seconds: float) -> dict[str, object]:
    magnitude = _magnitude(series)
    dynamic = _dynamic_component(series.t, magnitude)
    fs = _estimated_sample_rate(series.t)
    spectrum = _spectral_summary(series.t, dynamic)
    jerk = _jerk(series.t, magnitude)
    units = "m/s^2" if series.name == "accelerometer" else "rad/s"

    return {
        "sample_count": int(len(series.t)),
        "duration_seconds": _round(float(series.t[-1] - series.t[0])) if len(series.t) > 1 else 0.0,
        "estimated_sample_rate_hz": _round(fs),
        "accuracy_mode": _mode_int(series.accuracy),
        "axis_units": units,
        "window_seconds": window_seconds,
        "x": _stats(series.x),
        "y": _stats(series.y),
        "z": _stats(series.z),
        "magnitude": _stats(magnitude),
        "dynamic": {
            "rms": _round(_rms(dynamic)),
            "std": _round(float(np.std(dynamic))),
            "peak_abs": _round(float(np.max(np.abs(dynamic)))) if len(dynamic) else None,
            "peak_to_peak": _round(_peak_to_peak(dynamic)),
            "mean_abs": _round(float(np.mean(np.abs(dynamic)))) if len(dynamic) else None,
            "variance": _round(float(np.var(dynamic))) if len(dynamic) else None,
            "skewness": _round(_skewness(dynamic)),
            "kurtosis": _round(_kurtosis(dynamic)),
            "crest_factor": _round(_crest_factor(dynamic)),
            "shape_factor": _round(_shape_factor(dynamic)),
            "impulse_factor": _round(_impulse_factor(dynamic)),
            "clearance_factor": _round(_clearance_factor(dynamic)),
            "zero_crossing_rate": _round(_zero_crossing_rate(dynamic)),
            "energy": _round(float(np.sum(dynamic * dynamic))) if len(dynamic) else None,
            "entropy": _round(_signal_entropy(dynamic)),
        },
        "jerk": {
            "rms": _round(_rms(jerk)),
            "max_abs": _round(float(np.max(np.abs(jerk)))) if len(jerk) else None,
            "peak_to_peak": _round(_peak_to_peak(jerk)),
            "crest_factor": _round(_crest_factor(jerk)),
        },
        "spectrum": spectrum,
    }


def _window_summaries(
    series_items: Iterable[SensorSeries],
    duration_seconds: float,
    window_seconds: float,
) -> list[dict[str, object]]:
    window_count = max(1, int(math.ceil(duration_seconds / window_seconds)))
    windows: list[dict[str, object]] = []
    for idx in range(window_count):
        start = idx * window_seconds
        end = min(duration_seconds, start + window_seconds)
        sensor_payload: dict[str, object] = {}
        for series in series_items:
            mask = (series.t >= start) & (series.t < end if idx < window_count - 1 else series.t <= end)
            if np.any(mask):
                sensor_payload[series.name] = _single_window_metrics(
                    SensorSeries(
                        name=series.name,
                        t=series.t[mask],
                        x=series.x[mask],
                        y=series.y[mask],
                        z=series.z[mask],
                        accuracy=series.accuracy[mask],
                    )
                )

        windows.append(
            {
                "index": idx,
                "start_seconds": _round(start),
                "end_seconds": _round(end),
                "duration_seconds": _round(max(0.0, end - start)),
                "sensors": sensor_payload,
            }
        )
    return windows


def _single_window_metrics(series: SensorSeries) -> dict[str, object]:
    magnitude = _magnitude(series)
    dynamic = magnitude - float(np.mean(magnitude))
    jerk = _jerk(series.t, magnitude)
    spectrum = _spectral_summary(series.t, dynamic)
    return {
        "sample_count": int(len(series.t)),
        "estimated_sample_rate_hz": _round(_estimated_sample_rate(series.t)),
        "accuracy_mode": _mode_int(series.accuracy),
        "magnitude_mean": _round(float(np.mean(magnitude))),
        "magnitude_std": _round(float(np.std(magnitude))),
        "magnitude_rms": _round(_rms(magnitude)),
        "magnitude_min": _round(float(np.min(magnitude))),
        "magnitude_max": _round(float(np.max(magnitude))),
        "magnitude_peak_to_peak": _round(_peak_to_peak(magnitude)),
        "dynamic_rms": _round(_rms(dynamic)),
        "dynamic_peak_abs": _round(float(np.max(np.abs(dynamic)))),
        "dynamic_kurtosis": _round(_kurtosis(dynamic)),
        "dynamic_skewness": _round(_skewness(dynamic)),
        "dynamic_crest_factor": _round(_crest_factor(dynamic)),
        "dynamic_impulse_factor": _round(_impulse_factor(dynamic)),
        "dynamic_shape_factor": _round(_shape_factor(dynamic)),
        "dynamic_entropy": _round(_signal_entropy(dynamic)),
        "zero_crossing_rate": _round(_zero_crossing_rate(dynamic)),
        "axis_peak_to_peak": {
            "x": _round(_peak_to_peak(series.x)),
            "y": _round(_peak_to_peak(series.y)),
            "z": _round(_peak_to_peak(series.z)),
        },
        "jerk_rms": _round(_rms(jerk)),
        "jerk_max_abs": _round(float(np.max(np.abs(jerk)))) if len(jerk) else None,
        "dominant_frequency_hz": spectrum["dominant_frequency_hz"],
        "spectral_centroid_hz": spectrum["spectral_centroid_hz"],
        "spectral_entropy": spectrum["spectral_entropy"],
    }


def _add_window_change_scores(windows: list[dict[str, object]]) -> None:
    sensors = sorted(
        {
            sensor
            for window in windows
            for sensor in (window.get("sensors") if isinstance(window.get("sensors"), dict) else {})
        }
    )
    for sensor in sensors:
        values = []
        indexes = []
        for idx, window in enumerate(windows):
            sensor_payload = window["sensors"].get(sensor) if isinstance(window.get("sensors"), dict) else None
            if not isinstance(sensor_payload, dict):
                continue
            score_input = [
                sensor_payload.get("dynamic_rms"),
                sensor_payload.get("dynamic_peak_abs"),
                sensor_payload.get("jerk_rms"),
                sensor_payload.get("magnitude_peak_to_peak"),
                sensor_payload.get("dynamic_crest_factor"),
                sensor_payload.get("dynamic_kurtosis"),
            ]
            finite = [float(item) for item in score_input if isinstance(item, int | float) and math.isfinite(float(item))]
            if finite:
                values.append(float(np.mean(finite)))
                indexes.append(idx)

        scores = _robust_scores(np.array(values, dtype=np.float64))
        for idx, score in zip(indexes, scores, strict=False):
            payload = windows[idx]["sensors"][sensor]
            payload["change_score"] = _round(float(score))
            payload["strong_change"] = bool(score >= 3.5)
            payload["severity"] = _severity(score)


def _build_plots(series_by_name: dict[str, SensorSeries], windows: list[dict[str, object]]) -> dict[str, object]:
    plots: dict[str, object] = {}
    for sensor, series in series_by_name.items():
        magnitude = _magnitude(series)
        dynamic = _dynamic_component(series.t, magnitude)
        plots[f"{sensor}_timeseries"] = _plot_timeseries(sensor, series, magnitude)
        plots[f"{sensor}_dynamic"] = _plot_dynamic(sensor, series.t, dynamic)
        plots[f"{sensor}_spectrum"] = _plot_spectrum(sensor, series.t, dynamic)
        plots[f"{sensor}_window_scores"] = _plot_window_scores(sensor, windows)
    return plots


def _plot_payload(title: str, image_bytes: bytes) -> dict[str, object]:
    return {
        "title": title,
        "content_type": "image/png",
        "encoding": "base64",
        "image_base64": base64.b64encode(image_bytes).decode("ascii"),
    }


def _figure_to_png(fig: plt.Figure) -> bytes:
    buffer = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buffer, format="png", dpi=140)
    plt.close(fig)
    return buffer.getvalue()


def _plot_timeseries(sensor: str, series: SensorSeries, magnitude: np.ndarray) -> dict[str, object]:
    fig, axes = plt.subplots(2, 1, figsize=(11, 6), sharex=True)
    axes[0].plot(series.t, series.x, linewidth=1.0, label="x")
    axes[0].plot(series.t, series.y, linewidth=1.0, label="y")
    axes[0].plot(series.t, series.z, linewidth=1.0, label="z")
    axes[0].set_title(f"{sensor}: ejes")
    axes[0].set_ylabel("valor")
    axes[0].grid(True, alpha=0.25)
    axes[0].legend(loc="upper right")

    axes[1].plot(series.t, magnitude, color="black", linewidth=1.0)
    axes[1].set_title("magnitud")
    axes[1].set_xlabel("tiempo (s)")
    axes[1].set_ylabel("|v|")
    axes[1].grid(True, alpha=0.25)
    return _plot_payload(f"{sensor} time series", _figure_to_png(fig))


def _plot_dynamic(sensor: str, t: np.ndarray, dynamic: np.ndarray) -> dict[str, object]:
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(t, dynamic, color="#2563eb", linewidth=1.0)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title(f"{sensor}: componente dinamica")
    ax.set_xlabel("tiempo (s)")
    ax.set_ylabel("dinamica")
    ax.grid(True, alpha=0.25)
    return _plot_payload(f"{sensor} dynamic component", _figure_to_png(fig))


def _plot_spectrum(sensor: str, t: np.ndarray, signal: np.ndarray) -> dict[str, object]:
    fig, ax = plt.subplots(figsize=(11, 4))
    fs = _estimated_sample_rate(t)
    if fs > 0 and len(signal) >= 4:
        centered = signal - float(np.mean(signal))
        window = np.hanning(len(centered))
        spectrum = np.fft.rfft(centered * window)
        freqs = np.fft.rfftfreq(len(centered), d=1.0 / fs)
        amp = np.abs(spectrum) * 2.0 / max(float(np.sum(window)), 1.0)
        keep = (freqs > 0.2) & (freqs <= min(60.0, fs / 2.0))
        ax.plot(freqs[keep], amp[keep], color="#7c3aed", linewidth=1.0)
    ax.set_title(f"{sensor}: espectro dinamico")
    ax.set_xlabel("frecuencia (Hz)")
    ax.set_ylabel("amplitud")
    ax.grid(True, alpha=0.25)
    return _plot_payload(f"{sensor} spectrum", _figure_to_png(fig))


def _plot_window_scores(sensor: str, windows: list[dict[str, object]]) -> dict[str, object]:
    centers = []
    scores = []
    rms_values = []
    for window in windows:
        payload = window.get("sensors", {}).get(sensor) if isinstance(window.get("sensors"), dict) else None
        if not isinstance(payload, dict):
            continue
        start = float(window.get("start_seconds") or 0.0)
        end = float(window.get("end_seconds") or start)
        centers.append((start + end) / 2.0)
        scores.append(float(payload.get("change_score") or 0.0))
        rms_values.append(float(payload.get("dynamic_rms") or 0.0))

    fig, ax = plt.subplots(figsize=(11, 4))
    if centers:
        ax.plot(centers, scores, color="#dc2626", linewidth=1.4, label="change score")
        ax.plot(centers, rms_values, color="#059669", linewidth=1.0, alpha=0.8, label="dynamic RMS")
        ax.axhline(3.5, color="#dc2626", linestyle="--", linewidth=0.8)
        ax.legend(loc="upper right")
    ax.set_title(f"{sensor}: ventanas de observacion")
    ax.set_xlabel("tiempo (s)")
    ax.set_ylabel("score")
    ax.grid(True, alpha=0.25)
    return _plot_payload(f"{sensor} window scores", _figure_to_png(fig))


def _build_metricas(sensor_summaries: dict[str, dict[str, object]]) -> dict[str, object]:
    groups = []
    for sensor, summary in sensor_summaries.items():
        dynamic = summary.get("dynamic") if isinstance(summary.get("dynamic"), dict) else {}
        jerk = summary.get("jerk") if isinstance(summary.get("jerk"), dict) else {}
        spectrum = summary.get("spectrum") if isinstance(summary.get("spectrum"), dict) else {}
        magnitude = summary.get("magnitude") if isinstance(summary.get("magnitude"), dict) else {}
        units = str(summary.get("axis_units") or "")
        groups.append(
            {
                "clave": sensor,
                "etiqueta": "Acelerometro" if sensor == "accelerometer" else "Giroscopio",
                "metricas": [
                    _sensor_metric(sensor, "sample_count", "Muestras", summary.get("sample_count"), "", f"sensor_summaries.{sensor}.sample_count"),
                    _sensor_metric(sensor, "estimated_sample_rate_hz", "Frecuencia estimada", summary.get("estimated_sample_rate_hz"), "Hz", f"sensor_summaries.{sensor}.estimated_sample_rate_hz"),
                    _sensor_metric(sensor, "magnitude_mean", "Magnitud media", magnitude.get("mean"), units, f"sensor_summaries.{sensor}.magnitude.mean"),
                    _sensor_metric(sensor, "magnitude_std", "Desviacion de magnitud", magnitude.get("std"), units, f"sensor_summaries.{sensor}.magnitude.std"),
                    _sensor_metric(sensor, "magnitude_peak_to_peak", "Pico a pico de magnitud", magnitude.get("peak_to_peak"), units, f"sensor_summaries.{sensor}.magnitude.peak_to_peak"),
                    _sensor_metric(sensor, "dynamic_rms", "RMS dinamico", dynamic.get("rms"), units, f"sensor_summaries.{sensor}.dynamic.rms"),
                    _sensor_metric(sensor, "dynamic_peak_abs", "Pico dinamico absoluto", dynamic.get("peak_abs"), units, f"sensor_summaries.{sensor}.dynamic.peak_abs"),
                    _sensor_metric(sensor, "dynamic_peak_to_peak", "Pico a pico dinamico", dynamic.get("peak_to_peak"), units, f"sensor_summaries.{sensor}.dynamic.peak_to_peak"),
                    _sensor_metric(sensor, "dynamic_kurtosis", "Kurtosis dinamica", dynamic.get("kurtosis"), "", f"sensor_summaries.{sensor}.dynamic.kurtosis"),
                    _sensor_metric(sensor, "dynamic_skewness", "Skewness dinamica", dynamic.get("skewness"), "", f"sensor_summaries.{sensor}.dynamic.skewness"),
                    _sensor_metric(sensor, "dynamic_crest_factor", "Crest factor dinamico", dynamic.get("crest_factor"), "", f"sensor_summaries.{sensor}.dynamic.crest_factor"),
                    _sensor_metric(sensor, "dynamic_shape_factor", "Shape factor dinamico", dynamic.get("shape_factor"), "", f"sensor_summaries.{sensor}.dynamic.shape_factor"),
                    _sensor_metric(sensor, "dynamic_impulse_factor", "Impulse factor dinamico", dynamic.get("impulse_factor"), "", f"sensor_summaries.{sensor}.dynamic.impulse_factor"),
                    _sensor_metric(sensor, "dynamic_clearance_factor", "Clearance factor dinamico", dynamic.get("clearance_factor"), "", f"sensor_summaries.{sensor}.dynamic.clearance_factor"),
                    _sensor_metric(sensor, "dynamic_zero_crossing_rate", "Cruces por cero dinamicos", dynamic.get("zero_crossing_rate"), "ratio", f"sensor_summaries.{sensor}.dynamic.zero_crossing_rate"),
                    _sensor_metric(sensor, "dynamic_entropy", "Entropia dinamica", dynamic.get("entropy"), "", f"sensor_summaries.{sensor}.dynamic.entropy"),
                    _sensor_metric(sensor, "jerk_rms", "Jerk RMS", jerk.get("rms"), f"{units}/s", f"sensor_summaries.{sensor}.jerk.rms"),
                    _sensor_metric(sensor, "jerk_max_abs", "Jerk maximo absoluto", jerk.get("max_abs"), f"{units}/s", f"sensor_summaries.{sensor}.jerk.max_abs"),
                    _sensor_metric(sensor, "dominant_frequency_hz", "Frecuencia dominante", spectrum.get("dominant_frequency_hz"), "Hz", f"sensor_summaries.{sensor}.spectrum.dominant_frequency_hz"),
                    _sensor_metric(sensor, "dominant_amplitude", "Amplitud dominante", spectrum.get("dominant_amplitude"), units, f"sensor_summaries.{sensor}.spectrum.dominant_amplitude"),
                    _sensor_metric(sensor, "spectral_centroid_hz", "Centroide espectral", spectrum.get("spectral_centroid_hz"), "Hz", f"sensor_summaries.{sensor}.spectrum.spectral_centroid_hz"),
                    _sensor_metric(sensor, "spectral_bandwidth_hz", "Bandwidth espectral", spectrum.get("spectral_bandwidth_hz"), "Hz", f"sensor_summaries.{sensor}.spectrum.spectral_bandwidth_hz"),
                    _sensor_metric(sensor, "spectral_flatness", "Flatness espectral", spectrum.get("spectral_flatness"), "", f"sensor_summaries.{sensor}.spectrum.spectral_flatness"),
                    _sensor_metric(sensor, "spectral_entropy", "Entropia espectral", spectrum.get("spectral_entropy"), "", f"sensor_summaries.{sensor}.spectrum.spectral_entropy"),
                    _sensor_metric(sensor, "band_power_low", "Energia banda baja", (spectrum.get("band_powers") or {}).get("low_0_5_hz"), "power", f"sensor_summaries.{sensor}.spectrum.band_powers.low_0_5_hz"),
                    _sensor_metric(sensor, "band_power_mid", "Energia banda media", (spectrum.get("band_powers") or {}).get("mid_5_20_hz"), "power", f"sensor_summaries.{sensor}.spectrum.band_powers.mid_5_20_hz"),
                    _sensor_metric(sensor, "band_power_high", "Energia banda alta", (spectrum.get("band_powers") or {}).get("high_20_60_hz"), "power", f"sensor_summaries.{sensor}.spectrum.band_powers.high_20_60_hz"),
                ],
            }
        )
    return {
        "version_esquema": "1.0",
        "politica": "metricas_ventanas_500ms_para_baseline_anomalias",
        "grupos": groups,
    }


def _sensor_metric(sensor: str, key: str, label: str, value: object, unit: str, source: str) -> dict[str, object]:
    return _metric(f"{sensor}_{key}", label, value, unit, source)


def _metric(key: str, label: str, value: object, unit: str, source: str) -> dict[str, object]:
    return {"clave": key, "etiqueta": label, "valor": value, "unidad": unit, "fuente": source}


def _magnitude(series: SensorSeries) -> np.ndarray:
    return np.sqrt(series.x * series.x + series.y * series.y + series.z * series.z)


def _dynamic_component(t: np.ndarray, magnitude: np.ndarray) -> np.ndarray:
    if len(magnitude) < 3:
        return magnitude - float(np.mean(magnitude))
    fs = _estimated_sample_rate(t)
    trend_window = max(3, int(round(fs * 0.75))) if fs > 0 else 3
    trend_window = min(trend_window, len(magnitude))
    kernel = np.ones(trend_window, dtype=np.float64) / trend_window
    trend = np.convolve(magnitude, kernel, mode="same")
    return magnitude - trend


def _jerk(t: np.ndarray, magnitude: np.ndarray) -> np.ndarray:
    if len(t) < 2:
        return np.array([], dtype=np.float64)
    dt = np.diff(t)
    dm = np.diff(magnitude)
    valid = dt > 0
    if not np.any(valid):
        return np.array([], dtype=np.float64)
    return dm[valid] / dt[valid]


def _estimated_sample_rate(t: np.ndarray) -> float:
    if len(t) < 2:
        return 0.0
    dt = np.diff(t)
    dt = dt[dt > 0]
    if len(dt) == 0:
        return 0.0
    return float(1.0 / np.median(dt))


def _spectral_summary(t: np.ndarray, signal: np.ndarray) -> dict[str, object]:
    if len(signal) < 4:
        return _empty_spectrum()
    fs = _estimated_sample_rate(t)
    if fs <= 0:
        return _empty_spectrum()
    centered = signal - float(np.mean(signal))
    window = np.hanning(len(centered))
    spectrum = np.fft.rfft(centered * window)
    freqs = np.fft.rfftfreq(len(centered), d=1.0 / fs)
    amp = np.abs(spectrum) * 2.0 / max(float(np.sum(window)), 1.0)
    power = amp * amp
    valid = (freqs > 0.2) & (freqs <= fs / 2.0)
    if not np.any(valid):
        return _empty_spectrum()

    valid_freqs = freqs[valid]
    valid_amp = amp[valid]
    valid_power = power[valid]
    total_power = float(np.sum(valid_power))
    if total_power <= 1e-18:
        return _empty_spectrum()

    peak_index = int(np.argmax(valid_amp))
    centroid = float(np.sum(valid_freqs * valid_power) / total_power)
    bandwidth = float(np.sqrt(np.sum(((valid_freqs - centroid) ** 2) * valid_power) / total_power))
    normalized_power = valid_power / total_power
    entropy = float(-np.sum(normalized_power * np.log2(normalized_power + 1e-18)) / math.log2(len(normalized_power))) if len(normalized_power) > 1 else 0.0
    flatness = float(np.exp(np.mean(np.log(valid_power + 1e-18))) / (np.mean(valid_power) + 1e-18))

    return {
        "dominant_frequency_hz": _round(float(valid_freqs[peak_index])),
        "dominant_amplitude": _round(float(valid_amp[peak_index])),
        "spectral_centroid_hz": _round(centroid),
        "spectral_bandwidth_hz": _round(bandwidth),
        "spectral_flatness": _round(flatness),
        "spectral_entropy": _round(entropy),
        "total_power": _round(total_power),
        "band_powers": {
            "low_0_5_hz": _round(_band_power(valid_freqs, valid_power, 0.2, 5.0)),
            "mid_5_20_hz": _round(_band_power(valid_freqs, valid_power, 5.0, 20.0)),
            "high_20_60_hz": _round(_band_power(valid_freqs, valid_power, 20.0, min(60.0, fs / 2.0))),
        },
    }


def _empty_spectrum() -> dict[str, object]:
    return {
        "dominant_frequency_hz": None,
        "dominant_amplitude": None,
        "spectral_centroid_hz": None,
        "spectral_bandwidth_hz": None,
        "spectral_flatness": None,
        "spectral_entropy": None,
        "total_power": None,
        "band_powers": {
            "low_0_5_hz": None,
            "mid_5_20_hz": None,
            "high_20_60_hz": None,
        },
    }


def _band_power(freqs: np.ndarray, power: np.ndarray, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    mask = (freqs >= low) & (freqs < high)
    if not np.any(mask):
        return 0.0
    return float(np.sum(power[mask]))


def _stats(values: np.ndarray) -> dict[str, object]:
    if len(values) == 0:
        return {"mean": None, "std": None, "rms": None, "min": None, "max": None, "peak_to_peak": None}
    return {
        "mean": _round(float(np.mean(values))),
        "std": _round(float(np.std(values))),
        "rms": _round(_rms(values)),
        "min": _round(float(np.min(values))),
        "max": _round(float(np.max(values))),
        "peak_to_peak": _round(_peak_to_peak(values)),
        "skewness": _round(_skewness(values)),
        "kurtosis": _round(_kurtosis(values)),
        "crest_factor": _round(_crest_factor(values)),
    }


def _rms(values: np.ndarray) -> float:
    if len(values) == 0:
        return 0.0
    return float(np.sqrt(np.mean(values * values)))


def _peak_to_peak(values: np.ndarray) -> float:
    if len(values) == 0:
        return 0.0
    return float(np.max(values) - np.min(values))


def _skewness(values: np.ndarray) -> float | None:
    if len(values) < 2:
        return None
    centered = values - float(np.mean(values))
    std = float(np.std(values))
    if std <= 1e-18:
        return 0.0
    return float(np.mean((centered / std) ** 3))


def _kurtosis(values: np.ndarray) -> float | None:
    if len(values) < 2:
        return None
    centered = values - float(np.mean(values))
    std = float(np.std(values))
    if std <= 1e-18:
        return 0.0
    return float(np.mean((centered / std) ** 4))


def _crest_factor(values: np.ndarray) -> float | None:
    rms = _rms(values)
    if rms <= 1e-18:
        return None
    return float(np.max(np.abs(values)) / rms)


def _shape_factor(values: np.ndarray) -> float | None:
    mean_abs = float(np.mean(np.abs(values))) if len(values) else 0.0
    if mean_abs <= 1e-18:
        return None
    return float(_rms(values) / mean_abs)


def _impulse_factor(values: np.ndarray) -> float | None:
    mean_abs = float(np.mean(np.abs(values))) if len(values) else 0.0
    if mean_abs <= 1e-18:
        return None
    return float(np.max(np.abs(values)) / mean_abs)


def _clearance_factor(values: np.ndarray) -> float | None:
    if len(values) == 0:
        return None
    denominator = float(np.mean(np.sqrt(np.abs(values))) ** 2)
    if denominator <= 1e-18:
        return None
    return float(np.max(np.abs(values)) / denominator)


def _zero_crossing_rate(values: np.ndarray) -> float | None:
    if len(values) < 2:
        return None
    signs = np.signbit(values)
    return float(np.mean(signs[1:] != signs[:-1]))


def _signal_entropy(values: np.ndarray, bins: int = 32) -> float | None:
    if len(values) < 2:
        return None
    hist, _ = np.histogram(values, bins=bins)
    total = float(np.sum(hist))
    if total <= 0:
        return None
    probabilities = hist.astype(np.float64) / total
    probabilities = probabilities[probabilities > 0]
    if len(probabilities) <= 1:
        return 0.0
    return float(-np.sum(probabilities * np.log2(probabilities)) / math.log2(bins))


def _robust_scores(values: np.ndarray) -> np.ndarray:
    if len(values) == 0:
        return values
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    if mad <= 1e-12:
        std = float(np.std(values))
        if std <= 1e-12:
            return np.zeros_like(values)
        return np.maximum(0.0, (values - median) / std)
    return np.maximum(0.0, 0.6745 * (values - median) / mad)


def _severity(score: float) -> str:
    if score >= 6.0:
        return "critical"
    if score >= 3.5:
        return "high"
    if score >= 2.0:
        return "medium"
    return "normal"


def _mode_int(values: np.ndarray) -> int | None:
    if len(values) == 0:
        return None
    unique, counts = np.unique(values, return_counts=True)
    return int(unique[int(np.argmax(counts))])


def _metadata_value(metadata: dict[str, str], key: str) -> str | None:
    return metadata.get(key)


def _metadata_number(metadata: dict[str, str], key: str) -> float | None:
    value = metadata.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _round(value: float | None, digits: int = 6) -> float | None:
    if value is None or not math.isfinite(float(value)):
        return None
    return round(float(value), digits)
