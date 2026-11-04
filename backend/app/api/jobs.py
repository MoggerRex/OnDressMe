from uuid import uuid4

from fastapi import APIRouter, File, Header, HTTPException, UploadFile

from app.core.config import settings
from app.schemas.jobs import JobCreated, JobState, OutfitJobRequest, WorkerResult
from app.services.job_manager import JobManager
from app.services.storage.files import save_upload

router = APIRouter(prefix="/api")
jobs = JobManager()


@router.post("/avatar/jobs", response_model=JobCreated, status_code=202)
def create_avatar_job(profile_id: str, image: UploadFile = File(...)) -> JobCreated:
    job_id = str(uuid4())
    relative_path = save_upload(image, job_id)
    state = jobs.create("avatar", {"profile_id": profile_id, "image_path": relative_path}, job_id=job_id)
    return JobCreated(job_id=state.job_id, status=state.status)


@router.post("/outfits/jobs", response_model=JobCreated, status_code=202)
def create_outfit_job(request: OutfitJobRequest) -> JobCreated:
    state = jobs.create("outfit", request.model_dump())
    return JobCreated(job_id=state.job_id, status=state.status)


@router.get("/jobs/{job_id}", response_model=JobState)
def get_job(job_id: str) -> JobState:
    state = jobs.get(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return state


@router.post("/internal/jobs/{job_id}/result", response_model=JobState)
def update_job(
    job_id: str,
    result: WorkerResult,
    x_worker_token: str | None = Header(default=None),
) -> JobState:
    if settings.internal_worker_token and x_worker_token != settings.internal_worker_token:
        raise HTTPException(status_code=401, detail="Invalid worker token")
    if jobs.get(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")
    jobs.update(job_id, result.status, result.result, result.error)
    return jobs.get(job_id)
