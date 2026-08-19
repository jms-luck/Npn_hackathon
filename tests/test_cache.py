from redis.exceptions import ConnectionError

from backend.app.services import cache


class FakeRedis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def setex(self, key, ttl, value):
        self.values[key] = value

    def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)

    def scan_iter(self, match, count=200):
        prefix = match.removesuffix("*")
        return (key for key in list(self.values) if key.startswith(prefix))

    def ping(self):
        return True


def test_cache_round_trip_and_prefix_invalidation(monkeypatch) -> None:
    client = FakeRedis()
    monkeypatch.setattr(cache, "redis_client", lambda: client)
    cache.cache_set("jobs:active:1", {"items": [1]}, 30)
    cache.cache_set("jobs:active:2", {"items": [2]}, 30)
    assert cache.cache_get("jobs:active:1") == {"items": [1]}
    cache.cache_delete_prefix("jobs:active:")
    assert cache.cache_get("jobs:active:1") is None
    assert cache.cache_get("jobs:active:2") is None
    assert cache.cache_health()


def test_cache_fails_open_when_redis_is_unavailable(monkeypatch) -> None:
    class BrokenRedis:
        def get(self, key):
            raise ConnectionError("unavailable")

    monkeypatch.setattr(cache, "redis_client", lambda: BrokenRedis())
    assert cache.cache_get("profile:1") is None
