import json
import re
import base64
import math
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from backend.app.core.config import settings
from backend.app.services.cache import cache_get, cache_set


GITHUB_API = "https://api.github.com"
TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9+#.-]{2,}", re.IGNORECASE)
STOP_WORDS = {
    "about", "and", "application", "build", "built", "code", "data", "for", "from", "github", "have",
    "into", "project", "projects", "repository", "resume", "that", "their", "this", "using",
    "the", "with", "work", "worked", "year", "years",
}


class GitHubProfileError(RuntimeError):
    pass


def github_username(profile_url: str) -> str:
    parsed = urlparse(profile_url)
    hostname = (parsed.hostname or "").lower().removeprefix("www.")
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.scheme != "https" or hostname != "github.com" or len(parts) != 1:
        raise ValueError("A canonical GitHub profile URL is required")
    return parts[0]


def _github_get(path: str) -> object:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "HireAI-GitHub-Evidence/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    try:
        with urlopen(Request(f"{GITHUB_API}{path}", headers=headers), timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404:
            raise GitHubProfileError("GitHub profile was not found") from exc
        if exc.code in (403, 429):
            raise GitHubProfileError("GitHub API rate limit reached; try again later") from exc
        raise GitHubProfileError("GitHub profile verification failed") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GitHubProfileError("GitHub profile data is temporarily unavailable") from exc


def fetch_public_github_evidence(profile_url: str) -> dict:
    username = github_username(profile_url)
    cache_key = f"github:evidence:{username.lower()}"
    if cached := cache_get(cache_key):
        return cached
    profile = _github_get(f"/users/{username}")
    repository_limit = 30 if settings.github_token else 10
    repositories = _github_get(f"/users/{username}/repos?per_page={repository_limit}&sort=updated")
    if not isinstance(profile, dict) or not isinstance(repositories, list):
        raise GitHubProfileError("GitHub returned an unexpected response")
    canonical_login = str(profile.get("login") or "")
    canonical_url = str(profile.get("html_url") or "")
    verified = canonical_login.lower() == username.lower() and canonical_url.lower().rstrip("/") == profile_url.lower().rstrip("/")
    repository_evidence = []
    for repo in repositories[:repository_limit]:
        owner = str((repo.get("owner") or {}).get("login") or username)
        name = str(repo.get("name") or "")
        try:
            languages = _github_get(f"/repos/{owner}/{name}/languages")
        except GitHubProfileError:
            languages = {}
        try:
            readme_payload = _github_get(f"/repos/{owner}/{name}/readme")
            readme_text = base64.b64decode((readme_payload or {}).get("content", "")).decode("utf-8", errors="ignore")[:20_000]
        except (GitHubProfileError, ValueError):
            readme_text = ""
        try:
            commits = _github_get(f"/repos/{owner}/{name}/commits?author={username}&per_page=100")
            candidate_commits = len(commits) if isinstance(commits, list) else 0
        except GitHubProfileError:
            candidate_commits = 0
        if repo.get("fork") and candidate_commits == 0:
            continue
        repository_evidence.append({
            "name": name,
            "url": repo.get("html_url"),
            "description": repo.get("description"),
            "topics": repo.get("topics") or [],
            "language": repo.get("language"),
            "languages": languages if isinstance(languages, dict) else {},
            "readme_text": readme_text,
            "fork": bool(repo.get("fork")),
            "archived": bool(repo.get("archived")),
            "updated_at": repo.get("pushed_at") or repo.get("updated_at"),
            "stars": int(repo.get("stargazers_count") or 0),
            "candidate_commits": candidate_commits,
        })
    evidence = {
        "verified": verified,
        "verification_status": "VERIFIED_PUBLIC_PROFILE" if verified else "PROFILE_MISMATCH",
        "username": canonical_login or username,
        "profile_url": canonical_url or profile_url,
        "profile_name": profile.get("name"),
        "created_at": profile.get("created_at"),
        "public_repositories": int(profile.get("public_repos") or 0),
        "repositories": repository_evidence,
    }
    cache_set(cache_key, evidence, settings.cache_github_ttl)
    return evidence


def _tokens(value: str) -> set[str]:
    return {token.lower() for token in TOKEN_PATTERN.findall(value or "") if token.lower() not in STOP_WORDS}


def score_repository_relevance(resume_text: str, repositories: list[dict]) -> tuple[int, list[dict]]:
    resume_tokens = _tokens(resume_text)
    scored = []
    for repository in repositories:
        if repository.get("archived"):
            continue
        languages = repository.get("languages") or ({repository.get("language"): 1} if repository.get("language") else {})
        repo_text = " ".join(
            [
                str(repository.get("name") or "").replace("-", " ").replace("_", " "),
                str(repository.get("description") or ""),
                " ".join(repository.get("topics") or []),
                " ".join(languages.keys()),
                str(repository.get("readme_text") or ""),
            ]
        )
        repo_tokens = _tokens(repo_text)
        matched = sorted(resume_tokens & repo_tokens)
        raw_signal = min(len(matched) / max(1, min(len(repo_tokens), 12)), 1.0)
        ownership_weight = 1.0 if not repository.get("fork") else min(1.0, int(repository.get("candidate_commits") or 0) / 5)
        activity_weight = min(1.0, 0.5 + 0.1 * min(int(repository.get("stars") or 0), 5))
        updated_at = repository.get("updated_at")
        if updated_at:
            pushed = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
            days = (datetime.now(timezone.utc) - pushed).days
            recency_weight = 1.0 if days <= 180 else 0.85 if days <= 365 else 0.6 if days <= 730 else 0.4
        else:
            recency_weight = 0.5
        weighted_signal = raw_signal * ownership_weight * activity_weight * recency_weight
        score = round((1 - math.exp(-weighted_signal / 0.35)) * 100) if weighted_signal else 0
        scored.append({
            "name": repository.get("name"),
            "url": repository.get("url"),
            "language": repository.get("language"),
            "relevance_score": score,
            "matched_terms": matched[:10],
            "updated_at": repository.get("updated_at"),
            "candidate_commits": int(repository.get("candidate_commits") or 0),
            "evidence": {"languages": sorted(languages), "topics": repository.get("topics") or [], "readme_match": bool(matched)},
        })
    scored.sort(key=lambda item: (-item["relevance_score"], item["name"] or ""))
    top = [item for item in scored if item["relevance_score"] > 0][:3]
    weights = (0.5, 0.3, 0.2)[:len(top)]
    relevance = round(sum(item["relevance_score"] * weight for item, weight in zip(top, weights)) / sum(weights)) if top else 0
    return relevance, scored[:5]


def evaluate_github_resume_evidence(profile_url: str | None, resume_text: str) -> dict:
    if not profile_url:
        return {"verified": False, "verification_status": "NOT_PROVIDED", "relevance_score": None, "repositories": []}
    evidence = fetch_public_github_evidence(profile_url)
    relevance, repositories = score_repository_relevance(resume_text, evidence["repositories"])
    active_repositories = [repo for repo in evidence["repositories"] if not repo["archived"]]
    recent_cutoff = datetime.now(timezone.utc).year - 2
    recently_active = sum(1 for repo in active_repositories if repo.get("updated_at") and int(repo["updated_at"][:4]) >= recent_cutoff)
    return {
        "verified": evidence["verified"],
        "verification_status": evidence["verification_status"],
        "username": evidence["username"],
        "profile_url": evidence["profile_url"],
        "public_repositories": evidence["public_repositories"],
        "recently_active_repositories": recently_active,
        "relevance_score": relevance,
        "repositories": repositories,
        "disclaimer": "A public profile can be verified, but account ownership cannot be proven from public GitHub data alone.",
    }