from fastapi import APIRouter, Depends, HTTPException, Query
import re
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.dependencies import require_role
from backend.app.database.connection import get_db
from backend.app.models import Application, Candidate, Company, GlobalApplicant, Interview, Interviewer, JobPosting, MatchResult, Recruiter, Resume, User
from backend.app.services.blob import create_download_url, delete_resume as delete_blob
from backend.app.core.config import settings
from backend.app.services.cache import cache_get, cache_set
from backend.app.services.public_ids import format_public_id, parse_public_id
from backend.app.services.audit_reader import read_audit_events
from backend.app.services.verification_codes import generate_company_verification_code


router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_role("ADMIN"))])


class CompanyWrite(BaseModel):
    company_name: str = Field(min_length=2, max_length=255)
    company_size: str | None = None
    company_profile: str | None = None
    verification_code: str | None = None

    @field_validator("verification_code", mode="before")
    @classmethod
    def normalize_verification_code(cls, value):
        return str(value).strip() if value is not None and str(value).strip() else None


class UserUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    is_active: bool | None = None


class JobWrite(BaseModel):
    Job_Role: str = Field(min_length=2, max_length=255)
    company_ID: str
    location: str | None = None
    work_type: str | None = None
    status: str = "DRAFT"


class CandidateUpdate(BaseModel):
    phone: str | None = None
    location: str | None = None
    profile_summary: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None


class StaffUpdate(BaseModel):
    company_ID: str | None = None
    designation: str | None = None
    phone: str | None = None


class ApplicationUpdate(BaseModel):
    status: str = Field(min_length=2, max_length=30)


