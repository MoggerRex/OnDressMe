import json
import os

import httpx
from redis import Redis
from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    redis = Redis.from_url(os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"), decode_responses=True)
    backend_url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
    token = os.getenv("WORKER_TOKEN", "")
    print("Outfit worker ready; Ollama/Llama integration is not installed.", flush=True)
    while True:
        _, raw_job = redis.blpop("outfit_jobs")
        job = json.loads(raw_job)
        job_id = job["job_id"]
        redis.hset(f"job:{job_id}", mapping={"status": "running"})
        payload = {"status": "failed", "error": "Outfit generation is not implemented yet"}
        headers = {"X-Worker-Token": token} if token else {}
        with httpx.Client(timeout=30) as client:
            response = client.post(f"{backend_url}/api/internal/jobs/{job_id}/result", json=payload, headers=headers)
            response.raise_for_status()


if __name__ == "__main__":
    main()
