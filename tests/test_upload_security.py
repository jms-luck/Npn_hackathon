from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from backend.app.services.parser import safe_resume_filename, validate_resume_file


def docx_bytes(*extra_entries: tuple[str, bytes]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", b"<Types />")
        archive.writestr("word/document.xml", b"<document />")
        for name, content in extra_entries:
            archive.writestr(name, content)
    return output.getvalue()


def test_resume_filename_removes_client_paths() -> None:
    assert safe_resume_filename("../../candidate.pdf") == "candidate.pdf"


def test_docx_validation_accepts_minimal_safe_structure() -> None:
    name, content_type = validate_resume_file("resume.docx", docx_bytes())
    assert name == "resume.docx"
    assert content_type.endswith("document")


def test_docx_validation_rejects_macros_and_unsafe_paths() -> None:
    with pytest.raises(ValueError, match="Active or embedded"):
        validate_resume_file("resume.docx", docx_bytes(("word/vbaProject.bin", b"macro")))
    with pytest.raises(ValueError, match="unsafe path"):
        validate_resume_file("resume.docx", docx_bytes(("../payload.bin", b"payload")))