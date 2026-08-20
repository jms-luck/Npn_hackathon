import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.dependencies import get_candidate
from backend.app.database.connection import get_db
from backend.app.models import Application, Candidate, Company, DsaEvaluation, JobPosting, Resume, User
from backend.app.schemas.contracts import ApplicationCreate, ApplicationResponse, DsaEvaluationRequest, DsaEvaluationResponse, ResumeResponse
from backend.app.services.ai import index_resume_for_job
from backend.app.services.cache import cache_get, cache_set
from backend.app.core.config import settings
from backend.app.services.graph import sync_application_entities
from backend.app.services.leetcode import LeetCodeError, fetch_leetcode_profile, normalize_leetcode_username, score_dsa_profile
from backend.app.services.github_profiles import GitHubProfileError, evaluate_github_resume_evidence


router = APIRouter(tags=["candidate"])
logger = logging.getLogger("hireai.candidate")


@router.get("/candidate/profile")
def candidate_profile(candidate: Candidate = Depends(get_candidate)) -> dict:
    return {"candidate_id": candidate.candidate_id, "phone": candidate.phone, "location": candidate.location, "profile_summary": candidate.profile_summary}


@router.post("/candidate/github-evaluation")
def evaluate_candidate_github(candidate: Candidate = Depends(get_candidate), db: Session = Depends(get_db)) -> dict:
    if not candidate.github_url:
        raise HTTPException(status_code=400, detail="Add a GitHub profile URL before verification")
    resume = db.scalar(select(Resume).where(Resume.candidate_id == candidate.candidate_id, Resume.extracted_text.is_not(None)).order_by(Resume.version.desc()).limit(1))
    if not resume:
        raise HTTPException(status_code=404, detail="Upload a parsed resume before evaluating project relevance")
    try:
        result = evaluate_github_resume_evidence(candidate.github_url, resume.extracted_text or "")
    except (GitHubProfileError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {**result, "resume_id": resume.resume_id}


def dsa_evaluation_payload(evaluation: DsaEvaluation) -> dict:
    return {**evaluation.result_json, "evaluated_at": evaluation.evaluated_at}


@router.get("/candidate/dsa-evaluation", response_model=DsaEvaluationResponse)
def get_dsa_evaluation(candidate: Candidate = Depends(get_candidate), db: Session = Depends(get_db)) -> dict:
    evaluation = db.scalar(select(DsaEvaluation).where(DsaEvaluation.candidate_id == candidate.candidate_id))
    if not evaluation:
        raise HTTPException(status_code=404, detail="No DSA evaluation has been run")
    return dsa_evaluation_payload(evaluation)


@router.post("/candidate/dsa-evaluation", response_model=DsaEvaluationResponse)
def evaluate_dsa(payload: DsaEvaluationRequest, candidate: Candidate = Depends(get_candidate), db: Session = Depends(get_db)) -> dict:
    try:
        username = normalize_leetcode_username(payload.username_or_url)
        cache_key = f"leetcode:dsa:{username.lower()}"
        result = cache_get(cache_key)
        if result is None:
            result = score_dsa_profile(fetch_leetcode_profile(username))
            cache_set(cache_key, result, settings.cache_leetcode_ttl)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LeetCodeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    evaluation = db.scalar(select(DsaEvaluation).where(DsaEvaluation.candidate_id == candidate.candidate_id))
    if evaluation:
        evaluation.leetcode_username = result["username"]
        evaluation.score = result["score"]
        evaluation.level = result["level"]
        evaluation.result_json = result
        evaluation.evaluated_at = func.now()
    else:
        evaluation = DsaEvaluation(
            candidate_id=candidate.candidate_id,
            leetcode_username=result["username"],
            score=result["score"],
            level=result["level"],
            result_json=result,
        )
        db.add(evaluation)
    db.commit()
    db.refresh(evaluation)
    return dsa_evaluation_payload(evaluation)


@router.get("/candidate/resumes", response_model=list[ResumeResponse])
def candidate_resumes(candidate: Candidate = Depends(get_candidate), db: Session = Depends(get_db)) -> list[Resume]:
    return list(db.scalars(select(Resume).where(Resume.candidate_id == candidate.candidate_id).order_by(Resume.version.desc())))


@router.get("/candidate/applications", response_model=list[ApplicationResponse])
def candidate_applications(candidate: Candidate = Depends(get_candidate), db: Session = Depends(get_db)) -> list[Application]:
    return list(db.scalars(select(Application).where(Application.candidate_id == candidate.candidate_id).order_by(Application.applied_at.desc())))


@router.post("/jobs/{job_id}/apply", response_model=ApplicationResponse, status_code=201)
def apply(job_id: int, payload: ApplicationCreate, candidate: Candidate = Depends(get_candidate), db: Session = Depends(get_db)) -> Application:
    job = db.get(JobPosting, job_id)
    resume = db.get(Resume, payload.resume_id)
    if not job or job.status != "ACTIVE":
        raise HTTPException(status_code=404, detail="Active job not found")
    if not resume or resume.candidate_id != candidate.candidate_id:
        raise HTTPException(status_code=404, detail="Resume not found")
    application = Application(candidate_id=candidate.candidate_id, job_id=job_id, resume_id=resume.resume_id)
    db.add(application)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="You already applied for this job")
    db.refresh(application)
    try:
        index_resume_for_job(job, resume)
    except Exception:
        # The application remains authoritative; recruiter ranking retries indexing.
        logger.exception("Could not index resume %s for job %s", resume.resume_id, job_id)
    try:
        user = db.get(User, candidate.user_id)
        company = db.get(Company, job.company_id)
        sync_application_entities(job, candidate, user, resume, company, application.application_id, application.status, "JOB", application.applied_at)
    except Exception:
        logger.exception("Could not sync Neo4j application %s", application.application_id)
    return application