def db_id(public_id: str, entity: str) -> int:
    try:
        return parse_public_id(public_id, entity)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def pagination(total: int, page: int, limit: int, items: list) -> dict:
    return {"items": items, "total": total, "page": page, "limit": limit, "pages": max(1, (total + limit - 1) // limit)}


def ordering(column, order: str):
    return column.desc() if order == "desc" else column.asc()


def commit_or_conflict(db: Session, detail: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=detail) from exc


def company_item(item: Company) -> dict:
    return {
        "company_ID": format_public_id("company", item.company_id), "company_name": item.company_name,
        "company_size": item.company_size, "company_profile": item.company_profile,
        "verification_code": item.verification_code, "created_at": item.created_at,
    }


def resume_section(text: str | None, labels: list[str]) -> str | None:
    if not text:
        return None
    all_labels = ["Skills", "Experience", "Education", "Education and Qualifications", "Projects", "Profile Summary", "Target Role"]
    for label in labels:
        match = re.search(rf"(?:^|\n)\s*{re.escape(label)}\s*:\s*(.*?)(?=\n\s*(?:{'|'.join(re.escape(item) for item in all_labels)})\s*:|\Z)", text, re.IGNORECASE | re.DOTALL)
        if match and match.group(1).strip():
            return match.group(1).strip()
    return None


@router.get("/overview")
def overview(db: Session = Depends(get_db)) -> dict:
    if cached := cache_get("admin:overview"):
        return cached
    models = {"companies": Company, "users": User, "jobs": JobPosting, "applications": Application, "resumes": Resume, "interviews": Interview, "candidates": Candidate, "recruiters": Recruiter, "interviewers": Interviewer, "global_applicants": GlobalApplicant, "matches": MatchResult}
    payload = {name: db.scalar(select(func.count()).select_from(model)) or 0 for name, model in models.items()}
    cache_set("admin:overview", payload, settings.cache_default_ttl)
    return payload


@router.get("/audit")
def audit_events(
    q: str | None = None,
    service: str | None = None,
    outcome: str | None = Query(None, pattern="^(SUCCESS|REJECTED|ERROR|UNKNOWN)?$"),
    sort_by: str = "timestamp",
    order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    total, items = read_audit_events(settings.log_dir, page, limit, q, service, outcome, order)
    return pagination(total, page, limit, items)


@router.get("/companies")
def companies(q: str | None = None, sort_by: str = "company_name", order: str = Query("asc", pattern="^(asc|desc)$"), page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)) -> dict:
    filters = [Company.company_name.ilike(f"%{q.strip()}%")] if q else []
    sort = {"company_ID": Company.company_id, "company_name": Company.company_name, "company_size": Company.company_size, "created_at": Company.created_at}.get(sort_by, Company.company_name)
    total = db.scalar(select(func.count()).select_from(Company).where(*filters)) or 0
    rows = db.scalars(select(Company).where(*filters).order_by(ordering(sort, order)).offset((page - 1) * limit).limit(limit)).all()
    return pagination(total, page, limit, [company_item(item) for item in rows])


@router.post("/companies", status_code=201)
def create_company(payload: CompanyWrite, db: Session = Depends(get_db)) -> dict:
    values = payload.model_dump()
    values["verification_code"] = values["verification_code"] or generate_company_verification_code()
    item = Company(**values)
    db.add(item); commit_or_conflict(db, "A company with this name already exists"); db.refresh(item)
    return company_item(item)


@router.put("/companies/{company_ID}")
def update_company(company_ID: str, payload: CompanyWrite, db: Session = Depends(get_db)) -> dict:
    item = db.get(Company, db_id(company_ID, "company"))
    if not item: raise HTTPException(404, "Company not found")
    values = payload.model_dump()
    values["verification_code"] = values["verification_code"] or generate_company_verification_code()
    for key, value in values.items(): setattr(item, key, value)
    commit_or_conflict(db, "A company with this name already exists"); db.refresh(item)
    return company_item(item)


@router.delete("/companies/{company_ID}", status_code=204)
def delete_company(company_ID: str, db: Session = Depends(get_db)) -> None:
    item = db.get(Company, db_id(company_ID, "company"))
    if not item: raise HTTPException(404, "Company not found")
    used = db.scalar(select(JobPosting.job_id).where(JobPosting.company_id == item.company_id)) or db.scalar(select(Recruiter.recruiter_id).where(Recruiter.company_id == item.company_id)) or db.scalar(select(Interviewer.interviewer_id).where(Interviewer.company_id == item.company_id))
    if used: raise HTTPException(409, "Company is referenced by jobs or staff")
    db.delete(item); db.commit()


@router.get("/users")
def users(q: str | None = None, role: str | None = None, sort_by: str = "created_at", order: str = Query("desc", pattern="^(asc|desc)$"), page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)) -> dict:
    filters = []
    if q: filters.append(or_(User.name.ilike(f"%{q.strip()}%"), User.email.ilike(f"%{q.strip()}%")))
    if role: filters.append(User.role == role.upper())
    sort = {"User_Id": User.user_id, "name": User.name, "email": User.email, "role": User.role, "created_at": User.created_at}.get(sort_by, User.created_at)
    total = db.scalar(select(func.count()).select_from(User).where(*filters)) or 0
    rows = db.scalars(select(User).where(*filters).order_by(ordering(sort, order)).offset((page - 1) * limit).limit(limit)).all()
    items = [{"User_Id": format_public_id("user", x.user_id), "name": x.name, "email": x.email, "role": x.role, "is_active": x.is_active, "created_at": x.created_at} for x in rows]
    return pagination(total, page, limit, items)


@router.put("/users/{User_Id}")
def update_user(User_Id: str, payload: UserUpdate, db: Session = Depends(get_db)) -> dict:
    item = db.get(User, db_id(User_Id, "user"))
    if not item: raise HTTPException(404, "User not found")
    for key, value in payload.model_dump(exclude_unset=True).items(): setattr(item, key, value)
    commit_or_conflict(db, "Email is already registered"); db.refresh(item)
    return {"User_Id": format_public_id("user", item.user_id), "name": item.name, "email": item.email, "role": item.role, "is_active": item.is_active}


@router.delete("/users/{User_Id}", status_code=204)
def delete_user(User_Id: str, db: Session = Depends(get_db)) -> None:
    item = db.get(User, db_id(User_Id, "user"))
    if not item: raise HTTPException(404, "User not found")
    if item.role == "ADMIN": raise HTTPException(409, "The default admin cannot be deleted")
    db.delete(item); commit_or_conflict(db, "User has related records and cannot be deleted")


@router.get("/jobs")
def jobs(q: str | None = None, status: str | None = None, sort_by: str = "Job_Id", order: str = Query("desc", pattern="^(asc|desc)$"), page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)) -> dict:
    filters = []
    if q: filters.append(or_(JobPosting.job_title.ilike(f"%{q.strip()}%"), Company.company_name.ilike(f"%{q.strip()}%")))
    if status: filters.append(JobPosting.status == status.upper())
    sort = {"Job_Id": JobPosting.job_id, "Job_Role": JobPosting.job_title, "company_name": Company.company_name, "status": JobPosting.status, "created_at": JobPosting.created_at}.get(sort_by, JobPosting.job_id)
    base = select(JobPosting, Company).join(Company, JobPosting.company_id == Company.company_id).where(*filters)
    total = db.scalar(select(func.count()).select_from(JobPosting).join(Company).where(*filters)) or 0
    rows = db.execute(base.order_by(ordering(sort, order)).offset((page - 1) * limit).limit(limit)).all()
    items = [{"Job_Id": format_public_id("job", job.job_id), "Job_Role": job.job_title, "company_name": company.company_name, "company_ID": format_public_id("company", company.company_id), "location": job.location, "work_type": job.work_type, "status": job.status, "created_at": job.created_at} for job, company in rows]
    return pagination(total, page, limit, items)


