"""Unit tests for the ASGI per-client rate-limit middleware (WP-P7-02).

Remediation F-1 coverage:

- distinct clients consume distinct budgets (no global-budget bleed);
- two middleware instances for the same client share one Redis-backed
  budget (cross-instance/cross-process semantics);
- XFF parsing: single/multiple/malformed/missing values;
- IPv4 and IPv6 canonicalization;
- bounded, Redis-safe client identifiers (no unbounded key material);
- Redis failure remains fail-closed for ordinary requests;
- /health is exempt from budget consumption and stays reachable while
  the limiter's Redis is down.

Middleware behavior is tested against a trivial ASGI stub app using an
injected in-memory fake Redis client (shared by all per-client limiters
of one middleware); the /health exemption tests use the real FastAPI
app's /health endpoint (which performs its own dependency checks and
maps failures to a degraded snapshot without needing the database).
No real Redis is used anywhere.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send

from app.api.middleware.rate_limit import (
    RateLimitMiddleware,
    client_identifier_from_scope,
    parse_forwarded_for,
)
from app.core.rate_limit import canonicalize_client_identifier
from app.main import app as fastapi_app


class _FakeRedis:
    """Minimal in-memory Redis fake implementing the client surface the
    limiter uses: script_load/evalsha (with a tiny INCR/EXPIRE
    interpreter) and aclose."""

    def __init__(self, fail: bool = False) -> None:
        self.counters: dict[str, int] = {}
        self.ttls: dict[str, int] = {}
        self.scripts: dict[str, str] = {}
        self.fail = fail

    async def script_load(self, script: str) -> str:
        sha = f"sha-{len(self.scripts)}"
        self.scripts[sha] = script
        return sha

    async def evalsha(self, sha: str, numkeys: int, *keys_and_args: str) -> int:
        if self.fail:
            raise RuntimeError("simulated limiter Redis failure")
        key = keys_and_args[0]
        ttl = keys_and_args[1]
        assert self.scripts.get(sha) is not None, "unknown script sha"
        self.counters[key] = self.counters.get(key, 0) + 1
        if self.counters[key] == 1:
            self.ttls[key] = int(ttl)
        return self.counters[key]

    async def aclose(self) -> None:
        pass


class _StubApp:
    """A DB-free ASGI app returning 200 for every request."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse({"ok": True})
        await response(scope, receive, send)


_STUB_APP = _StubApp()


def _enforced_middleware(
    shared_client: _FakeRedis,
    *,
    limit: int = 2,
    target: Any | None = None,
) -> RateLimitMiddleware:
    """A middleware forced into enforcing mode with an injected fake."""
    middleware = RateLimitMiddleware(target if target is not None else _STUB_APP)
    middleware._enforce = True  # noqa: SLF001 - test seam
    middleware._shared_client = shared_client  # noqa: SLF001 - test seam
    middleware._limit = limit  # noqa: SLF001 - test seam
    return middleware


def _stub_transport(
    shared_client: _FakeRedis, *, limit: int = 2, target: Any | None = None
) -> ASGITransport:
    return ASGITransport(
        app=_enforced_middleware(shared_client, limit=limit, target=target)
    )


# ---------------------------------------------------------------------------
# Client-identifier parsing and canonicalization (pure)
# ---------------------------------------------------------------------------


class TestParseForwardedFor:
    def test_leftmost_token_of_first_header_wins(self) -> None:
        assert parse_forwarded_for(["203.0.113.7, 10.0.0.1"]) == "203.0.113.7"

    def test_second_header_used_when_first_is_empty(self) -> None:
        assert parse_forwarded_for(["", "198.51.100.9"]) == "198.51.100.9"

    def test_multiple_headers_first_non_empty_token_wins(self) -> None:
        assert parse_forwarded_for(["", "  ", "192.0.2.1, 10.1.1.1"]) == "192.0.2.1"

    def test_malformed_whitespace_only_yields_none(self) -> None:
        assert parse_forwarded_for(["   ,  ", ","]) is None

    def test_missing_yields_none(self) -> None:
        assert parse_forwarded_for([]) is None


class TestCanonicalClientIdentifier:
    def test_ipv4_strictly_parsed(self) -> None:
        assert canonicalize_client_identifier("203.0.113.7") == "ip:v4:203.0.113.7"

    def test_ipv6_normalized(self) -> None:
        raw = "2001:0db8:0000:0000:0000:0000:0000:0001"
        assert canonicalize_client_identifier(raw) == "ip:v6:2001:db8::1"

    def test_absent_client_falls_back_to_shared_anonymous_bucket(self) -> None:
        assert canonicalize_client_identifier("") == "client:anonymous"
        assert canonicalize_client_identifier("   ") == "client:anonymous"

    def test_non_ip_values_hashed_not_echoed(self) -> None:
        token = canonicalize_client_identifier("evil-attacker-controlled-text-*" * 5)
        assert "evil-attacker" not in token
        assert token.startswith("client:")

    def test_identifier_bounded_for_hostile_inputs(self) -> None:
        token = canonicalize_client_identifier("x" * 100_000)
        assert len(token) <= 50

    def test_distinct_inputs_map_to_distinct_identifiers(self) -> None:
        a = canonicalize_client_identifier("alpha.example")
        b = canonicalize_client_identifier("beta.example")
        ip = canonicalize_client_identifier("192.0.2.1")
        unknown = canonicalize_client_identifier("")
        assert len({a, b, ip, unknown}) == 4


