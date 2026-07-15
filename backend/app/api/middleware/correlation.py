"""Pure ASGI correlation-ID middleware.

Uses raw ASGI primitives instead of Starlette's BaseHTTPMiddleware to
avoid task-scope issues with ContextVar propagation.  Every request gets
a canonical UUID v4 correlation ID that is bound to structlog's
contextvars for the duration of the request and cleared afterwards.

Header contract:
- Response always carries exactly one ``X-Correlation-ID`` header.
- Missing header  → new UUID v4 generated.
- Valid UUID v4   → normalised to canonical lowercase form.
- Invalid value   → HTTP 400, server-generated correlation ID on response.
- Duplicate incoming headers → same HTTP 400 contract.
"""

from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.context import correlation_context
from app.core.correlation import (
    CORRELATION_HEADER,
    InvalidCorrelationIdError,
    generate_correlation_id,
    validate_correlation_id,
)

_HEADER_LOWER = CORRELATION_HEADER.lower()
_HEADER_LOWER_BYTES = _HEADER_LOWER.encode()


def _extract_all_client_correlation_ids(scope: Scope) -> list[str]:
    """Return all values of the correlation header (may be zero or more)."""
    values: list[str] = []
    for header_name, header_value in scope.get("headers", []):
        if header_name == _HEADER_LOWER_BYTES:
            values.append(header_value.decode("latin-1"))
    return values


async def _send_invalid_id_response(
    scope: Scope,
    receive: Receive,
    send: Send,
) -> None:
    """Reject the request with HTTP 400 and a server-generated correlation ID."""
    error_id = generate_correlation_id()
    response = JSONResponse(
        status_code=400,
        content={
            "error": "invalid_correlation_id",
            "detail": "X-Correlation-ID is not a valid UUID v4",
            "correlation_id": error_id,
        },
        headers={_HEADER_LOWER: error_id},
    )
    await response(scope, receive, send)


class CorrelationIdMiddleware:
    """ASGI middleware that ensures every HTTP request has a correlation ID.

    Uses a pure ASGI ``__call__(scope, receive, send)`` interface rather than
    ``BaseHTTPMiddleware`` to guarantee ContextVar propagation through the
    request lifetime.  Only ``scope["type"] == "http"`` scopes are processed;
    all other scope types (lifespan, websocket) pass through unchanged.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Initialise the middleware wrapping an ASGI app."""
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        """Process a single ASGI scope."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # ---- resolve correlation ID -------------------------------------
        client_ids = _extract_all_client_correlation_ids(scope)

        if len(client_ids) == 0:
            # No header: generate fresh UUID v4.
            with correlation_context() as canonical_id:
                await self._dispatch_with_header(canonical_id, scope, receive, send)
            return

        if len(client_ids) > 1:
            # Duplicate correlation headers: reject.
            await _send_invalid_id_response(scope, receive, send)
            return

        # Exactly one header: validate and normalise.
        # Treat empty or whitespace-only values as invalid.
        header_value = client_ids[0].strip()
        if not header_value:
            await _send_invalid_id_response(scope, receive, send)
            return

        try:
            canonical_id = validate_correlation_id(header_value)
        except InvalidCorrelationIdError:
            await _send_invalid_id_response(scope, receive, send)
            return

        # Valid: bind and dispatch.
        with correlation_context(canonical_id):
            await self._dispatch_with_header(canonical_id, scope, receive, send)

    async def _dispatch_with_header(
        self,
        canonical_id: str,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Call the wrapped app, injecting/normalising the response header."""
        value_bytes = canonical_id.encode()

        async def sending(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers: list[tuple[bytes, bytes]] = list(
                    message.get("headers", [])
                )
                # Strip any pre-existing correlation headers (case-insensitive).
                headers = [
                    (name, value)
                    for name, value in headers
                    if name.lower() != _HEADER_LOWER_BYTES
                ]
                # Prepend our canonical header.
                headers.insert(0, (_HEADER_LOWER_BYTES, value_bytes))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, sending)
