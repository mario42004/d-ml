# d-ml

APIs de analisis de `d-ml`.

Este repositorio contiene servicios FastAPI dockerizados e independientes.

## Audio

El servicio de audio publica:

- `GET /health`
- `POST /audioanalisys`

El portal PHP/frontend vive en un repositorio separado: `d-ml-front`.

## Servicio

El codigo principal esta en:

```text
audio_scalogram_api/
```

La API recibe un archivo de audio por `multipart/form-data` en el campo
`audio_file`. El procesamiento valida una duracion maxima de 20 segundos,
calcula internamente por frames de 5 segundos y devuelve solo metricas globales
del audio completo en la respuesta normal.

## Desarrollo Local

```bash
cd audio_scalogram_api
docker compose up --build
```

Prueba local:

```bash
curl -X POST "http://localhost:8001/audioanalisys" \
  -F "audio_file=@./sample.wav" \
  -F "output=json"
```

## Produccion

La imagen se publica desde GitHub Actions en GHCR:

```text
ghcr.io/mario42004/d-ml-audio-scalogram-api:latest
```

En produccion, Nginx expone:

```text
https://api.d-ml.eu/audioanalisys
```

y proxy a la API en el puerto interno `8001`.

## Documentacion

- [Audio Scalogram API](docs/audio-scalogram-api.md)

## Sensores DATS

El servicio de acelerometro/giroscopio vive aparte, sin dependencia de la API de audio:

```text
vibration_dats_api/
```

Publica:

- `GET /health`
- `POST /datsanalysis`
- `POST /vibrationanalysis`

Recibe archivos `.dat` en `multipart/form-data` con el campo `dat_file` y devuelve
metricas globales y por ventanas de observacion de 500 ms para analizar vibraciones,
cambios fuertes y futuros baselines de anomalias.
