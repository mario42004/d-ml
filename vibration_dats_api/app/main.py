from fastapi import FastAPI

from app.core.config import settings
from app.routers.dats import router as dats_router


app = FastAPI(title=settings.app_name)
app.include_router(dats_router)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name, "environment": settings.app_env}
