from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationInfo, field_validator

from backend.app.services.social_profiles import normalize_social_profile


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    role: str | None = None


class CandidateRegister(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=8)
    phone: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None

    @field_validator("linkedin_url", "github_url", mode="before")
    @classmethod
    def normalize_profile(cls, value, info: ValidationInfo):
        provider = "linkedin" if info.field_name == "linkedin_url" else "github"
        return normalize_social_profile(value, provider)


class StaffRegister(CandidateRegister):
    company_id: int
    verification_code: str | None = None
    designation: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class DsaEvaluationRequest(BaseModel):
    username_or_url: str = Field(min_length=1, max_length=200)


class DsaEvaluationResponse(BaseModel):
    username: str
    profile_url: str
    score: int = Field(ge=0, le=100)
    level: str
    total_solved: int
    difficulty: dict[str, int]
    topic_coverage_score: int
    difficulty_depth_score: int
    topics: list[dict]
    strongest_topics: list[str]
    focus_topics: list[str]
    recent_solved: list[dict]
    methodology: str
    evaluated_at: datetime | None = None


class UserResponse(ORMModel):
    user_id: int
    name: str
    email: EmailStr
    role: str
    is_active: bool


class CompanyResponse(ORMModel):
    company_id: int
    company_name: str
    company_size: str | None
    company_profile: str | None


class CompanyCreate(BaseModel):
    company_name: str = Field(min_length=2, max_length=255)
    company_size: str | None = None
    company_profile: str | None = None
    verification_code: str = Field(min_length=4, max_length=255)


class JobCreate(BaseModel):
    job_title: str
    role: str | None = None
    experience: str | None = None
    qualifications: str | None = None
    salary_range: str | None = None
    location: str | None = None
    country: str | None = None
    work_type: str | None = None
    skills: str | None = None
    responsibilities: str | None = None
    benefits: str | None = None
    job_description: str | None = None


class JobUpdate(JobCreate):
    job_title: str | None = None


class JobResponse(ORMModel):
    Job_Id: str | None = None
    job_id: int
    company_id: int
    company_name: str | None = None
    recruiter_id: int | None
    job_title: str
    role: str | None
    experience: str | None
    qualifications: str | None
    salary_range: str | None
    location: str | None
    country: str | None
    work_type: str | None
    skills: str | None
    responsibilities: str | None
    benefits: str | None
    job_description: str | None
    source_type: str
    status: str
    job_posting_date: date | None


class ResumeResponse(ORMModel):
    resume_id: int
    candidate_id: int
    version: int
    original_filename: str
    content_type: str | None
    parsing_status: str
    created_at: datetime


class ApplicationCreate(BaseModel):
    resume_id: int


class ApplicationResponse(ORMModel):
    application_id: int
    candidate_id: int
    job_id: int
    resume_id: int
    status: str
    applied_at: datetime


class MatchResponse(ORMModel):
    match_id: int
    job_id: int
    candidate_id: int
    resume_id: int
    semantic_score: Decimal
    github_score: Decimal | None
    github_verified: bool | None
    github_evidence: dict
    overall_score: Decimal
    matched_skills: list
    missing_skills: list
    explanation: str | None
    ranking: int | None