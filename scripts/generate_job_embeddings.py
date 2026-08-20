import argparse
import json
import sys
from pathlib import Path

from qdrant_client import models
from sqlalchemy import select


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.core.config import settings
from backend.app.database.connection import SessionLocal
from backend.app.models import JobPosting
from backend.app.services.ai import _text_hash, _upsert_points, configure_job_collection_for_scale, embed_texts, ensure_collections, prepare_job_text, qdrant_client


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--checkpoint", default=str(ROOT / "job_embeddings_checkpoint.json"))
    parser.add_argument("--restart", action="store_true")
    args = parser.parse_args()

    checkpoint_path = Path(args.checkpoint)
    last_job_id = 0
    if checkpoint_path.exists() and not args.restart:
        last_job_id = int(json.loads(checkpoint_path.read_text()).get("last_job_id", 0))

    ensure_collections()
    vectors = qdrant_client()
    configure_job_collection_for_scale(vectors)
    processed = 0
    with SessionLocal() as db:
        while True:
            jobs = list(db.scalars(
                select(JobPosting)
                .where(JobPosting.status == "ACTIVE", JobPosting.job_id > last_job_id)
                .order_by(JobPosting.job_id)
                .limit(args.batch_size)
            ))
            if not jobs:
                break
            texts = [prepare_job_text(job) for job in jobs]
            embeddings = embed_texts(texts)
            points = [
                models.PointStruct(
                    id=job.job_id,
                    vector=embedding,
                    payload={"job_id": job.job_id, "company_id": job.company_id, "source_type": job.source_type, "text_hash": _text_hash(text)},
                )
                for job, text, embedding in zip(jobs, texts, embeddings, strict=True)
            ]
            _upsert_points(vectors, settings.qdrant_job_collection, points)
            last_job_id = jobs[-1].job_id
            processed += len(jobs)
            checkpoint_path.write_text(json.dumps({"last_job_id": last_job_id, "processed": processed}, indent=2))
            print(f"embedded {processed} jobs; last job_id={last_job_id}")


if __name__ == "__main__":
    main()