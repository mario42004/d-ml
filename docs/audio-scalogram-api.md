# Audio Scalogram API

Nueva API independiente para desplegar en un contenedor separado del resto de servicios.

## Objetivo

Recibir un archivo de audio y devolver un analisis reutilizable para inspeccion humana, comparacion historica y futura deteccion de anomalias.

## Ubicacion

- `audio_scalogram_api/`

## Contrato inicial

### Request

- metodo: `POST`
- ruta principal: `/audioanalisys`
- alias temporal de compatibilidad: `/scalogram`
- tipo: `multipart/form-data`
- campo obligatorio: `audio_file`

### Parametros opcionales

- `sample_rate`
- `wavelet`
- `width_min`
- `width_max`
- `colormap`
- `visualization`
- `output`

### Response

- por defecto: `image/png` de una visualizacion tecnica
- opcional: `JSON` con:
  - version del analisis y visualizacion principal
  - `metricas` como bloque canonico unificado de calidad, energia,
    dinamica temporal, autocorrelacion, espectro, MFCC y tiempo-frecuencia opcional
  - imagen principal en `base64`
  - varias visualizaciones adicionales en `base64`

## Visualizaciones previstas

- `dashboard`: resumen visual de forma de onda, energia RMS, espectro medio y mel spectrogram
- `waveform`: amplitud frente a tiempo
- `rms_energy`: evolucion temporal de la energia
- `spectrum`: espectro medio para comparar bandas dominantes
- `mel_spectrogram`: mapa tiempo-frecuencia mas interpretable para usuario final
- `scalogram`: salida wavelet, mantenida como vista complementaria

## Features previstas para series historicas

- metadatos del audio: frecuencia original, frecuencia efectiva, duracion, numero de muestras, Nyquist y tamano de archivo
- features temporales: RMS, zero crossing rate, amplitud, crest factor, rango dinamico, silencio, clipping y desplazamiento DC
- features espectrales: centroide, bandwidth, rolloff, flatness, contraste, flujo espectral, frecuencia dominante y picos principales
- `analysis_engine` procesa internamente frames de 5 segundos para audios de hasta 20 segundos, pero la respuesta normal expone solo `metricas` agregadas de todo el audio.

## Contrato JSON publico

`output=json` no expone el payload interno completo de `analysis_engine`.
`metricas` no incluye metadatos del archivo, configuracion de visualizacion ni detalles
operativos de framing; esos datos los gestiona el front. La forma publica estable es:

```json
{
  "analysis_version": "2.1",
  "primary_visualization": "dashboard",
  "metricas": {
    "version_esquema": "1.0",
    "politica": "metricas_canonicas_unificadas",
    "grupos": [
      {
        "clave": "signal_quality",
        "etiqueta": "Calidad de senal",
        "metricas": [
          {
            "clave": "silence_sample_ratio",
            "etiqueta": "Silencio por muestras",
            "valor": 0.12,
            "unidad": "ratio",
            "fuente": "analysis_engine.quality.silence_ratio",
            "descripcion": "Proporcion de muestras por debajo del umbral de energia."
          }
        ]
      }
    ]
  },
  "plots": {},
  "content_type": "image/png",
  "filename": "analysis.png",
  "image_base64": "...",
  "encoding": "base64"
}
```

## Frontend

La propia API sirve una interfaz web ligera en `GET /` para:

- subir audio
- lanzar el analisis
- ver metricas clave
- comparar las visualizaciones sin depender todavia del portal principal

## Despliegue

Esta API se ejecuta en su propio contenedor Docker y no comparte runtime con el resto de APIs del proyecto.
En produccion, nginx escucha en `443` y proxyfica hacia el contenedor en `8001`, por lo que los clientes externos deben usar:

```text
https://api.d-ml.eu/audioanalisys
```

El puerto `8001` queda como detalle interno del host/contenedor.
