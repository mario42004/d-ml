# d-ml

Monorepo de la marca `d-ml`.

El objetivo de este repositorio es reunir servicios, soluciones y piezas operativas orientadas al procesamiento de audio, con una arquitectura modular que permita desplegar componentes independientes segun el caso de uso.

## Estado actual

El modulo activo de analisis es:

- `audio_scalogram_api/`: API independiente en `FastAPI` para recibir un audio y devolver analisis temporal y espectral, metricas y visualizaciones

El portal PHP del repositorio consume ese servicio para publicar `Audioprint` a usuarios finales y administradores.

La siguiente evolucion funcional ya aterrizada en el modelo de plataforma es:

- `Smart Tales`: producto narrativo para generar cuentos infantiles personalizados con voces familiares clonadas, perfiles por menor e historial de reproduccion

## Modulo activo

### `audio_scalogram_api/`

Servicio dockerizado pensado para correr en un servidor remoto como contenedor independiente.

Endpoints disponibles:

- `GET /health`
- `POST /audioanalisys`

El endpoint `POST /audioanalisys` recibe un archivo de audio por `multipart/form-data` en el campo `audio_file` y devuelve analisis enriquecido. Puede responder con imagen o con `json`, incluyendo metricas, plots, metadatos y `analysis_engine`.

## Arranque rapido

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

## Estructura del repositorio

- `audio_scalogram_api/`: servicio activo publicado actualmente
- `docs/`: decisiones, arquitectura y notas funcionales
- `assets/`, `portal/`, `includes/`, `config/`: base del portal web y capa publica en PHP

## Documentacion

- [Arquitectura](docs/architecture.md)
- [Audio Scalogram API](docs/audio-scalogram-api.md)
- [Smart Tales Integration](docs/smart-tales-integration.md)

## Siguiente evolucion prevista

- desplegar `audio_scalogram_api` en servidor remoto
- incorporar nuevos servicios independientes bajo el mismo monorepo
- conectar en fases posteriores la capa web, el portal y futuras APIs cloud
- activar `Smart Tales` como nuevo producto conectado al sistema comun de usuarios, roles y portal
