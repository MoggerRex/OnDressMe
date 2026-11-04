from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.core.config import settings


def save_upload(upload: UploadFile, job_id: str) -> str:
    directory = settings.storage_path / "uploads"
    directory.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload.filename or "").suffix.lower()
    destination = directory / f"{job_id}{suffix}"
    with destination.open("wb") as target:
        while chunk := upload.file.read(1024 * 1024):
            target.write(chunk)
            if target.tell() > settings.max_upload_mb * 1024 * 1024:
                destination.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Uploaded file exceeds MAX_UPLOAD_MB")
    return str(destination.relative_to(settings.storage_path))
