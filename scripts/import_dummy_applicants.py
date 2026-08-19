import argparse
import hashlib
import json
import mimetypes
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
from azure.core.exceptions import ResourceExistsError
from azure.storage.blob import BlobServiceClient, ContentSettings
from sqlalchemy import func, select


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.core.config import settings
from backend.app.core.security import hash_password
from backend.app.database.connection import SessionLocal
from backend.app.models import Candidate, GlobalApplicant, Resume, User
from backend.app.services.social_profiles import fill_missing_social_profiles


TEXT_FIELDS = (
    "target_job_category",
    "skills",
    "experience",
    "education_qualifications",
    "projects",
    "profile_summary",
)


def value(record: dict, key: str) -> str | None:
    raw = record.get(key)
    if pd.isna(raw) or not str(raw).strip():
        return None
    return str(raw).strip()


def extracted_text(record: dict) -> str:
    labels = {
        "target_job_category": "Target Role",
        "skills": "Skills",
        "experience": "Experience",
        "education_qualifications": "Education and Qualifications",
        "projects": "Projects",
        "profile_summary": "Profile Summary",
    }
    return "\n\n".join(
        f"{labels[field]}: {content}"
        for field in TEXT_FIELDS
        if (content := value(record, field))
    )


def import_candidate(email: str, records: list[dict], csv_path: Path, container) -> int:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user and user.role != "CANDIDATE":
            print(f"skipped {email}; existing role is {user.role}")
            return 0

        first_record = records[0]
        if not user:
            user = User(
                name=str(first_record["full_name"]).strip(),
                email=email,
                password_hash=hash_password(str(first_record["password"])),
                role="CANDIDATE",
            )
            db.add(user)
            db.flush()

        candidate = db.scalar(select(Candidate).where(Candidate.user_id == user.user_id))
        if not candidate:
            candidate = Candidate(
                user_id=user.user_id,
                phone=value(first_record, "phone"),
                location=value(first_record, "location"),
                profile_summary=value(first_record, "profile_summary"),
            )
            db.add(candidate)
            db.flush()

        next_version = (db.scalar(select(func.max(Resume.version)).where(Resume.candidate_id == candidate.candidate_id)) or 0) + 1
        latest_resume = None
        for record in records:
            relative_path = Path(str(record["resume_file"]))
            source_path = csv_path.parent / relative_path
            source_key = hashlib.sha256(str(relative_path).lower().encode("utf-8")).hexdigest()[:16]
            blob_path = f"candidate_{candidate.candidate_id}/dummy/{source_key}_{source_path.name}"
            resume = db.scalar(select(Resume).where(Resume.blob_path == blob_path))

            if not resume:
                resume_text = extracted_text(record)
                fill_missing_social_profiles(candidate, resume_text)
                content_type = mimetypes.guess_type(source_path.name)[0] or "application/pdf"
                try:
                    container.upload_blob(
                        name=blob_path,
                        data=source_path.read_bytes(),
                        overwrite=False,
                        content_settings=ContentSettings(content_type=content_type),
                    )
                except ResourceExistsError:
                    pass
                resume = Resume(
                    candidate_id=candidate.candidate_id,
                    version=next_version,
                    original_filename=source_path.name,
                    blob_path=blob_path,
                    content_type=content_type,
                    extracted_text=resume_text,
                    parsing_status="COMPLETED",
                )
                db.add(resume)
                db.flush()
                next_version += 1
            latest_resume = resume

        pool_entry = db.scalar(select(GlobalApplicant).where(GlobalApplicant.candidate_id == candidate.candidate_id))
        if pool_entry:
            pool_entry.resume_id = latest_resume.resume_id
        else:
            db.add(GlobalApplicant(candidate_id=candidate.candidate_id, resume_id=latest_resume.resume_id))
        db.commit()
        return len(records)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=str(ROOT / "dataset" / "Resumes PDF" / "dummy applicants.csv"))
    parser.add_argument("--checkpoint", default=str(ROOT / "dummy_applicants_checkpoint.json"))
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    csv_path = Path(args.file).resolve()
    frame = pd.read_csv(csv_path)
    if args.limit is not None:
        frame = frame.head(args.limit)

    missing_columns = {"full_name", "email", "password", "resume_file"} - set(frame.columns)
    if missing_columns:
        raise ValueError(f"Missing required columns: {sorted(missing_columns)}")

    missing_files = [
        str(relative_path)
        for relative_path in frame["resume_file"]
        if not (csv_path.parent / Path(str(relative_path))).is_file()
    ]
    if missing_files:
        raise FileNotFoundError(f"Missing {len(missing_files)} resume files; first: {missing_files[0]}")

    unique_candidates = frame["email"].str.strip().str.lower().nunique()
    print(f"validated {len(frame)} rows, {unique_candidates} unique candidates, {len(frame)} resume files")
    if args.dry_run:
        return

    if not settings.azure_storage_connection_string:
        raise RuntimeError("Azure Blob Storage is not configured")

    checkpoint_path = Path(args.checkpoint)
    completed_emails: set[str] = set()
    if checkpoint_path.exists() and not args.restart:
        completed_emails = set(json.loads(checkpoint_path.read_text()).get("completed_emails", []))

    blob_service = BlobServiceClient.from_connection_string(settings.azure_storage_connection_string)
    container = blob_service.get_container_client(settings.azure_storage_container)
    if not container.exists():
        container.create_container()

    frame["email_key"] = frame["email"].str.strip().str.lower()
    candidate_groups = {
        email: group.drop(columns="email_key").to_dict("records")
        for email, group in frame.groupby("email_key", sort=False)
        if email not in completed_emails
    }
    failures = []
    processed_rows = 0
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(import_candidate, email, records, csv_path, container): email
            for email, records in candidate_groups.items()
        }
        for completed_count, future in enumerate(as_completed(futures), start=1):
            email = futures[future]
            try:
                processed_rows += future.result()
                completed_emails.add(email)
                checkpoint_path.write_text(json.dumps({"completed_emails": sorted(completed_emails)}, indent=2))
            except Exception as exc:
                failures.append((email, str(exc)))
                print(f"failed {email}: {exc}")
            if completed_count % 10 == 0 or completed_count == len(futures):
                print(f"completed {completed_count}/{len(futures)} candidate groups ({processed_rows} rows this run)")
    if failures:
        raise RuntimeError(f"{len(failures)} candidate groups failed; rerun to retry them")


if __name__ == "__main__":
    main()