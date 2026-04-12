# Audio Scalogram API

API independiente en `FastAPI` para generar un escalograma a partir de un archivo de audio.

## Estructura

- `app/main.py`: punto de entrada
- `app/routers/scalogram.py`: endpoint HTTP
- `app/services/scalogram.py`: logica de carga de audio y generacion de imagen
- `Dockerfile`: imagen para despliegue remoto
- `docker-compose.yml`: arranque local o en servidor

## Endpoint

- `GET /health`
- `POST /scalogram`

## Uso

El endpoint `POST /scalogram` recibe un archivo multipart en el campo `audio_file`.

Campos opcionales:

- `sample_rate`
- `wavelet`
- `width_min`
- `width_max`
- `colormap`
- `output`

`output=image` devuelve directamente un `image/png`.

`output=json` devuelve metadatos del procesado junto con la imagen codificada en `base64`.

## Ejemplo con curl

```bash
curl -X POST "http://localhost:8001/scalogram" \
  -F "audio_file=@./sample.wav" \
  -F "wavelet=morl" \
  -F "width_min=1" \
  -F "width_max=128" \
  --output scalogram.png
```

## Docker

```bash
docker compose up --build
```
