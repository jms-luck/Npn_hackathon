import pytest

from backend.app.models import Candidate
from backend.app.schemas.contracts import CandidateRegister
from backend.app.services.social_profiles import extract_social_profiles, fill_missing_social_profiles, normalize_social_profile


def test_usernames_and_urls_are_canonicalized() -> None:
    assert normalize_social_profile("jane.doe", "linkedin") == "https://www.linkedin.com/in/jane.doe"
    assert normalize_social_profile("linkedin.com/in/jane-doe/", "linkedin") == "https://www.linkedin.com/in/jane-doe"
    assert normalize_social_profile("@janedoe", "github") == "https://github.com/janedoe"
    assert normalize_social_profile("https://github.com/jane-doe", "github") == "https://github.com/jane-doe"


def test_wrong_domains_and_invalid_usernames_are_rejected() -> None:
    with pytest.raises(ValueError, match="Only linkedin.com"):
        normalize_social_profile("https://example.com/in/jane", "linkedin")
    with pytest.raises(ValueError, match="Invalid Github username"):
        normalize_social_profile("invalid_user", "github")


def test_registration_schema_normalizes_optional_profiles() -> None:
    payload = CandidateRegister(name="Jane", email="jane@example.com", password="Testing123!", linkedin_url="jane-doe", github_url="github.com/janedoe")
    assert payload.linkedin_url == "https://www.linkedin.com/in/jane-doe"
    assert payload.github_url == "https://github.com/janedoe"


def test_resume_profiles_are_extracted_and_only_fill_missing_values() -> None:
    text = "LinkedIn: https://www.linkedin.com/in/jane-doe\nGitHub username: @janedoe"
    assert extract_social_profiles(text) == {"linkedin_url": "https://www.linkedin.com/in/jane-doe", "github_url": "https://github.com/janedoe"}
    candidate = Candidate(user_id=1, linkedin_url="https://www.linkedin.com/in/manual-profile")
    assert fill_missing_social_profiles(candidate, text)
    assert candidate.linkedin_url == "https://www.linkedin.com/in/manual-profile"
    assert candidate.github_url == "https://github.com/janedoe"
