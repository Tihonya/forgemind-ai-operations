"""Unit tests for the correlation-ID ASGI middleware."""

from __future__ import annotations

import asyncio
import re
import uuid
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.types import Receive, Scope, Send

from app.core.context import bind_correlation_id, get_correlation_id
from app.core.correlation import CORRELATION_HEADER
from app.main import app

_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@pytest.fixture()
def client() -> AsyncClient:
    """Return an httpx AsyncClient wired to the FastAPI app."""
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://testserver")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _cid(response: Any) -> str:
    """Return the single correlation-id header value or raise."""
    # httpx Headers API varies by version: getlist() in older, get_list() in newer
    values = response.headers.get_list(CORRELATION_HEADER)
    assert len(values) == 1, f"expected exactly one header, got {values!r}"
    return values[0]


# ---------------------------------------------------------------------------
# valid / absent / invalid
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_absent_header_generates_uuid4(client: AsyncClient) -> None:
    """No input header -> middleware generates a valid UUID v4."""
    response = await client.get("/health")
    value = _cid(response)
    assert _UUID4_RE.match(value), f"{value!r} is not UUID v4"


@pytest.mark.asyncio
async def test_valid_header_echoed_canonical(client: AsyncClient) -> None:
    """A clean UUID v4 input is echoed in canonical lowercase form."""
    cid_in = str(uuid.uuid4())
    response = await client.get("/health", headers={CORRELATION_HEADER: cid_in})
    assert _cid(response) == cid_in


@pytest.mark.asyncio
async def test_uppercase_header_normalized(client: AsyncClient) -> None:
    """An upper-case UUID v4 is normalised to lowercase canonical form."""
    cid_in = str(uuid.uuid4()).upper()
    response = await client.get("/health", headers={CORRELATION_HEADER: cid_in})
    assert _cid(response) == cid_in.lower()


@pytest.mark.asyncio
async def test_malformed_header_returns_400(client: AsyncClient) -> None:
    """Non-UUID input -> 400 with a valid server-generated correlation ID."""
    response = await client.get(
        "/health", headers={CORRELATION_HEADER: "not-a-uuid"}
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "invalid_correlation_id"
    assert body["detail"] == "X-Correlation-ID is not a valid UUID v4"
    server_cid = _cid(response)
    assert _UUID4_RE.match(server_cid)


@pytest.mark.asyncio
async def test_non_v4_uuid_returns_400(client: AsyncClient) -> None:
    """A valid UUID that is not version 4 -> 400."""
    v1 = str(uuid.uuid1())
    response = await client.get("/health", headers={CORRELATION_HEADER: v1})
    assert response.status_code == 400
    assert _UUID4_RE.match(_cid(response))


@pytest.mark.asyncio
async def test_empty_header_returns_400() -> None:
    """Empty X-Correlation-ID header -> 400 with server-generated correlation ID.

    Header present but empty is invalid input (not "absent"). Downstream
    must not be dispatched.
    """
    from app.api.middleware.correlation import CorrelationIdMiddleware

    downstream_called = False

    async def dummy_app(scope: Scope, receive: Receive, send: Send) -> None:  # noqa: ARG001
        nonlocal downstream_called
        downstream_called = True  # pragma: no cover

    mw = CorrelationIdMiddleware(dummy_app)
    captured: dict[str, Any] = {}

    async def receive_noop() -> dict[str, Any]:
        return {"type": "http.disconnect"}  # pragma: no cover

    async def capturing_send(message: Any) -> None:
        if message["type"] == "http.response.start":
            captured["status"] = message["status"]
            captured["headers"] = [
                (
                    n if isinstance(n, str) else n.decode(),
                    v if isinstance(v, str) else v.decode(),
                )
                for n, v in message.get("headers", [])
            ]

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/health",
        "raw_path": b"/health",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"testserver"),
            (b"x-correlation-id", b""),
        ],
    }

    await mw(scope, receive_noop, capturing_send)

    assert captured["status"] == 400
    cid_values = [
        v for n, v in captured["headers"] if n.lower() == "x-correlation-id"
    ]
    assert len(cid_values) == 1
    assert _UUID4_RE.match(cid_values[0])
    assert not downstream_called


