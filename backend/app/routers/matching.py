import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.core.dependencies import get_candidate, get_recruiter
from backend.app.database.connection import get_db
from backend.app.models import Application, Candidate, Company, GlobalApplicant, JobPosting, MatchResult, Recruiter, Resume, User
from backend.app.schemas.contracts import MatchResponse
from backend.app.services.ai import explain_match, fallback_match_explanation, prepare_job_text, search_applicant_resumes, search_jobs_for_resume
from backend.app.core.config import settings
from backend.app.services.graph import graph_suitability
from backend.app.services.github_profiles import GitHubProfileError, evaluate_github_resume_evidence
from backend.app.services.explainability import build_suitability_explanation
from backend.app.routers.jobs import job_payload


router = APIRouter(tags=["matching"])
logger = logging.getLogger("hireai.matching")


def combined_match_score(semantic_score: float, github_evidence: dict) -> float:
    relevance = github_evidence.get("relevance_score")
    if not github_evidence.get("verified") or relevance is None:
        return semantic_score
    return semantic_score * 0.85 + max(0.0, min(100.0, float(relevance))) * 0.15


def github_evidence_for(candidate: Candidate, resume: Resume) -> dict:
    try:
        return evaluate_github_resume_evidence(candidate.github_url, resume.extracted_text or "")
    except (GitHubProfileError, ValueError) as exc:
        logger.warning("GitHub evidence unavailable for candidate %s: %s", candidate.candidate_id, type(exc).__name__)
        return {"verified": False, "verification_status": "UNAVAILABLE", "relevance_score": None, "repositories": []}


def github_explanation(evidence: dict) -> str:
    status = evidence.get("verification_status", "UNAVAILABLE")
    relevance = evidence.get("relevance_score")
    if relevance is None:
        return f"GitHub evidence: {status}; it did not affect the score."
    repository_names = [item.get("name") for item in evidence.get("repositories", []) if item.get("relevance_score", 0) > 0][:3]
    projects = ", ".join(repository_names) if repository_names else "no resume-related public repositories"
    return f"GitHub evidence: {status}, {relevance}% resume-project relevance; strongest repository evidence: {projects}."


@router.post("/candidate/match")
def candidate_match(resume_id: int, limit: int = Query(20, le=50), candidate: Candidate = Depends(get_candidate), db: Session = Depends(get_db)) -> list[dict]:
    resume = db.get(Resume, resume_id)
    if not resume or resume.candidate_id != candidate.candidate_id or not resume.extracted_text:
        raise HTTPException(status_code=404, detail="Parsed resume not found")
    try:
        points = search_jobs_for_resume(resume, limit)
    except Exception as exc:
        logger.exception("Candidate job matching unavailable for candidate %s", candidate.candidate_id)
        raise HTTPException(status_code=503, detail="Job matching is temporarily unavailable while the vector index is prepared") from exc
    job_ids = [int(point.payload["job_id"]) for point in points]
    rows = db.execute(select(JobPosting, Company.company_name).join(Company).where(JobPosting.job_id.in_(job_ids), JobPosting.status == "ACTIVE")).all() if job_ids else []
    jobs = {job.job_id: (job, company_name) for job, company_name in rows}
    results = []
    for point in points:
        job_id = int(point.payload["job_id"])
        if job_id not in jobs:
            continue
        job, company_name = jobs[job_id]
        score = max(0.0, min(1.0, float(point.score)))
        results.append({**job_payload(job, company_name), "score": score, "semantic_score": round(score * 100, 2), "resume_id": resume.resume_id})
    return results


@router.get("/candidate/recommended-jobs")
def recommended_jobs(resume_id: int, limit: int = Query(20, ge=1, le=50), candidate: Candidate = Depends(get_candidate), db: Session = Depends(get_db)) -> list[dict]:
    return candidate_match(resume_id, limit, candidate, db)


