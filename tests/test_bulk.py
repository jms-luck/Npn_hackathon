import pytest
from fastapi import HTTPException

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import load_workbook

from backend.app.routers.bulk import credential_workbook, parse_rows, resume_files_from_zip


def test_parse_bulk_csv_accepts_valid_rows() -> None:
    rows = parse_rows(
        b"full_name,email,phone,location,resume_filename\nJane Doe,JANE@example.com,555,NY,jane.pdf\n"
    )

    assert rows == [{
        "full_name": "Jane Doe",
        "email": "jane@example.com",
        "phone": "555",
        "location": "NY",
        "resume_filename": "jane.pdf",
        "resume_key": "jane.pdf",
    }]


def test_parse_bulk_csv_requires_template_columns() -> None:
    with pytest.raises(HTTPException) as error:
        parse_rows(b"name,email\nJane,jane@example.com\n")

    assert error.value.status_code == 400
    assert "resume_filename" in error.value.detail


def test_parse_bulk_csv_rejects_duplicate_emails() -> None:
    content = b"full_name,email,resume_filename\nJane,jane@example.com,a.pdf\nJane Again,jane@example.com,b.pdf\n"

    with pytest.raises(HTTPException) as error:
        parse_rows(content)

    assert error.value.status_code == 400
    assert "Duplicate email" in error.value.detail


def test_credential_workbook_contains_new_applicant_passwords() -> None:
    content = credential_workbook([{"name": "Jane", "email": "jane@example.com", "password": "initial-secret", "candidate_id": 7, "resume_filename": "jane.pdf"}])
    sheet = load_workbook(BytesIO(content)).active
    assert sheet["B2"].value == "jane@example.com"
    assert sheet["C2"].value == "initial-secret"


def test_resume_zip_rejects_unsafe_paths() -> None:
    archive = BytesIO()
    with ZipFile(archive, "w", ZIP_DEFLATED) as bundle:
        bundle.writestr("../resume.pdf", b"%PDF-invalid")
    with pytest.raises(HTTPException, match="unsafe path"):
        resume_files_from_zip(archive.getvalue())
