# DATS Vibration API

API FastAPI independiente para analizar archivos `.dat` con acelerometro y giroscopio.
No comparte codigo ni endpoints con la API de audio.

## Endpoints

- `GET /health`
- `POST /datsanalysis`
- `POST /vibrationanalysis` alias compatible

`POST /datsanalysis` recibe `multipart/form-data`:

- `dat_file`: archivo `.dat`
- `window_ms`: ventana de observacion, por defecto `500`

La captura puede durar hasta 180 segundos. La respuesta incluye resumen global por sensor
y metricas por ventanas de 500 ms para detectar vibraciones, cambios fuertes y construir
baselines historicos por fenomeno.

## Metricas principales

- frecuencia de muestreo estimada por sensor
- estadisticos por eje y magnitud
- componente dinamica de la magnitud
- RMS dinamico, pico dinamico y pico a pico
- jerk aproximado
- frecuencia dominante por FFT compacta
- `change_score`, `strong_change` y `severity` por ventana

## Uso local

```bash
docker compose up --build
```

```bash
curl -X POST "http://localhost:8002/datsanalysis" \
  -F "dat_file=@../dats_examples/testings_dats/car_2909_20260509_130719.dat" \
  -F "window_ms=500"
```
