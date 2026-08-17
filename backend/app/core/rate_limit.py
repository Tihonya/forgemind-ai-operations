"""Redis-backed distributed rate limiting (WP-P7-02).

The existing limiter in :mod:`app.ai.provider.openai_chat_provider` is
per-process: in a multi-worker deployment (uvicorn ``--workers 4`` plus
ARQ workers) every process keeps its own independent window, so the
configured limit is silently multiplied by the number of processes.

This module provides :class:`RedisRateLimiter` — a fixed-window counter
limiter whose state lives in Redis, so every backend/worker process
shares one window per scope. It is the production-safe limiting
primitive required by the Phase 7 deployment contract
(docs/planning/phase_7_deployment_contract.md, section 6).

Design properties:

- Lua-scripted check-and-increment is atomic: concurrent attempts from
  different processes cannot race past the limit.
- The key includes a sub-second ordinal of the window start time, so
  successive windows never collide in the same state.
- TTL bounds key retention to ``window_seconds + 1`` (no unbounded key
  growth).
- Failure handling is configurable and explicit: ``fail_closed``
  (default) converts any limiter failure into a
  :class:`RateLimitError` so a Redis outage never silently disables
  limiting; ``fail_open`` proceeds without limiting (used only where an
  operator has explicitly accepted that degradation).
- Key names and log fields contain ordinary text only (scope, counters)
  and never secrets.
"""

from __future__ import annotations

import contextlib
import time
from typing import Any

from app.config import settings
from app.core.logging import get_logger

_logger = get_logger(__name__)


class RateLimitError(Exception):
    """Raised when a request is rejected by the distributed rate limiter."""


_DEFAULT_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""


class RedisRateLimiter:
    """Fixed-window distributed rate limiter backed by Redis.

    Guarantees that at most ``max_calls`` calls are admitted within any
    ``window_seconds`` window **per scope**, shared across every process
    that uses the same Redis instance and the same scope name.

    Args:
        scope: A stable identifier for the resource being limited (for
            example ``"ai-provider"``). Distinct scopes get independent
            budgets.
        max_calls: Maximum number of admitted calls per window.
        window_seconds: Fixed-window length in seconds.
        redis_url: Optional Redis endpoint. When ``None``/empty, the
            limiter derives its endpoint from ``settings.redis_url``.
        key_prefix: Redis key prefix. Defaults to the application-wide
            prefix so eviction rules can address all limiter keys at once.
        fail_closed: When True (default) any Redis failure raises
            :class:`RateLimitError` from :meth:`check_and_increment`;
            when False the failure is logged and the call is admitted.
        clock: Injectable clock function (seconds, epoch-based) for
            tests. Defaults to :func:`time.time`.
    """

    def __init__(
        self,
        *,
        scope: str,
        max_calls: int,
        window_seconds: int = 60,
        redis_url: str | None = None,
        client: Any | None = None,
        key_prefix: str = "",
        fail_closed: bool = True,
        clock: Any = None,
    ) -> None:
        from redis.asyncio import Redis

        if not scope:
            raise ValueError("scope must not be empty")
        if max_calls <= 0:
            raise ValueError(f"max_calls must be positive, got {max_calls}")
        if window_seconds <= 0:
            raise ValueError(f"window_seconds must be positive, got {window_seconds}")

        self._scope = scope
        self._max_calls = max_calls
        self._window_seconds = window_seconds
        self._clock = clock if clock is not None else time.time
        self._fail_closed = fail_closed

        prefix = key_prefix or settings.rate_limit_redis_key_prefix
        self._key_prefix = prefix

        # An injected client is shared across limiter instances (one
        # connection pool per process). An owned client is lazy — Redis
        # performs no network I/O until the first command.
        self._owns_client = client is None
        if client is not None:
            self._client = client
        else:
            endpoint = redis_url or settings.rate_limit_redis_url or settings.redis_url
            self._client = Redis.from_url(endpoint)

        self._script_sha: str | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def check_and_increment(self) -> None:
        """Atomically admit or reject one call.

        Raises:
            RateLimitError: If the per-scope budget for the current
                window is exhausted, or (in ``fail_closed`` mode) if the
                Redis operation fails.
        """
        now = float(self._clock())
        window_key = self._window_key(now)
        ttl_seconds = str(self._window_seconds + 1)

        try:
            count = await self._count(window_key, ttl_seconds)
        except Exception as exc:
            if not self._fail_closed:
                _logger.warning(
                    "rate_limit.degraded_fail_open",
                    scope=self._scope,
                    error_type=type(exc).__name__,
                )
                return
            raise RateLimitError(
                "Rate limiter unavailable; request rejected (fail_closed). "
                f"Cause: {type(exc).__name__}"
            ) from exc

        if count > self._max_calls:
            _logger.warning(
                "rate_limit.rejected",
                scope=self._scope,
                count=int(count),
                max_calls=self._max_calls,
                window_seconds=self._window_seconds,
            )
            raise RateLimitError(
                f"Rate limit exceeded for scope {self._scope!r}: "
                f"allowed {self._max_calls} calls per {self._window_seconds}s"
            )

    async def close(self) -> None:
        """Close the underlying Redis client (best effort).

        An injected (shared) client is never closed here.
        """
        if self._owns_client:
            with contextlib.suppress(Exception):
                await self._client.aclose()
        self._script_sha = None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _window_key(self, now: float) -> str:
        """Compute the Redis key for the window containing ``now``.

        The sub-second ordinal of the window start time guarantees that
        successive windows never share a key, so a call at the very end
        of one window is never rejected against the next window's fresh
        counter.
        """
        ordinal = int(now * 1000) // (self._window_seconds * 1000)
        return f"{self._key_prefix}:{self._scope}:{ordinal}"

    async def _count(self, key: str, ttl_seconds: str) -> int:
        """Run the atomic check-and-increment script and return the count.

        The script is loaded lazily on first use. If ``evalsha`` fails
        after a load (e.g. the server restarted and the script cache was
        evicted), the script is re-loaded once and re-tried; a second
        failure propagates to the caller, which converts it to
        :class:`RateLimitError` in ``fail_closed`` mode.
        """
        try:
            sha = self._script_sha or await self._client.script_load(_DEFAULT_SCRIPT)
            self._script_sha = sha
            result = await self._client.evalsha(sha, 1, key, ttl_seconds)
        except Exception:
            # Script cache may have been evicted; reload once.
            self._script_sha = None
            sha = await self._client.script_load(_DEFAULT_SCRIPT)
            self._script_sha = sha
            result = await self._client.evalsha(sha, 1, key, ttl_seconds)
        return int(result)
