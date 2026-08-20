from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse

from backend.app.core.audit_middleware import audit_request
from backend.app.core.config import settings
from backend.app.core.logging_config import service_logger, setup_logging
from backend.app.core.rate_limit import rate_limit_request
from backend.app.core.security_headers import security_headers_request
from backend.app.routers import admin, auth, bulk, candidate, companies, interviews, jobs, matching, resumes
from backend.app.services.bootstrap import ensure_default_admin
from backend.app.services.verification_codes import ensure_company_verification_codes
from backend.app.database.connection import SessionLocal


setup_logging()
system_logger = service_logger("system")


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_default_admin()
    with SessionLocal() as db:
        generated_codes = ensure_company_verification_codes(db)
    if generated_codes:
        system_logger.info("company_verification_codes_generated", extra={"count": generated_codes})
    system_logger.info("application_started", extra={"app_name": settings.app_name})
    yield
    system_logger.info("application_stopped", extra={"app_name": settings.app_name})


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.middleware("http")(audit_request)
app.middleware("http")(rate_limit_request)
app.middleware("http")(security_headers_request)
app.add_middleware(GZipMiddleware, minimum_size=1_000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_origin_regex=r"https://.*\.devtunnels\.ms",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(companies.router, prefix=settings.api_prefix)
app.include_router(jobs.router, prefix=settings.api_prefix)
app.include_router(candidate.router, prefix=settings.api_prefix)
app.include_router(resumes.router, prefix=settings.api_prefix)
app.include_router(matching.router, prefix=settings.api_prefix)
app.include_router(interviews.router, prefix=settings.api_prefix)
app.include_router(admin.router, prefix=settings.api_prefix)
app.include_router(bulk.router, prefix=settings.api_prefix)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


frontend_dist = Path(settings.frontend_dist_dir).resolve()
if (frontend_dist / "index.html").is_file():
    @app.get("/{full_path:path}", include_in_schema=False)
    def frontend_app(full_path: str):
        requested = (frontend_dist / full_path).resolve()
        if requested.is_relative_to(frontend_dist) and requested.is_file():
            return FileResponse(requested)
        return FileResponse(frontend_dist / "index.html")