@pytest.mark.asyncio
async def test_whitespace_only_header_returns_400() -> None:
    """Whitespace-only X-Correlation-ID -> same 400 contract as empty header."""
    from app.api.middleware.correlation import CorrelationIdMiddleware

    downstream_called = False

    async def dummy_app(scope: Scope, receive: Receive, send: Send) -> None:  # noqa: ARG001
        nonlocal downstream_called
        downstream_called = True  # pragma: no cover

    mw = CorrelationIdMiddleware(dummy_app)
    captured: dict[str, Any] = {}

    async def receive_noop() -> dict[str, Any]:
        return {"type": "http.disconnect"}  # pragma: no cover

    async def capturing_send(message: Any) -> None:
        if message["type"] == "http.response.start":
            captured["status"] = message["status"]
            captured["headers"] = [
                (
                    n if isinstance(n, str) else n.decode(),
                    v if isinstance(v, str) else v.decode(),
                )
                for n, v in message.get("headers", [])
            ]

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/health",
        "raw_path": b"/health",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"testserver"),
            (b"x-correlation-id", b"   \t  "),
        ],
    }

    await mw(scope, receive_noop, capturing_send)

    assert captured["status"] == 400
    cid_values = [
        v for n, v in captured["headers"] if n.lower() == "x-correlation-id"
    ]
    assert len(cid_values) == 1
    assert _UUID4_RE.match(cid_values[0])
    assert not downstream_called


@pytest.mark.asyncio
async def test_duplicate_headers_returns_400() -> None:
    """Duplicate X-Correlation-ID headers -> 400 contract.

    httpx cannot send duplicate headers easily, so we invoke the middleware
    directly with a crafted ASGI scope.
    """
    from app.api.middleware.correlation import CorrelationIdMiddleware

    async def dummy_app(scope: Scope, receive: Receive, send: Send) -> None:  # noqa: ARG001
        pass  # pragma: no cover - must not be reached

    mw = CorrelationIdMiddleware(dummy_app)

    captured: dict[str, Any] = {}

    async def receive_noop() -> dict[str, Any]:
        return {"type": "http.disconnect"}  # pragma: no cover

    async def capturing_send(message: Any) -> None:
        if message["type"] == "http.response.start":
            captured["status"] = message["status"]
            captured["headers"] = [
                (
                    n if isinstance(n, str) else n.decode(),
                    v if isinstance(v, str) else v.decode(),
                )
                for n, v in message.get("headers", [])
            ]

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/health",
        "raw_path": b"/health",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"testserver"),
            (b"x-correlation-id", str(uuid.uuid4()).encode()),
            (b"x-correlation-id", str(uuid.uuid4()).encode()),
        ],
    }

    await mw(scope, receive_noop, capturing_send)

    assert captured["status"] == 400
    cid_values = [
        v for n, v in captured["headers"]
        if n.lower() == "x-correlation-id"
    ]
    assert len(cid_values) == 1, f"expected one cid header, got {cid_values}"
    assert _UUID4_RE.match(cid_values[0])


# ---------------------------------------------------------------------------
# exactly-one header
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_response_has_exactly_one_correlation_header(
    client: AsyncClient,
) -> None:
    response = await client.get("/health")
    assert len(response.headers.get_list(CORRELATION_HEADER)) == 1


# ---------------------------------------------------------------------------
# context visible inside endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_visible_inside_endpoint(client: AsyncClient) -> None:
    """Inject a route that exposes the bound context to prove propagation."""
    from fastapi.responses import JSONResponse

    @app.get("/__test_correlation_ctx")
    async def _ctx_probe() -> JSONResponse:
        return JSONResponse({"correlation_id": get_correlation_id()})

    try:
        cid = str(uuid.uuid4())
        response = await client.get(
            "/__test_correlation_ctx", headers={CORRELATION_HEADER: cid}
        )
        assert response.json()["correlation_id"] == cid
    finally:
        for route in list(app.routes):
            if getattr(route, "path", None) == "/__test_correlation_ctx":
                app.routes.remove(route)


