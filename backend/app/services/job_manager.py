import json
from uuid import uuid4

from redis import Redis

from app.core.config import settings
from app.schemas.jobs import JobKind, JobState


class JobManager:
    def __init__(self) -> None:
        self.redis = Redis.from_url(settings.redis_url, decode_responses=True)

    def create(self, kind: JobKind, payload: dict, job_id: str | None = None) -> JobState:
        job_id = job_id or str(uuid4())
        state = JobState(job_id=job_id, kind=kind, status="queued")
        self.redis.hset(
            f"job:{job_id}",
            mapping={"kind": kind, "status": state.status, "payload": json.dumps(payload)},
        )
        self.redis.rpush(f"{kind}_jobs", json.dumps({"job_id": job_id, **payload}))
        return state

    def get(self, job_id: str) -> JobState | None:
        values = self.redis.hgetall(f"job:{job_id}")
        if not values:
            return None
        result = json.loads(values["result"]) if values.get("result") else None
        return JobState(
            job_id=job_id,
            kind=values["kind"],
            status=values["status"],
            result=result,
            error=values.get("error"),
        )

    def update(self, job_id: str, status: str, result: dict | None = None, error: str | None = None) -> None:
        mapping = {"status": status}
        if result is not None:
            mapping["result"] = json.dumps(result)
        if error is not None:
            mapping["error"] = error
        self.redis.hset(f"job:{job_id}", mapping=mapping)
