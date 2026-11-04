import argparse
import os
import sys
import time

import httpx
from dotenv import load_dotenv
from redis import Redis

load_dotenv()


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Worker D connectivity")
    parser.add_argument("--e2e", action="store_true", help="Create a test outfit job and wait for its result")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    redis_url = os.getenv("REDIS_URL", "")
    backend_url = os.getenv("BACKEND_URL", "").rstrip("/")
    if not redis_url or not backend_url:
        print("ERROR: REDIS_URL and BACKEND_URL are required in .env")
        return 2

    checks_passed = True
    try:
        redis = Redis.from_url(redis_url, decode_responses=True)
        redis.ping(timeout=5)
        print("OK Redis:", redis_url.split("@")[-1])
    except Exception as error:
        print(f"ERROR Redis connection: {error}")
        checks_passed = False

    try:
        response = httpx.get(f"{backend_url}/health", timeout=5)
        response.raise_for_status()
        print("OK Backend:", response.json())
    except Exception as error:
        print(f"ERROR Backend connection: {error}")
        checks_passed = False

    if not checks_passed:
        print("Connectivity check failed. Verify Tailscale, services and firewall rules.")
        return 1

    if not args.e2e:
        print("Connectivity check passed. Use --e2e while worker.py is running to test a complete job.")
        return 0

    try:
        response = httpx.post(
            f"{backend_url}/api/outfits/jobs",
            json={
                "profile_id": "connection-test",
                "wardrobe_item_ids": ["test-item"],
                "preferences": {"test": True},
            },
            timeout=10,
        )
        response.raise_for_status()
        job_id = response.json()["job_id"]
        print("Created test job:", job_id)
    except Exception as error:
        print(f"ERROR Creating test job: {error}")
        return 1

    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        response = httpx.get(f"{backend_url}/api/jobs/{job_id}", timeout=5)
        response.raise_for_status()
        state = response.json()
        print("Job state:", state["status"])
        if state["status"] in {"completed", "failed"}:
            print("End-to-end check passed:", state)
            return 0
        time.sleep(1)

    print(f"ERROR Job {job_id} did not finish in {args.timeout} seconds")
    return 1


if __name__ == "__main__":
    sys.exit(main())
