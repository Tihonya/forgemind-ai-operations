"""Unit tests for the Redis-backed distributed rate limiter (WP-P7-02).

All tests use an in-memory fake Redis client — no network, no real
Redis instance required.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.rate_limit import RateLimitError, RedisRateLimiter


class _FakeRedis:
    """Minimal in-memory Redis fake implementing the client surface the
    limiter uses: script_load/evalsha (with a tiny INCR/EXPIRE
    interpreter) and aclose."""

    def __init__(self, fail_on: str | None = None) -> None:
        self.counters: dict[str, int] = {}
        self.ttls: dict[str, int] = {}
        self.scripts: dict[str, str] = {}
        self.fail_on = fail_on
        self.evalsha_calls = 0
        self.script_load_calls = 0
        self.closed = False

    async def script_load(self, script: str) -> str:
        self.script_load_calls += 1
        sha = f"sha-{len(self.scripts)}"
        self.scripts[sha] = script
        return sha

    async def evalsha(self, sha: str, numkeys: int, *keys_and_args: str) -> int:
        if self.fail_on == "evalsha":
            raise RuntimeError("simulated evalsha failure")
        self.evalsha_calls += 1
        key = keys_and_args[0]
        ttl = keys_and_args[1]
        assert self.scripts.get(sha) is not None, "unknown script sha"
        if "INCR" in self.scripts[sha]:
            self.counters[key] = self.counters.get(key, 0) + 1
            if self.counters[key] == 1:
                self.ttls[key] = int(ttl)
            return self.counters[key]
        raise RuntimeError("unknown script body")

    async def aclose(self) -> None:
        self.closed = True


def test_window_key_stable_within_window_and_changes_across_windows() -> None:
    # Windows are epoch-aligned: t // 60 seconds. 1000s and 1019.999s
    # share window [960, 1020); 1020.001 opens the next one.
    limiter = RedisRateLimiter(
        scope="unit", max_calls=5, window_seconds=60, client=_FakeRedis(),
        clock=lambda: 1000.0,
    )
    first = limiter._window_key(1000.0)
    late_same_window = limiter._window_key(1019.999)
    next_window = limiter._window_key(1020.001)
    assert first == late_same_window
    assert first != next_window


@pytest.mark.asyncio
async def test_check_and_increment_admits_up_to_limit_then_raises() -> None:
    limiter = RedisRateLimiter(
        scope="unit", max_calls=2, client=_FakeRedis(), clock=lambda: 1000.0
    )
    await limiter.check_and_increment()
    await limiter.check_and_increment()
    with pytest.raises(RateLimitError):
        await limiter.check_and_increment()


@pytest.mark.asyncio
async def test_script_loaded_lazily_and_reused() -> None:
    fake = _FakeRedis()
    limiter = RedisRateLimiter(
        scope="unit", max_calls=5, client=fake, clock=lambda: 1000.0
    )
    await limiter.check_and_increment()
    await limiter.check_and_increment()
    # First call loads the script, subsequent calls evalsha the cached sha.
    assert fake.script_load_calls == 1
    assert fake.evalsha_calls == 2


@pytest.mark.asyncio
async def test_evalsha_failure_reloads_script_once() -> None:
    class FailingOnce(_FakeRedis):
        def __init__(self) -> None:
            super().__init__()
            self._failures_left = 1

        async def evalsha(
            self, sha: str, numkeys: int, *keys_and_args: str
        ) -> int:
            if self._failures_left > 0:
                self._failures_left -= 1
                self.evalsha_calls += 1
                raise RuntimeError("simulated script-cache eviction")
            return await super().evalsha(sha, numkeys, *keys_and_args)

    fake = FailingOnce()
    limiter = RedisRateLimiter(
        scope="unit", max_calls=5, client=fake, clock=lambda: 1000.0
    )
    # First call: load -> evalsha fails -> reload -> evalsha succeeds.
    await limiter.check_and_increment()
    assert fake.script_load_calls == 2
    assert fake.evalsha_calls == 2


@pytest.mark.asyncio
async def test_fail_closed_raises_on_client_error() -> None:
    limiter = RedisRateLimiter(
        scope="unit", max_calls=5, client=_FakeRedis(fail_on="evalsha"),
        clock=lambda: 1000.0, fail_closed=True,
    )
    with pytest.raises(RateLimitError, match="fail_closed"):
        await limiter.check_and_increment()


@pytest.mark.asyncio
async def test_fail_open_proceeds_on_client_error() -> None:
    limiter = RedisRateLimiter(
        scope="unit", max_calls=5, client=_FakeRedis(fail_on="evalsha"),
        clock=lambda: 1000.0, fail_closed=False,
    )
    # No exception — the call is admitted when the limiter is degraded.
    await limiter.check_and_increment()


@pytest.mark.asyncio
async def test_close_closes_owned_client_and_clears_script_sha() -> None:
    fake = _FakeRedis()
    with patch("redis.asyncio.Redis.from_url", return_value=fake):
        limiter = RedisRateLimiter(
            scope="unit",
            max_calls=5,
            redis_url="redis://placeholder:6379/0",
            clock=lambda: 1000.0,
        )
    await limiter.check_and_increment()
    assert limiter._script_sha is not None
    await limiter.close()
    assert fake.closed is True
    assert limiter._script_sha is None


@pytest.mark.asyncio
async def test_injected_client_never_closed_by_limiter() -> None:
    fake = _FakeRedis()
    first = RedisRateLimiter(scope="a", max_calls=5, client=fake)
    second = RedisRateLimiter(scope="b", max_calls=5, client=fake)
    await first.close()
    assert fake.closed is False
    await second.check_and_increment()  # still usable after first.close()


@pytest.mark.asyncio
async def test_custom_key_prefix_and_scope_used_in_key() -> None:
    fake = _FakeRedis()
    limiter = RedisRateLimiter(
        scope="custom-scope", max_calls=5, client=fake, key_prefix="pfx",
        clock=lambda: 1000.0,
    )
    await limiter.check_and_increment()
    assert any(k.startswith("pfx:custom-scope:") for k in fake.counters)


@pytest.mark.asyncio
async def test_ttl_set_to_window_plus_one() -> None:
    fake = _FakeRedis()
    limiter = RedisRateLimiter(
        scope="unit", max_calls=5, window_seconds=30, client=fake,
        clock=lambda: 1000.0,
    )
    await limiter.check_and_increment()
    assert list(fake.ttls.values()) == [31]


@pytest.mark.asyncio
async def test_new_window_gets_fresh_budget() -> None:
    fake = _FakeRedis()
    t = [1000.0]

    def clock() -> float:
        return t[0]

    limiter = RedisRateLimiter(
        scope="unit", max_calls=2, window_seconds=60, client=fake, clock=clock
    )
    await limiter.check_and_increment()
    await limiter.check_and_increment()
    with pytest.raises(RateLimitError):
        await limiter.check_and_increment()
    # Roll the clock into the next 60s window — budget resets.
    t[0] = 1061.0
    await limiter.check_and_increment()


def test_constructor_rejects_invalid_arguments() -> None:
    with pytest.raises(ValueError, match="scope"):
        RedisRateLimiter(scope="", max_calls=1, client=_FakeRedis())
    with pytest.raises(ValueError, match="max_calls"):
        RedisRateLimiter(scope="x", max_calls=0, client=_FakeRedis())
    with pytest.raises(ValueError, match="window_seconds"):
        RedisRateLimiter(scope="x", max_calls=1, window_seconds=0, client=_FakeRedis())
