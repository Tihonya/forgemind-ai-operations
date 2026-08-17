"""ASGI application-level rate limiting backed by the shared Redis limiter.

Pure ASGI middleware (same pattern as the correlation middleware) that
enforces ``settings.rate_limit_per_minute`` per minute per client address
across every backend worker process, using
:class:`app.core.rate_limit.RedisRateLimiter`.

Contract:

- Limiting decision is made AFTER the correlation header is normalized
  (this middleware is registered inside the correlation middleware).
- On rejection the response is HTTP 429 with a stable JSON error body
  carrying a server-generated correlation ID, and an
  ``X-RateLimit-Limit`` header advertising the budget.
- Health/liveness requests are NOT exempt: they are bounded like any
  other request so probes cannot bypass the application budget.
- Fail-closed: when Redis is unreachable and the configured degraded
  mode is ``fail_closed`` (default), requests are rejected with 429
  rather than silently unlimited.
- Limiter state lives in Redis, so the budget is shared across all
  backend processes (the per-process sliding window in the chat
  provider is a separate concern and is replaced by the same Redis
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

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import settings
from app.core.correlation import CORRELATION_HEADER, generate_correlation_id
from app.core.logging import get_logger
from app.core.rate_limit import RateLimitError, RedisRateLimiter

_logger = get_logger(__name__)

# Request-scoped budget consumed by this middleware.
_LIMIT_SCOPE = "http-requests"

# Environments in which the shared HTTP budget is enforced. Development
# and tests keep their existing per-process behavior.
_ENFORCING_ENVIRONMENTS = ("staging", "production")


def _extract_client_ip(scope: Scope) -> str:
    """Return a stable client identifier for the scope.

    Trusts ``X-Forwarded-For`` only when the deployment reverse proxy
    (Caddy) is the sole client — which is the production topology. The
    value is sanitized down to a short token so no arbitrary input
    becomes part of a Redis key.
    """
    for header_name, header_value in scope.get("headers", []):
        if header_name == b"x-forwarded-for":
            first = str(header_value.decode("latin-1")).split(",")[0].strip()
            if first:
                return first[:64]

    client = scope.get("client")
    if client and isinstance(client[0], str):
        return client[0][:64]
    return "unknown"


class RateLimitMiddleware:
    """Shared-budget HTTP rate limiting (WP-P7-02).

    Enforcement is enabled only when ``distributed_rate_limit_enabled``
    and the environment is staging/production. Other environments pass
    every request through without consuming a Redis slot.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._enforce = (
            settings.distributed_rate_limit_enabled
            and settings.environment in _ENFORCING_ENVIRONMENTS
        )
        self._limiter: RedisRateLimiter | None = None
        self._limit = settings.rate_limit_per_minute
        if self._enforce:
            self._limiter = RedisRateLimiter(
                scope=_LIMIT_SCOPE,
                max_calls=settings.rate_limit_per_minute,
                window_seconds=settings.rate_limit_window_seconds,
                fail_closed=(settings.rate_limit_degraded_mode == "fail_closed"),
            )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if not self._enforce or self._limiter is None:
            await self.app(scope, receive, send)
            return

        try:
            await self._limiter.check_and_increment()
        except RateLimitError:
            await self._send_rejected(scope, receive, send)
            return
        except Exception as exc:  # pragma: no cover - defensive
            # The limiter converts all failures itself; this is a last
            # resort so an unexpected internal error can never surface
            # as an open path.
            _logger.error(
                "rate_limit.middleware.unexpected_error",
                error_type=type(exc).__name__,
            )
            await self._send_rejected(scope, receive, send)
            return

        await self.app(scope, receive, send)

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
