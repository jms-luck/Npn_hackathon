from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database.connection import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class User(TimestampMixin, Base):
    __tablename__ = "users"
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(30))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Company(TimestampMixin, Base):
    __tablename__ = "companies"
    company_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    company_size: Mapped[str | None] = mapped_column(String(100))
    company_profile: Mapped[str | None] = mapped_column(Text)
    verification_code: Mapped[str | None] = mapped_column(String(255))


class Recruiter(Base):
    __tablename__ = "recruiters"
    recruiter_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), unique=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.company_id"), index=True)
    designation: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    user: Mapped[User] = relationship()
    company: Mapped[Company] = relationship()


class Candidate(Base):
    __tablename__ = "candidates"
    candidate_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), unique=True)
    phone: Mapped[str | None] = mapped_column(String(50))
    location: Mapped[str | None] = mapped_column(String(255))
    profile_summary: Mapped[str | None] = mapped_column(Text)
    linkedin_url: Mapped[str | None] = mapped_column(Text)
    github_url: Mapped[str | None] = mapped_column(Text)
    portfolio_url: Mapped[str | None] = mapped_column(Text)
    user: Mapped[User] = relationship()


class DsaEvaluation(Base):
    __tablename__ = "dsa_evaluations"
    evaluation_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.candidate_id", ondelete="CASCADE"), unique=True, index=True)
    leetcode_username: Mapped[str] = mapped_column(String(30), index=True)
    score: Mapped[int] = mapped_column(Integer)
    level: Mapped[str] = mapped_column(String(30))
    result_json: Mapped[dict] = mapped_column(JSON)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Interviewer(Base):
    __tablename__ = "interviewers"
    interviewer_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), unique=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.company_id"), index=True)
    designation: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    user: Mapped[User] = relationship()


class JobPosting(TimestampMixin, Base):
    __tablename__ = "job_postings"
    job_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    external_job_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.company_id"), index=True)
    recruiter_id: Mapped[int | None] = mapped_column(ForeignKey("recruiters.recruiter_id"))
    experience: Mapped[str | None] = mapped_column(String(255))
    qualifications: Mapped[str | None] = mapped_column(Text)
    salary_range: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(255))
    country: Mapped[str | None] = mapped_column(String(255))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    work_type: Mapped[str | None] = mapped_column(String(100))
    job_posting_date: Mapped[date | None] = mapped_column(Date)
    preference: Mapped[str | None] = mapped_column(Text)
    contact_person: Mapped[str | None] = mapped_column(String(255))
    contact: Mapped[str | None] = mapped_column(String(255))
    job_title: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str | None] = mapped_column(String(255))
    job_portal: Mapped[str | None] = mapped_column(String(255))
    job_description: Mapped[str | None] = mapped_column(Text)
    benefits: Mapped[str | None] = mapped_column(Text)
    skills: Mapped[str | None] = mapped_column(Text)
    responsibilities: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(30), default="RECRUITER")
    status: Mapped[str] = mapped_column(String(30), default="DRAFT", index=True)
    company: Mapped[Company] = relationship()


class Resume(Base):
    __tablename__ = "resumes"
    __table_args__ = (UniqueConstraint("candidate_id", "version"),)
    resume_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.candidate_id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    original_filename: Mapped[str] = mapped_column(String(255))
    blob_path: Mapped[str] = mapped_column(Text, unique=True)
    content_type: Mapped[str | None] = mapped_column(String(255))
    extracted_text: Mapped[str | None] = mapped_column(Text)
    parsing_status: Mapped[str] = mapped_column(String(30), default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("candidate_id", "job_id"),)
    application_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.candidate_id"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_postings.job_id"), index=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.resume_id"))
    status: Mapped[str] = mapped_column(String(30), default="APPLIED")
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GlobalApplicant(Base):
    __tablename__ = "global_applicants"
    global_applicant_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.candidate_id", ondelete="CASCADE"), unique=True, index=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.resume_id"))
    status: Mapped[str] = mapped_column(String(30), default="APPLIED")
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MatchResult(Base):
    __tablename__ = "match_results"
    __table_args__ = (UniqueConstraint("job_id", "resume_id"),)
    match_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_postings.job_id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.candidate_id", ondelete="CASCADE"))
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.resume_id", ondelete="CASCADE"))
    semantic_score: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    github_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    github_verified: Mapped[bool | None] = mapped_column(Boolean)
    github_evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    skill_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    experience_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    qualification_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    overall_score: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    matched_skills: Mapped[list] = mapped_column(JSON, default=list)
    missing_skills: Mapped[list] = mapped_column(JSON, default=list)
    explanation: Mapped[str | None] = mapped_column(Text)
    ranking: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Interview(Base):
    __tablename__ = "interviews"
    interview_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.application_id", ondelete="CASCADE"), unique=True)
    interviewer_id: Mapped[int] = mapped_column(ForeignKey("interviewers.interviewer_id"))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="SCHEDULED")
    feedback: Mapped[str | None] = mapped_column(Text)
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())