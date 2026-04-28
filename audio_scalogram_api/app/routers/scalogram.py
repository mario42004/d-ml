from __future__ import annotations

import base64

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse, Response

from app.analysis_engine import run_analysis_engine
from app.core.config import settings
from app.services.scalogram import build_scalogram, serialize_result


router = APIRouter(tags=["audioanalisys"])


def _get_nested(source: dict[str, object], path: list[str]) -> object | None:
    value: object = source
    for segment in path:
        if not isinstance(value, dict) or segment not in value:
            return None
        value = value[segment]
    return value


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
        "key": key,
        "label": label,
        "value": value,
        "unit": unit,
        "source": source,
        "description": description,
    }


def _group(key: str, label: str, metrics: list[dict[str, object]]) -> dict[str, object]:
    return {
        "key": key,
        "label": label,
        "metrics": [metric for metric in metrics if metric["value"] is not None],
    }


def build_coherent_metrics(
    *,
    legacy_payload: dict[str, object],
    engine_payload: dict[str, object],
) -> dict[str, object]:
    quality = engine_payload.get("quality") if isinstance(engine_payload.get("quality"), dict) else {}
    input_audio = engine_payload.get("input_audio") if isinstance(engine_payload.get("input_audio"), dict) else {}
    framing = engine_payload.get("framing") if isinstance(engine_payload.get("framing"), dict) else {}
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

    groups = [
        _group(
            "audio_context",
            "Audio y contexto de analisis",
            [
                _metric(
                    key="duration_seconds",
                    label="Duracion",
                    value=input_audio.get("duration_seconds") or quality.get("duration_seconds"),
                    unit="s",
                    source="analysis_engine.input_audio.duration_seconds",
                    description="Duracion total del audio analizado.",
                ),
                _metric(
                    key="sample_rate_original_hz",
                    label="Sample rate original",
                    value=quality.get("sample_rate_original"),
                    unit="Hz",
                    source="analysis_engine.quality.sample_rate_original",
                    description="Frecuencia de muestreo detectada en el archivo original.",
                ),
                _metric(
                    key="sample_rate_analysis_hz",
                    label="Sample rate de analisis",
                    value=input_audio.get("internal_sample_rate") or quality.get("sample_rate_internal"),
                    unit="Hz",
                    source="analysis_engine.input_audio.internal_sample_rate",
                    description="Frecuencia usada por el motor canonico de analisis.",
                ),
                _metric(
                    key="channels_original",
                    label="Canales originales",
                    value=input_audio.get("channels_original") or quality.get("channels_original"),
                    source="analysis_engine.input_audio.channels_original",
                    description="Numero de canales detectados antes de convertir internamente a mono.",
                ),
                _metric(
                    key="frame_count",
                    label="Frames internos",
                    value=framing.get("frame_count"),
                    source="analysis_engine.framing.frame_count",
                    description="Cantidad de frames usados para agregacion interna.",
                ),
                _metric(
                    key="frame_duration_seconds",
                    label="Duracion de frame",
                    value=framing.get("frame_duration_seconds"),
                    unit="s",
                    source="analysis_engine.framing.frame_duration_seconds",
                    description="Duracion objetivo de cada frame interno.",
                ),
                _metric(
                    key="max_audio_duration_seconds",
                    label="Duracion maxima admitida",
                    value=quality.get("max_allowed_duration_seconds"),
                    unit="s",
                    source="analysis_engine.quality.max_allowed_duration_seconds",
                    description="Limite de duracion aplicado por la API.",
                ),
            ],
        ),
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
                    key="dc_offset",
                    label="DC offset",
                    value=quality.get("dc_offset"),
                    source="analysis_engine.quality.dc_offset",
                    description="Desplazamiento medio de la forma de onda.",
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
                    key="active_duration_seconds",
                    label="Duracion activa",
                    value=basic_features.get("active_duration_seconds"),
                    unit="s",
                    source="analysis_engine.global_features.basic_features.active_duration_seconds",
                    description="Tiempo estimado con actividad util de senal.",
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
                    key="spectral_bandwidth_mean_hz",
                    label="Ancho de banda espectral medio",
                    value=spectral.get("spectral_bandwidth_mean"),
                    unit="Hz",
                    source="analysis_engine.spectral_summary.spectral_bandwidth_mean",
                    description="Dispersion media de energia alrededor del centroide.",
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
                    key="band_energy_entropy",
                    label="Entropia de bandas",
                    value=spectral.get("band_energy_entropy"),
                    source="analysis_engine.spectral_summary.band_energy_entropy",
                    description="Distribucion de energia entre bandas.",
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
            ],
        ),
    ]

    return {
        "schema_version": "1.0",
        "policy": "canonical_analysis_engine_first",
        "measurement_context": {
            "max_audio_duration_seconds": quality.get("max_allowed_duration_seconds"),
            "frame_duration_seconds": framing.get("frame_duration_seconds"),
            "sample_rate_original_hz": quality.get("sample_rate_original"),
            "sample_rate_analysis_hz": input_audio.get("internal_sample_rate") or quality.get("sample_rate_internal"),
            "notes": [
                "analysis_engine is the canonical source for audio metrics.",
                "legacy temporal_analysis and spectral_analysis remain for compatibility and plots.",
                "sample_rate_analysis_hz is the rate used for canonical calculations.",
            ],
        },
        "groups": [group for group in groups if group["metrics"]],
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
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unable to process the provided audio file: {exc}",
        ) from exc

    if output == "json":
        payload = serialize_result(result, include_images=True)
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
        payload["analysis_engine"] = analysis_engine_payload
        payload["metrics"] = build_coherent_metrics(
            legacy_payload=payload,
            engine_payload=analysis_engine_payload,
        )
        payload["content_type"] = "image/png"
        payload["filename"] = f"{audio_file.filename or 'analysis'}.png"
        payload["image_base64"] = base64.b64encode(result.primary_image.image_bytes).decode("ascii")
        payload["encoding"] = "base64"
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
