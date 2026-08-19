from time import perf_counter
from uuid import uuid4

from fastapi import Request

from backend.app.core.logging_config import audit_event, service_logger
from backend.app.core.security import decode_access_token
from backend.app.services.cache import cache_delete, cache_delete_prefix
from backend.app.services.audit_reader import mask_client_ip


SERVICE_PATHS = (
    ("/api/auth", "auth"),
    ("/api/admin", "admin"),
    ("/api/companies", "companies"),
    ("/api/candidate", "candidate"),
    ("/api/resumes", "resumes"),
    ("/api/interviewer", "interviews"),
)


def service_for_path(path: str) -> str:
    if "/applicants/bulk" in path:
        return "bulk"
    if "/match" in path or "/suitability" in path or path.endswith("/applicants") or path.endswith("/matches"):
        return "matching"
    if path.startswith("/api/recruiter/interviews"):
        return "interviews"
    if path.startswith("/api/jobs") or path.startswith("/api/recruiter/jobs"):
        return "jobs"
    for prefix, service in SERVICE_PATHS:
        if path.startswith(prefix):
            return service
    return "system"


def actor_from_request(request: Request) -> tuple[str | None, str | None]:
    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        return None, None
    try:
        payload = decode_access_token(authorization.split(" ", 1)[1])
        return payload.get("sub"), payload.get("role")
    except ValueError:
        return None, None


async def audit_request(request: Request, call_next):
    started = perf_counter()
    request_id = request.headers.get("x-request-id") or uuid4().hex
    service = service_for_path(request.url.path)
    user_id, role = actor_from_request(request)
    fields = {
        "request_id": request_id,
        "service": service,
        "method": request.method,
        "path": request.url.path,
        "client_ip": mask_client_ip(request.client.host if request.client else None),
        "user_id": user_id,
        "role": role,
        "is_write": request.method in {"POST", "PUT", "PATCH", "DELETE"},
    }
    try:
        response = await call_next(request)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and response.status_code < 400:
            cache_delete("admin:overview")
            if "/jobs" in request.url.path:
                cache_delete_prefix("jobs:active:")
                cache_delete_prefix("graph:job:")
            if "/companies" in request.url.path:
                cache_delete_prefix("companies:")
            if "/users" in request.url.path or "/candidates" in request.url.path or "/recruiters" in request.url.path or "/interviewers" in request.url.path or "/resumes" in request.url.path or "/auth/register" in request.url.path:
                cache_delete_prefix("profile:")
        fields.update({"status": response.status_code, "duration_ms": round((perf_counter() - started) * 1000, 2), "outcome": "success" if response.status_code < 400 else "rejected"})
        service_logger(service).info("http_request", extra=fields)
        audit_event(service, "http_request", **{key: value for key, value in fields.items() if key != "service"})
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception as exc:
        fields.update({"status": 500, "duration_ms": round((perf_counter() - started) * 1000, 2), "outcome": "error", "error_type": type(exc).__name__})
        service_logger(service).exception("http_request_failed", extra=fields)
        audit_event(service, "http_request_failed", **{key: value for key, value in fields.items() if key != "service"})
        raise
