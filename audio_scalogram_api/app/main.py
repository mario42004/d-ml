from fastapi import FastAPI

from app.core.config import settings
from app.routers.scalogram import router as scalogram_router


app = FastAPI(title=settings.app_name)
app.include_router(scalogram_router)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name, "environment": settings.app_env}
