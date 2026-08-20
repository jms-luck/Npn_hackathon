import pytest

from backend.app.services.github_profiles import github_username, score_repository_relevance


def test_github_username_requires_canonical_profile_url() -> None:
    assert github_username("https://github.com/jane-doe") == "jane-doe"
    with pytest.raises(ValueError, match="canonical"):
        github_username("https://github.com/jane-doe/project")


def test_resume_related_repository_outranks_unrelated_repository() -> None:
    resume = "Projects: Built a FastAPI recruitment service with PostgreSQL, Redis, Docker, and React."
    repositories = [
        {"name": "hire-api", "url": "https://github.com/jane/hire-api", "description": "FastAPI recruitment backend", "topics": ["postgresql", "redis", "docker"], "language": "Python", "languages": {"Python": 5000}, "readme_text": "FastAPI PostgreSQL Redis Docker", "stars": 3, "candidate_commits": 12, "fork": False, "archived": False, "updated_at": "2026-01-01T00:00:00Z"},
        {"name": "recipe-book", "url": "https://github.com/jane/recipe-book", "description": "Family recipes and cooking notes", "topics": ["food"], "language": "HTML", "languages": {"HTML": 1000}, "readme_text": "recipes", "stars": 0, "candidate_commits": 2, "fork": False, "archived": False, "updated_at": "2026-01-01T00:00:00Z"},
    ]
    relevance, details = score_repository_relevance(resume, repositories)
    assert relevance > 40
    assert details[0]["name"] == "hire-api"
    assert details[0]["relevance_score"] > details[1]["relevance_score"]
    assert "fastapi" in details[0]["matched_terms"]