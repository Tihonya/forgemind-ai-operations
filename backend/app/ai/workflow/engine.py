"""WorkflowEngine foundation (WP-REC-03B).

The WorkflowEngine creates workflow runs, applies state transitions
through the explicit state machine, persists authoritative run state,
records WorkflowStep lifecycle entries, and calls ChatProvider.complete()
through the merged WP-REC-03A interface.

Package-boundary constraints (WP-REC-03B):

- The engine establishes the provider-call and step-recording
  foundation but does NOT validate structured output (03C).
- The engine transitions to AWAITING_VALIDATION after a successful
  provider call, but does NOT transition to COMPLETED — that
  transition requires validation (03C) and is deferred.
- No Recommendation row is persisted from raw provider output.
- No automatic retry is implemented (03D).
- No ARQ or HTTP execution is added (03F).
- No reconciler is added (03F).

The engine uses dependency injection for ChatProvider and the async
session, supporting deterministic tests with FakeChatProvider or test
doubles.

Transaction ownership:

The engine operates within a caller-provided AsyncSession. It does not
commit or rollback the session — the caller owns the transaction
boundary. This allows the engine to be used in both request-scoped and
worker-scoped (ARQ) contexts. Run state changes and step records are
flushed within the session so that the caller can commit them
atomically.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider.chat_provider import ChatProvider, ChatResult
from app.ai.provider.exceptions import (
    ChatProviderConfigurationError,
    ChatProviderError,
    PermanentChatProviderError,
    TransientChatProviderError,
)
from app.ai.workflow.state_machine import (
    WorkflowState,
    validate_transition,
)
from app.core.logging import get_logger
from app.models.workflow import WorkflowRun, WorkflowStep

_logger = get_logger(__name__)

# Safe error classification codes stored in error_code columns.
# These are bounded strings — never contain exception messages or secrets.
_ERROR_CODE_PROVIDER_TRANSIENT = "PROVIDER_TRANSIENT"
_ERROR_CODE_PROVIDER_PERMANENT = "PROVIDER_PERMANENT"
_ERROR_CODE_PROVIDER_CONFIG = "PROVIDER_CONFIG"
_ERROR_CODE_INTERNAL = "INTERNAL_ERROR"


class WorkflowEngine:
    """Foundation workflow engine (WP-REC-03B).

    Creates workflow runs, executes the provider-call step, records
    workflow steps, and applies state transitions through the explicit
    state machine. Does not validate structured output, persist
    recommendations, or implement retry.

    Args:
        provider: ChatProvider instance (from WP-REC-03A). Used for
            the provider-call step via ``complete()``.
        session: AsyncSession for persistence. The caller owns the
            transaction boundary (commit/rollback).
        clock: Optional clock callable for deterministic time in tests.
            Defaults to ``time.monotonic``.
    """

    def __init__(
        self,
        *,
        provider: ChatProvider,
        session: AsyncSession,
        clock: Any = None,
    ) -> None:
        self._provider = provider
        self._session = session
        self._clock = clock if clock is not None else time.monotonic

    async def create_run(
        self,
        *,
        plan_id: UUID,
        correlation_id: UUID | None = None,
        triggered_by: str | None = None,
    ) -> WorkflowRun:
        """Create a new workflow run in PENDING state.

        Args:
            plan_id: Production plan UUID to analyse.
            correlation_id: Optional correlation UUID. If not provided,
                a new UUID v4 is generated.
            triggered_by: Optional username/system identifier.

        Returns:
            The created WorkflowRun instance (PENDING state). The
            instance is added to the session but not committed — the
            caller owns the transaction boundary.
        """
        if correlation_id is None:
            correlation_id = uuid4()

        run = WorkflowRun(
            correlation_id=correlation_id,
            state=WorkflowState.PENDING,
            plan_id=plan_id,
            triggered_by=triggered_by,
        )
        self._session.add(run)
        await self._session.flush()

        _logger.info(
            "workflow.run.created",
            run_id=str(run.id),
            correlation_id=str(correlation_id),
            state=WorkflowState.PENDING.value,
            plan_id=str(plan_id),
        )
        return run

    async def execute_provider_call(
        self,
        run: WorkflowRun,
        *,
        prompt: str,
        schema: dict[str, Any] | None = None,
    ) -> ChatResult | None:
        """Execute the provider-call step for a workflow run.

        Transitions the run from PENDING to RUNNING, calls
        ChatProvider.complete(), records a WorkflowStep with model
        metadata, and transitions to AWAITING_VALIDATION on success.

        On provider failure, transitions to FAILED_PROVIDER and records
        the error. On internal error, transitions to FAILED_INTERNAL.

        This method does NOT:
        - Validate the provider output (that is 03C).
        - Persist a Recommendation (that is 03F).
        - Retry on transient failure (that is 03D).

        Args:
            run: The WorkflowRun to execute. Must be in PENDING state.
            prompt: The prompt text for the provider.
            schema: Optional JSON schema for structured output.

        Returns:
            The ChatResult on success, or None if the provider call
            failed (the run is transitioned to a FAILED state).

        Raises:
            StateMachineError: If the run is not in PENDING state.
        """
        # Transition PENDING → RUNNING
        await self._transition_run(run, WorkflowState.RUNNING)

        # Record step start
        step = WorkflowStep(
            run_id=run.id,
            correlation_id=run.correlation_id,
            seq=await self._next_step_seq(run.id),
            step_name="provider_call",
            status="started",
        )
        self._session.add(step)
        await self._session.flush()

        start = self._clock()
        chat_result: ChatResult | None = None
        error_code: str | None = None
        error_detail: str | None = None
        model_name: str | None = None
        latency_ms: int | None = None
        token_usage: dict[str, int] | None = None
        step_metadata: dict[str, Any] | None = None

        try:
            context: dict[str, Any] = {
                "correlation_id": str(run.correlation_id),
                "run_id": str(run.id),
            }
            chat_result = await self._provider.complete(
                prompt=prompt,
                schema=schema,
                context=context,
            )
        except TransientChatProviderError as exc:
            error_code = _ERROR_CODE_PROVIDER_TRANSIENT
            error_detail = _safe_error_summary(exc)
        except PermanentChatProviderError as exc:
            error_code = _ERROR_CODE_PROVIDER_PERMANENT
            error_detail = _safe_error_summary(exc)
        except ChatProviderConfigurationError as exc:
            error_code = _ERROR_CODE_PROVIDER_CONFIG
            error_detail = _safe_error_summary(exc)
        except ChatProviderError as exc:
            # Unknown ChatProviderError subclass — treat as permanent.
            error_code = _ERROR_CODE_PROVIDER_PERMANENT
            error_detail = _safe_error_summary(exc)
        except Exception as exc:
            # Unexpected non-provider error — internal failure.
            error_code = _ERROR_CODE_INTERNAL
            error_detail = _safe_error_summary(exc)

        latency_ms = int((self._clock() - start) * 1000)

        if chat_result is not None:
            # Success — populate step with model metadata
            model_name = chat_result.model
            token_usage = chat_result.usage if chat_result.usage else None
            step_metadata = dict(chat_result.metadata)
            step.status = "completed"
            step.model_name = model_name
            step.latency_ms = latency_ms
            step.token_usage = token_usage
            step.step_metadata = step_metadata
            step.completed_at = datetime.now(UTC)

            # Transition RUNNING → AWAITING_VALIDATION
            await self._transition_run(run, WorkflowState.AWAITING_VALIDATION)

            _logger.info(
                "workflow.step.completed",
                run_id=str(run.id),
                correlation_id=str(run.correlation_id),
                step_name="provider_call",
                model=model_name,
                latency_ms=latency_ms,
            )
        else:
            # Failure — record error in step
            step.status = "failed"
            step.latency_ms = latency_ms
            step.error_code = error_code
            step.error_detail = error_detail
            step.completed_at = datetime.now(UTC)

            # Determine target failure state
            if error_code == _ERROR_CODE_INTERNAL:
                target_state = WorkflowState.FAILED_INTERNAL
            else:
                target_state = WorkflowState.FAILED_PROVIDER

            # Store safe error info on the run as well
            run.error_code = error_code
            run.error_detail = error_detail

            await self._transition_run(run, target_state)

            _logger.warning(
                "workflow.step.failed",
                run_id=str(run.id),
                correlation_id=str(run.correlation_id),
                step_name="provider_call",
                error_code=error_code,
                latency_ms=latency_ms,
            )

        await self._session.flush()
        return chat_result

    async def fail_internal(
        self,
        run: WorkflowRun,
        *,
        error_detail: str,
        error_code: str = _ERROR_CODE_INTERNAL,
    ) -> None:
        """Transition a run to FAILED_INTERNAL.

        Used when an internal error occurs outside the provider-call
        step (e.g., an invalid transition attempt or an unexpected
        engine-level failure).

        Args:
            run: The WorkflowRun to fail.
            error_detail: Safe error summary (no secrets).
            error_code: Safe error classification code.
        """
        run.error_code = error_code
        run.error_detail = error_detail
        await self._transition_run(run, WorkflowState.FAILED_INTERNAL)
        await self._session.flush()

    async def _transition_run(
        self,
        run: WorkflowRun,
        to_state: WorkflowState,
    ) -> None:
        """Validate and apply a state transition to a WorkflowRun.

        Updates the run's state, started_at, and completed_at fields.
        Raises StateMachineError if the transition is invalid — the
        caller is responsible for handling this (typically by
        transitioning to FAILED_INTERNAL).

        Does NOT commit the transaction — the caller owns the boundary.
        """
        from_state = WorkflowState(run.state)
        validate_transition(from_state, to_state)

        now = datetime.now(UTC)
        run.state = to_state.value

        if to_state == WorkflowState.RUNNING:
            run.started_at = now
        if to_state in (
            WorkflowState.COMPLETED,
            WorkflowState.FAILED_VALIDATION,
            WorkflowState.FAILED_PROVIDER,
            WorkflowState.FAILED_INTERNAL,
        ):
            run.completed_at = now

        _logger.info(
            "workflow.run.transition",
            run_id=str(run.id),
            correlation_id=str(run.correlation_id),
            from_state=from_state.value,
            to_state=to_state.value,
        )

    async def _next_step_seq(self, run_id: UUID) -> int:
        """Determine the next step sequence number for a run.

        Queries the session for existing steps and returns max(seq) + 1.
        Returns 0 if no steps exist yet.
        """
        from sqlalchemy import func, select

        result = await self._session.execute(
            select(func.max(WorkflowStep.seq))
            .where(WorkflowStep.run_id == run_id)
        )
        max_seq = result.scalar()
        return (max_seq or -1) + 1


def _safe_error_summary(exc: Exception) -> str:
    """Extract a safe, bounded error summary from an exception.

    Returns the exception type name and a truncated message. Never
    includes stack traces, API keys, or raw provider payloads. The
    exception message may contain response content, so we use the type
    name as the primary identifier and include a truncated message only
    if it is safe (does not contain known secret patterns).

    Args:
        exc: The exception to summarize.

    Returns:
        A safe, bounded error summary string (max ~200 chars).
    """
    exc_name = type(exc).__name__
    message = str(exc)
    # Truncate to prevent unbounded error detail.
    if len(message) > 150:
        message = message[:150] + "..."
    return f"{exc_name}: {message}" if message else exc_name
