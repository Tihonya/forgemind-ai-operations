"""Deterministic fake chat provider for testing.

Produces identical responses for identical prompts without any network
calls. Uses SHA-256 hashing (not Python's built-in hash) to ensure
cross-process determinism. The response content is a deterministic JSON-
shaped string derived from the prompt, allowing downstream validation
tests to exercise a realistic-looking payload.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from app.core.logging import get_logger

from .chat_provider import ChatProvider, ChatResult
from .exceptions import ChatProviderConfigurationError

_logger = get_logger(__name__)


class FakeChatProvider(ChatProvider):
    """Deterministic fake chat provider for testing.

    Produces a deterministic JSON response string derived from the prompt
    via SHA-256 hashing. The response always has a ``prompt_hash`` field
    so that callers can verify determinism. No network calls are made.

    The provider accepts an optional ``clock`` callable for injecting a
    deterministic time source in tests. When no clock is provided,
    :func:`time.monotonic` is used.
    """

    def __init__(
        self,
        *,
        model: str = "fake-chat-model",
        clock: Any = None,
    ) -> None:
        if not model:
            raise ChatProviderConfigurationError("model must not be empty")
        self._model = model
        self._clock = clock if clock is not None else time.monotonic

    async def complete(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> ChatResult:
        if not prompt:
            raise ChatProviderConfigurationError("prompt must not be empty")

        correlation_id = ""
        run_id = ""
        if context is not None:
            correlation_id = str(context.get("correlation_id", ""))
            run_id = str(context.get("run_id", ""))

        start = self._clock()

        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

        response_body: dict[str, Any] = {
            "prompt_hash": prompt_hash,
            "model": self._model,
            "schema_requested": schema is not None,
        }

        content = json.dumps(response_body, sort_keys=True)
        latency_ms = (self._clock() - start) * 1000.0

        safe_metadata: dict[str, Any] = {
            "latency_ms": round(latency_ms, 3),
            "provider": "fake",
        }
        if correlation_id:
            safe_metadata["correlation_id"] = correlation_id
        if run_id:
            safe_metadata["run_id"] = run_id

        self._log_success(
            correlation_id=correlation_id,
            run_id=run_id,
            model=self._model,
            latency_ms=latency_ms,
        )

        return ChatResult(
            content=content,
            model=self._model,
            finish_reason="stop",
            usage={},
            metadata=safe_metadata,
        )

    def _log_success(
        self,
        *,
        correlation_id: str,
        run_id: str,
        model: str,
        latency_ms: float,
    ) -> None:
        log_kwargs: dict[str, Any] = {
            "model": model,
            "latency_ms": round(latency_ms, 3),
            "status": "success",
            "provider": "fake",
        }
        if correlation_id:
            log_kwargs["correlation_id"] = correlation_id
        if run_id:
            log_kwargs["run_id"] = run_id
        _logger.info("chat_provider.complete", **log_kwargs)
