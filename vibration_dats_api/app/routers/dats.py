from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.core.config import settings
from app.services.dats_analysis import DatsAnalysisError, analyze_dats_bytes


router = APIRouter(tags=["dats-vibration"])


@router.post("/datsanalysis")
async def datsanalysis(
    dat_file: UploadFile = File(...),
    window_ms: int = Form(settings.default_window_ms),
) -> dict[str, object]:
    raw = await dat_file.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(raw) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"El archivo supera el limite de {settings.max_upload_size_mb} MB.",
        )

    try:
        return analyze_dats_bytes(
            raw,
            filename=dat_file.filename or "capture.dat",
            window_ms=window_ms,
            max_duration_seconds=settings.max_capture_duration_seconds,
            min_window_ms=settings.min_window_ms,
            max_window_ms=settings.max_window_ms,
        )
    except DatsAnalysisError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/vibrationanalysis")
async def vibrationanalysis(
    dat_file: UploadFile = File(...),
    window_ms: int = Form(settings.default_window_ms),
) -> dict[str, object]:
    return await datsanalysis(dat_file=dat_file, window_ms=window_ms)