@router.post("/jobs", status_code=201)
def create_job(payload: JobWrite, db: Session = Depends(get_db)) -> dict:
    company = db.get(Company, db_id(payload.company_ID, "company"))
    if not company: raise HTTPException(404, "Company not found")
    item = JobPosting(company_id=company.company_id, job_title=payload.Job_Role, role=payload.Job_Role, location=payload.location, work_type=payload.work_type, source_type="RECRUITER", status=payload.status.upper())
    db.add(item); db.commit(); db.refresh(item)
    return {"Job_Id": format_public_id("job", item.job_id), "Job_Role": item.job_title, "company_name": company.company_name, "status": item.status}


@router.put("/jobs/{Job_Id}")
def update_job(Job_Id: str, payload: JobWrite, db: Session = Depends(get_db)) -> dict:
    item = db.get(JobPosting, db_id(Job_Id, "job")); company = db.get(Company, db_id(payload.company_ID, "company"))
    if not item: raise HTTPException(404, "Job not found")
    if not company: raise HTTPException(404, "Company not found")
    item.job_title = payload.Job_Role; item.role = payload.Job_Role; item.company_id = company.company_id; item.location = payload.location; item.work_type = payload.work_type; item.status = payload.status.upper(); db.commit(); db.refresh(item)
    return {"Job_Id": format_public_id("job", item.job_id), "Job_Role": item.job_title, "company_name": company.company_name, "status": item.status}


@router.delete("/jobs/{Job_Id}", status_code=204)
def delete_job(Job_Id: str, db: Session = Depends(get_db)) -> None:
    item = db.get(JobPosting, db_id(Job_Id, "job"))
    if not item: raise HTTPException(404, "Job not found")
    if db.scalar(select(Application.application_id).where(Application.job_id == item.job_id)): raise HTTPException(409, "Job has applications and cannot be deleted")
    db.delete(item); db.commit()


@router.get("/candidates")
def candidates(q: str | None = None, sort_by: str = "candidate_id", order: str = Query("asc", pattern="^(asc|desc)$"), page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)) -> dict:
    filters = [or_(User.name.ilike(f"%{q.strip()}%"), User.email.ilike(f"%{q.strip()}%"), Candidate.location.ilike(f"%{q.strip()}%"))] if q else []
    sort = {"candidate_id": Candidate.candidate_id, "candidate_name": User.name, "location": Candidate.location}.get(sort_by, Candidate.candidate_id)
    total = db.scalar(select(func.count()).select_from(Candidate).join(User).where(*filters)) or 0
    rows = db.execute(select(Candidate, User).join(User).where(*filters).order_by(ordering(sort, order)).offset((page - 1) * limit).limit(limit)).all()
    items = [{"candidate_id": format_public_id("candidate", c.candidate_id), "candidate_name": u.name, "email": u.email, "phone": c.phone, "location": c.location, "profile_summary": c.profile_summary, "profile_preview": (c.profile_summary[:90] + "...") if c.profile_summary and len(c.profile_summary) > 90 else c.profile_summary} for c, u in rows]
    return pagination(total, page, limit, items)


