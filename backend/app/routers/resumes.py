from pathlib import Path
from uuid import uuid4
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.dependencies import get_candidate, get_current_user
from backend.app.database.connection import get_db
from backend.app.models import Application, Candidate, JobPosting, Recruiter, Resume, User
from backend.app.schemas.contracts import ResumeResponse
from backend.app.services.ai import upsert_resume
from backend.app.services.blob import create_download_url, delete_resume, upload_resume
from backend.app.services.parser import extract_resume_text, validate_resume_file
from backend.app.services.social_profiles import fill_missing_social_profiles


router = APIRouter(prefix="/resumes", tags=["resumes"])
logger = logging.getLogger("hireai.resumes")


@router.post("/upload", response_model=ResumeResponse, status_code=201)
def upload(file: UploadFile = File(...), candidate: Candidate = Depends(get_candidate), db: Session = Depends(get_db)) -> Resume:
    extension = Path(file.filename or "").suffix.lower()
    if extension not in {".pdf", ".docx"}:
        raise HTTPException(status_code=415, detail="Only PDF and DOCX resumes are supported")
    content = file.file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Resume exceeds 10 MB")
    try:
        filename, content_type = validate_resume_file(file.filename or f"resume{extension}", content)
        text = extract_resume_text(filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not text:
        raise HTTPException(status_code=400, detail="No text could be safely extracted from the resume")
    version = (db.scalar(select(func.max(Resume.version)).where(Resume.candidate_id == candidate.candidate_id)) or 0) + 1
    blob_path = f"candidate_{candidate.candidate_id}/resume_v{version}_{uuid4().hex}{extension}"
    resume = Resume(candidate_id=candidate.candidate_id, version=version, original_filename=filename, blob_path=blob_path, content_type=content_type, parsing_status="PROCESSING")
    blob_uploaded = False
    try:
        fill_missing_social_profiles(candidate, text)
        upload_resume(blob_path, content, content_type)
        blob_uploaded = True
        resume.extracted_text = text
        resume.parsing_status = "COMPLETED"
        db.add(resume)
        db.commit()
        db.refresh(resume)
    except Exception as exc:
        db.rollback()
        if blob_uploaded:
            try:
                delete_resume(blob_path)
            except Exception:
                logger.exception("Could not clean up failed resume upload")
        logger.exception("Resume storage failed for candidate %s", candidate.candidate_id)
        raise HTTPException(status_code=502, detail="Resume storage is temporarily unavailable") from exc
    try:
        upsert_resume(resume.resume_id, candidate.candidate_id, text)
    except Exception:
        logger.exception("Resume %s was stored but vector indexing failed", resume.resume_id)
    return resume


def authorized_resume(resume_id: int, user: User, db: Session) -> Resume:
    resume = db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    if user.role == "CANDIDATE":
        candidate = db.scalar(select(Candidate).where(Candidate.user_id == user.user_id))
        if candidate and resume.candidate_id == candidate.candidate_id:
            return resume
    if user.role == "RECRUITER":
        recruiter = db.scalar(select(Recruiter).where(Recruiter.user_id == user.user_id))
        if not recruiter:
            raise HTTPException(status_code=403, detail="Resume access denied")
        statement = select(Application.application_id).join(JobPosting).where(Application.resume_id == resume_id, JobPosting.company_id == recruiter.company_id)
        if db.scalar(statement):
            return resume
    raise HTTPException(status_code=403, detail="Resume access denied")


@router.get("/{resume_id}")
def get_resume(resume_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    resume = authorized_resume(resume_id, user, db)
    return {"resume": ResumeResponse.model_validate(resume), "download_url": create_download_url(resume.blob_path)}


@router.delete("/{resume_id}", status_code=204)
def remove_resume(resume_id: int, candidate: Candidate = Depends(get_candidate), db: Session = Depends(get_db)) -> None:
    resume = db.get(Resume, resume_id)
    if not resume or resume.candidate_id != candidate.candidate_id:
        raise HTTPException(status_code=404, detail="Resume not found")
    if db.scalar(select(Application.application_id).where(Application.resume_id == resume_id)):
        raise HTTPException(status_code=409, detail="A submitted resume cannot be deleted")
    delete_resume(resume.blob_path)
    db.delete(resume)
    db.commit()