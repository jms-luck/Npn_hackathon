from backend.app.core.rate_limit import RateRule, consume_rate_limit, rate_rule


def test_sensitive_routes_have_bounded_rate_rules() -> None:
    assert rate_rule("POST", "/api/auth/login").limit == 10
    assert rate_rule("POST", "/api/resumes/upload").window_seconds == 3_600
    assert rate_rule("POST", "/api/recruiter/jobs/7/match").name == "matching"
    assert rate_rule("GET", "/api/candidate/recommended-jobs").limit == 20
    assert rate_rule("GET", "/api/jobs") is None


def test_rate_limit_uses_atomic_redis_counter(monkeypatch) -> None:
    calls = []

    class FakeRedis:
        def eval(self, script, key_count, key, window):
            calls.append((key_count, key, window))
            return [3, 42]

    monkeypatch.setattr("backend.app.core.rate_limit.redis_client", lambda: FakeRedis())
    allowed, remaining, retry_after = consume_rate_limit(RateRule("login", 3, 60), "ip:127.0.0.1")
    assert allowed
    assert remaining == 0
    assert retry_after == 42
    assert calls[0][1].startswith("rate:login:")
    assert "127.0.0.1" not in calls[0][1]