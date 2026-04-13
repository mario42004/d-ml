from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.routers.scalogram import router as scalogram_router


app = FastAPI(title=settings.app_name)
app.include_router(scalogram_router)

static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def frontend() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name, "environment": settings.app_env}