def recruiter_job(job_id: int, recruiter: Recruiter, db: Session) -> JobPosting:
    job = db.get(JobPosting, job_id)
    if not job or job.company_id != recruiter.company_id:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def applicant_items(job_id: int, db: Session) -> tuple[list[dict], list[Resume]]:
    rows = db.execute(select(Application, Resume, Candidate, User).join(Resume, Application.resume_id == Resume.resume_id).join(Candidate, Application.candidate_id == Candidate.candidate_id).join(User, Candidate.user_id == User.user_id).where(Application.job_id == job_id)).all()
    explicit_candidate_ids = {candidate.candidate_id for _, _, candidate, _ in rows}
    global_rows = db.execute(select(GlobalApplicant, Resume, Candidate, User).join(Resume, GlobalApplicant.resume_id == Resume.resume_id).join(Candidate, GlobalApplicant.candidate_id == Candidate.candidate_id).join(User, Candidate.user_id == User.user_id).where(GlobalApplicant.candidate_id.not_in(explicit_candidate_ids))).all()
    explicit = [{"application_id": app.application_id, "candidate_id": candidate.candidate_id, "candidate_name": user.name, "resume_id": resume.resume_id, "applied_at": app.applied_at, "status": app.status, "scope": "JOB"} for app, resume, candidate, user in rows]
    global_items = [{"application_id": -item.global_applicant_id, "candidate_id": candidate.candidate_id, "candidate_name": user.name, "resume_id": resume.resume_id, "applied_at": item.applied_at, "status": item.status, "scope": "ALL_JOBS"} for item, resume, candidate, user in global_rows]
    resumes = [resume for _, resume, _, _ in rows] + [resume for _, resume, _, _ in global_rows]
    return explicit + global_items, resumes


def ranked_applicant_items(job: JobPosting, db: Session) -> tuple[list[dict], list]:
    items, resumes = applicant_items(job.job_id, db)
    db.commit()
    try:
        points = search_applicant_resumes(job, resumes)
    except Exception:
        logger.exception("Semantic applicant ranking failed for job %s", job.job_id)
        for item in items:
            item.update({"semantic_score": None, "ranking": None, "ranking_status": "UNAVAILABLE"})
        return items, []
    point_by_resume = {int(point.payload["resume_id"]): point for point in points}
    for item in items:
        point = point_by_resume.get(item["resume_id"])
        item["semantic_score"] = round(max(0.0, min(1.0, float(point.score))) * 100, 3) if point else None
        item["ranking"] = None
        item["ranking_status"] = "RANKED" if point else "PENDING"
    items.sort(key=lambda item: (item["semantic_score"] is None, -(item["semantic_score"] or 0), item["candidate_name"].lower()))
    for rank, item in enumerate((item for item in items if item["semantic_score"] is not None), start=1):
        item["ranking"] = rank
    return items, points


def apply_stored_match_scores(items: list[dict], job_id: int, db: Session) -> list[dict]:
    stored = {result.resume_id: result for result in db.scalars(select(MatchResult).where(MatchResult.job_id == job_id))}
    for item in items:
        result = stored.get(item["resume_id"])
        if not result:
            continue
        item.update({
            "overall_score": float(result.overall_score),
            "github_score": float(result.github_score) if result.github_score is not None else None,
            "github_verified": result.github_verified,
            "github_evidence": result.github_evidence,
            "ranking": result.ranking,
        })
    items.sort(key=lambda item: (item.get("ranking") is None, item.get("ranking") or 0, item["candidate_name"].lower()))
    return items


@router.get("/recruiter/jobs/{job_id}/applicants")
def applicants(job_id: int, recruiter: Recruiter = Depends(get_recruiter), db: Session = Depends(get_db)) -> list[dict]:
    job = recruiter_job(job_id, recruiter, db)
    items, _ = ranked_applicant_items(job, db)
    return apply_stored_match_scores(items, job_id, db)


