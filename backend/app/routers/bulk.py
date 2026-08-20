import csv
import logging
from io import BytesIO, StringIO
from pathlib import Path
from secrets import token_urlsafe
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from openpyxl import Workbook
from pydantic import EmailStr, TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.dependencies import get_recruiter
from backend.app.core.security import hash_password
from backend.app.database.connection import get_db
from backend.app.models import Application, Candidate, Company, JobPosting, Recruiter, Resume, User
from backend.app.routers.jobs import owned_job
from backend.app.services.ai import index_resumes_for_job
from backend.app.services.blob import delete_resume, upload_resume
from backend.app.services.parser import extract_resume_text, validate_resume_file
from backend.app.services.graph import sync_application_records, sync_candidate_records, sync_resume_records
from backend.app.services.public_ids import format_public_id
from backend.app.services.social_profiles import fill_missing_social_profiles


router = APIRouter(tags=["bulk applicants"])
logger = logging.getLogger("hireai.bulk")
EMAIL_ADAPTER = TypeAdapter(EmailStr)
MAX_BULK_ROWS = 200
MAX_RESUME_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 500 * 1024 * 1024
TEMPLATE = "full_name,email,phone,location,resume_filename\nJane Doe,jane@example.com,+1-555-0100,New York,jane-doe.pdf\n"


@router.get("/recruiter/jobs/{job_id}/applicants/bulk-template")
def bulk_template(job_id: int, recruiter: Recruiter = Depends(get_recruiter), db: Session = Depends(get_db)) -> Response:
    owned_job(job_id, recruiter, db)
    return Response(
        TEMPLATE,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="job-{job_id}-applicants-template.csv"'},
    )


def parse_rows(content: bytes) -> list[dict[str, str]]:
    try:
        reader = csv.DictReader(StringIO(content.decode("utf-8-sig")))
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded") from exc
    required = {"full_name", "email", "resume_filename"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        raise HTTPException(status_code=400, detail=f"CSV must include columns: {', '.join(sorted(required))}")
    rows = []
    seen_emails = set()
    for line_number, raw in enumerate(reader, start=2):
        row = {key: (value or "").strip() for key, value in raw.items() if key}
        if not any(row.values()):
            continue
        if not row.get("full_name") or not row.get("resume_filename"):
            raise HTTPException(status_code=400, detail=f"CSV line {line_number} is missing full_name or resume_filename")
        try:
            row["email"] = str(EMAIL_ADAPTER.validate_python(row.get("email", ""))).lower()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"CSV line {line_number} has an invalid email") from exc
        if row["email"] in seen_emails:
            raise HTTPException(status_code=400, detail=f"Duplicate email in CSV: {row['email']}")
        seen_emails.add(row["email"])
        row["resume_key"] = Path(row["resume_filename"]).name.lower()
        rows.append(row)
    if not rows:
        raise HTTPException(status_code=400, detail="CSV has no applicant rows")
    if len(rows) > MAX_BULK_ROWS:
        raise HTTPException(status_code=413, detail=f"A bulk upload supports at most {MAX_BULK_ROWS} applicants")
    return rows


def resume_files_from_zip(content: bytes) -> list[tuple[str, bytes, str]]:
    if len(content) > MAX_TOTAL_BYTES:
        raise HTTPException(status_code=413, detail="Resume ZIP exceeds 500 MB")
    try:
        with ZipFile(BytesIO(content)) as archive:
            entries = [entry for entry in archive.infolist() if not entry.is_dir()]
            if len(entries) > MAX_BULK_ROWS:
                raise HTTPException(status_code=413, detail=f"Resume ZIP may contain at most {MAX_BULK_ROWS} files")
            if sum(entry.file_size for entry in entries) > MAX_TOTAL_BYTES:
                raise HTTPException(status_code=413, detail="Extracted ZIP content exceeds 500 MB")
            files = []
            for entry in entries:
                path = Path(entry.filename)
                if path.is_absolute() or ".." in path.parts:
                    raise HTTPException(status_code=400, detail="Resume ZIP contains an unsafe path")
                filename = path.name
                if Path(filename).suffix.lower() not in {".pdf", ".docx"}:
                    raise HTTPException(status_code=415, detail=f"Unsupported file in resume ZIP: {filename}")
                payload = archive.read(entry)
                try:
                    safe_name, content_type = validate_resume_file(filename, payload)
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=f"Unsafe resume file: {filename}") from exc
                files.append((safe_name, payload, content_type))
            return files
    except BadZipFile as exc:
        raise HTTPException(status_code=400, detail="Invalid resume ZIP archive") from exc


