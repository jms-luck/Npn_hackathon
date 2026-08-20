from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.dependencies import get_current_user
from backend.app.database.connection import get_db
from backend.app.models import Application, Candidate, Interview, Interviewer, JobPosting, Recruiter, Resume, User


router = APIRouter(prefix="/assistant", tags=["role assistants"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)


def role_assistant_reply(user: User, message: str, db: Session) -> dict:
    normalized = message.casefold()
    if user.role == "CANDIDATE":
        candidate = db.scalar(select(Candidate).where(Candidate.user_id == user.user_id))
        applications = db.scalar(select(func.count()).select_from(Application).where(Application.candidate_id == candidate.candidate_id)) or 0
        resumes = db.scalar(select(func.count()).select_from(Resume).where(Resume.candidate_id == candidate.candidate_id)) or 0
        statuses = db.execute(select(Application.status, func.count()).where(Application.candidate_id == candidate.candidate_id).group_by(Application.status)).all()
        answer = f"You have {applications} applications and {resumes} resumes. " + ("Application status: " + ", ".join(f"{status}: {count}" for status, count in statuses) if statuses else "No applications have been submitted yet.")
        suggestions = ["Show my application status", "How many resumes do I have?", "Where are my job matches?"]
    elif user.role == "RECRUITER":
        recruiter = db.scalar(select(Recruiter).where(Recruiter.user_id == user.user_id))
        jobs = db.scalar(select(func.count()).select_from(JobPosting).where(JobPosting.company_id == recruiter.company_id)) or 0
        applications = db.scalar(select(func.count()).select_from(Application).join(JobPosting).where(JobPosting.company_id == recruiter.company_id)) or 0
        interviews = db.scalar(select(func.count()).select_from(Interview).join(Application).join(JobPosting).where(JobPosting.company_id == recruiter.company_id)) or 0
        answer = f"Your company workspace contains {jobs} jobs, {applications} explicit applications, and {interviews} scheduled interviews. Use a job's applicant page to verify, select, and schedule candidates."
        suggestions = ["How do I schedule an interview?", "How do I upload a ZIP?", "What does GitHub verification mean?"]
    elif user.role == "INTERVIEWER":
        interviewer = db.scalar(select(Interviewer).where(Interviewer.user_id == user.user_id))
        assigned = db.scalar(select(func.count()).select_from(Interview).where(Interview.interviewer_id == interviewer.interviewer_id)) or 0
        pending = db.scalar(select(func.count()).select_from(Interview).where(Interview.interviewer_id == interviewer.interviewer_id, Interview.status == "SCHEDULED")) or 0
        answer = f"You have {assigned} assigned interviews, including {pending} awaiting feedback. Open a candidate to review suitability, then submit a score and job-relevant feedback."
        suggestions = ["Show my pending interviews", "How do I submit feedback?", "What evidence should I validate?"]
    else:
        users = db.scalar(select(func.count()).select_from(User)) or 0
        jobs = db.scalar(select(func.count()).select_from(JobPosting)) or 0
        interviews = db.scalar(select(func.count()).select_from(Interview)) or 0
        answer = f"Platform summary: {users} users, {jobs} jobs, and {interviews} interviews. Use All data for managed records and Audit Trail for access and security events."
        suggestions = ["Where is the audit trail?", "How are company codes generated?", "What can admins manage?"]
    if any(term in normalized for term in ("password", "secret", "token", "credential")):
        answer = "I cannot reveal passwords, tokens, verification codes, or service credentials. Use the authorized admin controls or your account workflow."
    return {"role": user.role, "answer": answer, "suggestions": suggestions, "scope": f"{user.role.lower()}-only data"}


@router.post("/chat")
def chat(payload: ChatRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return role_assistant_reply(user, payload.message, db)