@router.get("/candidates/{candidate_id}")
def candidate_details(candidate_id: str, db: Session = Depends(get_db)) -> dict:
    row = db.execute(select(Candidate, User).join(User).where(Candidate.candidate_id == db_id(candidate_id, "candidate"))).first()
    if not row: raise HTTPException(404, "Candidate not found")
    candidate, user = row
    resumes = db.scalars(select(Resume).where(Resume.candidate_id == candidate.candidate_id).order_by(Resume.version.desc())).all()
    latest_text = resumes[0].extracted_text if resumes else None
    return {"candidate_id": format_public_id("candidate", candidate.candidate_id), "candidate_name": user.name, "email": user.email, "profile_summary": candidate.profile_summary, "skills": resume_section(latest_text, ["Skills"]), "experience": resume_section(latest_text, ["Experience"]), "education": resume_section(latest_text, ["Education and Qualifications", "Education"]), "phone": candidate.phone, "location": candidate.location, "linkedin_url": candidate.linkedin_url, "github_url": candidate.github_url, "portfolio_url": candidate.portfolio_url, "resume_information": [{"resume_ref": format_public_id("resume", r.resume_id), "resume_name": r.original_filename, "version": r.version, "uploaded_date": r.created_at} for r in resumes]}


@router.put("/candidates/{candidate_id}")
def update_candidate(candidate_id: str, payload: CandidateUpdate, db: Session = Depends(get_db)) -> dict:
    item = db.get(Candidate, db_id(candidate_id, "candidate"))
    if not item: raise HTTPException(404, "Candidate not found")
    for key, value in payload.model_dump(exclude_unset=True).items(): setattr(item, key, value)
    db.commit(); return {"candidate_id": format_public_id("candidate", item.candidate_id), "updated": True}


@router.delete("/candidates/{candidate_id}", status_code=204)
def delete_candidate(candidate_id: str, db: Session = Depends(get_db)) -> None:
    item = db.get(Candidate, db_id(candidate_id, "candidate"))
    if not item: raise HTTPException(404, "Candidate not found")
    if db.scalar(select(Application.application_id).where(Application.candidate_id == item.candidate_id)): raise HTTPException(409, "Candidate has applications and cannot be deleted")
    db.delete(item); commit_or_conflict(db, "Candidate has related records and cannot be deleted")


def staff_page(db: Session, model, entity: str, id_column, q: str | None, page: int, limit: int, order: str) -> dict:
    filters = [or_(User.name.ilike(f"%{q.strip()}%"), User.email.ilike(f"%{q.strip()}%"), Company.company_name.ilike(f"%{q.strip()}%"))] if q else []
    total = db.scalar(select(func.count()).select_from(model).join(User).join(Company).where(*filters)) or 0
    rows = db.execute(select(model, User, Company).join(User).join(Company).where(*filters).order_by(ordering(id_column, order)).offset((page - 1) * limit).limit(limit)).all()
    items = [{f"{entity}_id" if entity == "recruiter" else "interviewer_Id": format_public_id(entity, getattr(staff, f"{entity}_id")), "name": user.name, "email": user.email, "company_name": company.company_name, "company_ID": format_public_id("company", company.company_id), "designation": staff.designation, "phone": staff.phone} for staff, user, company in rows]
    return pagination(total, page, limit, items)


@router.get("/recruiters")
def recruiters(q: str | None = None, order: str = Query("asc", pattern="^(asc|desc)$"), page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)) -> dict:
    return staff_page(db, Recruiter, "recruiter", Recruiter.recruiter_id, q, page, limit, order)


@router.put("/recruiters/{recruiter_id}")
def update_recruiter(recruiter_id: str, payload: StaffUpdate, db: Session = Depends(get_db)) -> dict:
    item = db.get(Recruiter, db_id(recruiter_id, "recruiter"))
    if not item: raise HTTPException(404, "Recruiter not found")
    if payload.company_ID is not None: item.company_id = db_id(payload.company_ID, "company")
    if payload.designation is not None: item.designation = payload.designation
    if payload.phone is not None: item.phone = payload.phone
    commit_or_conflict(db, "Recruiter update conflicts with related data"); return {"recruiter_id": format_public_id("recruiter", item.recruiter_id), "updated": True}