def credential_workbook(credentials: list[dict]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "New Applicants"
    sheet.append(["Full Name", "Email", "Initial Password", "Candidate ID", "Resume"])
    for item in credentials:
        sheet.append([item["name"], item["email"], item["password"], item["candidate_id"], item["resume_filename"]])
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for column, width in {"A": 28, "B": 34, "C": 28, "D": 16, "E": 34}.items():
        sheet.column_dimensions[column].width = width
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


@router.post("/recruiter/jobs/{job_id}/applicants/bulk", status_code=201)
def bulk_upload(
    job_id: int,
    csv_file: UploadFile = File(...),
    resume_files: list[UploadFile] | None = File(None),
    resume_archive: UploadFile | None = File(None),
    recruiter: Recruiter = Depends(get_recruiter),
    db: Session = Depends(get_db),
) -> dict:
    job = owned_job(job_id, recruiter, db)
    rows = parse_rows(csv_file.file.read())
    if not resume_files and not resume_archive:
        raise HTTPException(status_code=400, detail="Upload a ZIP archive or individual resume files")
    resume_files = resume_files or []
    if len(resume_files) > MAX_BULK_ROWS:
        raise HTTPException(status_code=413, detail=f"Upload at most {MAX_BULK_ROWS} resume files")

    files: dict[str, tuple[str, bytes, str | None]] = {}
    total_bytes = 0
    if resume_archive:
        for filename, content, content_type in resume_files_from_zip(resume_archive.file.read()):
            key = filename.lower()
            if key in files:
                raise HTTPException(status_code=400, detail=f"Duplicate resume filename: {filename}")
            files[key] = (filename, content, content_type)
            total_bytes += len(content)
    for upload in resume_files:
        filename = Path(upload.filename or "").name
        extension = Path(filename).suffix.lower()
        if extension not in {".pdf", ".docx"}:
            raise HTTPException(status_code=415, detail=f"Unsupported resume file: {filename}")
        content = upload.file.read()
        if len(content) > MAX_RESUME_BYTES:
            raise HTTPException(status_code=413, detail=f"Resume exceeds 10 MB: {filename}")
        try:
            filename, content_type = validate_resume_file(filename, content)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Unsafe resume file: {filename}") from exc
        total_bytes += len(content)
        key = filename.lower()
        if key in files:
            raise HTTPException(status_code=400, detail=f"Duplicate uploaded filename: {filename}")
        files[key] = (filename, content, content_type)
    if total_bytes > MAX_TOTAL_BYTES:
        raise HTTPException(status_code=413, detail="Bulk resume files exceed 500 MB")

    missing = [row["resume_filename"] for row in rows if row["resume_key"] not in files]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing uploaded resume files: {', '.join(missing[:5])}")

    emails = [row["email"] for row in rows]
    users_by_email = {user.email: user for user in db.scalars(select(User).where(User.email.in_(emails)))}
    existing_users = list(users_by_email.values())
    candidates_by_user = {item.user_id: item for item in db.scalars(select(Candidate).where(Candidate.user_id.in_([user.user_id for user in existing_users])))} if existing_users else {}
    existing_candidate_ids = [candidate.candidate_id for candidate in candidates_by_user.values()]
    applied_candidates = set(db.scalars(select(Application.candidate_id).where(Application.job_id == job_id, Application.candidate_id.in_(existing_candidate_ids)))) if existing_candidate_ids else set()
    uploaded_blob_paths = []
    created_resumes: list[Resume] = []
    created_candidates = 0
    skipped = 0
    credentials = []

    try:
        for row in rows:
            user = users_by_email.get(row["email"])
            initial_password = None
            if user and user.role != "CANDIDATE":
                raise HTTPException(status_code=409, detail=f"Email belongs to a {user.role.lower()} account: {row['email']}")
            candidate = candidates_by_user.get(user.user_id) if user else None
            if candidate and candidate.candidate_id in applied_candidates:
                skipped += 1
                continue
            if not user:
                initial_password = token_urlsafe(14)
                user = User(name=row["full_name"], email=row["email"], password_hash=hash_password(initial_password), role="CANDIDATE")
                db.add(user)
                db.flush()
                users_by_email[user.email] = user
            if not candidate:
                candidate = Candidate(user_id=user.user_id, phone=row.get("phone") or None, location=row.get("location") or None)
                db.add(candidate)
                db.flush()
                candidates_by_user[user.user_id] = candidate
                created_candidates += 1
                if initial_password:
                    credentials.append({"name": user.name, "email": user.email, "password": initial_password, "candidate_id": candidate.candidate_id, "resume_filename": row["resume_filename"]})

            version = (db.scalar(select(func.max(Resume.version)).where(Resume.candidate_id == candidate.candidate_id)) or 0) + 1
            filename, content, content_type = files[row["resume_key"]]
            text = extract_resume_text(filename, content)
            if not text:
                raise HTTPException(status_code=400, detail=f"No text could be extracted from {filename}")
            fill_missing_social_profiles(candidate, text)
            blob_path = f"candidate_{candidate.candidate_id}/bulk/{uuid4().hex}_{filename}"
            upload_resume(blob_path, content, content_type)
            uploaded_blob_paths.append(blob_path)
            resume = Resume(candidate_id=candidate.candidate_id, version=version, original_filename=filename, blob_path=blob_path, content_type=content_type, extracted_text=text, parsing_status="COMPLETED")
            db.add(resume)
            db.flush()
            db.add(Application(candidate_id=candidate.candidate_id, job_id=job_id, resume_id=resume.resume_id))
            created_resumes.append(resume)
        db.commit()
    except HTTPException:
        db.rollback()
        for blob_path in uploaded_blob_paths:
            try:
                delete_resume(blob_path)
            except Exception:
                logger.exception("Could not clean up bulk-upload blob %s", blob_path)
        raise
    except Exception as exc:
        db.rollback()
        for blob_path in uploaded_blob_paths:
            try:
                delete_resume(blob_path)
            except Exception:
                logger.exception("Could not clean up bulk-upload blob %s", blob_path)
        raise HTTPException(status_code=502, detail="Bulk upload processing failed") from exc

    indexed = True
    try:
        index_resumes_for_job(job, created_resumes)
    except Exception:
        indexed = False
        logger.exception("Bulk resumes were saved but Qdrant indexing failed for job %s", job_id)
    graph_synced = True
    try:
        candidate_ids = [resume.candidate_id for resume in created_resumes]
        candidates = {item.candidate_id: item for item in db.scalars(select(Candidate).where(Candidate.candidate_id.in_(candidate_ids)))}
        users = {item.user_id: item for item in db.scalars(select(User).where(User.user_id.in_([item.user_id for item in candidates.values()])))}
        company = db.get(Company, job.company_id)
        applications = {item.resume_id: item for item in db.scalars(select(Application).where(Application.job_id == job_id, Application.resume_id.in_([item.resume_id for item in created_resumes])))}
        sync_candidate_records([{"candidate_id":item.candidate_id,"public_id":format_public_id("candidate",item.candidate_id),"name":users[item.user_id].name,"email":users[item.user_id].email,"phone":item.phone,"location":item.location,"profile_summary":item.profile_summary,"linkedin_url":item.linkedin_url,"github_url":item.github_url,"portfolio_url":item.portfolio_url} for item in candidates.values()])
        sync_resume_records([{"candidate_id":item.candidate_id,"resume_id":item.resume_id,"public_id":f"RES_{item.resume_id:03d}","name":item.original_filename,"version":item.version,"content_type":item.content_type,"parsing_status":item.parsing_status,"created_at":item.created_at.isoformat() if item.created_at else None} for item in created_resumes])
        sync_application_records([{"candidate_id":item.candidate_id,"resume_id":item.resume_id,"company_id":company.company_id,"company_public_id":format_public_id("company",company.company_id),"company_name":company.company_name,"job_id":job.job_id,"job_public_id":format_public_id("job",job.job_id),"job_title":job.job_title,"job_description":job.job_description,"skills":job.skills,"application_id":applications[item.resume_id].application_id,"application_public_id":format_public_id("application",applications[item.resume_id].application_id),"status":applications[item.resume_id].status,"scope":"JOB","applied_at":applications[item.resume_id].applied_at.isoformat() if applications[item.resume_id].applied_at else None} for item in created_resumes])
    except Exception:
        graph_synced = False
        logger.exception("Bulk applicants were saved but Neo4j sync failed for job %s", job_id)
    workbook = credential_workbook(credentials)
    return Response(
        workbook,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="job-{job_id}-new-applicant-credentials.xlsx"',
            "X-Applications-Created": str(len(created_resumes)),
            "X-Candidates-Created": str(created_candidates),
            "X-Duplicates-Skipped": str(skipped),
            "X-Indexed": str(indexed).lower(),
            "X-Graph-Synced": str(graph_synced).lower(),
            "Cache-Control": "no-store, max-age=0",
        },
    )
