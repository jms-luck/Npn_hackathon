import secrets

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.app.models import Company


VERIFICATION_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_company_verification_code(length: int = 10) -> str:
    return "COMP-" + "".join(secrets.choice(VERIFICATION_ALPHABET) for _ in range(length))


def ensure_company_verification_codes(db: Session) -> int:
    companies = list(db.scalars(select(Company).where(or_(Company.verification_code.is_(None), func.length(func.trim(Company.verification_code)) == 0))))
    for company in companies:
        company.verification_code = generate_company_verification_code()
    if companies:
        db.commit()
    return len(companies)