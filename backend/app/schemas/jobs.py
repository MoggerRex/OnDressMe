from typing import Any, Literal

from pydantic import BaseModel, Field


JobKind = Literal["avatar", "outfit"]
JobStatus = Literal["queued", "running", "completed", "failed"]


class OutfitJobRequest(BaseModel):
    profile_id: str = Field(min_length=1)
    wardrobe_item_ids: list[str] = Field(default_factory=list)
    preferences: dict[str, Any] = Field(default_factory=dict)


class JobCreated(BaseModel):
    job_id: str
    status: JobStatus


class JobState(BaseModel):
    job_id: str
    kind: JobKind
    status: JobStatus
    result: dict[str, Any] | None = None
    error: str | None = None


class WorkerResult(BaseModel):
    status: Literal["completed", "failed"]
    result: dict[str, Any] | None = None
    error: str | None = None
