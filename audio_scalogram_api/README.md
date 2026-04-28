# Audio Scalogram API

API independiente en `FastAPI` para generar analisis temporal y espectral de audio, junto con visualizaciones tecnicas para usuario final.

## Estructura

- `app/main.py`: punto de entrada
- `app/routers/scalogram.py`: endpoint HTTP
- `app/services/scalogram.py`: logica de carga de audio, extraccion de features y generacion de visualizaciones
- `app/static/`: frontend ligero servido por la propia API
- `Dockerfile`: imagen para despliegue remoto
- `docker-compose.yml`: arranque local o en servidor

## Endpoint

- `GET /`
- `GET /health`
- `POST /audioanalisys`

## Uso

El endpoint `POST /audioanalisys` recibe un archivo multipart en el campo `audio_file`.
`POST /scalogram` se mantiene como alias temporal para compatibilidad.

Campos opcionales:

- `sample_rate`
- `wavelet`
- `width_min`
- `width_max`
- `colormap`
- `visualization`
- `output`

`visualization` acepta:

- `dashboard`
- `waveform`
- `rms_energy`
- `spectrum`
- `mel_spectrogram`
- `scalogram`

`output=image` devuelve directamente un `image/png` de la visualizacion principal.

`output=json` devuelve:

- metadatos del audio y del analisis
- metricas temporales agregadas
- metricas espectrales agregadas
- `analysis_engine` con validacion, normalizacion a 16 kHz, framing y metricas de calidad
- la imagen principal en `base64`
- un conjunto de graficos tecnicos adicionales en `base64`

La clave `analysis_engine` sigue la Fase 0 del documento maestro de Audio Health Research. En modo
normal no devuelve audio bruto, matrices grandes, espectrogramas completos ni artefactos pesados.

Regla operativa actual:

- duracion maxima del audio: 20 segundos
- procesamiento interno por frames de 5 segundos sin solape
- los frames son solo una estrategia de calculo
- la respuesta normal expone metricas agregadas de todo el audio, no metricas por frame
- Fase 3 añade `spectral_summary` compacto: centroide, bandwidth, rolloff, flatness,
  contraste, flux, frecuencia dominante, energia por bandas low/mid/high y PSD resumida
- Fase 4 añade `cepstral_summary` compacto: MFCC mean/std, delta MFCC opcional,
  envolvente espectral resumida y features de voz solo si se activan por configuracion
- Fase 5 añade `time_frequency_summary` opcional y desactivado por defecto; cuando se
  activa devuelve solo escala/entropia/concentracion/modulacion compacta, nunca matrices CWT

## Ejemplo con curl

```bash
curl -X POST "http://localhost:8001/audioanalisys" \
  -F "audio_file=@./sample.wav" \
  -F "visualization=dashboard" \
  --output analysis.png
```

```bash
curl -X POST "http://localhost:8001/audioanalisys" \
  -F "audio_file=@./sample.wav" \
  -F "output=json"
```

## Docker

```bash
docker compose up --build
```

En servidor con `nginx` instalado en el host, este `docker-compose.yml` deja la API accesible solo en:

```text
127.0.0.1:8001
```

Eso permite que `nginx` haga proxy a la API sin exponer el puerto `8001` publicamente.

## Exponerla por 443

Si el hosting que consume la API no puede salir a `:8001`, no conviene mover `uvicorn` directamente al puerto `443`.
La forma correcta es dejar la app en `8001` dentro de Docker y poner `nginx` delante en `80/443`.

Si ya configuraste `nginx` directamente en el servidor Ubuntu, te basta con:

```nginx
proxy_pass http://127.0.0.1:8001;
```

Se ha incluido:

- `docker-compose.prod.yml`
- `deploy/nginx.conf`

Estructura esperada para certificados:

```text
audio_scalogram_api/
  certs/
    fullchain.pem
    privkey.pem
```

Arranque en produccion desde GHCR:

```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

La imagen por defecto es:

```text
ghcr.io/mario42004/d-ml-audio-scalogram-api:latest
```

Para fijar una version concreta publicada por GitHub Actions:

```env
AUDIO_SCALOGRAM_IMAGE=ghcr.io/mario42004/d-ml-audio-scalogram-api:sha-<commit>
```

Entonces la API quedara expuesta en:

```text
https://api.d-ml.eu/
https://api.d-ml.eu/audioanalisys
https://api.d-ml.eu/health
```

Si el portal Audioprint corre fuera del host de Docker, configura:

```env
AUDIOPRINT_AUDIOANALISYS_API_URL=https://api.d-ml.eu/audioanalisys
```

`http://127.0.0.1:8001/audioanalisys` solo es correcto cuando el portal y el contenedor de la API comparten host/red local.

## Nota importante

Si cambias en `docker-compose.yml` solo esto:

```yaml
ports:
  - "443:8001"
```

la app quedara escuchando en el puerto `443`, pero seguira siendo HTTP plano, no HTTPS.
Eso puede servir solo como prueba puntual con una URL tipo `http://host:443/audioanalisys`, pero no es la opcion recomendada para produccion.
