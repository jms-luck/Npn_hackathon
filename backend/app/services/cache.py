import json
from functools import lru_cache
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from backend.app.core.config import settings
from backend.app.core.logging_config import service_logger


logger = service_logger("system")


@lru_cache
def redis_client() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1)


def cache_get(key: str) -> Any | None:
    try:
        value = redis_client().get(key)
        if value is None:
            return None
        logger.info("cache_hit", extra={"cache_key": key})
        return json.loads(value)
    except (RedisError, ValueError) as exc:
        logger.warning("cache_read_failed", extra={"cache_key": key, "error_type": type(exc).__name__})
        return None


def cache_get_raw(key: str) -> str | None:
    try:
        value = redis_client().get(key)
        if value is not None:
            logger.info("cache_hit", extra={"cache_key": key})
        return value
    except RedisError as exc:
        logger.warning("cache_read_failed", extra={"cache_key": key, "error_type": type(exc).__name__})
        return None


def cache_set(key: str, value: Any, ttl: int | None = None) -> None:
    try:
        redis_client().setex(key, ttl or settings.cache_default_ttl, json.dumps(value, default=str))
        logger.info("cache_set", extra={"cache_key": key, "ttl": ttl or settings.cache_default_ttl})
    except (RedisError, TypeError) as exc:
        logger.warning("cache_write_failed", extra={"cache_key": key, "error_type": type(exc).__name__})


def cache_set_raw(key: str, value: str, ttl: int | None = None) -> None:
    try:
        redis_client().setex(key, ttl or settings.cache_default_ttl, value)
        logger.info("cache_set", extra={"cache_key": key, "ttl": ttl or settings.cache_default_ttl})
    except RedisError as exc:
        logger.warning("cache_write_failed", extra={"cache_key": key, "error_type": type(exc).__name__})


def cache_delete(*keys: str) -> None:
    if not keys:
        return
    try:
        redis_client().delete(*keys)
        logger.info("cache_deleted", extra={"cache_keys": list(keys)})
    except RedisError as exc:
        logger.warning("cache_delete_failed", extra={"error_type": type(exc).__name__})


def cache_delete_prefix(prefix: str) -> None:
    try:
        client = redis_client()
        keys = list(client.scan_iter(match=f"{prefix}*", count=200))
        if keys:
            client.delete(*keys)
        logger.info("cache_prefix_deleted", extra={"cache_prefix": prefix, "count": len(keys)})
    except RedisError as exc:
        logger.warning("cache_delete_failed", extra={"cache_prefix": prefix, "error_type": type(exc).__name__})


def cache_health() -> bool:
    try:
        return bool(redis_client().ping())
    except RedisError:
        return False
