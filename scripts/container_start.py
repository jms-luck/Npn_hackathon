import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qdrant_client import QdrantClient
from redis.exceptions import RedisError
from sqlalchemy import distinct, func, select

from backend.app.core.config import settings
from backend.app.database.connection import SessionLocal
from backend.app.models import Application, Candidate, GlobalApplicant, JobPosting, Resume
from backend.app.services.cache import redis_client
from backend.app.services.graph import neo4j_driver


def requires_seed(source_count: int, indexed_count: int | None) -> bool | None:
    return None if indexed_count is None else indexed_count < source_count


def requires_rebuild(source_count: int, indexed_count: int | None) -> bool | None:
    return None if indexed_count is None else indexed_count > source_count


def postgres_counts() -> dict[str, int]:
    with SessionLocal() as db:
        return {
            "active_jobs": db.scalar(select(func.count()).select_from(JobPosting).where(JobPosting.status == "ACTIVE")) or 0,
            "parsed_resumes": db.scalar(select(func.count()).select_from(Resume).where(Resume.extracted_text.is_not(None))) or 0,
            "candidate_nodes": db.scalar(select(func.count()).select_from(Candidate)) or 0,
            "resume_nodes": db.scalar(select(func.count()).select_from(Resume)) or 0,
            "application_edges": db.scalar(select(func.count()).select_from(Application)) or 0,
            "talent_pool_edges": db.scalar(select(func.count()).select_from(GlobalApplicant)) or 0,
            "application_jobs": db.scalar(select(func.count(distinct(Application.job_id)))) or 0,
        }


def qdrant_plan(source: dict[str, int]) -> dict:
    try:
        client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None, timeout=5)
        collections = {item.name for item in client.get_collections().collections}
        job_points = client.get_collection(settings.qdrant_job_collection).points_count if settings.qdrant_job_collection in collections else 0
        resume_points = client.get_collection(settings.qdrant_resume_collection).points_count if settings.qdrant_resume_collection in collections else 0
        application_collections = sum(name.startswith("job_") and name.endswith("_applicant_resumes") for name in collections)
        return {
            "state": "available",
            "job_points": job_points,
            "resume_points": resume_points,
            "application_job_collections": application_collections,
            "seed_jobs": requires_seed(source["active_jobs"], job_points),
            "seed_resumes": requires_seed(source["parsed_resumes"], resume_points),
            "seed_application_jobs": requires_seed(source["application_jobs"], application_collections),
            "rebuild_jobs": requires_rebuild(source["active_jobs"], job_points),
            "rebuild_resumes": requires_rebuild(source["parsed_resumes"], resume_points),
            "rebuild_application_jobs": requires_rebuild(source["application_jobs"], application_collections),
        }
    except Exception as exc:
        return {"state": "unavailable", "error_type": type(exc).__name__, "seed_jobs": None, "seed_resumes": None, "seed_application_jobs": None}


def neo4j_plan(source: dict[str, int]) -> dict:
    if not settings.neo4j_uri:
        return {"state": "disabled", "seed_required": False}
    try:
        with neo4j_driver().session() as session:
            counts = session.run(
                "MATCH (c:Candidate) WITH count(c) AS candidates "
                "OPTIONAL MATCH (r:Resume) WITH candidates, count(r) AS resumes "
                "OPTIONAL MATCH ()-[a:APPLIED_TO]->() WITH candidates, resumes, count(a) AS applications "
                "OPTIONAL MATCH ()-[t:IN_TALENT_POOL]->() RETURN candidates, resumes, applications, count(t) AS talent_pool"
            ).single()
        indexed = {"candidate_nodes": counts["candidates"], "resume_nodes": counts["resumes"], "application_edges": counts["applications"], "talent_pool_edges": counts["talent_pool"]}
        needed = any(indexed[key] < source[key] for key in indexed)
        rebuild = any(indexed[key] > source[key] for key in indexed)
        return {"state": "available", **indexed, "seed_required": needed, "rebuild_required": rebuild}
    except Exception as exc:
        return {"state": "unavailable", "error_type": type(exc).__name__, "seed_required": None}


def redis_status() -> dict:
    try:
        return {"state": "available" if redis_client().ping() else "unavailable"}
    except RedisError as exc:
        return {"state": "unavailable", "error_type": type(exc).__name__}


def external_index_plan() -> dict:
    source = postgres_counts()
    return {"postgresql": source, "qdrant": qdrant_plan(source), "neo4j": neo4j_plan(source), "redis": redis_status()}


def run_seed(*arguments: str) -> None:
    subprocess.run([sys.executable, *arguments], check=True)


def main() -> None:
    if not settings.skip_external_index_check:
        plan = external_index_plan()
        print(json.dumps({"external_index_preflight": plan}, sort_keys=True), flush=True)
        if settings.auto_seed_external_indexes:
            qdrant = plan["qdrant"]
            if qdrant.get("seed_jobs"):
                run_seed("scripts/generate_job_embeddings.py", "--batch-size", "100")
            if qdrant.get("seed_resumes") or qdrant.get("seed_application_jobs"):
                run_seed("scripts/seed_docker_qdrant.py", "--batch-size", "32")
            if plan["neo4j"].get("seed_required"):
                run_seed("scripts/seed_neo4j.py", "--batch-size", "250")
    os.execvp("uvicorn", ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", os.getenv("PORT", "8000")])


if __name__ == "__main__":
    main()