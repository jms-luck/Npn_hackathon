from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile, is_zipfile

from docx import Document
from pypdf import PdfReader


MAX_RESUME_BYTES = 10 * 1024 * 1024
MAX_DOCX_ENTRIES = 1_000
MAX_DOCX_UNCOMPRESSED_BYTES = 25 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
MAX_PDF_PAGES = 100
MAX_EXTRACTED_TEXT_CHARS = 250_000
DOCX_REQUIRED_ENTRIES = {"[Content_Types].xml", "word/document.xml"}
DOCX_BLOCKED_PREFIXES = ("word/activeX/", "word/embeddings/", "customUI/")


def safe_resume_filename(filename: str) -> str:
    name = Path(filename or "").name.strip()
    name = "".join(character for character in name if character.isprintable() and character not in {'"', "'"})
    if not name or len(name) > 255:
        raise ValueError("Invalid resume filename")
    return name


def validate_resume_file(filename: str, content: bytes) -> tuple[str, str]:
    safe_name = safe_resume_filename(filename)
    suffix = Path(safe_name).suffix.lower()
    if suffix not in {".pdf", ".docx"}:
        raise ValueError("Only PDF and DOCX resumes are supported")
    if not content:
        raise ValueError("Resume file is empty")
    if len(content) > MAX_RESUME_BYTES:
        raise ValueError("Resume exceeds 10 MB")
    if suffix == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise ValueError("File content does not match the PDF extension")
        try:
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted:
                raise ValueError("Encrypted PDF resumes are not supported")
            if len(reader.pages) > MAX_PDF_PAGES:
                raise ValueError(f"PDF resumes may contain at most {MAX_PDF_PAGES} pages")
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Invalid PDF resume") from exc
        return safe_name, "application/pdf"

    if not is_zipfile(BytesIO(content)):
        raise ValueError("File content does not match the DOCX extension")
    try:
        with ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            names = {entry.filename for entry in entries}
            if len(entries) > MAX_DOCX_ENTRIES:
                raise ValueError("DOCX archive contains too many entries")
            if not DOCX_REQUIRED_ENTRIES.issubset(names):
                raise ValueError("Invalid DOCX document structure")
            total_uncompressed = 0
            for entry in entries:
                path = Path(entry.filename)
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("DOCX archive contains an unsafe path")
                if entry.filename.endswith("vbaProject.bin") or entry.filename.startswith(DOCX_BLOCKED_PREFIXES):
                    raise ValueError("Active or embedded DOCX content is not allowed")
                total_uncompressed += entry.file_size
                if entry.compress_size and entry.file_size / entry.compress_size > MAX_COMPRESSION_RATIO:
                    raise ValueError("DOCX archive compression ratio is unsafe")
            if total_uncompressed > MAX_DOCX_UNCOMPRESSED_BYTES:
                raise ValueError("DOCX archive expands beyond the allowed size")
    except BadZipFile as exc:
        raise ValueError("Invalid DOCX resume") from exc
    return safe_name, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def extract_resume_text(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages).strip()
        if len(text) > MAX_EXTRACTED_TEXT_CHARS:
            raise ValueError("Extracted resume text exceeds the allowed size")
        return text
    if suffix == ".docx":
        text = "\n".join(paragraph.text for paragraph in Document(BytesIO(content)).paragraphs).strip()
        if len(text) > MAX_EXTRACTED_TEXT_CHARS:
            raise ValueError("Extracted resume text exceeds the allowed size")
        return text
    raise ValueError("Only PDF and DOCX resumes are supported")