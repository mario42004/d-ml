# d-ml

API de analisis de audio de `d-ml`.

Este repositorio queda dedicado al servicio FastAPI dockerizado que publica el
endpoint de analisis:

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
