import json
import subprocess
import sys
from pathlib import Path

from qdrant_client import QdrantClient
from sqlalchemy import func, select


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.core.config import settings
from backend.app.database.connection import SessionLocal
from backend.app.models import Candidate, JobPosting, Resume


def run_stage(name: str, *arguments: str) -> None:
    print(json.dumps({"stage": name, "status": "starting"}), flush=True)
    subprocess.run([sys.executable, *arguments], cwd=ROOT, check=True)
    print(json.dumps({"stage": name, "status": "complete"}), flush=True)


def final_counts() -> dict:
    with SessionLocal() as db:
        counts = {
            "active_jobs": db.scalar(select(func.count()).select_from(JobPosting).where(JobPosting.status == "ACTIVE")) or 0,
            "candidates": db.scalar(select(func.count()).select_from(Candidate)) or 0,
            "parsed_resumes": db.scalar(select(func.count()).select_from(Resume).where(Resume.extracted_text.is_not(None))) or 0,
        }
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None, timeout=10)
    collections = {item.name for item in client.get_collections().collections}
    counts["job_vectors"] = client.get_collection(settings.qdrant_job_collection).points_count if settings.qdrant_job_collection in collections else 0
    counts["resume_vectors"] = client.get_collection(settings.qdrant_resume_collection).points_count if settings.qdrant_resume_collection in collections else 0
    return counts


def main() -> None:
    run_stage("applicants_and_blob", "scripts/import_dummy_applicants.py", "--restart", "--workers", "8")
    run_stage("resume_vectors", "scripts/seed_docker_qdrant.py", "--batch-size", "32")
    run_stage("neo4j", "scripts/seed_neo4j.py", "--batch-size", "250")
    run_stage("postgresql_jobs", "scripts/import_jobs.py")
    run_stage("job_vectors", "scripts/generate_job_embeddings.py", "--batch-size", "100")
    print(json.dumps({"status": "complete", "counts": final_counts()}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()