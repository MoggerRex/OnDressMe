import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("API_HOST", "0.0.0.0")
    port: int = int(os.getenv("API_PORT", "8000"))
    redis_url: str = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    storage_path: Path = Path(os.getenv("STORAGE_PATH", "./storage"))
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "10"))
    internal_worker_token: str = os.getenv("INTERNAL_WORKER_TOKEN", "")
    avatar_worker_url: str = os.getenv("AVATAR_WORKER_URL", "http://localhost:8101")
    outfit_worker_url: str = os.getenv("OUTFIT_WORKER_URL", "http://localhost:8102")
    cors_origins: tuple[str, ...] = tuple(
        origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if origin.strip()
    )


settings = Settings()
