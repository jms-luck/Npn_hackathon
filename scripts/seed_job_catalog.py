import json
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_with_retries(name: str, arguments: list[str], attempts: int = 10) -> None:
    for attempt in range(1, attempts + 1):
        print(json.dumps({"stage": name, "attempt": attempt, "status": "starting"}), flush=True)
        result = subprocess.run([sys.executable, *arguments], cwd=ROOT)
        if result.returncode == 0:
            print(json.dumps({"stage": name, "attempt": attempt, "status": "complete"}), flush=True)
            return
        if attempt < attempts:
            delay = min(30, 2 ** attempt)
            print(json.dumps({"stage": name, "attempt": attempt, "status": "retrying", "delay_seconds": delay}), flush=True)
            time.sleep(delay)
    raise RuntimeError(f"{name} failed after {attempts} attempts")


def main() -> None:
    run_with_retries("postgresql_jobs", ["scripts/import_jobs.py"], attempts=100)
    run_with_retries("qdrant_job_vectors", ["scripts/generate_job_embeddings.py", "--batch-size", "100"], attempts=1_000)
    print(json.dumps({"status": "complete"}), flush=True)


if __name__ == "__main__":
    main()