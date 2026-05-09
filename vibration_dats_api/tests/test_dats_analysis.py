import asyncio
import io
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "vibration_dats_api"))

from app.routers.dats import datsanalysis  # noqa: E402
from app.services.dats_analysis import analyze_dats_bytes  # noqa: E402
from starlette.datastructures import UploadFile  # noqa: E402


ACCEL_ONLY_DAT = b"""# Vibrations acquisition
# file=accelerometer_only.dat
# sensor_period_us=5000
# columns=session_start_wall_time_ms,wall_time_ms,sensor_time_ns,sensor,accuracy,x,y,z
1000,1000,1000000000,accelerometer,3,0.0,0.0,9.8
1000,1005,1005000000,accelerometer,3,0.2,0.1,10.2
1000,1010,1010000000,accelerometer,3,0.4,0.2,9.7
1000,1015,1015000000,accelerometer,3,0.1,0.1,9.9
1000,1020,1020000000,accelerometer,3,0.0,0.0,9.8
"""


ACCEL_GYRO_DAT = b"""# Vibrations acquisition
# file=car_fixture.dat
# phenomenon=carro
# target_sample_rate_hz=10
# sensor_period_us=100000
# columns=session_start_wall_time_ms,wall_time_ms,sensor_time_ns,sensor,accuracy,x,y,z
1000,1000,1000000000,gyroscope,3,0.01,0.02,0.03
1000,1004,1004000000,accelerometer,3,0.0,5.3,8.0
1000,1100,1100000000,gyroscope,3,0.03,0.01,0.02
1000,1104,1104000000,accelerometer,3,0.2,5.4,8.2
1000,1200,1200000000,gyroscope,3,0.07,0.03,0.01
1000,1204,1204000000,accelerometer,3,0.1,5.5,8.1
1000,1300,1300000000,gyroscope,3,0.02,0.02,0.04
1000,1304,1304000000,accelerometer,3,-0.1,5.2,7.9
1000,1600,1600000000,gyroscope,3,0.30,0.20,0.10
1000,1604,1604000000,accelerometer,3,1.2,6.3,10.5
"""


def test_analyzes_accelerometer_and_gyroscope_example() -> None:
    payload = analyze_dats_bytes(ACCEL_GYRO_DAT, filename="car_fixture.dat")

    assert payload["capture"]["window_ms"] == 500
    assert "accelerometer" in payload["capture"]["sensors"]
    assert "gyroscope" in payload["capture"]["sensors"]
    assert payload["sensor_summaries"]["accelerometer"]["sample_count"] > 0
    assert payload["sensor_summaries"]["gyroscope"]["sample_count"] > 0
    assert payload["sensor_summaries"]["accelerometer"]["dynamic"]["kurtosis"] is not None
    assert payload["sensor_summaries"]["accelerometer"]["spectrum"]["spectral_centroid_hz"] is not None
    assert payload["plots"]["accelerometer_timeseries"]["encoding"] == "base64"
    assert payload["windows"]
    first_window = payload["windows"][0]
    assert "accelerometer" in first_window["sensors"]
    assert "change_score" in first_window["sensors"]["accelerometer"]
    metric_keys = [
        metric["clave"]
        for group in payload["metricas"]["grupos"]
        for metric in group["metricas"]
    ]
    assert len(metric_keys) == len(set(metric_keys))
    assert "accelerometer_dynamic_rms" in metric_keys
    assert "gyroscope_dynamic_rms" in metric_keys
    assert "accelerometer_dynamic_kurtosis" in metric_keys
    assert "accelerometer_spectral_centroid_hz" in metric_keys


def test_analyzes_accelerometer_only_example() -> None:
    payload = analyze_dats_bytes(ACCEL_ONLY_DAT, filename="accelerometer_only.dat")

    assert payload["capture"]["sensors"] == ["accelerometer"]
    assert payload["capture"]["duration_seconds"] <= 180
    assert payload["sensor_summaries"]["accelerometer"]["estimated_sample_rate_hz"] > 100


def test_datsanalysis_endpoint_accepts_multipart_upload() -> None:
    payload = asyncio.run(
        datsanalysis(
            dat_file=UploadFile(file=io.BytesIO(ACCEL_GYRO_DAT), filename="car_fixture.dat"),
            window_ms=500,
        )
    )

    assert payload["file"]["filename"] == "car_fixture.dat"
    assert payload["capture"]["window_count"] > 0