@router.delete("/recruiters/{recruiter_id}", status_code=204)
def delete_recruiter(recruiter_id: str, db: Session = Depends(get_db)) -> None:
    item = db.get(Recruiter, db_id(recruiter_id, "recruiter"))
    if not item: raise HTTPException(404, "Recruiter not found")
    db.execute(JobPosting.__table__.update().where(JobPosting.recruiter_id == item.recruiter_id).values(recruiter_id=None)); db.delete(item); db.commit()


@router.get("/interviewers")
def interviewers(q: str | None = None, order: str = Query("asc", pattern="^(asc|desc)$"), page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)) -> dict:
    return staff_page(db, Interviewer, "interviewer", Interviewer.interviewer_id, q, page, limit, order)


@router.put("/interviewers/{interviewer_Id}")
def update_interviewer(interviewer_Id: str, payload: StaffUpdate, db: Session = Depends(get_db)) -> dict:
    item = db.get(Interviewer, db_id(interviewer_Id, "interviewer"))
    if not item: raise HTTPException(404, "Interviewer not found")
    if payload.company_ID is not None: item.company_id = db_id(payload.company_ID, "company")
    if payload.designation is not None: item.designation = payload.designation
    if payload.phone is not None: item.phone = payload.phone
    commit_or_conflict(db, "Interviewer update conflicts with related data"); return {"interviewer_Id": format_public_id("interviewer", item.interviewer_id), "updated": True}


@router.delete("/interviewers/{interviewer_Id}", status_code=204)
def delete_interviewer(interviewer_Id: str, db: Session = Depends(get_db)) -> None:
    item = db.get(Interviewer, db_id(interviewer_Id, "interviewer"))
    if not item: raise HTTPException(404, "Interviewer not found")
    if db.scalar(select(Interview.interview_id).where(Interview.interviewer_id == item.interviewer_id)): raise HTTPException(409, "Interviewer has interviews and cannot be deleted")
    db.delete(item); db.commit()


@router.get("/applications")
def applications(q: str | None = None, status: str | None = None, sort_by: str = "applied_date", order: str = Query("desc", pattern="^(asc|desc)$"), page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)) -> dict:
    filters = []
    if q: filters.append(or_(User.name.ilike(f"%{q.strip()}%"), JobPosting.job_title.ilike(f"%{q.strip()}%"), Company.company_name.ilike(f"%{q.strip()}%")))
    if status: filters.append(Application.status == status.upper())
    sort = {"Application_Id": Application.application_id, "candidate_name": User.name, "job_Role": JobPosting.job_title, "company_name": Company.company_name, "status": Application.status, "applied_date": Application.applied_at}.get(sort_by, Application.applied_at)
    joins = select(Application, User, JobPosting, Company).join(Candidate, Application.candidate_id == Candidate.candidate_id).join(User, Candidate.user_id == User.user_id).join(JobPosting, Application.job_id == JobPosting.job_id).join(Company, JobPosting.company_id == Company.company_id)
    total = db.scalar(select(func.count()).select_from(Application).join(Candidate).join(User).join(JobPosting).join(Company).where(*filters)) or 0
    rows = db.execute(joins.where(*filters).order_by(ordering(sort, order)).offset((page - 1) * limit).limit(limit)).all()
    items = [{"Application_Id": format_public_id("application", app.application_id), "candidate_name": user.name, "candidate_id": format_public_id("candidate", app.candidate_id), "job_Role": job.job_title, "Job_Id": format_public_id("job", app.job_id), "company_name": company.company_name, "status": app.status, "applied_date": app.applied_at} for app, user, job, company in rows]
    return pagination(total, page, limit, items)


@router.put("/applications/{Application_Id}")
def update_application(Application_Id: str, payload: ApplicationUpdate, db: Session = Depends(get_db)) -> dict:
    item = db.get(Application, db_id(Application_Id, "application"))
    if not item: raise HTTPException(404, "Application not found")
    item.status = payload.status.upper(); db.commit(); return {"Application_Id": format_public_id("application", item.application_id), "status": item.status}


@router.delete("/applications/{Application_Id}", status_code=204)
def delete_application(Application_Id: str, db: Session = Depends(get_db)) -> None:
    item = db.get(Application, db_id(Application_Id, "application"))
    if not item: raise HTTPException(404, "Application not found")
    db.delete(item); db.commit()


