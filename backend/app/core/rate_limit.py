from dataclasses import dataclass
from hashlib import sha256

from fastapi import Request
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError

from backend.app.core.audit_middleware import actor_from_request
from backend.app.core.logging_config import audit_event, service_logger
from backend.app.services.cache import redis_client


logger = service_logger("system")


@dataclass(frozen=True)
class RateRule:
    name: str
    limit: int
    window_seconds: int


def rate_rule(method: str, path: str) -> RateRule | None:
    if method == "POST" and path == "/api/auth/login":
        return RateRule("login", 10, 60)
    if method == "POST" and path.startswith("/api/auth/register/"):
        return RateRule("registration", 5, 3_600)
    if method == "POST" and path == "/api/resumes/upload":
        return RateRule("resume_upload", 10, 3_600)
    if method == "POST" and path.endswith("/applicants/bulk"):
        return RateRule("bulk_upload", 5, 3_600)
    if path.endswith("/suitability") or (method == "POST" and path.endswith("/match")):
        return RateRule("matching", 30, 60)
    if method == "POST" and path == "/api/candidate/dsa-evaluation":
        return RateRule("external_profile", 10, 3_600)
    if method == "GET" and path == "/api/candidate/recommended-jobs":
        return RateRule("candidate_matching", 20, 3_600)
    return None


def _rate_key(rule: RateRule, identifier: str) -> str:
    digest = sha256(identifier.encode("utf-8")).hexdigest()[:24]
    return f"rate:{rule.name}:{digest}"


def consume_rate_limit(rule: RateRule, identifier: str) -> tuple[bool, int, int]:
    script = """
    local current = redis.call('INCR', KEYS[1])
    if current == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
    return {current, redis.call('TTL', KEYS[1])}
    """
    try:
        current, ttl = redis_client().eval(script, 1, _rate_key(rule, identifier), rule.window_seconds)
        return int(current) <= rule.limit, max(0, rule.limit - int(current)), max(1, int(ttl))
    except RedisError as exc:
        logger.warning("rate_limit_unavailable", extra={"rule": rule.name, "error_type": type(exc).__name__})
        return True, rule.limit, rule.window_seconds


async def rate_limit_request(request: Request, call_next):
    rule = rate_rule(request.method, request.url.path)
    if not rule:
        return await call_next(request)
    user_id, _ = actor_from_request(request)
    identifier = f"user:{user_id}" if user_id else f"ip:{request.client.host if request.client else 'unknown'}"
    allowed, remaining, retry_after = consume_rate_limit(rule, identifier)
    if not allowed:
        audit_event("system", "rate_limit_rejected", rule=rule.name, path=request.url.path, user_id=user_id)
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests; retry later"},
            headers={"Retry-After": str(retry_after), "X-RateLimit-Limit": str(rule.limit), "X-RateLimit-Remaining": "0"},
        )
    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(rule.limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    return response