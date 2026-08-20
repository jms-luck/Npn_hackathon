import pytest
from fastapi.testclient import TestClient

from backend.app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from backend.app.main import app
from backend.app.routers.admin import resume_section
from backend.app.routers.jobs import job_payload
from backend.app.models import JobPosting
from backend.app.services.parser import extract_resume_text, validate_resume_file


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_password_hashing_and_jwt() -> None:
    hashed = hash_password("correct-horse-battery-staple")
    assert hashed != "correct-horse-battery-staple"
    assert verify_password("correct-horse-battery-staple", hashed)
    payload = decode_access_token(create_access_token(25, "RECRUITER"))
    assert payload["sub"] == "25"
    assert payload["role"] == "RECRUITER"


def test_parser_rejects_unsupported_files() -> None:
    with pytest.raises(ValueError, match="Only PDF and DOCX"):
        extract_resume_text("resume.txt", b"plain text")


def test_resume_validation_rejects_extension_spoofing() -> None:
    with pytest.raises(ValueError, match="does not match"):
        validate_resume_file("resume.pdf", b"not a pdf")


def test_candidate_details_extract_labeled_resume_sections() -> None:
    text = "Skills: Python, SQL\nExperience: Five years\nEducation and Qualifications: BSc Computer Science"
    assert resume_section(text, ["Skills"]) == "Python, SQL"
    assert resume_section(text, ["Experience"]) == "Five years"
    assert resume_section(text, ["Education and Qualifications"]) == "BSc Computer Science"


def test_job_payload_contains_candidate_visible_metadata() -> None:
    job = JobPosting(job_id=25, company_id=3, recruiter_id=None, job_title="AI Engineer", salary_range="$100k-$120k", qualifications="BSc", country="India", location="Remote", source_type="DATASET", status="ACTIVE")
    payload = job_payload(job, "Hire AI")
    assert payload["Job_Id"] == "JOB_025"
    assert payload["company_name"] == "Hire AI"
    assert payload["salary_range"] == "$100k-$120k"
    assert payload["qualifications"] == "BSc"
    assert payload["country"] == "India"
    assert payload["location"] == "Remote"


def test_required_routes_are_registered() -> None:
    paths = app.openapi()["paths"]
    required = {
        "/api/auth/login",
        "/api/assistant/chat",
        "/api/auth/profile",
        "/api/jobs",
        "/api/companies/options",
        "/api/resumes/upload",
        "/api/candidate/match",
        "/api/candidate/recommended-jobs",
        "/api/candidate/dsa-evaluation",
        "/api/candidate/github-evaluation",
        "/api/recruiter/jobs/{job_id}/match",
        "/api/recruiter/jobs/{job_id}/match-progress",
        "/api/recruiter/jobs/{job_id}",
        "/api/recruiter/jobs/{job_id}/applicants/bulk-template",
        "/api/recruiter/jobs/{job_id}/applicants/bulk",
        "/api/recruiter/jobs/{job_id}/applicants/{candidate_id}/suitability",
        "/api/interviewer/candidates",
        "/api/recruiter/interviewers",
        "/api/interviewer/interviews/{interview_id}/suitability",
        "/api/auth/register/interviewer",
        "/api/admin/overview",
        "/api/admin/audit",
        "/api/admin/companies",
        "/api/admin/matches",
    }
    assert required <= paths.keys()
    assert "/api/auth/register/admin" not in paths
    assert "post" in paths["/api/admin/companies"]
    crud = {
        "/api/admin/companies/{company_ID}": {"put", "delete"},
        "/api/admin/users/{User_Id}": {"put", "delete"},
        "/api/admin/jobs/{Job_Id}": {"put", "delete"},
        "/api/admin/candidates/{candidate_id}": {"get", "put", "delete"},
        "/api/admin/recruiters/{recruiter_id}": {"put", "delete"},
        "/api/admin/interviewers/{interviewer_Id}": {"put", "delete"},
        "/api/admin/applications/{Application_Id}": {"put", "delete"},
        "/api/admin/resumes/{resume_ref}/access": {"get"},
        "/api/admin/resumes/{resume_ref}": {"delete"},
    }
    for path, methods in crud.items():
        assert methods <= paths[path].keys()


def test_admin_routes_require_authentication() -> None:
    response = client.get("/api/admin/overview")
    assert response.status_code == 401
    create_response = client.post("/api/admin/companies", json={"company_name": "Test", "verification_code": "1234"})
    assert create_response.status_code == 401