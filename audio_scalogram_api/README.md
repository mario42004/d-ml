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
- `POST /scalogram`

## Uso

El endpoint `POST /scalogram` recibe un archivo multipart en el campo `audio_file`.

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
- la imagen principal en `base64`
- un conjunto de graficos tecnicos adicionales en `base64`

## Ejemplo con curl

```bash
curl -X POST "http://localhost:8001/scalogram" \
  -F "audio_file=@./sample.wav" \
  -F "visualization=dashboard" \
  --output analysis.png
```

```bash
curl -X POST "http://localhost:8001/scalogram" \
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

Arranque en produccion:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Entonces la API quedara expuesta en:

```text
https://tu-dominio/
https://tu-dominio/scalogram
https://tu-dominio/health
```

## Nota importante

Si cambias en `docker-compose.yml` solo esto:

```yaml
ports:
  - "443:8001"
```

la app quedara escuchando en el puerto `443`, pero seguira siendo HTTP plano, no HTTPS.
Eso puede servir solo como prueba puntual con una URL tipo `http://host:443/scalogram`, pero no es la opcion recomendada para produccion.
