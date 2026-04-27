from __future__ import annotations

import base64

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse, Response

from app.analysis_engine import run_analysis_engine
from app.core.config import settings
from app.services.scalogram import build_scalogram, serialize_result


router = APIRouter(tags=["audioanalisys"])


@router.post(
    "/audioanalisys",
    responses={
        200: {"content": {"image/png": {}}},
    },
)
@router.post(
    "/scalogram",
    include_in_schema=False,
    responses={
        200: {"content": {"image/png": {}}},
    },
)
async def create_audioanalisys(
    audio_file: UploadFile = File(...),
    sample_rate: int | None = Form(default=None),
    wavelet: str | None = Form(default=None),
    width_min: int | None = Form(default=None),
    width_max: int | None = Form(default=None),
    colormap: str | None = Form(default=None),
    visualization: str = Form(default="dashboard"),
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
            visualization=visualization,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unable to process the provided audio file: {exc}",
        ) from exc

    if output == "json":
        payload = serialize_result(result, include_images=True)
        payload["analysis_engine"] = run_analysis_engine(
            audio_input=contents,
            sample_rate=sample_rate,
            original_format=(
                audio_file.filename.rsplit(".", 1)[-1]
                if audio_file.filename and "." in audio_file.filename
                else None
            ),
            filename=audio_file.filename,
        )
        payload["content_type"] = "image/png"
        payload["filename"] = f"{audio_file.filename or 'analysis'}.png"
        payload["image_base64"] = base64.b64encode(result.primary_image.image_bytes).decode("ascii")
        payload["encoding"] = "base64"
        return JSONResponse(payload)

    return Response(
        content=result.primary_image.image_bytes,
        media_type="image/png",
        headers={
            "Content-Disposition": f'inline; filename="{audio_file.filename or visualization}.png"',
            "X-Analysis-Sample-Rate": str(result.metadata.sample_rate),
            "X-Analysis-Duration": str(result.metadata.duration_seconds),
            "X-Analysis-Visualization": result.primary_image.key,
            "X-Analysis-Wavelet": result.scalogram_config.wavelet,
        },
    )
