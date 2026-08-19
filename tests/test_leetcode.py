import pytest

from backend.app.services.leetcode import LeetCodeProfile, normalize_leetcode_username, score_dsa_profile


def test_leetcode_username_and_profile_url_are_normalized() -> None:
    assert normalize_leetcode_username("code_solver-7") == "code_solver-7"
    assert normalize_leetcode_username("https://leetcode.com/u/code_solver-7/") == "code_solver-7"
    with pytest.raises(ValueError, match="profile URL"):
        normalize_leetcode_username("https://leetcode.com/problems/two-sum/")


def test_dsa_score_rewards_topic_breadth_and_difficulty_depth() -> None:
    profile = LeetCodeProfile(
        username="candidate",
        difficulty_counts={"all": 180, "easy": 80, "medium": 80, "hard": 20},
        topic_counts={slug: config["target"] for slug, config in __import__("backend.app.services.leetcode", fromlist=["CORE_TOPICS"]).CORE_TOPICS.items()},
        recent_solved=[],
    )
    result = score_dsa_profile(profile)
    assert result["score"] >= 90
    assert result["level"] == "Advanced"
    assert result["topic_coverage_score"] == 100
    assert result["difficulty"]["hard"] == 20


def test_dsa_score_identifies_core_topic_gaps() -> None:
    profile = LeetCodeProfile("new_user", {"all": 12, "easy": 10, "medium": 2, "hard": 0}, {"array": 8}, [])
    result = score_dsa_profile(profile)
    assert result["score"] < 25
    assert "Dynamic programming" in result["focus_topics"]
    assert result["topics"][0]["name"] == "Arrays"