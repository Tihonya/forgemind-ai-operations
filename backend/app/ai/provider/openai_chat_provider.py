"""OpenAI-compatible chat/reasoning provider adapter.

Wraps the OpenAI async client for chat completions. Reuses the existing
Settings fields (openai_api_key, openai_api_base, openai_chat_model,
llm_timeout_seconds, llm_max_retries, ai_rate_limit_per_minute).

SDK retries are disabled (max_retries=0) so that transient errors surface
as TransientChatProviderError for the caller to handle. Workflow-level
outage retry is owned by WP-REC-03D; this adapter performs a single
attempt and classifies failures deterministically.

Rate limiting is per OpenAIChatProvider instance: a sliding-window
limiter enforces ``rate_limit_per_minute`` calls per minute.  Limiter
state is stored in-process and is not shared between provider
instances, processes, or workers.  This is NOT a distributed limiter —
multi-process deployments (e.g., multiple Uvicorn workers) each get
their own independent window.  Distributed rate limiting is out of
scope for WP-REC-03A.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any, cast

from openai import APIStatusError, AsyncOpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from app.core.logging import get_logger

from .chat_provider import ChatProvider, ChatResult
from .exceptions import (
    ChatProviderConfigurationError,
    ChatProviderError,
    PermanentChatProviderError,
    TransientChatProviderError,
)

_logger = get_logger(__name__)

# OpenAI SDK exception type names classified as transient.
_TRANSIENT_TYPES: tuple[str, ...] = (
    "APIConnectionError",
    "APITimeoutError",
    "RateLimitError",
    "InternalServerError",
)

# OpenAI SDK exception type names classified as permanent.
_PERMANENT_TYPES: tuple[str, ...] = (
    "AuthenticationError",
    "PermissionDeniedError",
    "BadRequestError",
    "UnprocessableEntityError",
    "NotFoundError",
    "ConflictError",
)


class _SlidingWindowRateLimiter:
    """Per-instance sliding-window rate limiter.

    Allows at most ``max_calls`` calls within any 60-second window.
    Uses a deque of monotonic timestamps pruned on each acquire.

    Scope: the limiter state lives in-process and is owned by a single
    ``OpenAIChatProvider`` instance.  It is NOT shared between provider
    instances, processes, or workers.  Each provider instance gets its
    own limiter.

    Cancellation-safe: if the asyncio.sleep is cancelled, the timestamp
    is NOT consumed — the caller's CancelledError propagates without
    counting against the rate limit.
    """

    def __init__(
        self,
        max_calls: int,
        clock: Any = None,
    ) -> None:
        if max_calls <= 0:
            raise ValueError(f"max_calls must be positive, got {max_calls}")
        self._max_calls = max_calls
        self._clock = clock if clock is not None else time.monotonic
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Block until a call slot is available, then record it.

        Raises:
            asyncio.CancelledError: if the wait is cancelled. The
                timestamp is NOT consumed on cancellation.
        """
        while True:
            async with self._lock:
                now = self._clock()
                window_start = now - 60.0
                # Prune expired timestamps.
                while self._timestamps and self._timestamps[0] <= window_start:
                    self._timestamps.popleft()
                if len(self._timestamps) < self._max_calls:
                    self._timestamps.append(now)
                    return
                # Calculate how long to wait until the oldest call expires.
                wait_seconds = self._timestamps[0] - window_start

            # Wait outside the lock so other coroutines are not blocked
            # from checking. If cancelled here, no timestamp was consumed.
            await asyncio.sleep(max(wait_seconds, 0.001))


