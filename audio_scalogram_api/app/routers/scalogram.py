from __future__ import annotations

import base64

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse, Response

from app.analysis_engine import run_analysis_engine
from app.core.config import settings
from app.services.scalogram import build_scalogram, serialize_result


router = APIRouter(tags=["audioanalisys"])


def _metric(
    *,
    key: str,
    label: str,
    value: object | None,
    unit: str = "",
    source: str,
    description: str,
) -> dict[str, object]:
    return {
        "clave": key,
        "etiqueta": label,
        "valor": value,
        "unidad": unit,
        "fuente": source,
        "descripcion": description,
    }


def _group(key: str, label: str, metrics: list[dict[str, object]]) -> dict[str, object]:
    return {
        "clave": key,
        "etiqueta": label,
        "metricas": [metric for metric in metrics if metric["valor"] is not None],
    }


def build_metricas(
    *,
    legacy_payload: dict[str, object],
    engine_payload: dict[str, object],
) -> dict[str, object]:
    quality = engine_payload.get("quality") if isinstance(engine_payload.get("quality"), dict) else {}
    global_features = (
        engine_payload.get("global_features") if isinstance(engine_payload.get("global_features"), dict) else {}
    )
    basic_features = (
        global_features.get("basic_features") if isinstance(global_features.get("basic_features"), dict) else {}
    )
    temporal = engine_payload.get("temporal_summary") if isinstance(engine_payload.get("temporal_summary"), dict) else {}
    spectral = engine_payload.get("spectral_summary") if isinstance(engine_payload.get("spectral_summary"), dict) else {}
    cepstral = engine_payload.get("cepstral_summary") if isinstance(engine_payload.get("cepstral_summary"), dict) else {}
    time_frequency = (
        engine_payload.get("time_frequency_summary")
        if isinstance(engine_payload.get("time_frequency_summary"), dict)
        else {}
    )
    autocorrelation = (
        legacy_payload.get("autocorrelation_analysis")
        if isinstance(legacy_payload.get("autocorrelation_analysis"), dict)
        else {}
    )

    mfcc_mean = cepstral.get("mfcc_mean") if isinstance(cepstral.get("mfcc_mean"), list) else []
    mfcc_std = cepstral.get("mfcc_std") if isinstance(cepstral.get("mfcc_std"), list) else []
    delta_mfcc_mean = cepstral.get("delta_mfcc_mean") if isinstance(cepstral.get("delta_mfcc_mean"), list) else []
    delta_mfcc_std = cepstral.get("delta_mfcc_std") if isinstance(cepstral.get("delta_mfcc_std"), list) else []
    spectral_envelope = (
        cepstral.get("spectral_envelope_summary")
        if isinstance(cepstral.get("spectral_envelope_summary"), dict)
        else {}
    )
    psd_summary = (
        spectral.get("power_spectral_density_summary")
        if isinstance(spectral.get("power_spectral_density_summary"), dict)
        else {}
    )
    modulation_summary = (
        time_frequency.get("modulation_energy_summary")
        if isinstance(time_frequency.get("modulation_energy_summary"), dict)
        else {}
    )

    groups = [
        _group(
            "signal_quality",
            "Calidad de senal",
            [
                _metric(
                    key="quality_flag",
                    label="Bandera de calidad",
                    value=quality.get("quality_flag"),
                    source="analysis_engine.quality.quality_flag",
                    description="Estado general de validacion tecnica del audio.",
                ),
                _metric(
                    key="valid_audio",
                    label="Audio valido",
                    value=quality.get("valid_audio"),
                    source="analysis_engine.quality.valid_audio",
                    description="Indica si el audio cumple las reglas basicas de analisis.",
                ),
                _metric(
                    key="silence_sample_ratio",
                    label="Silencio por muestras",
                    value=quality.get("silence_ratio"),
                    unit="ratio",
                    source="analysis_engine.quality.silence_ratio",
                    description="Proporcion de muestras por debajo del umbral de energia.",
                ),
                _metric(
                    key="active_ratio",
                    label="Actividad",
                    value=quality.get("active_ratio"),
                    unit="ratio",
                    source="analysis_engine.quality.active_ratio",
                    description="Proporcion de muestras con actividad util de senal.",
                ),
                _metric(
                    key="silence_frame_ratio",
                    label="Silencio por frames",
                    value=temporal.get("silence_frame_ratio"),
                    unit="ratio",
                    source="analysis_engine.temporal_summary.silence_frame_ratio",
                    description="Proporcion de frames internos clasificados como silenciosos.",
                ),
                _metric(
                    key="clipping_ratio",
                    label="Clipping",
                    value=quality.get("clipping_ratio"),
                    unit="ratio",
                    source="analysis_engine.quality.clipping_ratio",
                    description="Proporcion de muestras cercanas al maximo digital.",
                ),
                _metric(
                    key="snr_estimate",
                    label="SNR estimado",
                    value=quality.get("snr_estimate"),
                    unit="dB",
                    source="analysis_engine.quality.snr_estimate",
                    description="SNR estimado.",
                ),
                _metric(
                    key="estimated_noise_floor",
                    label="Piso de ruido estimado",
                    value=quality.get("estimated_noise_floor"),
                    source="analysis_engine.quality.estimated_noise_floor",
                    description="Percentil bajo de amplitud usado como aproximacion del ruido de fondo.",
                ),
                _metric(
                    key="dc_offset",
                    label="DC offset",
                    value=quality.get("dc_offset"),
                    source="analysis_engine.quality.dc_offset",
                    description="Desplazamiento medio de la forma de onda.",
                ),
                _metric(
                    key="mean_amplitude",
                    label="Amplitud media",
                    value=quality.get("mean_amplitude"),
                    source="analysis_engine.quality.mean_amplitude",
                    description="Amplitud absoluta media del audio normalizado internamente.",
                ),
            ],
        ),
        _group(
            "amplitude_energy",
            "Amplitud y energia",
            [
                _metric(
                    key="rms_mean",
                    label="RMS medio",
                    value=basic_features.get("rms_mean"),
                    source="analysis_engine.global_features.basic_features.rms_mean",
                    description="Energia RMS media agregada del audio completo.",
                ),
                _metric(
                    key="rms_std",
                    label="RMS desviacion",
                    value=basic_features.get("rms_std"),
                    source="analysis_engine.global_features.basic_features.rms_std",
                    description="Variabilidad de energia RMS agregada.",
                ),
                _metric(
                    key="rms_min",
                    label="RMS minimo",
                    value=basic_features.get("rms_min"),
                    source="analysis_engine.global_features.basic_features.rms_min",
                    description="Energia RMS minima observada.",
                ),
                _metric(
                    key="rms_max",
                    label="RMS maximo",
                    value=basic_features.get("rms_max"),
                    source="analysis_engine.global_features.basic_features.rms_max",
                    description="Energia RMS maxima observada.",
                ),
                _metric(
                    key="rms_median",
                    label="RMS mediano",
                    value=basic_features.get("rms_median"),
                    source="analysis_engine.global_features.basic_features.rms_median",
                    description="Mediana de energia RMS agregada.",
                ),
                _metric(
                    key="short_time_energy_mean",
                    label="Energia corta media",
                    value=basic_features.get("short_time_energy_mean"),
                    source="analysis_engine.global_features.basic_features.short_time_energy_mean",
                    description="Energia media calculada en ventanas cortas.",
                ),
                _metric(
                    key="short_time_energy_std",
                    label="Energia corta desviacion",
                    value=basic_features.get("short_time_energy_std"),
                    source="analysis_engine.global_features.basic_features.short_time_energy_std",
                    description="Variabilidad de energia en ventanas cortas.",
                ),
                _metric(
                    key="zero_crossing_rate_mean",
                    label="Cruces por cero medios",
                    value=basic_features.get("zero_crossing_rate_mean"),
                    unit="ratio",
                    source="analysis_engine.global_features.basic_features.zero_crossing_rate_mean",
                    description="Tasa media de cambios de signo de la senal.",
                ),
                _metric(
                    key="zero_crossing_rate_std",
                    label="Cruces por cero desviacion",
                    value=basic_features.get("zero_crossing_rate_std"),
                    unit="ratio",
                    source="analysis_engine.global_features.basic_features.zero_crossing_rate_std",
                    description="Variabilidad de la tasa de cruces por cero.",
                ),
                _metric(
                    key="peak_amplitude",
                    label="Pico de amplitud",
                    value=quality.get("peak_amplitude"),
                    source="analysis_engine.quality.peak_amplitude",
                    description="Maximo absoluto de amplitud tras carga y normalizacion interna.",
                ),
                _metric(
                    key="crest_factor",
                    label="Crest factor",
                    value=basic_features.get("crest_factor"),
                    source="analysis_engine.global_features.basic_features.crest_factor",
                    description="Relacion entre pico y energia RMS.",
                ),
                _metric(
                    key="peak_count",
                    label="Picos de amplitud",
                    value=basic_features.get("peak_count"),
                    source="analysis_engine.global_features.basic_features.peak_count",
                    description="Cantidad agregada de picos relevantes de amplitud.",
                ),
                _metric(
                    key="dynamic_range_db",
                    label="Rango dinamico",
                    value=basic_features.get("dynamic_range_db"),
                    unit="dB",
                    source="analysis_engine.global_features.basic_features.dynamic_range_db",
                    description="Diferencia en dB entre zonas de baja y alta energia RMS.",
                ),
                _metric(
                    key="active_duration_seconds",
                    label="Duracion activa",
                    value=basic_features.get("active_duration_seconds"),
                    unit="s",
                    source="analysis_engine.global_features.basic_features.active_duration_seconds",
                    description="Tiempo estimado con actividad util de senal.",
                ),
                _metric(
                    key="energy_entropy",
                    label="Entropia de energia",
                    value=basic_features.get("energy_entropy"),
                    source="analysis_engine.global_features.basic_features.energy_entropy",
                    description="Dispersion temporal de la energia agregada.",
                ),
            ],
        ),
        _group(
            "temporal_structure",
            "Estructura temporal",
            [
                _metric(
                    key="stability_index",
                    label="Indice de estabilidad",
                    value=temporal.get("stability_index"),
                    unit="ratio",
                    source="analysis_engine.temporal_summary.stability_index",
                    description="Consistencia temporal agregada desde los frames internos.",
                ),
                _metric(
                    key="variability_index",
                    label="Indice de variabilidad",
                    value=temporal.get("variability_index"),
                    unit="ratio",
                    source="analysis_engine.temporal_summary.variability_index",
                    description="Variacion temporal relativa entre frames internos.",
                ),
                _metric(
                    key="num_energy_peaks",
                    label="Picos de energia",
                    value=temporal.get("num_energy_peaks"),
                    source="analysis_engine.temporal_summary.num_energy_peaks",
                    description="Numero de picos detectados en la energia por frames.",
                ),
                _metric(
                    key="time_to_peak_seconds",
                    label="Tiempo al pico",
                    value=temporal.get("time_to_peak_seconds"),
                    unit="s",
                    source="analysis_engine.temporal_summary.time_to_peak_seconds",
                    description="Tiempo hasta el frame de mayor energia.",
                ),
                _metric(
                    key="early_energy_ratio",
                    label="Energia inicial",
                    value=temporal.get("early_energy_ratio"),
                    unit="ratio",
                    source="analysis_engine.temporal_summary.early_energy_ratio",
                    description="Proporcion de energia ubicada en el primer tercio del audio.",
                ),
                _metric(
                    key="middle_energy_ratio",
                    label="Energia media",
                    value=temporal.get("middle_energy_ratio"),
                    unit="ratio",
                    source="analysis_engine.temporal_summary.middle_energy_ratio",
                    description="Proporcion de energia ubicada en el tercio central.",
                ),
                _metric(
                    key="late_energy_ratio",
                    label="Energia final",
                    value=temporal.get("late_energy_ratio"),
                    unit="ratio",
                    source="analysis_engine.temporal_summary.late_energy_ratio",
                    description="Proporcion de energia ubicada en el ultimo tercio.",
                ),
            ],
        ),
        _group(
            "autocorrelation",
            "Autocorrelacion",
            [
                _metric(
                    key="autocorrelation_peak_count",
                    label="Picos de autocorrelacion",
                    value=autocorrelation.get("peak_count"),
                    source="autocorrelation_analysis.peak_count",
                    description="Numero de picos encontrados en autocorrelacion.",
                ),
                _metric(
                    key="strongest_peak_lag_seconds",
                    label="Lag del primer pico",
                    value=autocorrelation.get("strongest_peak_lag_seconds"),
                    unit="s",
                    source="autocorrelation_analysis.strongest_peak_lag_seconds",
                    description="Retardo del pico de autocorrelacion mas fuerte.",
                ),
                _metric(
                    key="second_peak_lag_seconds",
                    label="Lag del segundo pico",
                    value=autocorrelation.get("second_peak_lag_seconds"),
                    unit="s",
                    source="autocorrelation_analysis.second_peak_lag_seconds",
                    description="Retardo del segundo pico mas fuerte.",
                ),
                _metric(
                    key="peak_distance_seconds",
                    label="Distancia entre picos",
                    value=autocorrelation.get("peak_distance_seconds"),
                    unit="s",
                    source="autocorrelation_analysis.peak_distance_seconds",
                    description="Separacion temporal entre los dos picos principales.",
                ),
                _metric(
                    key="peak_distance_samples",
                    label="Distancia entre picos",
                    value=autocorrelation.get("peak_distance_samples"),
                    unit="samples",
                    source="autocorrelation_analysis.peak_distance_samples",
                    description="Separacion en muestras entre los dos picos principales.",
                ),
            ],
        ),
        _group(
            "spectral",
            "Espectral",
            [
                _metric(
                    key="dominant_frequency_hz",
                    label="Frecuencia dominante",
                    value=spectral.get("dominant_frequency"),
                    unit="Hz",
                    source="analysis_engine.spectral_summary.dominant_frequency",
                    description="Frecuencia principal calculada por el motor canonico.",
                ),
                _metric(
                    key="spectral_centroid_mean_hz",
                    label="Centroide espectral medio",
                    value=spectral.get("spectral_centroid_mean"),
                    unit="Hz",
                    source="analysis_engine.spectral_summary.spectral_centroid_mean",
                    description="Centro de masa espectral medio.",
                ),
                _metric(
                    key="spectral_centroid_std_hz",
                    label="Centroide espectral desviacion",
                    value=spectral.get("spectral_centroid_std"),
                    unit="Hz",
                    source="analysis_engine.spectral_summary.spectral_centroid_std",
                    description="Variabilidad del centro de masa espectral.",
                ),
                _metric(
                    key="spectral_bandwidth_mean_hz",
                    label="Ancho de banda espectral medio",
                    value=spectral.get("spectral_bandwidth_mean"),
                    unit="Hz",
                    source="analysis_engine.spectral_summary.spectral_bandwidth_mean",
                    description="Dispersion media de energia alrededor del centroide.",
                ),
                _metric(
                    key="spectral_bandwidth_std_hz",
                    label="Ancho de banda espectral desviacion",
                    value=spectral.get("spectral_bandwidth_std"),
                    unit="Hz",
                    source="analysis_engine.spectral_summary.spectral_bandwidth_std",
                    description="Variabilidad de la dispersion espectral.",
                ),
                _metric(
                    key="spectral_rolloff_85_mean_hz",
                    label="Rolloff 85",
                    value=spectral.get("spectral_rolloff_85_mean"),
                    unit="Hz",
                    source="analysis_engine.spectral_summary.spectral_rolloff_85_mean",
                    description="Frecuencia bajo la que se acumula el 85% de energia.",
                ),
                _metric(
                    key="spectral_rolloff_95_mean_hz",
                    label="Rolloff 95",
                    value=spectral.get("spectral_rolloff_95_mean"),
                    unit="Hz",
                    source="analysis_engine.spectral_summary.spectral_rolloff_95_mean",
                    description="Frecuencia bajo la que se acumula el 95% de energia.",
                ),
                _metric(
                    key="spectral_flatness_mean",
                    label="Flatness espectral",
                    value=spectral.get("spectral_flatness_mean"),
                    unit="ratio",
                    source="analysis_engine.spectral_summary.spectral_flatness_mean",
                    description="Relacion entre textura tonal y ruidosa segun el motor canonico.",
                ),
                _metric(
                    key="spectral_flux_mean",
                    label="Flux espectral",
                    value=spectral.get("spectral_flux_mean"),
                    source="analysis_engine.spectral_summary.spectral_flux_mean",
                    description="Cambio medio del espectro a lo largo del tiempo.",
                ),
                _metric(
                    key="spectral_contrast_mean",
                    label="Contraste espectral",
                    value=spectral.get("spectral_contrast_mean"),
                    unit="dB",
                    source="analysis_engine.spectral_summary.spectral_contrast_mean",
                    description="Separacion media entre valles y picos espectrales.",
                ),
                _metric(
                    key="dominant_power",
                    label="Potencia dominante",
                    value=spectral.get("dominant_power"),
                    source="analysis_engine.spectral_summary.dominant_power",
                    description="Potencia asociada a la frecuencia dominante.",
                ),
                _metric(
                    key="band_energy_entropy",
                    label="Entropia de bandas",
                    value=spectral.get("band_energy_entropy"),
                    source="analysis_engine.spectral_summary.band_energy_entropy",
                    description="Distribucion de energia entre bandas.",
                ),
                _metric(
                    key="psd_total_power",
                    label="PSD potencia total",
                    value=psd_summary.get("total_power"),
                    source="analysis_engine.spectral_summary.power_spectral_density_summary.total_power",
                    description="Potencia total resumida de la densidad espectral.",
                ),
                _metric(
                    key="psd_mean_power",
                    label="PSD potencia media",
                    value=psd_summary.get("mean_power"),
                    source="analysis_engine.spectral_summary.power_spectral_density_summary.mean_power",
                    description="Potencia media resumida de la densidad espectral.",
                ),
                _metric(
                    key="psd_max_power",
                    label="PSD potencia maxima",
                    value=psd_summary.get("max_power"),
                    source="analysis_engine.spectral_summary.power_spectral_density_summary.max_power",
                    description="Potencia maxima resumida de la densidad espectral.",
                ),
                _metric(
                    key="psd_max_power_frequency_hz",
                    label="PSD frecuencia de potencia maxima",
                    value=psd_summary.get("max_power_frequency"),
                    unit="Hz",
                    source="analysis_engine.spectral_summary.power_spectral_density_summary.max_power_frequency",
                    description="Frecuencia asociada a la maxima potencia PSD resumida.",
                ),
            ],
        ),
        _group(
            "band_energy",
            "Energia por bandas",
            [
                _metric(
                    key="low_band_energy_ratio",
                    label="Banda baja",
                    value=spectral.get("low_band_energy_ratio"),
                    unit="ratio",
                    source="analysis_engine.spectral_summary.low_band_energy_ratio",
                    description="Proporcion de energia en banda baja.",
                ),
                _metric(
                    key="mid_band_energy_ratio",
                    label="Banda media",
                    value=spectral.get("mid_band_energy_ratio"),
                    unit="ratio",
                    source="analysis_engine.spectral_summary.mid_band_energy_ratio",
                    description="Proporcion de energia en banda media.",
                ),
                _metric(
                    key="high_band_energy_ratio",
                    label="Banda alta",
                    value=spectral.get("high_band_energy_ratio"),
                    unit="ratio",
                    source="analysis_engine.spectral_summary.high_band_energy_ratio",
                    description="Proporcion de energia en banda alta.",
                ),
            ],
        ),
        _group(
            "cepstral",
            "Cepstral",
            [
                *[
                    _metric(
                        key=f"mfcc_{index}_mean",
                        label=f"MFCC {index} medio",
                        value=value,
                        source=f"analysis_engine.cepstral_summary.mfcc_mean.{index}",
                        description="Coeficiente cepstral medio agregado del audio completo.",
                    )
                    for index, value in enumerate(mfcc_mean)
                ],
                *[
                    _metric(
                        key=f"mfcc_{index}_std",
                        label=f"MFCC {index} std",
                        value=value,
                        source=f"analysis_engine.cepstral_summary.mfcc_std.{index}",
                        description="Variabilidad del coeficiente cepstral en el audio completo.",
                    )
                    for index, value in enumerate(mfcc_std)
                ],
                *[
                    _metric(
                        key=f"delta_mfcc_{index}_mean",
                        label=f"Delta MFCC {index} medio",
                        value=value,
                        source=f"analysis_engine.cepstral_summary.delta_mfcc_mean.{index}",
                        description="Cambio medio del coeficiente cepstral.",
                    )
                    for index, value in enumerate(delta_mfcc_mean)
                ],
                *[
                    _metric(
                        key=f"delta_mfcc_{index}_std",
                        label=f"Delta MFCC {index} std",
                        value=value,
                        source=f"analysis_engine.cepstral_summary.delta_mfcc_std.{index}",
                        description="Variabilidad del cambio del coeficiente cepstral.",
                    )
                    for index, value in enumerate(delta_mfcc_std)
                ],
                _metric(
                    key="spectral_envelope_mean_log_energy",
                    label="Envolvente espectral energia log media",
                    value=spectral_envelope.get("mean_log_energy"),
                    source="analysis_engine.cepstral_summary.spectral_envelope_summary.mean_log_energy",
                    description="Energia log media de la envolvente espectral.",
                ),
                _metric(
                    key="spectral_envelope_std_log_energy",
                    label="Envolvente espectral energia log desviacion",
                    value=spectral_envelope.get("std_log_energy"),
                    source="analysis_engine.cepstral_summary.spectral_envelope_summary.std_log_energy",
                    description="Variabilidad de energia log en la envolvente espectral.",
                ),
                _metric(
                    key="spectral_envelope_min_log_energy",
                    label="Envolvente espectral energia log minima",
                    value=spectral_envelope.get("min_log_energy"),
                    source="analysis_engine.cepstral_summary.spectral_envelope_summary.min_log_energy",
                    description="Energia log minima de la envolvente espectral.",
                ),
                _metric(
                    key="spectral_envelope_max_log_energy",
                    label="Envolvente espectral energia log maxima",
                    value=spectral_envelope.get("max_log_energy"),
                    source="analysis_engine.cepstral_summary.spectral_envelope_summary.max_log_energy",
                    description="Energia log maxima de la envolvente espectral.",
                ),
            ],
        ),
        _group(
            "time_frequency",
            "Tiempo-frecuencia",
            [
                _metric(
                    key="time_frequency_enabled",
                    label="Tiempo-frecuencia habilitado",
                    value=time_frequency.get("enabled"),
                    source="analysis_engine.time_frequency_summary.enabled",
                    description="Indica si el modulo tiempo-frecuencia extendido esta activo.",
                ),
                _metric(
                    key="time_frequency_status",
                    label="Estado tiempo-frecuencia",
                    value=time_frequency.get("status"),
                    source="analysis_engine.time_frequency_summary.status",
                    description="Estado del modulo tiempo-frecuencia extendido.",
                ),
                _metric(
                    key="time_frequency_reason",
                    label="Motivo",
                    value=time_frequency.get("reason"),
                    source="analysis_engine.time_frequency_summary.reason",
                    description="Motivo tecnico cuando el modulo esta deshabilitado o falla.",
                ),
                _metric(
                    key="wavelet_entropy",
                    label="Entropia wavelet",
                    value=time_frequency.get("wavelet_entropy"),
                    source="analysis_engine.time_frequency_summary.wavelet_entropy",
                    description="Dispersion de energia entre escalas wavelet.",
                ),
                _metric(
                    key="time_frequency_concentration",
                    label="Concentracion tiempo-frecuencia",
                    value=time_frequency.get("time_frequency_concentration"),
                    unit="ratio",
                    source="analysis_engine.time_frequency_summary.time_frequency_concentration",
                    description="Proporcion de energia concentrada en las celdas tiempo-frecuencia mas intensas.",
                ),
                _metric(
                    key="frequency_centroid_timefreq_hz",
                    label="Centroide tiempo-frecuencia",
                    value=time_frequency.get("frequency_centroid_timefreq"),
                    unit="Hz",
                    source="analysis_engine.time_frequency_summary.frequency_centroid_timefreq",
                    description="Centroide frecuencial derivado del resumen tiempo-frecuencia.",
                ),
                _metric(
                    key="frequency_spread_timefreq_hz",
                    label="Dispersion tiempo-frecuencia",
                    value=time_frequency.get("frequency_spread_timefreq"),
                    unit="Hz",
                    source="analysis_engine.time_frequency_summary.frequency_spread_timefreq",
                    description="Dispersion frecuencial derivada del resumen tiempo-frecuencia.",
                ),
                _metric(
                    key="transient_index",
                    label="Indice transitorio",
                    value=time_frequency.get("transient_index"),
                    source="analysis_engine.time_frequency_summary.transient_index",
                    description="Variabilidad temporal de energia en el plano tiempo-frecuencia.",
                ),
                _metric(
                    key="modulation_energy_mean",
                    label="Modulacion energia media",
                    value=modulation_summary.get("mean"),
                    source="analysis_engine.time_frequency_summary.modulation_energy_summary.mean",
                    description="Cambio medio de energia temporal dentro del resumen tiempo-frecuencia.",
                ),
                _metric(
                    key="modulation_energy_std",
                    label="Modulacion energia desviacion",
                    value=modulation_summary.get("std"),
                    source="analysis_engine.time_frequency_summary.modulation_energy_summary.std",
                    description="Variabilidad del cambio de energia temporal.",
                ),
                _metric(
                    key="modulation_energy_max",
                    label="Modulacion energia maxima",
                    value=modulation_summary.get("max"),
                    source="analysis_engine.time_frequency_summary.modulation_energy_summary.max",
                    description="Cambio maximo de energia temporal.",
                ),
            ],
        ),
    ]

    return {
        "version_esquema": "1.0",
        "politica": "metricas_canonicas_unificadas",
        "grupos": [group for group in groups if group["metricas"]],
    }


