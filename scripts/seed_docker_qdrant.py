import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import distinct, func, select


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.database.connection import SessionLocal
from backend.app.models import Application, JobPosting, Resume
from backend.app.routers.matching import applicant_items
from backend.app.services.ai import (
    ensure_collections,
    index_resume_embeddings,
    qdrant_client,
    search_applicant_resumes,
)


def load_checkpoint(path: Path, restart: bool) -> dict:
    if restart or not path.exists():
        return {"last_resume_id": 0, "completed_job_ids": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_checkpoint(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def seed_resumes(state: dict, checkpoint_path: Path, batch_size: int) -> None:
    processed = 0
    while True:
        with SessionLocal() as db:
            resumes = list(
                db.scalars(
                    select(Resume)
                    .where(Resume.resume_id > int(state["last_resume_id"]))
                    .order_by(Resume.resume_id)
                    .limit(batch_size)
                )
            )
            db.expunge_all()
        if not resumes:
            break
        indexed = index_resume_embeddings(resumes)
        state["last_resume_id"] = resumes[-1].resume_id
        processed += indexed
        save_checkpoint(checkpoint_path, state)
        print(f"resume cache: indexed {processed} this run; last resume_id={state['last_resume_id']}")


def application_job_ids() -> list[int]:
    with SessionLocal() as db:
        return list(db.scalars(select(distinct(Application.job_id)).order_by(Application.job_id)))


def seed_application_jobs(state: dict, checkpoint_path: Path) -> None:
    completed = {int(job_id) for job_id in state.get("completed_job_ids", [])}
    pending = [job_id for job_id in application_job_ids() if job_id not in completed]
    for position, job_id in enumerate(pending, start=1):
        with SessionLocal() as db:
            job = db.get(JobPosting, job_id)
            if not job:
                completed.add(job_id)
                state["completed_job_ids"] = sorted(completed)
                save_checkpoint(checkpoint_path, state)
                continue
            _, resumes = applicant_items(job_id, db)
            db.commit()
            db.expunge_all()
        points = search_applicant_resumes(job, resumes)
        completed.add(job_id)
        state["completed_job_ids"] = sorted(completed)
        save_checkpoint(checkpoint_path, state)
        print(f"job collections: completed {position}/{len(pending)}; job_id={job_id}; points={len(points)}")


def print_plan() -> None:
    with SessionLocal() as db:
        resume_count = db.scalar(select(func.count()).select_from(Resume)) or 0
        parsed_count = db.scalar(select(func.count()).select_from(Resume).where(Resume.extracted_text.is_not(None))) or 0
        job_count = db.scalar(select(func.count(distinct(Application.job_id)))) or 0
    print({"resumes": resume_count, "parsed_resumes": parsed_count, "application_jobs": job_count})


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Docker Qdrant from PostgreSQL with resumable checkpoints.")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--checkpoint", default=str(ROOT / "docker_qdrant_seed_checkpoint.json"))
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print_plan()
    if args.dry_run:
        return

    checkpoint_path = Path(args.checkpoint)
    state = load_checkpoint(checkpoint_path, args.restart)
    ensure_collections()
    seed_resumes(state, checkpoint_path, args.batch_size)
    seed_application_jobs(state, checkpoint_path)

    client = qdrant_client()
    counts = {item.name: client.get_collection(item.name).points_count for item in client.get_collections().collections}
    print({"status": "complete", "collections": counts})


if __name__ == "__main__":
    main()