# ---------------------------------------------------------------------------
# structured log contains correlation_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_structlog_output_contains_correlation_id(
    client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A log emitted inside a request with context bound must carry correlation_id.

    The structlog pipeline includes merge_contextvars which adds the
    correlation_id field.  We explicitly configure logging here so that the
    structlog handler is wired up and caplog can capture the record.
    """
    import logging

    from app.core.logging import configure_logging, get_logger

    logger = get_logger("test.correlation")

    @app.get("/__test_correlation_log")
    async def _log_probe() -> dict[str, str]:
        logger.info("correlation-log-probe")
        return {"ok": "true"}

    try:
        configure_logging(level="INFO")
        with caplog.at_level(logging.INFO):
            response = await client.get("/__test_correlation_log")
        assert response.status_code == 200

        found = False
        for record in caplog.records:
            if "correlation-log-probe" in record.getMessage():
                msg = record.getMessage()
                if "correlation_id" in msg:
                    found = True
                    break
        assert found, (
            "structured log record missing correlation_id "
            f"(records seen: {[r.getMessage() for r in caplog.records]})"
        )
    finally:
        for route in list(app.routes):
            if getattr(route, "path", None) == "/__test_correlation_log":
                app.routes.remove(route)


# ---------------------------------------------------------------------------
# context cleared after request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_cleared_after_request(client: AsyncClient) -> None:
    """After the request, get_correlation_id must be None in the current task."""
    await client.get("/health")
    assert get_correlation_id() is None


# ---------------------------------------------------------------------------
# outer context restored after request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_outer_context_restored_after_request(client: AsyncClient) -> None:
    """A pre-bound outer correlation ID must be restored after the request."""
    outer_cid = str(uuid.uuid4())
    bind_correlation_id(outer_cid)
    try:
        request_cid = str(uuid.uuid4())
        response = await client.get(
            "/health", headers={CORRELATION_HEADER: request_cid}
        )
        # During the request, endpoint sees request_cid
        assert response.status_code == 200
        assert _cid(response) == request_cid
        # After the request, outer context is restored
        assert get_correlation_id() == outer_cid
    finally:
        from app.core.context import clear_correlation_id

        clear_correlation_id()


@pytest.mark.asyncio
async def test_outer_context_restored_on_exception(
    client: AsyncClient,
) -> None:
    """If the endpoint raises HTTPException, outer context is still restored.

    HTTPException is caught by Starlette's ExceptionMiddleware which emits
    a proper ASGI response flowing through our middleware — so the header IS
    present.  Non-HTTPException (e.g. RuntimeError) propagates to
    ServerErrorMiddleware which uses the outer send callable directly,
    bypassing our middleware's header injection.  See test_500_document_contract.
    """
    from fastapi import HTTPException

    outer_cid = str(uuid.uuid4())
    bind_correlation_id(outer_cid)

    @app.get("/__test_correlation_http_exc")
    async def _raise_probe() -> Any:
        raise HTTPException(status_code=500, detail="intentional")

    try:
        request_cid = str(uuid.uuid4())
        response = await client.get(
            "/__test_correlation_http_exc",
            headers={CORRELATION_HEADER: request_cid},
        )
        # HTTPException flows through ExceptionMiddleware → header present
        assert response.status_code == 500
        assert _UUID4_RE.match(_cid(response))
        # Outer context restored after exception
        assert get_correlation_id() == outer_cid
    finally:
        from app.core.context import clear_correlation_id

        clear_correlation_id()
        for route in list(app.routes):
            if getattr(route, "path", None) == "/__test_correlation_http_exc":
                app.routes.remove(route)


# ---------------------------------------------------------------------------
# sequential isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sequential_requests_do_not_leak(client: AsyncClient) -> None:
    """Second request must not see the first request's correlation ID."""
    cid_first = str(uuid.uuid4())
    response_first = await client.get(
        "/health", headers={CORRELATION_HEADER: cid_first}
    )
    assert _cid(response_first) == cid_first

    cid_second = str(uuid.uuid4())
    response_second = await client.get(
        "/health", headers={CORRELATION_HEADER: cid_second}
    )
    assert _cid(response_second) == cid_second

    response_third = await client.get("/health")
    third_cid = _cid(response_third)
    assert _UUID4_RE.match(third_cid)
    assert third_cid != cid_first
    assert third_cid != cid_second


# ---------------------------------------------------------------------------
# concurrent isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_requests_isolated(client: AsyncClient) -> None:
    """In-flight requests must see their own correlation ID."""
    cid_a = str(uuid.uuid4())
    cid_b = str(uuid.uuid4())

    async def _hit(cid: str) -> str:
        response = await client.get(
            "/health", headers={CORRELATION_HEADER: cid}
        )
        return _cid(response)

    results = await asyncio.gather(_hit(cid_a), _hit(cid_b))
    assert set(results) == {cid_a, cid_b}