@router.get("/resumes")
def resumes(q: str | None = None, sort_by: str = "uploaded_date", order: str = Query("desc", pattern="^(asc|desc)$"), page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)) -> dict:
    filters = [or_(User.name.ilike(f"%{q.strip()}%"), Resume.original_filename.ilike(f"%{q.strip()}%"))] if q else []
    sort = {"candidate_id": Candidate.candidate_id, "candidate_name": User.name, "resume_name": Resume.original_filename, "version": Resume.version, "uploaded_date": Resume.created_at}.get(sort_by, Resume.created_at)
    total = db.scalar(select(func.count()).select_from(Resume).join(Candidate, Resume.candidate_id == Candidate.candidate_id).join(User, Candidate.user_id == User.user_id).where(*filters)) or 0
    rows = db.execute(select(Resume, Candidate, User).select_from(Resume).join(Candidate, Resume.candidate_id == Candidate.candidate_id).join(User, Candidate.user_id == User.user_id).where(*filters).order_by(ordering(sort, order)).offset((page - 1) * limit).limit(limit)).all()
    items = [{"resume_ref": format_public_id("resume", r.resume_id), "candidate_id": format_public_id("candidate", c.candidate_id), "candidate_name": u.name, "resume_name": r.original_filename, "version": r.version, "uploaded_date": r.created_at, "parsing_status": r.parsing_status} for r, c, u in rows]
    return pagination(total, page, limit, items)


@router.get("/resumes/{resume_ref}/access")
def resume_access(resume_ref: str, db: Session = Depends(get_db)) -> dict:
    item = db.get(Resume, db_id(resume_ref, "resume"))
    if not item: raise HTTPException(404, "Resume not found")
    return {"view_url": create_download_url(item.blob_path), "download_url": create_download_url(item.blob_path, download_name=item.original_filename), "expires_in_minutes": 10}


@router.delete("/resumes/{resume_ref}", status_code=204)
def delete_resume(resume_ref: str, db: Session = Depends(get_db)) -> None:
    item = db.get(Resume, db_id(resume_ref, "resume"))
    if not item: raise HTTPException(404, "Resume not found")
    referenced = db.scalar(select(Application.application_id).where(Application.resume_id == item.resume_id)) or db.scalar(select(GlobalApplicant.global_applicant_id).where(GlobalApplicant.resume_id == item.resume_id)) or db.scalar(select(MatchResult.match_id).where(MatchResult.resume_id == item.resume_id))
    if referenced: raise HTTPException(409, "Resume is referenced by an application or talent pool")
    delete_blob(item.blob_path); db.delete(item); db.commit()


@router.get("/interviews")
def interviews(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)) -> dict:
    total = db.scalar(select(func.count()).select_from(Interview)) or 0
    rows = db.scalars(select(Interview).order_by(Interview.scheduled_at.desc()).offset((page - 1) * limit).limit(limit)).all()
    items = [{"interview_id": x.interview_id, "Application_Id": format_public_id("application", x.application_id), "interviewer_Id": format_public_id("interviewer", x.interviewer_id), "scheduled_at": x.scheduled_at, "status": x.status, "score": x.score} for x in rows]
    return pagination(total, page, limit, items)


@router.get("/global-applicants")
def global_applicants(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)) -> dict:
    total = db.scalar(select(func.count()).select_from(GlobalApplicant)) or 0
    rows = db.scalars(select(GlobalApplicant).order_by(GlobalApplicant.applied_at.desc()).offset((page - 1) * limit).limit(limit)).all()
    return pagination(total, page, limit, [{"candidate_id": format_public_id("candidate", x.candidate_id), "resume_ref": format_public_id("resume", x.resume_id), "status": x.status, "applied_date": x.applied_at} for x in rows])


@router.get("/matches")
def matches(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)) -> dict:
    total = db.scalar(select(func.count()).select_from(MatchResult)) or 0
    rows = db.scalars(select(MatchResult).order_by(MatchResult.created_at.desc()).offset((page - 1) * limit).limit(limit)).all()
    return pagination(total, page, limit, [{"match_id": x.match_id, "Job_Id": format_public_id("job", x.job_id), "candidate_id": format_public_id("candidate", x.candidate_id), "resume_ref": format_public_id("resume", x.resume_id), "semantic_score": x.semantic_score, "github_score": x.github_score, "github_verified": x.github_verified, "overall_score": x.overall_score, "ranking": x.ranking} for x in rows])
