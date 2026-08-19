from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.dependencies import get_current_user
from backend.app.core.security import create_access_token, hash_password, verify_password
from backend.app.database.connection import get_db
from backend.app.models import Candidate, Company, Interviewer, Recruiter, User
from backend.app.schemas.contracts import CandidateRegister, LoginRequest, StaffRegister, TokenResponse, UserResponse
from backend.app.core.config import settings
from backend.app.services.cache import cache_get, cache_set
from backend.app.services.public_ids import format_public_id


router = APIRouter(prefix="/auth", tags=["authentication"])


def create_user(db: Session, payload: CandidateRegister, role: str) -> User:
    if db.scalar(select(User).where(User.email == payload.email.lower())):
        raise HTTPException(status_code=409, detail="Email is already registered")
    user = User(name=payload.name, email=payload.email.lower(), password_hash=hash_password(payload.password), role=role)
    db.add(user)
    db.flush()
    return user


@router.post("/register/candidate", response_model=UserResponse, status_code=201)
def register_candidate(payload: CandidateRegister, db: Session = Depends(get_db)) -> User:
    try:
        user = create_user(db, payload, "CANDIDATE")
        db.add(Candidate(user_id=user.user_id, phone=payload.phone, location=payload.location, linkedin_url=payload.linkedin_url, github_url=payload.github_url))
        db.commit()
        db.refresh(user)
        return user
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Candidate could not be registered")


def register_staff(payload: StaffRegister, role: str, db: Session) -> User:
    company = db.get(Company, payload.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    if company.verification_code and company.verification_code != payload.verification_code:
        raise HTTPException(status_code=403, detail="Invalid company verification code")
    try:
        user = create_user(db, payload, role)
        profile_type = Recruiter if role == "RECRUITER" else Interviewer
        db.add(profile_type(user_id=user.user_id, company_id=company.company_id, designation=payload.designation, phone=payload.phone))
        db.commit()
        db.refresh(user)
        return user
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"{role.title()} could not be registered")


@router.post("/register/recruiter", response_model=UserResponse, status_code=201)
def register_recruiter(payload: StaffRegister, db: Session = Depends(get_db)) -> User:
    return register_staff(payload, "RECRUITER", db)


@router.post("/register/interviewer", response_model=UserResponse, status_code=201)
def register_interviewer(payload: StaffRegister, db: Session = Depends(get_db)) -> User:
    return register_staff(payload, "INTERVIEWER", db)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if payload.role and user.role != payload.role.upper():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"This account is not registered as {payload.role.lower()}")
    return TokenResponse(access_token=create_access_token(user.user_id, user.role))


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.get("/profile")
def profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    key = f"profile:{user.user_id}"
    if cached := cache_get(key):
        return cached
    payload = {"User_Id": format_public_id("user", user.user_id), "name": user.name, "email": user.email, "role": user.role}
    if user.role == "CANDIDATE":
        item = db.scalar(select(Candidate).where(Candidate.user_id == user.user_id))
        if item:
            payload.update({"candidate_id": format_public_id("candidate", item.candidate_id), "phone": item.phone, "location": item.location, "profile_summary": item.profile_summary, "linkedin_url": item.linkedin_url, "github_url": item.github_url, "portfolio_url": item.portfolio_url})
    elif user.role == "RECRUITER":
        row = db.execute(select(Recruiter, Company).join(Company).where(Recruiter.user_id == user.user_id)).first()
        if row:
            item, company = row
            payload.update({"recruiter_id": format_public_id("recruiter", item.recruiter_id), "designation": item.designation, "phone": item.phone, "company_ID": format_public_id("company", company.company_id), "company_name": company.company_name})
    elif user.role == "INTERVIEWER":
        row = db.execute(select(Interviewer, Company).join(Company).where(Interviewer.user_id == user.user_id)).first()
        if row:
            item, company = row
            payload.update({"interviewer_Id": format_public_id("interviewer", item.interviewer_id), "designation": item.designation, "phone": item.phone, "company_ID": format_public_id("company", company.company_id), "company_name": company.company_name})
    elif user.role == "ADMIN":
        payload.update({"access": "Platform administration", "default_admin": True})
    cache_set(key, payload, settings.cache_profile_ttl)
    return payload