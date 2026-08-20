from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.dependencies import get_interviewer, get_recruiter
from backend.app.database.connection import get_db
from backend.app.models import Application, Candidate, Interview, Interviewer, JobPosting, MatchResult, Recruiter, Resume, User
from backend.app.services.ai import search_applicant_resumes
from backend.app.services.explainability import build_suitability_explanation


router = APIRouter(tags=["interviews"])


class InterviewCreate(BaseModel):
    application_id: int
    interviewer_id: int
    scheduled_at: datetime


class Feedback(BaseModel):
    feedback: str = Field(min_length=3, max_length=5_000)
    score: float = Field(ge=0, le=100)


@router.get("/recruiter/interviewers")
def company_interviewers(recruiter: Recruiter = Depends(get_recruiter), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(select(Interviewer, User).join(User, Interviewer.user_id == User.user_id).where(Interviewer.company_id == recruiter.company_id, User.is_active.is_(True)).order_by(User.name)).all()
    return [{"interviewer_id": interviewer.interviewer_id, "name": user.name, "email": user.email, "designation": interviewer.designation} for interviewer, user in rows]


@router.post("/recruiter/interviews", status_code=201)
def schedule(payload: InterviewCreate, recruiter: Recruiter = Depends(get_recruiter), db: Session = Depends(get_db)) -> dict:
    application = db.get(Application, payload.application_id)
    interviewer = db.get(Interviewer, payload.interviewer_id)
    job = db.get(JobPosting, application.job_id) if application else None
    if not application or not job or job.company_id != recruiter.company_id:
        raise HTTPException(status_code=404, detail="Application not found")
    if not interviewer or interviewer.company_id != recruiter.company_id:
        raise HTTPException(status_code=404, detail="Interviewer not found")
    scheduled_at = payload.scheduled_at if payload.scheduled_at.tzinfo else payload.scheduled_at.replace(tzinfo=timezone.utc)
    if scheduled_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Interview must be scheduled in the future")
    if db.scalar(select(Interview.interview_id).where(Interview.application_id == application.application_id)):
        raise HTTPException(status_code=409, detail="An interview is already scheduled for this application")
    interview = Interview(application_id=application.application_id, interviewer_id=interviewer.interviewer_id, scheduled_at=scheduled_at)
    application.status = "INTERVIEW"
    db.add(interview)
    db.commit()
    db.refresh(interview)
    return {"interview_id": interview.interview_id, "status": interview.status}


@router.get("/interviewer/candidates")
def assigned(interviewer: Interviewer = Depends(get_interviewer), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(Interview, Application, Candidate, User, JobPosting)
        .join(Application, Interview.application_id == Application.application_id)
        .join(Candidate, Application.candidate_id == Candidate.candidate_id)
        .join(User, Candidate.user_id == User.user_id)
        .join(JobPosting, Application.job_id == JobPosting.job_id)
        .where(Interview.interviewer_id == interviewer.interviewer_id)
        .order_by(Interview.scheduled_at)
    ).all()
    return [
        {
            "interview_id": interview.interview_id,
            "application_id": application.application_id,
            "candidate_id": candidate.candidate_id,
            "candidate_name": user.name,
            "job_id": job.job_id,
            "job_title": job.job_title,
            "scheduled_at": interview.scheduled_at,
            "status": interview.status,
            "feedback": interview.feedback,
            "score": interview.score,
        }
        for interview, application, candidate, user, job in rows
    ]


@router.get("/interviewer/interviews/{interview_id}/suitability")
def interview_suitability(interview_id: int, interviewer: Interviewer = Depends(get_interviewer), db: Session = Depends(get_db)) -> dict:
    interview = db.get(Interview, interview_id)
    if not interview or interview.interviewer_id != interviewer.interviewer_id:
        raise HTTPException(status_code=404, detail="Interview not found")
    application = db.get(Application, interview.application_id)
    candidate = db.get(Candidate, application.candidate_id) if application else None
    user = db.get(User, candidate.user_id) if candidate else None
    job = db.get(JobPosting, application.job_id) if application else None
    resume = db.get(Resume, application.resume_id) if application else None
    if not application or not candidate or not user or not job or not resume:
        raise HTTPException(status_code=404, detail="Interview evidence not found")
    match = db.scalar(select(MatchResult).where(MatchResult.job_id == job.job_id, MatchResult.candidate_id == candidate.candidate_id))
    semantic_score = float(match.semantic_score) if match else None
    if semantic_score is None:
        try:
            points = search_applicant_resumes(job, [resume])
            semantic_score = round(max(0.0, min(1.0, float(points[0].score))) * 100, 3) if points else None
        except Exception:
            semantic_score = None
    return {
        "interview_id": interview.interview_id,
        "candidate_name": user.name,
        **build_suitability_explanation(job, candidate, resume, match, semantic_score),
    }


@router.post("/interviewer/interviews/{interview_id}/feedback")
def submit_feedback(interview_id: int, payload: Feedback, interviewer: Interviewer = Depends(get_interviewer), db: Session = Depends(get_db)) -> dict:
    interview = db.get(Interview, interview_id)
    if not interview or interview.interviewer_id != interviewer.interviewer_id:
        raise HTTPException(status_code=404, detail="Interview not found")
    interview.feedback = payload.feedback
    interview.score = payload.score
    interview.status = "COMPLETED"
    db.commit()
    return {"interview_id": interview.interview_id, "application_id": application.application_id, "interviewer_id": interviewer.interviewer_id, "scheduled_at": interview.scheduled_at, "status": interview.status}