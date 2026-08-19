import json
import logging
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.core.audit_middleware import service_for_path
from backend.app.core.config import settings
from backend.app.core.logging_config import JsonFormatter, service_logger
from backend.app.main import app


client = TestClient(app)


def test_paths_route_to_separate_services() -> None:
    assert service_for_path("/api/auth/login") == "auth"
    assert service_for_path("/api/admin/users") == "admin"
    assert service_for_path("/api/recruiter/jobs/1/applicants/bulk") == "bulk"
    assert service_for_path("/api/recruiter/jobs/1/match") == "matching"
    assert service_for_path("/api/resumes/1") == "resumes"
    assert service_for_path("/health") == "system"


def test_json_formatter_serializes_safe_structured_fields() -> None:
    record = logging.LogRecord("hireai.auth", logging.INFO, __file__, 1, "login", (), None)
    record.request_id = "request-1"
    record.user_id = "25"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["request_id"] == "request-1"
    assert payload["user_id"] == "25"
    assert "authorization" not in payload


def test_requests_get_request_ids_and_audit_entries() -> None:
    response = client.get("/health", headers={"X-Request-ID": "audit-test-request"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "audit-test-request"
    for name in ("system", "audit"):
        for handler in service_logger(name).handlers:
            handler.flush()
        path = Path(settings.log_dir) / f"{name}.log"
        assert path.exists()
        assert "audit-test-request" in path.read_text(encoding="utf-8")
