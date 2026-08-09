"""RetryingChatProvider — automatic provider retry/outage handler (WP-REC-03D).

Wraps a delegate :class:`ChatProvider` with bounded exponential backoff
retry for :class:`TransientChatProviderError`.  This is the **sole
application-level retry owner** (DEC-013 responsibility boundaries).

Design contract (WP-REC-03D):

- **Sole retry layer**: the OpenAI SDK has ``max_retries=0`` (disabled
  in ``OpenAIChatProvider``).  The workflow engine calls
  ``complete()`` once.  This wrapper performs all retries.  No nested
  retry multiplication.
- **Retry only transient errors**: :class:`PermanentChatProviderError`,
  :class:`ChatProviderConfigurationError`, unknown exceptions, and
  :class:`asyncio.CancelledError` are never retried.
- **Bounded**: retry count is governed by :class:`RetryPolicy` using
  ``settings.llm_max_retries`` (retries after the initial attempt;
  total calls = ``1 + max_retries``).
- **Safe observability**: logs contain only safe bounded fields
  (correlation_id, run_id, attempt_number, total_allowed_attempts,
  error_type, backoff_delay, outcome).  Never logs exception messages,
  response bodies, API keys, prompts, or context values beyond
  correlation_id and run_id.
- **Success metadata**: on success, retry metadata (``retry_count``,
  ``attempt_history``) is added to ``ChatResult.metadata`` and flows
  through the existing engine path into
  ``WorkflowStep.step_metadata``.
- **Exhaustion**: after retries are exhausted, a
  :class:`TransientChatProviderError` is re-raised.  The existing
  engine handler catches it and transitions the workflow to
  ``FAILED_PROVIDER`` with ``error_code=PROVIDER_TRANSIENT`` and
  ``error_detail=TransientChatProviderError`` (type name only).
- **No engine modification**: the wrapper is transparent to the
  engine.  ``ChatProvider.complete()`` signature is unchanged.
- **Cancellation-safe**: if :class:`asyncio.CancelledError` is raised
  during the provider call or the backoff sleep, it propagates
  immediately.  No further retry attempts are made.

Import graph (acyclic):

    app.ai.provider.factory
        → app.ai.workflow.outage_handler
            → app.ai.provider.chat_provider  (leaf)
            → app.ai.provider.exceptions     (leaf)
            → app.ai.workflow.retry_policy   (leaf)
            → app.core.logging               (leaf)

No circular dependency.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.ai.provider.chat_provider import ChatProvider, ChatResult
from app.ai.provider.exceptions import TransientChatProviderError
from app.ai.workflow.retry_policy import AsyncSleeper, RetryPolicy
from app.core.logging import get_logger

_logger = get_logger(__name__)

# Wrapper-controlled metadata keys.  These are added to
# ``ChatResult.metadata`` on success.  If the delegate already supplies
# the same keys, the wrapper's values take precedence (overwrite).
# This behavior is deterministic and covered by tests.
_META_RETRY_COUNT = "retry_count"
_META_ATTEMPT_HISTORY = "attempt_history"

# Safe fields recorded per attempt in the attempt history.
# Only bounded, deterministic values — never raw exception messages.
_SAFE_ATTEMPT_FIELDS: frozenset[str] = frozenset({
    "attempt_number",
    "outcome",
    "error_type",
    "backoff_delay_seconds",
})


class RetryingChatProvider(ChatProvider):
    """ChatProvider wrapper that retries transient failures.

    Wraps a delegate :class:`ChatProvider` and retries
    :class:`TransientChatProviderError` according to a
    :class:`RetryPolicy`.  All other exceptions propagate immediately
    without retry.

    The wrapper is transparent to the engine: ``complete()`` has the
    same signature and the same return type.  On success, retry
    metadata is added to ``ChatResult.metadata``.

    Args:
        delegate: The underlying :class:`ChatProvider` to wrap.
        policy: Retry policy governing retry count and backoff.
        sleeper: Optional async sleeper for deterministic tests.
            Defaults to :func:`asyncio.sleep`.
    """

    def __init__(
        self,
        *,
        delegate: ChatProvider,
        policy: RetryPolicy,
        sleeper: AsyncSleeper | None = None,
    ) -> None:
        self._delegate = delegate
        self._policy = policy
        self._sleeper: AsyncSleeper = sleeper if sleeper is not None else asyncio.sleep

    async def complete(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> ChatResult:
        """Generate a chat completion with automatic transient retry.

        Calls ``delegate.complete()`` up to ``policy.total_allowed_attempts``
        times.  Only :class:`TransientChatProviderError` is retried.

        Args:
            prompt: The user prompt text.  Passed unchanged to the
                delegate.
            schema: Optional JSON Schema dict.  Passed unchanged.
            context: Optional metadata dict.  ``correlation_id`` and
                ``run_id`` are read for logging.  Passed unchanged to
                the delegate.

        Returns:
            The delegate's :class:`ChatResult` with retry metadata
            added to ``.metadata``.

        Raises:
            TransientChatProviderError: After all retries are
                exhausted.  The existing engine handler catches this
                and transitions to ``FAILED_PROVIDER``.
            PermanentChatProviderError: Immediately, no retry.
            ChatProviderConfigurationError: Immediately, no retry.
            ChatProviderError: Other subtypes, immediately, no retry.
            asyncio.CancelledError: Immediately, no retry.
        """
        # Extract safe fields from context for logging.
        # Only correlation_id and run_id are read.  All other context
        # values are ignored for logging purposes.
        correlation_id = ""
        run_id = ""
        if context is not None:
            correlation_id = str(context.get("correlation_id", ""))
            run_id = str(context.get("run_id", ""))

        total_allowed = self._policy.total_allowed_attempts
        attempt_history: list[dict[str, Any]] = []
        retry_count = 0

        # 1-based attempt numbering.
        for attempt_number in range(1, total_allowed + 1):
            try:
                result = await self._delegate.complete(
                    prompt=prompt,
                    schema=schema,
                    context=context,
                )
            except TransientChatProviderError as exc:
                # Determine whether a retry is allowed.
                if not self._policy.should_retry(attempt_number):
                    # Exhausted — log and re-raise.
                    attempt_history.append(self._safe_attempt_record(
                        attempt_number=attempt_number,
                        outcome="exhausted",
                        error_type=type(exc).__name__,
                        backoff_delay_seconds=0.0,
                    ))
                    self._log_outcome(
                        correlation_id=correlation_id,
                        run_id=run_id,
                        attempt_number=attempt_number,
                        total_allowed_attempts=total_allowed,
                        retry_count=retry_count,
                        error_type=type(exc).__name__,
                        backoff_delay_seconds=0.0,
                        outcome="exhausted",
                    )
                    raise

                # Retry allowed — compute backoff, log, sleep, continue.
                delay = self._policy.compute_delay(attempt_number)
                attempt_history.append(self._safe_attempt_record(
                    attempt_number=attempt_number,
                    outcome="retrying",
                    error_type=type(exc).__name__,
                    backoff_delay_seconds=delay,
                ))
                self._log_outcome(
                    correlation_id=correlation_id,
                    run_id=run_id,
                    attempt_number=attempt_number,
                    total_allowed_attempts=total_allowed,
                    retry_count=retry_count,
                    error_type=type(exc).__name__,
                    backoff_delay_seconds=delay,
                    outcome="retrying",
                )
                retry_count += 1
                # Sleep before the next attempt.
                # CancelledError propagates immediately if raised here.
                await self._sleeper(delay)
                continue

            # Success — add retry metadata to the result.
            self._log_outcome(
                correlation_id=correlation_id,
                run_id=run_id,
                attempt_number=attempt_number,
                total_allowed_attempts=total_allowed,
                retry_count=retry_count,
                error_type="",
                backoff_delay_seconds=0.0,
                outcome="success",
            )

            return self._enrich_result(
                result=result,
                retry_count=retry_count,
                attempt_history=attempt_history,
            )

        # This line is unreachable: the loop either returns on success
        # or raises on exhaustion.  It exists for type-checker safety.
        raise TransientChatProviderError(
            "Retry loop exited without success or explicit exhaustion"
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_attempt_record(
        *,
        attempt_number: int,
        outcome: str,
        error_type: str,
        backoff_delay_seconds: float,
    ) -> dict[str, Any]:
        """Build a safe per-attempt record for the attempt history.

        Only bounded, deterministic fields are included.  Never
        contains exception messages, response bodies, or context values.
        """
        return {
            "attempt_number": attempt_number,
            "outcome": outcome,
            "error_type": error_type,
            "backoff_delay_seconds": backoff_delay_seconds,
        }

    @staticmethod
    def _log_outcome(
        *,
        correlation_id: str,
        run_id: str,
        attempt_number: int,
        total_allowed_attempts: int,
        retry_count: int,
        error_type: str,
        backoff_delay_seconds: float,
        outcome: str,
    ) -> None:
        """Log a structured retry outcome record.

        Only safe bounded fields are logged.  Never logs exception
        messages, response bodies, API keys, prompts, context values,
        or stack traces.
        """
        log_kwargs: dict[str, Any] = {
            "attempt_number": attempt_number,
            "total_allowed_attempts": total_allowed_attempts,
            "retry_count": retry_count,
            "outcome": outcome,
        }
        if error_type:
            log_kwargs["error_type"] = error_type
        if backoff_delay_seconds > 0:
            log_kwargs["backoff_delay_seconds"] = backoff_delay_seconds
        if correlation_id:
            log_kwargs["correlation_id"] = correlation_id
        if run_id:
            log_kwargs["run_id"] = run_id
        _logger.info("chat_provider.retry.attempt", **log_kwargs)

    @staticmethod
    def _enrich_result(
        *,
        result: ChatResult,
        retry_count: int,
        attempt_history: list[dict[str, Any]],
    ) -> ChatResult:
        """Add retry metadata to a successful ChatResult.

        Creates a new ``ChatResult`` with the delegate's data plus
        wrapper-controlled metadata keys.  The delegate's original
        metadata is preserved (not mutated).  Wrapper-controlled keys
        (``retry_count``, ``attempt_history``) take precedence over any
        same-named keys the delegate supplied.

        Args:
            result: The delegate's successful ChatResult.
            retry_count: Number of retries performed (0 = no retries).
            attempt_history: Safe per-attempt records.

        Returns:
            A new ChatResult with enriched metadata.
        """
        # Copy the delegate's metadata to avoid mutation.
        enriched_metadata: dict[str, Any] = dict(result.metadata)
        # Wrapper-controlled keys take precedence.
        enriched_metadata[_META_RETRY_COUNT] = retry_count
        enriched_metadata[_META_ATTEMPT_HISTORY] = attempt_history

        return ChatResult(
            content=result.content,
            model=result.model,
            finish_reason=result.finish_reason,
            usage=result.usage,
            metadata=enriched_metadata,
        )
