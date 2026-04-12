from __future__ import annotations

import base64

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse, Response

from app.core.config import settings
from app.services.scalogram import build_scalogram


router = APIRouter(prefix="/scalogram", tags=["scalogram"])


@router.post(
    "",
    responses={
        200: {"content": {"image/png": {}}},
    },
)
async def create_scalogram(
    audio_file: UploadFile = File(...),
    sample_rate: int | None = Form(default=None),
    wavelet: str | None = Form(default=None),
    width_min: int | None = Form(default=None),
    width_max: int | None = Form(default=None),
    colormap: str | None = Form(default=None),
    output: str = Form(default="image"),
):
    if output not in {"image", "json"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid output format. Use 'image' or 'json'.",
        )

    contents = await audio_file.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(contents) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded audio file is empty.",
        )
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File is too large. Max upload size is {settings.max_upload_size_mb} MB.",
        )

    try:
        result = build_scalogram(
            contents,
            sample_rate=sample_rate,
            wavelet=wavelet,
            width_min=width_min,
            width_max=width_max,
            colormap=colormap,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unable to process the provided audio file: {exc}",
        ) from exc

    if output == "json":
        return JSONResponse(
            {
                "content_type": "image/png",
                "filename": f"{audio_file.filename or 'scalogram'}.png",
                "sample_rate": result.sample_rate,
                "duration_seconds": result.duration_seconds,
                "sample_count": result.sample_count,
                "wavelet": result.wavelet,
                "width_min": result.width_min,
                "width_max": result.width_max,
                "colormap": result.colormap,
                "image_base64": base64.b64encode(result.image_bytes).decode("ascii"),
                "encoding": "base64",
            }
        )

    return Response(
        content=result.image_bytes,
        media_type="image/png",
        headers={
            "Content-Disposition": f'inline; filename="{audio_file.filename or "scalogram"}.png"',
            "X-Scalogram-Sample-Rate": str(result.sample_rate),
            "X-Scalogram-Duration": str(result.duration_seconds),
            "X-Scalogram-Wavelet": result.wavelet,
        },
    )
