"""ASGI application-level rate limiting backed by the shared Redis limiter.

Pure ASGI middleware (same pattern as the correlation middleware) that
enforces ``settings.rate_limit_per_minute`` per minute **per client
address** across every backend worker process, using
:class:`app.core.rate_limit.RedisRateLimiter`.

Client identification (WP-P7-02 remediation F-1):

- The client address is taken from ``X-Forwarded-For`` (leftmost
  non-empty token of the first forwarded header), which is trusted ONLY
  because the production topology has Caddy as the sole public client
  (Caddy appends the real client IP and drops spoofed forwarded values;
  the backend is reachable only through Caddy on the private frontend
  network).
- With no usable forwarded value the ``scope["client"]`` peer address
  (the reverse proxy's address in the production topology) is used.
- With no client information at all the request lands in a single
  shared ``client:anonymous`` bucket — never a per-request identity, so
  an untrusted source can never mint unbounded budgets.
- Every candidate is passed through
  :func:`app.core.rate_limit.canonicalize_client_identifier` before
  any Redis key is derived, so attacker-controlled text never becomes
  Redis key material (IPs are strictly parsed and normalized; anything
  else is a stable truncated SHA-256 digest).

Budget model:

- Each canonical client identifier namespaces its own fixed window, so
  distinct clients consume distinct budgets: one visitor cannot exhaust
  the budget available to any other visitor.
- The same client behind multiple backend processes shares ONE Redis
  counter (Lua INCR+EXPIRE, window keys including the client namespace).
- There is NO additional global defensive ceiling for HTTP traffic; the
  per-client budget is the whole story. (The AI/provider budget is a
  separate shared ``ai-provider`` limiter enforced at the provider
  boundary, per ``AI_RATE_LIMIT_PER_MINUTE`` — unrelated to this
  middleware.)
- ``/health`` is EXEMPT: it never consumes a client budget and remains
  reachable even when the limiter's Redis is unavailable, so monitoring
  can always observe dependency state (the health payload itself still
  performs its real Redis check and reports the degradation). The
  exemption is an exact route match (``/health`` or ``/health/`` only)
  and can never turn ``/health`` into a pass-through for any other
  route; normal application/API traffic stays limited.

Contract:

- This middleware is registered AFTER the correlation middleware in
  ``main.py``, so (Starlette add_middleware prepend semantics) it
  actually executes OUTSIDE (before) correlation normalization: a
  request rejected here carries a server-generated correlation ID
  minted on the 429 path itself (a request that passes through is
  normalized by the inner correlation middleware as usual).
- On rejection the response is HTTP 429 with a stable JSON error body
  carrying a server-generated correlation ID, and an
  ``X-RateLimit-Limit`` header advertising the per-client budget.
- Fail-closed: when Redis is unreachable and the configured degraded
  mode is ``fail_closed`` (default), ordinary requests are rejected
  with 429 rather than silently unlimited.
- Limiter state lives in Redis, so every per-client budget is shared
  across all backend processes (the per-process sliding window in the
  chat provider is a separate concern and is replaced by the same Redis
  limiter in multi-process deployments).

Environment gate (mirrors the provider-factory pattern): enforcement is
active when ``distributed_rate_limit_enabled`` is True AND the
environment is ``staging`` or ``production``. Development and test runs
pass through and keep using whatever process-local behavior they have.
Because Release 1 production configuration is required to set
``ENVIRONMENT=production`` (enforced by the production config
validator), the single-backend topology cannot silently run without
shared limiting.
"""

from __future__ import annotations

import contextlib
from collections import OrderedDict
from typing import Any

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import settings
from app.core.correlation import CORRELATION_HEADER, generate_correlation_id
from app.core.logging import get_logger
from app.core.rate_limit import (
    RateLimitError,
    RedisRateLimiter,
    canonicalize_client_identifier,
)

_logger = get_logger(__name__)

# Request-scoped budget consumed by this middleware. The effective Redis
# scope additionally includes the canonical client identifier.
_LIMIT_SCOPE = "http-requests"

# Key-scope template: {scope} is the fixed budget name above, {client}
# is the canonical client identifier. Distinct clients therefore
# resolve to distinct Redis keys and distinct budgets.
_LIMIT_SCOPE_FORMAT = "{scope}:{client}"

# Exact paths exempt from budget consumption. Exact-match only — the
# exemption can never be abused as an alternate application endpoint.
_HEALTH_PATHS = frozenset({"/health", "/health/"})

# Bounded number of per-client limiter instances retained per process.
# Exceeding it (only possible under an adversarial flood of distinct
# canonical identifiers) simply drops the per-client cache; clients
# re-register on their next request. Redis keys remain separately
# bounded by window TTLs.
_MAX_TRACKED_CLIENTS = 10_000

# Environments in which the shared HTTP budget is enforced. Development
# and tests keep their existing per-process behavior.
_ENFORCING_ENVIRONMENTS = ("staging", "production")


def _forwarded_candidates(scope: Scope) -> list[str]:
    """Return all raw ``X-Forwarded-For`` header values, in order."""
    return [
        header_value.decode("latin-1")
        for header_name, header_value in scope.get("headers", [])
        if header_name == b"x-forwarded-for"
    ]