class OpenAIChatProvider(ChatProvider):
    """OpenAI-compatible chat/reasoning provider.

    The provider accepts an injected ``client`` for testing. When no client
    is provided, a real :class:`AsyncOpenAI` instance is created from the
    supplied configuration.

    SDK retries are always disabled (max_retries=0) regardless of
    ``llm_max_retries``. The ``llm_max_retries`` setting is owned by the
    workflow-level outage handler (WP-REC-03D) and is not used here to
    avoid double retry.

    Rate limiting is process-local (see :class:`_SlidingWindowRateLimiter`).
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str | None = None,
        timeout_seconds: int = 30,
        rate_limit_per_minute: int = 10,
        client: AsyncOpenAI | None = None,
        rate_limiter: _SlidingWindowRateLimiter | None = None,
        clock: Any = None,
    ) -> None:
        if not api_key:
            raise ChatProviderConfigurationError("api_key must not be empty")
        if not model:
            raise ChatProviderConfigurationError("model must not be empty")
        if timeout_seconds <= 0:
            raise ChatProviderConfigurationError(
                f"timeout_seconds must be positive, got {timeout_seconds}"
            )
        if rate_limit_per_minute <= 0:
            raise ChatProviderConfigurationError(
                f"rate_limit_per_minute must be positive, got {rate_limit_per_minute}"
            )

        self._model = model
        self._timeout_seconds = timeout_seconds
        self._rate_limit_per_minute = rate_limit_per_minute

        if rate_limiter is not None:
            self._rate_limiter = rate_limiter
        else:
            self._rate_limiter = _SlidingWindowRateLimiter(
                max_calls=rate_limit_per_minute,
                clock=clock,
            )

        if client is not None:
            self._client: AsyncOpenAI = client
        else:
            client_kwargs: dict[str, Any] = {
                "api_key": api_key,
                "timeout": float(timeout_seconds),
                "max_retries": 0,
            }
            if base_url is not None:
                client_kwargs["base_url"] = base_url
            self._client = AsyncOpenAI(**client_kwargs)

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

        # Rate-limit before any API call. Cancellation here propagates
        # without consuming a slot.
        await self._rate_limiter.acquire()

        response_format = self._build_response_format(schema)
        start = time.monotonic()

        system_msg: ChatCompletionSystemMessageParam = {
            "role": "system",
            "content": "You are a supply risk intelligence assistant.",
        }
        user_msg: ChatCompletionUserMessageParam = {
            "role": "user",
            "content": prompt,
        }
        messages: list[ChatCompletionMessageParam] = [system_msg, user_msg]

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                response_format=cast(Any, response_format),
            )
        except Exception as exc:
            latency = time.monotonic() - start
            self._log_error(correlation_id, run_id, exc, latency)
            raise self._classify_error(exc) from exc

        latency_ms = (time.monotonic() - start) * 1000.0

        # Response-processing failures must also be classified and logged.
        try:
            return self._build_result(response, latency_ms, correlation_id, run_id)
        except PermanentChatProviderError as exc:
            self._log_error(correlation_id, run_id, exc, latency_ms)
            raise

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_response_format(
        schema: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Build the response_format argument for structured output.

        Returns a json_schema response_format dict when a schema is provided,
        or None when no schema is given. The provider does not validate the
        response against the schema — that is WP-REC-03C's responsibility.
        """
        if schema is None:
            return None
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "structured_output",
                "schema": schema,
                "strict": True,
            },
        }

    def _classify_error(self, exc: Exception) -> ChatProviderError:
        """Map an SDK exception to the appropriate ChatProviderError subclass.

        Classification is deterministic:
        - Known transient SDK errors -> TransientChatProviderError
        - Known permanent SDK errors -> PermanentChatProviderError
        - APIStatusError: 5xx -> transient, 4xx -> permanent
        - Unrecognised errors -> permanent by default (safe)

        Error messages never contain the original exception's message
        (which may include response content), only the exception type
        name and status code.
        """
        exc_name = type(exc).__name__
        if exc_name in _TRANSIENT_TYPES:
            return TransientChatProviderError(
                f"Transient OpenAI error ({exc_name})"
            )
        if exc_name in _PERMANENT_TYPES:
            return PermanentChatProviderError(
                f"Permanent OpenAI error ({exc_name})"
            )
        if isinstance(exc, APIStatusError):
            if exc.status_code >= 500:
                return TransientChatProviderError(
                    f"Transient OpenAI error (5xx {exc.status_code})"
                )
            return PermanentChatProviderError(
                f"Permanent OpenAI error (4xx {exc.status_code})"
            )
        # Unrecognised error — permanent by default to prevent retry storms.
        return PermanentChatProviderError(
            f"OpenAI chat API failed for model={self._model!r}: {exc_name}"
        )

    def _build_result(
        self,
        response: Any,
        latency_ms: float,
        correlation_id: str,
        run_id: str,
    ) -> ChatResult:
        """Build a ChatResult from an OpenAI ChatCompletion response.

        Validates that the response contains at least one choice with
        textual content. Token usage is extracted when available.
        """
        choices = getattr(response, "choices", None)
        if not choices:
            raise PermanentChatProviderError(
                f"OpenAI chat API returned no choices for model={self._model!r}"
            )

        first_choice = choices[0]
        message = getattr(first_choice, "message", None)
        if message is None:
            raise PermanentChatProviderError(
                "OpenAI chat API returned no message in first choice"
            )

        content = getattr(message, "content", None)
        if content is None:
            content = ""

        finish_reason = str(getattr(first_choice, "finish_reason", "") or "")

        usage_dict: dict[str, int] = {}
        usage = getattr(response, "usage", None)
        if usage is not None:
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                val = getattr(usage, key, None)
                if isinstance(val, int):
                    usage_dict[key] = val

        safe_metadata: dict[str, Any] = {
            "latency_ms": round(latency_ms, 3),
            "response_id": getattr(response, "id", ""),
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
            usage=usage_dict,
        )

        return ChatResult(
            content=content,
            model=self._model,
            finish_reason=finish_reason,
            usage=usage_dict,
            metadata=safe_metadata,
        )

    # ------------------------------------------------------------------
    # Logging — safe metadata only, never API keys or response content
    # ------------------------------------------------------------------

    def _log_success(
        self,
        *,
        correlation_id: str,
        run_id: str,
        model: str,
        latency_ms: float,
        usage: dict[str, int],
    ) -> None:
        log_kwargs: dict[str, Any] = {
            "model": model,
            "latency_ms": round(latency_ms, 3),
            "status": "success",
        }
        if usage:
            log_kwargs["usage"] = usage
        if correlation_id:
            log_kwargs["correlation_id"] = correlation_id
        if run_id:
            log_kwargs["run_id"] = run_id
        _logger.info("chat_provider.complete", **log_kwargs)

    def _log_error(
        self,
        correlation_id: str,
        run_id: str,
        exc: Exception,
        latency_ms: float,
    ) -> None:
        """Log a sanitized error record.

        Never logs the exception message (which may contain response
        content), only the exception type name and error classification.
        """
        log_kwargs: dict[str, Any] = {
            "model": self._model,
            "latency_ms": round(latency_ms, 3),
            "status": "error",
            "error_type": type(exc).__name__,
        }
        if correlation_id:
            log_kwargs["correlation_id"] = correlation_id
        if run_id:
            log_kwargs["run_id"] = run_id
        _logger.warning("chat_provider.complete", **log_kwargs)