@router.get("/recruiter/jobs/{job_id}/applicants/{candidate_id}/suitability")
def applicant_suitability(job_id: int, candidate_id: int, recruiter: Recruiter = Depends(get_recruiter), db: Session = Depends(get_db)) -> dict:
    job = recruiter_job(job_id, recruiter, db)
    candidate = db.get(Candidate, candidate_id)
    user = db.get(User, candidate.user_id) if candidate else None
    company = db.get(Company, job.company_id)
    application = db.scalar(select(Application).where(Application.job_id == job_id, Application.candidate_id == candidate_id))
    global_item = None if application else db.scalar(select(GlobalApplicant).where(GlobalApplicant.candidate_id == candidate_id))
    resume = db.get(Resume, application.resume_id if application else global_item.resume_id) if application or global_item else None
    if not candidate or not user or not company or not resume:
        raise HTTPException(status_code=404, detail="Applicant not found")
    semantic_score = None
    try:
        points = search_applicant_resumes(job, [resume])
        if points:
            semantic_score = round(max(0.0, min(1.0, float(points[0].score))) * 100, 3)
    except Exception:
        logger.exception("Could not calculate suitability score for job %s candidate %s", job_id, candidate_id)
    scope = "JOB" if application else "ALL_JOBS"
    status = application.status if application else global_item.status
    result = graph_suitability(job, candidate, user, resume, company, semantic_score, scope, status)
    stored_match = db.scalar(select(MatchResult).where(MatchResult.job_id == job_id, MatchResult.candidate_id == candidate_id))
    result["explainability"] = build_suitability_explanation(job, candidate, resume, stored_match, semantic_score)
    return result


@router.post("/recruiter/jobs/{job_id}/match", response_model=list[MatchResponse])
def match_applicants(job_id: int, recruiter: Recruiter = Depends(get_recruiter), db: Session = Depends(get_db)) -> list[MatchResult]:
    job = recruiter_job(job_id, recruiter, db)
    items, points = ranked_applicant_items(job, db)
    applicant_by_resume = {item["resume_id"]: item["candidate_id"] for item in items}
    db.execute(delete(MatchResult).where(MatchResult.job_id == job_id))
    results = []
    for position, point in enumerate(points):
        resume_id = int(point.payload["resume_id"])
        resume = db.get(Resume, resume_id)
        candidate = db.get(Candidate, applicant_by_resume[resume_id])
        semantic_score = max(0.0, min(1.0, float(point.score))) * 100
        github_evidence = github_evidence_for(candidate, resume) if position < settings.github_evaluations_per_match else {"verified": False, "verification_status": "SKIPPED_COST_LIMIT", "relevance_score": None, "repositories": []}
        overall_score = combined_match_score(semantic_score, github_evidence)
        explanation = explain_match(prepare_job_text(job), resume.extracted_text or "", semantic_score / 100) if position < settings.llm_explanations_per_match else fallback_match_explanation(semantic_score / 100)
        result = MatchResult(
            job_id=job_id,
            candidate_id=candidate.candidate_id,
            resume_id=resume_id,
            semantic_score=Decimal(str(round(semantic_score, 3))),
            github_score=Decimal(str(github_evidence["relevance_score"])) if github_evidence.get("relevance_score") is not None else None,
            github_verified=github_evidence.get("verified"),
            github_evidence=github_evidence,
            overall_score=Decimal(str(round(overall_score, 3))),
            matched_skills=[],
            missing_skills=[],
            explanation=f"{explanation}\n\n{github_explanation(github_evidence)}",
        )
        db.add(result)
        results.append(result)
    results.sort(key=lambda item: item.overall_score, reverse=True)
    for rank, result in enumerate(results, start=1):
        result.ranking = rank
    db.commit()
    for result in results:
        db.refresh(result)
    return results


@router.get("/recruiter/jobs/{job_id}/matches", response_model=list[MatchResponse])
def matches(job_id: int, recruiter: Recruiter = Depends(get_recruiter), db: Session = Depends(get_db)) -> list[MatchResult]:
    recruiter_job(job_id, recruiter, db)
    return list(db.scalars(select(MatchResult).where(MatchResult.job_id == job_id).order_by(MatchResult.ranking)))