import json
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


LEETCODE_GRAPHQL_URL = "https://leetcode.com/graphql"
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,30}$")

CORE_TOPICS = {
    "array": {"label": "Arrays", "target": 40, "weight": 15},
    "string": {"label": "Strings", "target": 30, "weight": 8},
    "hash-table": {"label": "Hash tables", "target": 25, "weight": 8},
    "linked-list": {"label": "Linked lists", "target": 20, "weight": 7},
    "stack": {"label": "Stacks", "target": 20, "weight": 6},
    "queue": {"label": "Queues", "target": 15, "weight": 4},
    "tree": {"label": "Trees", "target": 35, "weight": 12},
    "graph": {"label": "Graphs", "target": 30, "weight": 12},
    "dynamic-programming": {"label": "Dynamic programming", "target": 30, "weight": 12},
    "binary-search": {"label": "Binary search", "target": 25, "weight": 8},
    "heap-priority-queue": {"label": "Heaps", "target": 15, "weight": 5},
    "greedy": {"label": "Greedy", "target": 20, "weight": 3},
}

PROFILE_QUERY = """
query dsaProfile($username: String!, $recentLimit: Int!) {
  matchedUser(username: $username) {
    username
    submitStatsGlobal {
      acSubmissionNum { difficulty count submissions }
    }
    tagProblemCounts {
      advanced { tagName tagSlug problemsSolved }
      intermediate { tagName tagSlug problemsSolved }
      fundamental { tagName tagSlug problemsSolved }
    }
  }
  recentAcSubmissionList(username: $username, limit: $recentLimit) {
    title titleSlug timestamp
  }
}
"""


class LeetCodeError(RuntimeError):
    pass


@dataclass(frozen=True)
class LeetCodeProfile:
    username: str
    difficulty_counts: dict[str, int]
    topic_counts: dict[str, int]
    recent_solved: list[dict]


def normalize_leetcode_username(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("LeetCode username or profile URL is required")
    if "://" in raw or "leetcode.com" in raw.lower():
        url = raw if "://" in raw else f"https://{raw}"
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower().removeprefix("www.")
        if hostname != "leetcode.com":
            raise ValueError("Only leetcode.com profile URLs are accepted")
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) != 2 or parts[0].lower() != "u":
            raise ValueError("Use a LeetCode profile URL such as leetcode.com/u/username")
        username = parts[1]
    else:
        username = raw.strip("/@")
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("Invalid LeetCode username")
    return username


def fetch_leetcode_profile(username_or_url: str, timeout: float = 10.0) -> LeetCodeProfile:
    username = normalize_leetcode_username(username_or_url)
    body = json.dumps({"query": PROFILE_QUERY, "variables": {"username": username, "recentLimit": 10}}).encode("utf-8")
    request = Request(
        LEETCODE_GRAPHQL_URL,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "HireAI-DSA-Evaluator/1.0", "Referer": f"https://leetcode.com/u/{username}/"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise LeetCodeError("LeetCode profile data is temporarily unavailable") from exc
    if payload.get("errors"):
        raise LeetCodeError("LeetCode could not return this profile")
    data = payload.get("data") or {}
    user = data.get("matchedUser")
    if not user:
        raise LeetCodeError(f"LeetCode user '{username}' was not found or is private")

    stats = user.get("submitStatsGlobal") or {}
    difficulty_counts = {
        str(item.get("difficulty", "")).lower(): int(item.get("count") or 0)
        for item in stats.get("acSubmissionNum") or []
    }
    topic_counts = {}
    for group in (user.get("tagProblemCounts") or {}).values():
        for item in group or []:
            topic_counts[item.get("tagSlug", "")] = int(item.get("problemsSolved") or 0)
    recent_solved = [
        {
            "title": item.get("title"),
            "url": f"https://leetcode.com/problems/{item.get('titleSlug')}/",
            "timestamp": int(item.get("timestamp") or 0),
        }
        for item in data.get("recentAcSubmissionList") or []
    ]
    return LeetCodeProfile(username, difficulty_counts, topic_counts, recent_solved)


def score_dsa_profile(profile: LeetCodeProfile) -> dict:
    topics = []
    weighted_coverage = 0.0
    for slug, config in CORE_TOPICS.items():
        solved = profile.topic_counts.get(slug, 0)
        attainment = min(solved / config["target"], 1.0)
        weighted_coverage += attainment * config["weight"]
        topics.append({
            "slug": slug,
            "name": config["label"],
            "solved": solved,
            "target": config["target"],
            "strength": round(attainment * 100),
            "gap_priority": (1 - attainment) * config["weight"],
        })

    counts = profile.difficulty_counts
    difficulty_depth = (
        min(counts.get("easy", 0) / 100, 1.0) * 20
        + min(counts.get("medium", 0) / 75, 1.0) * 50
        + min(counts.get("hard", 0) / 25, 1.0) * 30
    )
    score = round(weighted_coverage * 0.75 + difficulty_depth * 0.25)
    level = "Advanced" if score >= 80 else "Strong" if score >= 65 else "Intermediate" if score >= 45 else "Developing" if score >= 25 else "Beginner"
    focus_topics = [
        item["name"]
        for item in sorted(topics, key=lambda item: (-item["gap_priority"], item["name"]))
        if item["strength"] < 50
    ][:4]
    for item in topics:
        item.pop("gap_priority")
    topics.sort(key=lambda item: (-item["strength"], item["name"]))
    return {
        "username": profile.username,
        "profile_url": f"https://leetcode.com/u/{profile.username}/",
        "score": score,
        "level": level,
        "total_solved": counts.get("all", sum(counts.get(key, 0) for key in ("easy", "medium", "hard"))),
        "difficulty": {key: counts.get(key, 0) for key in ("easy", "medium", "hard")},
        "topic_coverage_score": round(weighted_coverage),
        "difficulty_depth_score": round(difficulty_depth),
        "topics": topics,
        "strongest_topics": [item["name"] for item in topics if item["strength"] >= 70][:4],
        "focus_topics": focus_topics,
        "recent_solved": profile.recent_solved,
        "methodology": "75% weighted core-topic coverage and 25% Easy/Medium/Hard depth; counts are capped at published targets.",
    }