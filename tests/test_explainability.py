from decimal import Decimal
from types import SimpleNamespace

from backend.app.services.explainability import build_suitability_explanation


def test_explanation_exposes_weighted_evidence_strengths_and_gaps() -> None:
    job = SimpleNamespace(job_id=7, job_title="Backend Engineer", skills="Python, FastAPI, PostgreSQL, Kubernetes")
    candidate = SimpleNamespace(candidate_id=3, github_url="https://github.com/jane")
    resume = SimpleNamespace(extracted_text="Projects: Python FastAPI service backed by PostgreSQL.")
    match = SimpleNamespace(
        semantic_score=Decimal("82.0"), github_score=Decimal("76.0"), github_verified=True,
        overall_score=Decimal("81.1"), explanation="Evidence narrative.",
    )

    result = build_suitability_explanation(job, candidate, resume, match)

    assert result["overall_score"] == 81.1
    assert result["fit_level"] == "STRONG"
    assert [factor["weight"] for factor in result["factors"]] == [85, 0, 15]
    assert result["matched_skills"] == ["Python", "FastAPI", "PostgreSQL"]
    assert result["missing_skills"] == ["Kubernetes"]
    assert "decision support" in result["disclaimer"]


def test_explanation_does_not_penalize_missing_github() -> None:
    job = SimpleNamespace(job_id=8, job_title="Analyst", skills=None)
    candidate = SimpleNamespace(candidate_id=4, github_url=None)
    resume = SimpleNamespace(extracted_text="SQL analytics")

    result = build_suitability_explanation(job, candidate, resume, semantic_score=64.0)

    assert result["overall_score"] == 64.0
    assert result["factors"][0]["weight"] == 100
    assert len(result["factors"]) == 1