def build_json_payload(
    *,
    result: object,
    legacy_payload: dict[str, object],
    analysis_engine_payload: dict[str, object],
    filename: str | None,
) -> dict[str, object]:
    return {
        "analysis_version": result.analysis_version,
        "primary_visualization": result.primary_image.key,
        "metricas": build_metricas(
            legacy_payload=legacy_payload,
            engine_payload=analysis_engine_payload,
        ),
        "plots": legacy_payload.get("plots", {}),
        "content_type": "image/png",
        "filename": f"{filename or 'analysis'}.png",
        "image_base64": base64.b64encode(result.primary_image.image_bytes).decode("ascii"),
        "encoding": "base64",
    }


@router.post(
    "/audioanalisys",
    responses={
        200: {"content": {"image/png": {}}},
    },
)
@router.post(
    "/scalogram",
    include_in_schema=False,
    responses={
        200: {"content": {"image/png": {}}},
    },
)
async def create_audioanalisys(
    audio_file: UploadFile = File(...),
    sample_rate: int | None = Form(default=None),
    wavelet: str | None = Form(default=None),
    width_min: int | None = Form(default=None),
    width_max: int | None = Form(default=None),
    colormap: str | None = Form(default=None),
    visualization: str = Form(default="dashboard"),
    audio_description: str | None = Form(default=None),
    output: str = Form(default="image"),
):
    if output not in {"image", "json"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid output format. Use 'image' or 'json'.",
        )

    contents = await audio_file.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(contents) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded audio file is empty.",
        )
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File is too large. Max upload size is {settings.max_upload_size_mb} MB.",
        )

    try:
        result = build_scalogram(
            contents,
            sample_rate=sample_rate,
            wavelet=wavelet,
            width_min=width_min,
            width_max=width_max,
            colormap=colormap,
            visualization=visualization,
            audio_description=audio_description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unable to process the provided audio file: {exc}",
        ) from exc

    if output == "json":
        legacy_payload = serialize_result(result, include_images=True)
        analysis_engine_payload = run_analysis_engine(
            audio_input=contents,
            sample_rate=sample_rate,
            original_format=(
                audio_file.filename.rsplit(".", 1)[-1]
                if audio_file.filename and "." in audio_file.filename
                else None
            ),
            filename=audio_file.filename,
        )
        payload = build_json_payload(
            result=result,
            legacy_payload=legacy_payload,
            analysis_engine_payload=analysis_engine_payload,
            filename=audio_file.filename,
        )
        return JSONResponse(payload)

    return Response(
        content=result.primary_image.image_bytes,
        media_type="image/png",
        headers={
            "Content-Disposition": f'inline; filename="{audio_file.filename or visualization}.png"',
            "X-Analysis-Sample-Rate": str(result.metadata.sample_rate),
            "X-Analysis-Duration": str(result.metadata.duration_seconds),
            "X-Analysis-Visualization": result.primary_image.key,
            "X-Analysis-Wavelet": result.scalogram_config.wavelet,
        },
    )
