from sqlalchemy import select
import logging

from backend.app.core.config import settings
from backend.app.core.security import hash_password
from backend.app.database.connection import SessionLocal
from backend.app.models import User


logger = logging.getLogger("hireai.auth")


def ensure_default_admin() -> None:
    with SessionLocal() as db:
        if db.scalar(select(User.user_id).where(User.role == "ADMIN")):
            return
        if not settings.default_admin_email or not settings.default_admin_password:
            logger.warning("Default admin bootstrap skipped; configure DEFAULT_ADMIN_EMAIL and DEFAULT_ADMIN_PASSWORD")
            return
        if len(settings.default_admin_password) < 12:
            raise RuntimeError("DEFAULT_ADMIN_PASSWORD must contain at least 12 characters")
        email = settings.default_admin_email.strip().lower()
        if db.scalar(select(User.user_id).where(User.email == email)):
            raise RuntimeError("The default admin email is already used by another account")
        db.add(
            User(
                name="Hire AI Admin",
                email=email,
                password_hash=hash_password(settings.default_admin_password),
                role="ADMIN",
            )
        )
        db.commit()
