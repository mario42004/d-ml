from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass
from typing import Iterable

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

    return {
        "analysis_version": "1.0",
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
    dominant = _dominant_frequency(series.t, dynamic)
    jerk = _jerk(series.t, magnitude)

    return {
        "sample_count": int(len(series.t)),
        "duration_seconds": _round(float(series.t[-1] - series.t[0])) if len(series.t) > 1 else 0.0,
        "estimated_sample_rate_hz": _round(fs),
        "accuracy_mode": _mode_int(series.accuracy),
        "axis_units": "m/s^2" if series.name == "accelerometer" else "rad/s",
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
        },
        "jerk": {
            "rms": _round(_rms(jerk)),
            "max_abs": _round(float(np.max(np.abs(jerk)))) if len(jerk) else None,
        },
        "spectrum": dominant,
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
        "axis_peak_to_peak": {
            "x": _round(_peak_to_peak(series.x)),
            "y": _round(_peak_to_peak(series.y)),
            "z": _round(_peak_to_peak(series.z)),
        },
        "jerk_rms": _round(_rms(jerk)),
        "jerk_max_abs": _round(float(np.max(np.abs(jerk)))) if len(jerk) else None,
        "dominant_frequency_hz": _dominant_frequency(series.t, dynamic)["frequency_hz"],
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


def _build_metricas(sensor_summaries: dict[str, dict[str, object]]) -> dict[str, object]:
    groups = []
    for sensor, summary in sensor_summaries.items():
        dynamic = summary.get("dynamic") if isinstance(summary.get("dynamic"), dict) else {}
        jerk = summary.get("jerk") if isinstance(summary.get("jerk"), dict) else {}
        spectrum = summary.get("spectrum") if isinstance(summary.get("spectrum"), dict) else {}
        magnitude = summary.get("magnitude") if isinstance(summary.get("magnitude"), dict) else {}
        groups.append(
            {
                "clave": sensor,
                "etiqueta": "Acelerometro" if sensor == "accelerometer" else "Giroscopio",
                "metricas": [
                    _metric("sample_count", "Muestras", summary.get("sample_count"), "", f"sensor_summaries.{sensor}.sample_count"),
                    _metric(
                        "estimated_sample_rate_hz",
                        "Frecuencia estimada",
                        summary.get("estimated_sample_rate_hz"),
                        "Hz",
                        f"sensor_summaries.{sensor}.estimated_sample_rate_hz",
                    ),
                    _metric(
                        "magnitude_mean",
                        "Magnitud media",
                        magnitude.get("mean"),
                        str(summary.get("axis_units") or ""),
                        f"sensor_summaries.{sensor}.magnitude.mean",
                    ),
                    _metric(
                        "dynamic_rms",
                        "RMS dinamico",
                        dynamic.get("rms"),
                        str(summary.get("axis_units") or ""),
                        f"sensor_summaries.{sensor}.dynamic.rms",
                    ),
                    _metric(
                        "dynamic_peak_abs",
                        "Pico dinamico absoluto",
                        dynamic.get("peak_abs"),
                        str(summary.get("axis_units") or ""),
                        f"sensor_summaries.{sensor}.dynamic.peak_abs",
                    ),
                    _metric(
                        "jerk_rms",
                        "Jerk RMS",
                        jerk.get("rms"),
                        f"{summary.get('axis_units')}/s",
                        f"sensor_summaries.{sensor}.jerk.rms",
                    ),
                    _metric(
                        "dominant_frequency_hz",
                        "Frecuencia dominante",
                        spectrum.get("frequency_hz"),
                        "Hz",
                        f"sensor_summaries.{sensor}.spectrum.frequency_hz",
                    ),
                ],
            }
        )
    return {
        "version_esquema": "1.0",
        "politica": "metricas_ventanas_500ms_para_baseline_anomalias",
        "grupos": groups,
    }


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


def _dominant_frequency(t: np.ndarray, signal: np.ndarray) -> dict[str, object]:
    if len(signal) < 4:
        return {"frequency_hz": None, "amplitude": None}
    fs = _estimated_sample_rate(t)
    if fs <= 0:
        return {"frequency_hz": None, "amplitude": None}
    centered = signal - float(np.mean(signal))
    window = np.hanning(len(centered))
    spectrum = np.fft.rfft(centered * window)
    freqs = np.fft.rfftfreq(len(centered), d=1.0 / fs)
    amp = np.abs(spectrum) * 2.0 / max(float(np.sum(window)), 1.0)
    valid = (freqs > 0.2) & (freqs <= fs / 2.0)
    if not np.any(valid):
        return {"frequency_hz": None, "amplitude": None}
    index = int(np.argmax(amp[valid]))
    return {
        "frequency_hz": _round(float(freqs[valid][index])),
        "amplitude": _round(float(amp[valid][index])),
    }


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
    }


def _rms(values: np.ndarray) -> float:
    if len(values) == 0:
        return 0.0
    return float(np.sqrt(np.mean(values * values)))


def _peak_to_peak(values: np.ndarray) -> float:
    if len(values) == 0:
        return 0.0
    return float(np.max(values) - np.min(values))


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
