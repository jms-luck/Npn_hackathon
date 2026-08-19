from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.dependencies import get_recruiter
from backend.app.core.config import settings
from backend.app.database.connection import get_db
from backend.app.models import Company, JobPosting, Recruiter
from backend.app.schemas.contracts import JobCreate, JobResponse, JobUpdate
from backend.app.services.cache import cache_delete_prefix, cache_get, cache_set
from backend.app.services.public_ids import format_public_id


router = APIRouter(tags=["jobs"])


def job_payload(job: JobPosting, company_name: str | None) -> dict:
    payload = JobResponse.model_validate(job).model_dump(mode="json")
    payload.update({"Job_Id": format_public_id("job", job.job_id), "company_name": company_name})
    return payload


@router.get("/jobs", response_model=list[JobResponse])
def list_active_jobs(response: Response, limit: int = Query(50, le=100), offset: int = 0, db: Session = Depends(get_db)) -> list[JobPosting]:
    response.headers["Cache-Control"] = "public, max-age=30"
    key = f"jobs:active:{limit}:{offset}"
    if cached := cache_get(key):
        return cached
    statement = select(JobPosting, Company.company_name).join(Company, JobPosting.company_id == Company.company_id).where(JobPosting.status == "ACTIVE").order_by(JobPosting.job_id.desc()).offset(offset).limit(limit)
    rows = db.execute(statement).all()
    payload = [job_payload(job, company_name) for job, company_name in rows]
    cache_set(key, payload, settings.cache_job_ttl)
    return payload


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_active_job(job_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.execute(select(JobPosting, Company.company_name).join(Company).where(JobPosting.job_id == job_id, JobPosting.status == "ACTIVE")).first()
    if not row:
        raise HTTPException(status_code=404, detail="Active job not found")
    return job_payload(row[0], row[1])


@router.get("/recruiter/jobs", response_model=list[JobResponse])
def recruiter_jobs(limit: int = Query(24, ge=1, le=100), offset: int = Query(0, ge=0), recruiter: Recruiter = Depends(get_recruiter), db: Session = Depends(get_db)) -> list[dict]:
    statement = select(JobPosting, Company.company_name).join(Company).where(JobPosting.company_id == recruiter.company_id).order_by(JobPosting.job_id.desc()).offset(offset).limit(limit)
    return [job_payload(job, company_name) for job, company_name in db.execute(statement).all()]


@router.post("/recruiter/jobs", response_model=JobResponse, status_code=201)
def create_job(payload: JobCreate, recruiter: Recruiter = Depends(get_recruiter), db: Session = Depends(get_db)) -> JobPosting:
    job = JobPosting(**payload.model_dump(), company_id=recruiter.company_id, recruiter_id=recruiter.recruiter_id, source_type="RECRUITER", status="DRAFT")
    db.add(job)
    db.commit()
    db.refresh(job)
    cache_delete_prefix("jobs:active:")
    return job


def owned_job(job_id: int, recruiter: Recruiter, db: Session) -> JobPosting:
    job = db.get(JobPosting, job_id)
    if not job or job.company_id != recruiter.company_id:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.put("/recruiter/jobs/{job_id}", response_model=JobResponse)
def update_job(job_id: int, payload: JobUpdate, recruiter: Recruiter = Depends(get_recruiter), db: Session = Depends(get_db)) -> JobPosting:
    job = owned_job(job_id, recruiter, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(job, field, value)
    db.commit()
    db.refresh(job)
    cache_delete_prefix("jobs:active:")
    return job


@router.post("/recruiter/jobs/{job_id}/publish", response_model=JobResponse)
def publish_job(job_id: int, recruiter: Recruiter = Depends(get_recruiter), db: Session = Depends(get_db)) -> JobPosting:
    job = owned_job(job_id, recruiter, db)
    job.status = "ACTIVE"
    db.commit()
    db.refresh(job)
    cache_delete_prefix("jobs:active:")
    return job


@router.post("/recruiter/jobs/{job_id}/close", response_model=JobResponse)
def close_job(job_id: int, recruiter: Recruiter = Depends(get_recruiter), db: Session = Depends(get_db)) -> JobPosting:
    job = owned_job(job_id, recruiter, db)
    job.status = "CLOSED"
    db.commit()
    db.refresh(job)
    cache_delete_prefix("jobs:active:")
    return job


@router.get("/recruiter/jobs/{job_id}", response_model=JobResponse)
def recruiter_job(job_id: int, recruiter: Recruiter = Depends(get_recruiter), db: Session = Depends(get_db)) -> dict:
    job = owned_job(job_id, recruiter, db)
    company_name = db.scalar(select(Company.company_name).where(Company.company_id == job.company_id))
    return job_payload(job, company_name)