def parse_forwarded_for(forwarded_values: list[str]) -> str | None:
    """Return the accepted client address from forwarded header values.

    Trusted model: Caddy is the sole public client of the backend and
    delivers exactly one meaningful ``X-Forwarded-For`` whose leftmost
    token is the real client address (spoofed client-supplied values
    are dropped by Caddy). This function therefore returns the leftmost
    non-empty comma-token of the FIRST header that contains one;
    whitespace-only/malformed values yield ``None`` (malformed input is
    never treated as a distinct identity).
    """
    for raw in forwarded_values:
        for token in raw.split(","):
            candidate = token.strip()
            if candidate:
                return candidate
    return None


def client_identifier_from_scope(scope: Scope) -> str:
    """Return a canonical identifier for the request's source address.

    Preference order: parsed ``X-Forwarded-For`` client address, then
    the transport peer (``scope["client"]``), then the single shared
    ``client:anonymous`` bucket. Every candidate is canonicalized
    before use, so the result is always bounded, Redis-safe, and
    stable across processes.
    """
    forwarded = parse_forwarded_for(_forwarded_candidates(scope))
    if forwarded:
        return canonicalize_client_identifier(forwarded)

    client = scope.get("client")
    if client:
        host = client[0] if isinstance(client, (list, tuple)) else client
        if host:
            return canonicalize_client_identifier(str(host))

    return canonicalize_client_identifier("")


class RateLimitMiddleware:
    """Per-client shared-budget HTTP rate limiting (WP-P7-02).

    Enforcement is enabled only when ``distributed_rate_limit_enabled``
    and the environment is staging/production. Other environments pass
    every request through without consuming a Redis slot.

    Limiter instances are created lazily per canonical client
    identifier and share one injected Redis client, so per-client
    budgets live in the shared Redis key namespace across every
    middleware instance and every worker process.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._enforce = (
            settings.distributed_rate_limit_enabled
            and settings.environment in _ENFORCING_ENVIRONMENTS
        )
        self._limit = settings.rate_limit_per_minute
        self._window_seconds = settings.rate_limit_window_seconds
        self._fail_closed = settings.rate_limit_degraded_mode == "fail_closed"
        self._redis_url = settings.rate_limit_redis_url or settings.redis_url
        # One injected Redis client shared by every per-client limiter
        # (single connection pool per process). The middleware owns it;
        # individual limiters never close an injected client.
        self._shared_client: Any | None = None
        # Bounded per-client limiter registry, lazily populated.
        self._clients: OrderedDict[str, RedisRateLimiter] = OrderedDict()

        if self._enforce:
            from redis.asyncio import Redis

            self._shared_client = Redis.from_url(self._redis_url)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if not self._enforce or self._shared_client is None:
            await self.app(scope, receive, send)
            return

        if scope.get("path", "") in _HEALTH_PATHS:
            # Monitoring exemption: /health never consumes a client
            # budget and stays reachable during limiter Redis outages.
            # Exact-match only; nothing else inherits this exemption.
            await self.app(scope, receive, send)
            return

        client_identifier = client_identifier_from_scope(scope)
        limiter = self._limiter_for(client_identifier)

        try:
            await limiter.check_and_increment()
        except RateLimitError:
            await self._send_rejected(scope, receive, send)
            return
        except Exception as exc:  # pragma: no cover - defensive
            # The limiter converts all its own failures; this is a last
            # resort so an unexpected internal error can never surface
            # as an open path.
            _logger.error(
                "rate_limit.middleware.unexpected_error",
                error_type=type(exc).__name__,
            )
            await self._send_rejected(scope, receive, send)
            return

        await self.app(scope, receive, send)

    # ------------------------------------------------------------------
    # Per-client limiter registry
    # ------------------------------------------------------------------

    def _limiter_for(self, client_identifier: str) -> RedisRateLimiter:
        """Return (creating if needed) the limiter for one canonical client.

        Uses a bounded LRU-style registry: when the cap is exceeded the
        registry is reset, trading a tiny recompute for no unbounded
        per-process memory growth under client-churn attacks.
        """
        limiter = self._clients.get(client_identifier)
        if limiter is None:
            if len(self._clients) >= _MAX_TRACKED_CLIENTS:
                self._clients.clear()
            limiter = RedisRateLimiter(
                scope=_LIMIT_SCOPE,
                max_calls=self._limit,
                window_seconds=self._window_seconds,
                client=self._shared_client,
                fail_closed=self._fail_closed,
                client_identifier=client_identifier,
                scope_format=_LIMIT_SCOPE_FORMAT,
            )
            self._clients[client_identifier] = limiter
            self._clients.move_to_end(client_identifier)
        return limiter

    async def close(self) -> None:
        """Close the shared Redis client (process shutdown, best effort)."""
        if self._shared_client is not None:
            with contextlib.suppress(Exception):
                await self._shared_client.aclose()
            self._shared_client = None

    async def _send_rejected(self, scope: Scope, receive: Receive, send: Send) -> None:
        error_id = generate_correlation_id()
        response = JSONResponse(
            status_code=429,
            content={
                "error": "rate_limit_exceeded",
                "detail": (
                    f"Request rate limit exceeded "
                    f"({self._limit} requests per minute)"
                ),
                "correlation_id": error_id,
            },
            headers={
                CORRELATION_HEADER.lower(): error_id,
                "X-RateLimit-Limit": str(self._limit),
            },
        )
        await response(scope, receive, send)
