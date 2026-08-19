import pytest
from fastapi import HTTPException

from backend.app.routers.bulk import parse_rows


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