def test_scope_identifies_client_from_forwarded_header() -> None:
    scope: dict[str, Any] = {
        "type": "http",
        "headers": [(b"x-forwarded-for", b"203.0.113.9, 10.0.0.2")],
        "client": ("127.0.0.1", 12345),
    }
    assert client_identifier_from_scope(scope) == "ip:v4:203.0.113.9"


def test_scope_falls_back_to_peer_when_no_forwarded_value() -> None:
    scope: dict[str, Any] = {
        "type": "http",
        "headers": [],
        "client": ("127.0.0.1", 12345),
    }
    assert client_identifier_from_scope(scope) == "ip:v4:127.0.0.1"


def test_scope_falls_back_to_anonymous_when_nothing_available() -> None:
    scope: dict[str, Any] = {"type": "http", "headers": []}
    assert client_identifier_from_scope(scope) == "client:anonymous"


# ---------------------------------------------------------------------------
# Rejection/429 contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rejection_returns_429_flat_json() -> None:
    """A client exceeding its per-client budget receives HTTP 429."""
    shared = _FakeRedis()
    middleware = _enforced_middleware(shared, limit=1)

    transport = ASGITransport(app=middleware)
    headers = {"x-forwarded-for": "203.0.113.7"}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.get("/anything", headers=headers)
        second = await client.get("/anything", headers=headers)
        assert first.status_code == 200
        assert second.status_code == 429

    body = second.json()
    assert body["error"] == "rate_limit_exceeded"
    assert "correlation_id" in body
    assert second.headers["X-RateLimit-Limit"] == str(middleware._limit)  # noqa: SLF001


@pytest.mark.asyncio
async def test_allowed_request_passes_through() -> None:
    """An allowed request flows through to the wrapped app."""
    shared = _FakeRedis()
    middleware = _enforced_middleware(shared, limit=5)

    transport = ASGITransport(app=middleware)
    headers = {"x-forwarded-for": "203.0.113.7"}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/anything", headers=headers)

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Per-client budget separation (F-1 core proof)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_client_a_budget_does_not_consume_client_b_budget() -> None:
    """Distinct clients have distinct budgets and distinct Redis keys."""
    shared = _FakeRedis()
    middleware = _enforced_middleware(shared, limit=2)

    transport = ASGITransport(app=middleware)
    headers_a = {"x-forwarded-for": "203.0.113.7"}
    headers_b = {"x-forwarded-for": "198.51.100.9"}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Client A exhausts its own budget.
        await client.get("/anything", headers=headers_a)
        await client.get("/anything", headers=headers_a)
        exhausted_a = await client.get("/anything", headers=headers_a)
        assert exhausted_a.status_code == 429
        # Client B is unaffected — its budget is separate.
        response_b = await client.get("/anything", headers=headers_b)
        assert response_b.status_code == 200

    # Distinct Redis key namespaces: A's keys never hold B's counters.
    assert shared.counters
    assert any("ip:v4:203.0.113.7" in key for key in shared.counters)
    assert any("ip:v4:198.51.100.9" in key for key in shared.counters)


@pytest.mark.asyncio
async def test_same_client_shares_budget_across_two_middleware_instances() -> None:
    """Two limiter instances for one client share ONE Redis-backed budget."""
    shared = _FakeRedis()
    first = _enforced_middleware(shared, limit=2)
    second = _enforced_middleware(shared, limit=2)
    headers = {"x-forwarded-for": "203.0.113.7"}

    async with AsyncClient(
        transport=ASGITransport(app=first), base_url="http://test"
    ) as client:
        # First instance consumes one slot from the shared Redis budget.
        r0 = await client.get("/anything", headers=headers)
        assert r0.status_code == 200

    async with AsyncClient(
        transport=ASGITransport(app=second), base_url="http://test"
    ) as client:
        # Second instance sees the same counter (shared fake Redis):
        # first call admitted, second call exhausts the shared budget.
        r1 = await client.get("/anything", headers=headers)
        r2 = await client.get("/anything", headers=headers)
        assert r1.status_code == 200
        assert r2.status_code == 429


