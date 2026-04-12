# Audio Scalogram API

Nueva API independiente para desplegar en un contenedor separado del resto de servicios.

## Objetivo

Recibir un archivo de audio y devolver un escalograma en formato `PNG`.

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
- `output`

### Response

- por defecto: `image/png`
- opcional: `JSON` con metadatos e imagen codificada en `base64` usando `output=json`

## Despliegue

Esta API se ejecuta en su propio contenedor Docker y no comparte runtime con el resto de APIs del proyecto.
