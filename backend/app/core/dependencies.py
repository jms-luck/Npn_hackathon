from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.security import decode_access_token
from backend.app.database.connection import get_db
from backend.app.models import Candidate, Interviewer, Recruiter, User


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (ValueError, KeyError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive or missing user")
    return user


def require_role(*roles: str) -> Callable:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return dependency


def get_candidate(user: User = Depends(require_role("CANDIDATE")), db: Session = Depends(get_db)) -> Candidate:
    profile = db.scalar(select(Candidate).where(Candidate.user_id == user.user_id))
    if not profile:
        raise HTTPException(status_code=404, detail="Candidate profile not found")
    return profile


def get_recruiter(user: User = Depends(require_role("RECRUITER")), db: Session = Depends(get_db)) -> Recruiter:
    profile = db.scalar(select(Recruiter).where(Recruiter.user_id == user.user_id))
    if not profile:
        raise HTTPException(status_code=404, detail="Recruiter profile not found")
    return profile


def get_interviewer(user: User = Depends(require_role("INTERVIEWER")), db: Session = Depends(get_db)) -> Interviewer:
    profile = db.scalar(select(Interviewer).where(Interviewer.user_id == user.user_id))
    if not profile:
        raise HTTPException(status_code=404, detail="Interviewer profile not found")
    return profile