# ---------------------------------------------------------------------------
# Fail-closed Redis failure + /health exemption (F-7)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redis_failure_is_fail_closed_for_ordinary_requests() -> None:
    """Limiter Redis outage rejects ordinary requests with 429."""
    shared = _FakeRedis(fail=True)
    middleware = _enforced_middleware(shared, limit=60)

    transport = ASGITransport(app=middleware)
    headers = {"x-forwarded-for": "203.0.113.7"}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/anything", headers=headers)
        assert response.status_code == 429
        body = response.json()
        assert body["error"] == "rate_limit_exceeded"


@pytest.mark.asyncio
async def test_health_exempt_when_client_budget_exhausted() -> None:
    """Exhausted client budget still allows /health to execute."""
    shared = _FakeRedis()
    middleware = _enforced_middleware(shared, limit=1, target=fastapi_app)
    transport = ASGITransport(app=middleware)
    headers = {"x-forwarded-for": "203.0.113.7"}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.get("/", headers=headers)
        blocked = await client.get("/", headers=headers)
        health = await client.get("/health", headers=headers)
        assert first.status_code == 200  # admitted
        assert blocked.status_code == 429  # then budget exhausted
        # Health still executes normal health logic (HTTP 200 with the
        # flat health payload, even degraded).
        assert health.status_code == 200
        assert "status" in health.json()


@pytest.mark.asyncio
async def test_health_exempt_when_limiter_redis_unavailable() -> None:
    """Limiter Redis outage does not mask /health."""
    shared = _FakeRedis(fail=True)
    middleware = _enforced_middleware(shared, limit=60, target=fastapi_app)
    transport = ASGITransport(app=middleware)
    headers = {"x-forwarded-for": "203.0.113.7"}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ordinary = await client.get("/", headers=headers)
        health = await client.get("/health", headers=headers)
        assert ordinary.status_code == 429
        assert health.status_code == 200


@pytest.mark.asyncio
async def test_health_does_not_consume_client_budget() -> None:
    """A burst of /health calls never consumes ordinary budget."""
    shared = _FakeRedis()
    middleware = _enforced_middleware(shared, limit=2, target=fastapi_app)
    transport = ASGITransport(app=middleware)
    headers = {"x-forwarded-for": "203.0.113.7"}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(5):
            health = await client.get("/health", headers=headers)
            assert health.status_code == 200
        # The ordinary budget is untouched: both slots still available.
        first = await client.get("/", headers=headers)
        second = await client.get("/", headers=headers)
        assert first.status_code == 200
        assert second.status_code == 200


@pytest.mark.asyncio
async def test_health_handler_emits_no_secret_values() -> None:
    """The real /health payload contains no secrets (flat statuses only)."""
    shared = _FakeRedis()
    middleware = _enforced_middleware(shared, limit=60, target=fastapi_app)
    transport = ASGITransport(app=middleware)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/health")
        assert health.status_code == 200
        body = health.json()
        text = health.text
        # Dependency names are fine; credentials, URLs, and secret
        # descriptors must never appear.
        assert "password" not in text
        assert "secret" not in text
        assert "://" not in text
        assert body.get("status") in {
            "healthy",
            "degraded",
            "unhealthy",
        }
        assert isinstance(body.get("checks"), dict)


@pytest.mark.asyncio
async def test_health_exemption_is_exact_match_only() -> None:
    """Path variants of /health are NOT exempt from limiting."""
    shared = _FakeRedis()
    middleware = _enforced_middleware(shared, limit=1)
    transport = ASGITransport(app=middleware)
    headers = {"x-forwarded-for": "203.0.113.7"}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.get("/healthx", headers=headers)
        second = await client.get("/healthx", headers=headers)
        third = await client.get("/api/v1/health", headers=headers)
        assert first.status_code == 200  # first call within budget
        assert second.status_code == 429  # /healthx consumes budget
        assert third.status_code == 429  # budget now exhausted for client


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
        assert middleware._shared_client is None  # noqa: SLF001

    def test_production_environment_is_enforced(self, monkeypatch: Any) -> None:
        from app.config import settings as app_settings

        monkeypatch.setattr(app_settings, "environment", "production")
        monkeypatch.setattr(
            app_settings, "distributed_rate_limit_enabled", True
        )
        monkeypatch.setattr(app_settings, "redis_url", "redis://localhost:6379/0")
        middleware = RateLimitMiddleware(_passthrough_app())
        assert middleware._enforce is True  # noqa: SLF001
        assert middleware._shared_client is not None  # noqa: SLF001

    def test_disabled_flag_disables_even_in_production(self, monkeypatch: Any) -> None:
        from app.config import settings as app_settings

        monkeypatch.setattr(app_settings, "environment", "production")
        monkeypatch.setattr(
            app_settings, "distributed_rate_limit_enabled", False
        )
        middleware = RateLimitMiddleware(_passthrough_app())
        assert middleware._enforce is False  # noqa: SLF001
        assert middleware._shared_client is None  # noqa: SLF001


def _passthrough_app() -> Any:
    """A trivial ASGI app returning 200 for every request."""

    async def app_fn(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse({"ok": True})
        await response(scope, receive, send)

    return app_fn
