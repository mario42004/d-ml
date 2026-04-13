# Audio Scalogram API

Nueva API independiente para desplegar en un contenedor separado del resto de servicios.

## Objetivo

Recibir un archivo de audio y devolver un analisis reutilizable para inspeccion humana, comparacion historica y futura deteccion de anomalias.

## Ubicacion

- `audio_scalogram_api/`

## Contrato inicial

### Request

- metodo: `POST`
- ruta: `/scalogram`
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
  - metadatos del audio
  - metadatos de analisis
  - metricas temporales agregadas
  - metricas espectrales agregadas
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

## Frontend

La propia API sirve una interfaz web ligera en `GET /` para:

- subir audio
- lanzar el analisis
- ver metricas clave
- comparar las visualizaciones sin depender todavia del portal principal

## Despliegue

Esta API se ejecuta en su propio contenedor Docker y no comparte runtime con el resto de APIs del proyecto.
