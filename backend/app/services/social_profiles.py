import re
from urllib.parse import urlparse

from backend.app.models import Candidate


LINKEDIN_USERNAME = re.compile(r"^[A-Za-z0-9._-]{2,100}$")
GITHUB_USERNAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
LINKEDIN_URL = re.compile(r"(?i)(?:https?://)?(?:www\.)?linkedin\.com/(?:in/)?([A-Za-z0-9._%-]{2,100})")
GITHUB_URL = re.compile(r"(?i)(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9-]{1,39})")
LINKEDIN_LABEL = re.compile(r"(?im)^\s*linkedin(?:\s+(?:profile|username))?\s*[:\-]\s*@?([A-Za-z0-9._-]{2,100})\s*$")
GITHUB_LABEL = re.compile(r"(?im)^\s*github(?:\s+(?:profile|username))?\s*[:\-]\s*@?([A-Za-z0-9-]{1,39})\s*$")


def _username(value: str, provider: str) -> str:
    username = value.strip().strip("/@").split("?", 1)[0].split("#", 1)[0]
    pattern = LINKEDIN_USERNAME if provider == "linkedin" else GITHUB_USERNAME
    if not pattern.fullmatch(username):
        raise ValueError(f"Invalid {provider.title()} username")
    return username


def normalize_social_profile(value: str | None, provider: str) -> str | None:
    if value is None or not str(value).strip():
        return None
    raw = str(value).strip()
    domain = "linkedin.com" if provider == "linkedin" else "github.com"
    if "://" in raw or domain in raw.lower():
        url = raw if "://" in raw else f"https://{raw}"
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower().removeprefix("www.")
        if hostname != domain:
            raise ValueError(f"Only {domain} profile URLs are accepted")
        parts = [part for part in parsed.path.split("/") if part]
        if provider == "linkedin" and parts and parts[0].lower() == "in":
            parts = parts[1:]
        if len(parts) != 1:
            raise ValueError(f"Invalid {provider.title()} profile URL")
        username = _username(parts[0], provider)
    else:
        username = _username(raw, provider)
    return f"https://www.linkedin.com/in/{username}" if provider == "linkedin" else f"https://github.com/{username}"


def extract_social_profiles(text: str | None) -> dict[str, str | None]:
    if not text:
        return {"linkedin_url": None, "github_url": None}
    linkedin_match = LINKEDIN_URL.search(text) or LINKEDIN_LABEL.search(text)
    github_match = GITHUB_URL.search(text) or GITHUB_LABEL.search(text)
    result = {"linkedin_url": None, "github_url": None}
    if linkedin_match:
        try:
            result["linkedin_url"] = normalize_social_profile(linkedin_match.group(1), "linkedin")
        except ValueError:
            pass
    if github_match:
        try:
            result["github_url"] = normalize_social_profile(github_match.group(1), "github")
        except ValueError:
            pass
    return result


def fill_missing_social_profiles(candidate: Candidate, resume_text: str | None) -> bool:
    extracted = extract_social_profiles(resume_text)
    changed = False
    if not candidate.linkedin_url and extracted["linkedin_url"]:
        candidate.linkedin_url = extracted["linkedin_url"]
        changed = True
    if not candidate.github_url and extracted["github_url"]:
        candidate.github_url = extracted["github_url"]
        changed = True
    return changed
