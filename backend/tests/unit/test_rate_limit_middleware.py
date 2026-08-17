"""Unit tests for the ASGI shared rate-limit middleware (WP-P7-02).

Middleware behavior is tested against a plain ASGI stub app using an
injected fake limiter; no real Redis is used.

Environment gating (development/test pass-through; staging/production
enforce) is tested at the factory level by constructing the middleware
under a patched settings object, and enforced-construction behavior is
tested by replacing the middleware's limiter after construction.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.middleware.rate_limit import RateLimitMiddleware
from app.main import app


class _FakeLimiter:
    """Controllable limiter stub for middleware tests."""

    def __init__(self, allow: bool = True) -> None:
        self.allow = allow
        self.calls = 0
        self.failed = False

    async def check_and_increment(self) -> None:
        self.calls += 1
        if self.failed:
            raise RuntimeError("unexpected limiter failure")
        if not self.allow:
            from app.core.rate_limit import RateLimitError

            raise RateLimitError("rejected")


# ---------------------------------------------------------------------------
# Rejection/429 contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rejection_returns_429_flat_json() -> None:
    """An enforced middleware with a rejecting limiter returns HTTP 429."""
    fake = _FakeLimiter(allow=False)
    middleware = RateLimitMiddleware(app)
    middleware._enforce = True  # noqa: SLF001 - test seam
    middleware._limiter = fake  # type: ignore[assignment]  # noqa: SLF001

    transport = ASGITransport(app=middleware)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 429
    body = response.json()
    assert body["error"] == "rate_limit_exceeded"
    assert "correlation_id" in body
    assert response.headers["X-RateLimit-Limit"] == str(middleware._limit)  # noqa: SLF001
    assert fake.calls == 1


@pytest.mark.asyncio
async def test_allowed_request_passes_through() -> None:
    """An allowed request flows through to the wrapped app."""
    fake = _FakeLimiter(allow=True)
    middleware = RateLimitMiddleware(app)
    middleware._enforce = True  # noqa: SLF001
    middleware._limiter = fake  # type: ignore[assignment]  # noqa: SLF001

    transport = ASGITransport(app=middleware)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    # The real app responds (200 even though deps are unavailable — the
    # endpoint itself maps their failures to a degraded snapshot).
    assert response.status_code == 200
    assert fake.calls == 1


# ---------------------------------------------------------------------------
# Environment gate
# ---------------------------------------------------------------------------


class TestEnvironmentGate:
    """Middleware construction respects the environment settings."""

    def test_development_environment_is_not_enforced(self, monkeypatch: Any) -> None:
        from app.config import settings as app_settings

        monkeypatch.setattr(app_settings, "environment", "development")
        monkeypatch.setattr(
            app_settings, "distributed_rate_limit_enabled", True
        )
        middleware = RateLimitMiddleware(_passthrough_app())
        assert middleware._enforce is False  # noqa: SLF001
        assert middleware._limiter is None  # noqa: SLF001

    def test_production_environment_is_enforced(self, monkeypatch: Any) -> None:
        from app.config import settings as app_settings

        monkeypatch.setattr(app_settings, "environment", "production")
        monkeypatch.setattr(
            app_settings, "distributed_rate_limit_enabled", True
        )
        middleware = RateLimitMiddleware(_passthrough_app())
        assert middleware._enforce is True  # noqa: SLF001
        assert middleware._limiter is not None  # noqa: SLF001

    def test_disabled_flag_disables_even_in_production(self, monkeypatch: Any) -> None:
        from app.config import settings as app_settings

        monkeypatch.setattr(app_settings, "environment", "production")
        monkeypatch.setattr(
            app_settings, "distributed_rate_limit_enabled", False
        )
        middleware = RateLimitMiddleware(_passthrough_app())
        assert middleware._enforce is False  # noqa: SLF001
        assert middleware._limiter is None  # noqa: SLF001


def _passthrough_app() -> Any:
    """A trivial ASGI app returning 200 for every request."""

    from starlette.responses import JSONResponse
    from starlette.types import Receive, Scope, Send

    async def app_fn(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse({"ok": True})
        await response(scope, receive, send)

    return app_fn