# ---------------------------------------------------------------------------
# existing endpoints still pass
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_endpoint_still_works(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_root_endpoint_still_works(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "ForgeMind AI Operations"


# ---------------------------------------------------------------------------
# error paths have correlation header
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_404_has_correlation_header(client: AsyncClient) -> None:
    """A FastAPI-generated 404 must still get the X-Correlation-ID header."""
    response = await client.get("/nonexistent-route")
    assert response.status_code == 404
    value = _cid(response)
    assert _UUID4_RE.match(value)


@pytest.mark.asyncio
async def test_http_exception_500_has_correlation_header(
    client: AsyncClient,
) -> None:
    """HTTPException(500) flows through ExceptionMiddleware → header present.

    This is the standard FastAPI pattern for raising a 500 from a route.
    ExceptionMiddleware catches HTTPException and emits a proper ASGI
    response that flows through our middleware's header injection.
    """
    from fastapi import HTTPException

    @app.get("/__test_correlation_http_exc_500")
    async def _error_probe() -> Any:
        raise HTTPException(status_code=500, detail="intentional")

    try:
        response = await client.get("/__test_correlation_http_exc_500")
        assert response.status_code == 500
        assert _UUID4_RE.match(_cid(response))
    finally:
        for route in list(app.routes):
            if getattr(route, "path", None) == "/__test_correlation_http_exc_500":
                app.routes.remove(route)


@pytest.mark.asyncio
async def test_unhandled_exception_bypasses_header() -> None:
    """Raw exceptions reaching ServerErrorMiddleware do NOT get our header.

    Documented contract: Starlette's ServerErrorMiddleware uses the outer
    ``send`` callable (the one passed to it from above) when emitting its
    500 response after a non-HTTPException.  This bypasses our middleware's
    header-injection sending wrapper because the exception has already
    propagated past our ``await self.app(...)`` call.

    This is inherent ASGI middleware behaviour, not a bug to fix by
    swallowing broad exceptions.  In production, a real HTTP server
    (Uvicorn) handles this case with its own 500 response that also
    lacks application-level headers.

    This test invokes the middleware directly via ASGI harness.
    """
    from app.api.middleware.correlation import CorrelationIdMiddleware

    async def raising_app(scope: Scope, receive: Receive, send: Send) -> None:  # noqa: ARG001
        raise RuntimeError("unhandled")

    mw = CorrelationIdMiddleware(raising_app)

    captured_messages: list[dict[str, Any]] = []

    async def receive_noop() -> dict[str, Any]:
        return {"type": "http.disconnect"}  # pragma: no cover

    async def capturing_send(message: Any) -> None:
        captured_messages.append(message)

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/health",
        "raw_path": b"/health",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver")],
    }

    with pytest.raises(RuntimeError, match="unhandled"):
        await mw(scope, receive_noop, capturing_send)

    # No response.start was sent — the exception escaped before any ASGI
    # response could be produced.  This is the expected behaviour; our
    # middleware cannot retroactively inject a header.
    assert not any(
        m.get("type") == "http.response.start" for m in captured_messages
    )


# ---------------------------------------------------------------------------
# non-HTTP scope pass-through
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lifespan_scope_passes_through() -> None:
    """Lifespan scopes bypass correlation logic entirely."""
    messages_received: list[str] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        messages_received.append("inner_called")
        msg = await receive()
        messages_received.append(msg["type"])

    scope: Scope = {
        "type": "lifespan",
        "asgi": {"version": "3.0"},
    }

    from app.api.middleware.correlation import CorrelationIdMiddleware

    mw = CorrelationIdMiddleware(inner)

    async def receive_lifespan() -> dict[str, Any]:
        return {"type": "lifespan.startup"}

    async def send_noop(message: Any) -> None:
        pass

    await mw(scope, receive_lifespan, send_noop)
    assert messages_received == ["inner_called", "lifespan.startup"]


@pytest.mark.asyncio
async def test_websocket_scope_passes_through() -> None:
    """WebSocket scopes bypass correlation logic entirely."""
    messages_received: list[str] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        messages_received.append("inner_called")

    scope: Scope = {
        "type": "websocket",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "scheme": "ws",
        "path": "/ws",
        "raw_path": b"/ws",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver")],
    }

    from app.api.middleware.correlation import CorrelationIdMiddleware

    mw = CorrelationIdMiddleware(inner)

    async def receive_ws() -> dict[str, Any]:
        return {"type": "websocket.disconnect"}

    async def send_noop(message: Any) -> None:
        pass

    await mw(scope, receive_ws, send_noop)
    assert messages_received == ["inner_called"]
    # No correlation context should be bound
    assert get_correlation_id() is None


# ---------------------------------------------------------------------------
# response header ownership (endpoint sets its own correlation header)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_endpoint_correlation_header_replaced(
    client: AsyncClient,
) -> None:
    """If an endpoint sets its own X-Correlation-ID, middleware replaces it."""
    from starlette.responses import JSONResponse as StarletteJSONResponse

    @app.get("/__test_correlation_override")
    async def _override_probe() -> StarletteJSONResponse:
        return StarletteJSONResponse(
            content={"ok": True},
            headers={
                CORRELATION_HEADER: "deadbeef-dead-dead-dead-deaddeadbeef",
                "x-custom-header": "preserve-me",
            },
        )

    try:
        response = await client.get("/__test_correlation_override")
        # Exactly one correlation header
        cid = _cid(response)
        assert _UUID4_RE.match(cid)
        # Custom header preserved
        assert response.headers.get("x-custom-header") == "preserve-me"
    finally:
        for route in list(app.routes):
            if getattr(route, "path", None) == "/__test_correlation_override":
                app.routes.remove(route)
