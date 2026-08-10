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

Concurrency safety (DEC-013 §5):

State transitions are persisted using a database conditional UPDATE
(``UPDATE ... WHERE id = :run_id AND state = :expected_state
RETURNING id``). This serializes concurrent transitions for the same
run: exactly one contender wins, the other gets zero rows and a
:class:`~app.ai.workflow.state_machine.TransitionConflictError`.

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

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider.chat_provider import ChatProvider, ChatResult
from app.ai.provider.exceptions import (
    ChatProviderConfigurationError,
    ChatProviderError,
    PermanentChatProviderError,
    TransientChatProviderError,
)
from app.ai.workflow.state_machine import (
    TransitionConflictError,
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

# Allowlist of safe, deterministic error codes that may be stored in
# WorkflowRun.error_code. Any caller-provided error_code not in this set
# is replaced with _ERROR_CODE_INTERNAL.
_SAFE_ERROR_CODES: frozenset[str] = frozenset({
    _ERROR_CODE_INTERNAL,
    _ERROR_CODE_PROVIDER_TRANSIENT,
    _ERROR_CODE_PROVIDER_PERMANENT,
    _ERROR_CODE_PROVIDER_CONFIG,
})

# Allowlist of safe, deterministic error detail strings that may be
# persisted in WorkflowRun.error_detail via fail_internal(). These are
# short, human-readable classification labels — never raw exception
# messages, provider responses, or caller-provided text.
#
# New entries may be added here only after review — they must be:
#   - deterministic (not derived from external input);
#   - free of secrets, credentials, and raw payloads;
#   - bounded in length.
_SAFE_ERROR_DETAIL_REASONS: frozenset[str] = frozenset({
    "INTERNAL_ERROR",
    "INVALID_TRANSITION",
    "STEP_RECORD_ERROR",
    "STEP_SEQ_ERROR",
})


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
            dispatch_generation=0,
            pending_since=datetime.now(UTC),
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

        If the PENDING → RUNNING transition loses a concurrency race
        (another contender already moved the run out of PENDING),
        :class:`TransitionConflictError` is raised and the provider is
        NOT called.

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
            TransitionConflictError: If the PENDING → RUNNING
                transition loses a concurrency race.
            StateMachineError: If the run is not in PENDING state.
        """
        # Transition PENDING → RUNNING (conditional UPDATE).
        # If this loses the race, the provider is never called.
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

            # Pass safe error values explicitly into the conditional
            # terminal UPDATE. Do NOT mutate run.error_code/error_detail
            # on the ORM instance before the conditional UPDATE succeeds
            # — if the transition loses the race, dirty ORM error fields
            # could overwrite the winner's state on a later flush/commit.
            # error_detail is already a safe summary (type name only,
            # no raw exception message — see _safe_error_summary).
            await self._transition_run(
                run,
                target_state,
                error_code=error_code,
                error_detail=error_detail,
            )

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

        Persistence contract:

        This method does NOT persist arbitrary caller-provided text.
        The ``error_detail`` parameter is classified against a strict
        allowlist of safe, deterministic reason strings. If the
        provided value is not in the allowlist, it is replaced with
        ``INTERNAL_ERROR``. This ensures that no raw exception messages,
        provider responses, API keys, bearer tokens, passwords, or
        other untrusted content can be stored in ``error_detail``
        through this path.

        The ``error_code`` is always set to ``_ERROR_CODE_INTERNAL``
        (or an explicitly allowlisted safe code). It is deterministic
        and never contains caller text.

        Args:
            run: The WorkflowRun to fail.
            error_detail: Caller-provided error reason. This value is
                NOT persisted directly — it is classified against a
                safe allowlist. Unrecognized values are replaced with
                ``INTERNAL_ERROR``.
            error_code: Safe error classification code. Defaults to
                ``INTERNAL_ERROR``.
        """
        safe_detail = _classify_safe_error_detail(error_detail)
        safe_code = error_code if error_code in _SAFE_ERROR_CODES else _ERROR_CODE_INTERNAL
        # Do NOT mutate run.error_code/error_detail on the ORM instance
        # before the conditional UPDATE — pass them as parameters so the
        # terminal UPDATE is atomic and the loser cannot dirty the winner.
        await self._transition_run(
            run,
            WorkflowState.FAILED_INTERNAL,
            error_code=safe_code,
            error_detail=safe_detail,
        )
        await self._session.flush()

    async def retry_transition(self, run: WorkflowRun) -> bool:
        """Perform the D1 atomic conditional FAILED_* → PENDING retry transition.

        This is the serialization primitive for user-initiated retry
        (WP-REC-03F D1). It atomically:

        - transitions the run from an eligible failed state
          (``FAILED_PROVIDER``, ``FAILED_VALIDATION``, ``FAILED_INTERNAL``)
          to ``PENDING``;
        - increments ``dispatch_generation`` by exactly 1 (D5 §1);
        - resets ``pending_since`` to the current authoritative UTC
          timestamp (D6 §1);
        - clears ``error_code``, ``error_detail``, ``completed_at``,
          and ``started_at`` to NULL (D1 §11-12; D1 implementation
          choice: clear ``started_at`` so the new ``PENDING → RUNNING``
          transition sets a fresh start timestamp).

        The transition uses a conditional UPDATE:
        ``UPDATE ... WHERE id = :run_id AND state IN (:eligible_states)
        RETURNING id, dispatch_generation``.
        Exactly one concurrent caller wins; losers receive zero rows.

        The caller owns the transaction boundary (commit/rollback).

        Args:
            run: The WorkflowRun to retry. Must be in an eligible
                failed state.

        Returns:
            ``True`` if the transition succeeded (this caller won the
            race). ``False`` if the conditional UPDATE matched zero
            rows (the run is not in an eligible failed state or
            another caller already won the transition).

        Raises:
            StateMachineError: If the run's current state is not an
                eligible failed state (e.g. COMPLETED, PENDING,
                RUNNING, AWAITING_VALIDATION). This is raised by the
                pure state machine validation before any database
                UPDATE.
        """
        from_state = WorkflowState(run.state)
        validate_transition(from_state, WorkflowState.PENDING)

        now = datetime.now(UTC)
        eligible_states = (
            WorkflowState.FAILED_PROVIDER.value,
            WorkflowState.FAILED_VALIDATION.value,
            WorkflowState.FAILED_INTERNAL.value,
        )

        # Use expanding bindparam for the IN clause (asyncpg-compatible).
        from sqlalchemy import bindparam

        update_sql = text("""
            UPDATE workflow_runs
            SET state = :new_state,
                dispatch_generation = dispatch_generation + 1,
                pending_since = :now,
                error_code = NULL,
                error_detail = NULL,
                completed_at = NULL,
                started_at = NULL,
                updated_at = :now
            WHERE id = :run_id
              AND state IN :eligible_states
            RETURNING id, dispatch_generation
        """).bindparams(
            bindparam("eligible_states", expanding=True),
        )

        params: dict[str, Any] = {
            "new_state": WorkflowState.PENDING.value,
            "now": now,
            "run_id": str(run.id),
            "eligible_states": tuple(eligible_states),
        }

        result = await self._session.execute(update_sql, params)
        row = result.fetchone()

        if row is None:
            # The conditional UPDATE matched zero rows — the run is
            # not in an eligible failed state or another caller won.
            # Refresh the ORM instance to reflect authoritative state.
            await self._session.refresh(
                run,
                [
                    "state",
                    "dispatch_generation",
                    "pending_since",
                    "started_at",
                    "completed_at",
                    "error_code",
                    "error_detail",
                    "updated_at",
                ],
            )
            return False

        # Sync the ORM instance with the persisted values.
        run.state = WorkflowState.PENDING.value
        run.dispatch_generation = row[1]
        run.pending_since = now
        run.started_at = None
        run.completed_at = None
        run.error_code = None
        run.error_detail = None
        run.updated_at = now

        _logger.info(
            "workflow.run.retry_transition",
            run_id=str(run.id),
            correlation_id=str(run.correlation_id),
            from_state=from_state.value,
            to_state=WorkflowState.PENDING.value,
            dispatch_generation=run.dispatch_generation,
        )
        return True

    async def transition_to_running_with_generation(
        self,
        run: WorkflowRun,
        *,
        expected_generation: int,
    ) -> bool:
        """Generation-guarded PENDING → RUNNING transition (D6 §5).

        Atomically requires both ``state = PENDING`` AND
        ``dispatch_generation = :expected_generation`` before
        transitioning to RUNNING. This is the mandatory generation
        guard from D6 §5 — a pre-read followed by an UPDATE filtered
        only by ``state`` is insufficient.

        If the conditional UPDATE matches zero rows, the run is either:
        - no longer in PENDING (another worker already transitioned it);
        - still PENDING but with a different generation (stale job).

        In both cases, the caller (worker) must skip execution without
        invoking the provider or regressing workflow state.

        Args:
            run: The WorkflowRun to transition.
            expected_generation: The queued dispatch generation from
                the ARQ job identity/context (D5 §4).

        Returns:
            ``True`` if the transition succeeded (generation matched
            and state was PENDING). ``False`` if the conditional
            UPDATE matched zero rows (stale generation or state
            already changed).

        Raises:
            StateMachineError: If the run's current state is not
                PENDING (pure state machine validation).
        """
        from_state = WorkflowState(run.state)
        validate_transition(from_state, WorkflowState.RUNNING)

        now = datetime.now(UTC)
        update_sql = text("""
            UPDATE workflow_runs
            SET state = :new_state,
                started_at = :now,
                updated_at = :now
            WHERE id = :run_id
              AND state = :expected_state
              AND dispatch_generation = :expected_generation
            RETURNING id
        """)

        params: dict[str, Any] = {
            "new_state": WorkflowState.RUNNING.value,
            "now": now,
            "run_id": str(run.id),
            "expected_state": WorkflowState.PENDING.value,
            "expected_generation": expected_generation,
        }

        result = await self._session.execute(update_sql, params)
        row = result.fetchone()

        if row is None:
            await self._session.refresh(
                run,
                [
                    "state",
                    "dispatch_generation",
                    "started_at",
                    "updated_at",
                ],
            )
            return False

        run.state = WorkflowState.RUNNING.value
        run.started_at = now
        run.updated_at = now

        _logger.info(
            "workflow.run.transition_generation_guarded",
            run_id=str(run.id),
            correlation_id=str(run.correlation_id),
            from_state=from_state.value,
            to_state=WorkflowState.RUNNING.value,
            dispatch_generation=expected_generation,
        )
        return True

    async def transition_to_completed(
        self,
        run: WorkflowRun,
    ) -> None:
        """Transition a run from AWAITING_VALIDATION to COMPLETED.

        Used by the 03F vertical wiring after successful validation
        and recommendation persistence. The caller owns the transaction
        boundary.

        Args:
            run: The WorkflowRun to complete. Must be in
                AWAITING_VALIDATION state.

        Raises:
            StateMachineError: If the transition is invalid.
            TransitionConflictError: If the conditional UPDATE lost
                the race.
        """
        await self._transition_run(run, WorkflowState.COMPLETED)
        await self._session.flush()

    async def transition_to_failed_validation(
        self,
        run: WorkflowRun,
        *,
        error_code: str,
        error_detail: str,
    ) -> None:
        """Transition a run from AWAITING_VALIDATION to FAILED_VALIDATION.

        Used by the 03F vertical wiring when schema validation fails.

        Args:
            run: The WorkflowRun to fail.
            error_code: Safe error classification code.
            error_detail: Safe bounded error summary.

        Raises:
            StateMachineError: If the transition is invalid.
            TransitionConflictError: If the conditional UPDATE lost
                the race.
        """
        await self._transition_run(
            run,
            WorkflowState.FAILED_VALIDATION,
            error_code=error_code,
            error_detail=error_detail,
        )
        await self._session.flush()

    async def transition_to_failed_internal(
        self,
        run: WorkflowRun,
        *,
        error_code: str = _ERROR_CODE_INTERNAL,
        error_detail: str = _ERROR_CODE_INTERNAL,
    ) -> None:
        """Transition a run to FAILED_INTERNAL from any valid source state.

        Used by the 03F vertical wiring when an internal error occurs
        outside the provider-call step (e.g., risk engine failure,
        recommendation persistence failure).

        Args:
            run: The WorkflowRun to fail.
            error_code: Safe error classification code.
            error_detail: Safe bounded error summary.

        Raises:
            StateMachineError: If the transition is invalid.
            TransitionConflictError: If the conditional UPDATE lost
                the race.
        """
        safe_code = error_code if error_code in _SAFE_ERROR_CODES else _ERROR_CODE_INTERNAL
        safe_detail = _classify_safe_error_detail(error_detail)
        await self._transition_run(
            run,
            WorkflowState.FAILED_INTERNAL,
            error_code=safe_code,
            error_detail=safe_detail,
        )
        await self._session.flush()

    async def _transition_run(
        self,
        run: WorkflowRun,
        to_state: WorkflowState,
        *,
        error_code: str | None = None,
        error_detail: str | None = None,
    ) -> None:
        """Validate and persist a state transition via conditional UPDATE.

        Implements DEC-013 §5: concurrent transitions for the same run
        are serialized by a database conditional-transition rule
        (``UPDATE ... WHERE state = :expected RETURNING id``).

        The transition is first validated by the pure state machine
        (:func:`validate_transition`). Then a conditional UPDATE is
        executed against the database, atomically setting the new
        state, relevant timestamps, and error fields only if the
        current database state matches the expected source state.

        For terminal transitions, error_code and error_detail are
        passed as explicit parameters (not read from the ORM instance)
        and persisted atomically in the same UPDATE. This prevents the
        losing ORM instance from retaining dirty error fields that
        could overwrite the winner's state on a later flush/commit.

        If zero rows are returned (another contender won the race or
        the row was modified), the ORM instance is refreshed from the
        database — including state, timestamps, error fields, and
        updated_at — and :class:`TransitionConflictError` is raised.
        The refreshed ORM instance reflects all authoritative persisted
        state relevant to the transition, so a later flush/commit by
        the losing session will not overwrite the winner's state,
        timestamps, error_code, or error_detail.

        Does NOT commit the transaction — the caller owns the boundary.

        Args:
            run: The WorkflowRun to transition. Its ``state`` attribute
                is used as the expected current state for the
                conditional UPDATE.
            to_state: The target state.
            error_code: Safe error classification code for terminal
                transitions. Passed directly into the UPDATE, not via
                ORM mutation. If None, the column is set to NULL.
            error_detail: Safe error detail for terminal transitions.
                Passed directly into the UPDATE, not via ORM mutation.
                If None, the column is set to NULL.

        Raises:
            StateMachineError: If the transition is invalid per the
                pure state machine rules.
            TransitionConflictError: If the conditional UPDATE returned
                zero rows (the run's database state no longer matches
                the expected source state).
        """
        from_state = WorkflowState(run.state)
        validate_transition(from_state, to_state)

        now = datetime.now(UTC)

        is_terminal = to_state in (
            WorkflowState.COMPLETED,
            WorkflowState.FAILED_VALIDATION,
            WorkflowState.FAILED_PROVIDER,
            WorkflowState.FAILED_INTERNAL,
        )

        # Build the conditional UPDATE with timestamp columns.
        # The WHERE clause checks both run ID and expected current state.
        if to_state == WorkflowState.RUNNING:
            update_sql = text("""
                UPDATE workflow_runs
                SET state = :new_state,
                    started_at = :now,
                    updated_at = :now
                WHERE id = :run_id AND state = :expected_state
                RETURNING id
            """)
        elif is_terminal:
            # Terminal transitions set completed_at, error_code,
            # error_detail, and updated_at atomically in the same UPDATE.
            # error_code and error_detail are passed as explicit parameters
            # (not read from the ORM instance) to prevent dirty ORM state
            # from being persisted if the conditional UPDATE loses the race.
            update_sql = text("""
                UPDATE workflow_runs
                SET state = :new_state,
                    completed_at = :now,
                    error_code = :error_code,
                    error_detail = :error_detail,
                    updated_at = :now
                WHERE id = :run_id AND state = :expected_state
                RETURNING id
            """)
        else:
            # AWAITING_VALIDATION and other non-terminal, non-RUNNING
            # transitions: only update state and updated_at.
            update_sql = text("""
                UPDATE workflow_runs
                SET state = :new_state,
                    updated_at = :now
                WHERE id = :run_id AND state = :expected_state
                RETURNING id
            """)

        params: dict[str, Any] = {
            "new_state": to_state.value,
            "run_id": str(run.id),
            "expected_state": from_state.value,
            "now": now,
        }

        if is_terminal:
            params["error_code"] = error_code
            params["error_detail"] = error_detail

        result = await self._session.execute(update_sql, params)
        row = result.fetchone()

        if row is None:
            # The conditional UPDATE matched zero rows — another
            # contender won the race or the row's state changed.
            # Refresh ALL relevant fields from the database so the
            # ORM instance reflects authoritative persisted state.
            # This prevents dirty error_code/error_detail/updated_at
            # from being flushed later and overwriting the winner.
            await self._session.refresh(
                run,
                [
                    "state",
                    "started_at",
                    "completed_at",
                    "error_code",
                    "error_detail",
                    "updated_at",
                ],
            )
            raise TransitionConflictError(
                f"Conditional transition failed: run {run.id} expected "
                f"{from_state.value} but the row no longer matches. "
                f"Current DB state: {run.state}."
            )

        # Sync the ORM instance with the persisted values.
        # This ensures the ORM instance matches the DB after a
        # successful conditional UPDATE.
        run.state = to_state.value
        if to_state == WorkflowState.RUNNING:
            run.started_at = now
        if is_terminal:
            run.completed_at = now
            run.error_code = error_code
            run.error_detail = error_detail
        run.updated_at = now

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

        Flushes pending ORM objects before querying so that newly added
        WorkflowStep rows in the session's identity map are visible to
        the aggregate query. Without this flush, AsyncSession does not
        auto-flush pending INSERTs before a SELECT, causing max(seq) to
        return stale results and producing duplicate seq values (D1 §10
        append-only contract violation).

        Uses an explicit ``is None`` check rather than ``or`` to avoid
        the Python falsy-zero bug: ``0 or -1`` evaluates to ``-1``
        because ``0`` is falsy, which would return ``0`` instead of
        ``1`` when the max seq is a legitimate ``0`` from the first
        step.
        """
        from sqlalchemy import func, select

        # Flush pending ORM objects so newly added WorkflowStep rows
        # are visible to the aggregate query.
        await self._session.flush()

        result = await self._session.execute(
            select(func.max(WorkflowStep.seq))
            .where(WorkflowStep.run_id == run_id)
        )
        max_seq = result.scalar()
        if max_seq is None:
            return 0
        return max_seq + 1


def _safe_error_summary(exc: Exception) -> str:
    """Extract a safe error summary from an exception.

    Returns ONLY the exception type name — never the raw exception
    message. Exception messages may contain API keys, bearer tokens,
    passwords, authorization headers, or raw provider responses that
    must not be persisted.

    This conservative strategy ensures that no secret-bearing content
    from an exception message can leak into ``error_detail`` columns.

    Args:
        exc: The exception to summarize.

    Returns:
        The exception type name (e.g. ``"TransientChatProviderError"``).
        This is a safe, deterministic, bounded string.
    """
    return type(exc).__name__


def _classify_safe_error_detail(detail: str) -> str:
    """Classify a caller-provided error detail against a safe allowlist.

    This function implements the conservative persistence contract for
    ``fail_internal()``: only a deterministic, allowlisted safe reason
    is returned. Arbitrary caller-provided text — including short
    exception messages, JSON/provider responses, API keys, bearer
    tokens, passwords, and long messages — is never persisted. Instead,
    unrecognized values are replaced with ``INTERNAL_ERROR``.

    Regex-based secret detection is NOT used as the primary safety
    boundary. The allowlist is the boundary: if the value is not an
    exact match for a known safe reason, it is discarded.

    Args:
        detail: The raw error detail string from the caller. This may
            contain anything — it is never trusted.

    Returns:
        A safe, deterministic error detail string from the allowlist,
        or ``INTERNAL_ERROR`` if the input is not recognized.
    """
    if detail in _SAFE_ERROR_DETAIL_REASONS:
        return detail
    return _ERROR_CODE_INTERNAL
