import json
import os
from pathlib import Path

import httpx
from redis import Redis
from dotenv import load_dotenv

from classifier import predict_garment

load_dotenv()


def process_job(job: dict) -> dict:
    """Procesa una imagen local del trabajo; no inventa resultados sin imagen."""
    image_path = job.get("image_path")
    if not image_path:
        raise ValueError(
            "El trabajo no incluye 'image_path'. El backend debe enviar una ruta "
            "de imagen accesible por la computadora D."
        )
    artifact_path = Path(os.getenv("OUTFIT_MODEL_PATH", "outfit_classifier.joblib"))
    prediction = predict_garment(Path(image_path), artifact_path)
    return {"prediction": prediction}


def main() -> None:
    redis = Redis.from_url(os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"), decode_responses=True)
    backend_url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
    token = os.getenv("WORKER_TOKEN", "")
    print("Outfit worker ready; DINOv2 classifier enabled.", flush=True)
    while True:
        _, raw_job = redis.blpop("outfit_jobs")
        job = json.loads(raw_job)
        job_id = job["job_id"]
        redis.hset(f"job:{job_id}", mapping={"status": "running"})
        try:
            payload = {"status": "completed", "result": process_job(job)}
        except (FileNotFoundError, OSError, ValueError, RuntimeError) as exc:
            payload = {"status": "failed", "error": str(exc)}
        headers = {"X-Worker-Token": token} if token else {}
        with httpx.Client(timeout=30) as client:
            response = client.post(f"{backend_url}/api/internal/jobs/{job_id}/result", json=payload, headers=headers)
            response.raise_for_status()


if __name__ == "__main__":
    main()
