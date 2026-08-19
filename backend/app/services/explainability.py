from backend.app.models import Candidate, JobPosting, MatchResult, Resume
from backend.app.services.graph import parse_skills


def _explicit_skill_evidence(job: JobPosting, resume: Resume) -> tuple[list[str], list[str]]:
    required = parse_skills(job.skills)
    resume_text = (resume.extracted_text or "").casefold()
    matched = [skill for skill in required if skill.casefold() in resume_text]
    matched_keys = {skill.casefold() for skill in matched}
    missing = [skill for skill in required if skill.casefold() not in matched_keys]
    return matched, missing


def build_suitability_explanation(
    job: JobPosting,
    candidate: Candidate,
    resume: Resume,
    match: MatchResult | None = None,
    semantic_score: float | None = None,
) -> dict:
    matched_skills, missing_skills = _explicit_skill_evidence(job, resume)
    semantic = float(match.semantic_score) if match else semantic_score
    github_score = float(match.github_score) if match and match.github_score is not None else None
    github_verified = bool(match.github_verified) if match else False
    overall = float(match.overall_score) if match else semantic
    skill_coverage = round(len(matched_skills) / len(matched_skills + missing_skills) * 100, 1) if matched_skills or missing_skills else None

    factors = [{
        "name": "Resume-to-role semantic fit",
        "score": round(semantic, 1) if semantic is not None else None,
        "weight": 85 if github_verified and github_score is not None else 100,
        "evidence": "Full resume text compared with the job title, description, responsibilities, qualifications, and skills.",
    }]
    if skill_coverage is not None:
        factors.append({
            "name": "Explicit required-skill coverage",
            "score": skill_coverage,
            "weight": 0,
            "evidence": f"{len(matched_skills)} of {len(matched_skills + missing_skills)} listed job skills appear explicitly in the resume.",
        })
    if github_verified and github_score is not None:
        factors.append({
            "name": "Verified public GitHub project relevance",
            "score": round(github_score, 1),
            "weight": 15,
            "evidence": "Public repository names, descriptions, topics, and languages compared with resume project evidence.",
        })

    strengths = []
    if matched_skills:
        strengths.append(f"Resume explicitly demonstrates {', '.join(matched_skills[:8])}.")
    if semantic is not None and semantic >= 70:
        strengths.append(f"The complete resume has {semantic:.1f}% semantic similarity to this role.")
    if github_verified and github_score is not None:
        strengths.append(f"The verified public GitHub profile has {github_score:.1f}% project relevance to the resume.")
    if not strengths:
        strengths.append("No strong evidence factor has crossed the configured threshold yet.")

    gaps = [f"The resume does not explicitly verify: {', '.join(missing_skills[:8])}." ] if missing_skills else []
    if candidate.github_url and not github_verified:
        gaps.append("The supplied GitHub profile could not be verified, so it did not affect the score.")
    if not candidate.github_url:
        gaps.append("No GitHub profile was supplied; the score is based on resume evidence only.")
    if not gaps:
        gaps.append("No explicit skill gap was found; interview validation is still required.")

    level = "strong" if overall is not None and overall >= 75 else "moderate" if overall is not None and overall >= 55 else "limited"
    narrative = match.explanation if match and match.explanation else None
    return {
        "candidate_id": candidate.candidate_id,
        "job_id": job.job_id,
        "job_title": job.job_title,
        "overall_score": round(overall, 1) if overall is not None else None,
        "fit_level": level.upper(),
        "summary": f"Available evidence indicates {level} suitability for the {job.job_title} role.",
        "factors": factors,
        "strengths": strengths,
        "gaps": gaps,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "narrative": narrative,
        "disclaimer": "This is decision support, not a hiring decision. Validate claims in the interview and do not infer protected or personal characteristics.",
    }