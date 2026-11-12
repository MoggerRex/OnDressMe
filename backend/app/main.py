from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.jobs import router as jobs_router
from app.api.platform import router as platform_router
from app.core.config import settings

app = FastAPI(title="On Dress Me Central API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Montar la carpeta de almacenamiento persistente para servir assets 3D, previas y uploads
app.mount("/storage", StaticFiles(directory=str(settings.storage_path)), name="storage")

app.include_router(jobs_router)
app.include_router(platform_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "backend"}
