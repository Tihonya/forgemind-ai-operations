"""Unit tests for ingestion job worker function.

Tests cover ARQ retry semantics, transaction isolation, error classification,
correlation context binding, and worker registration. No live PostgreSQL,
Redis, or ARQ worker required.

Test categories:
1. Worker registration
2. Input validation
3. Successful ingestion flow
4. Retry semantics (transient errors)
5. Non-retryable errors (permanent failures)
6. Correlation context binding
7. Logging safety (no sensitive data)
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from arq import Retry

from app.core.correlation import InvalidCorrelationIdError
from app.jobs.ingestion import run_document_ingestion
from app.services.embedding_provider import (
    EmbeddingProviderConfigurationError,
    PermanentEmbeddingProviderError,
    TransientEmbeddingProviderError,
)
from app.services.ingestion import IngestionResult
from app.worker import WorkerSettings

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def _make_ctx(job_try: int = 1) -> dict[str, Any]:
    """Build minimal ARQ context dict."""
    return {"job_try": job_try}


def _valid_version_id() -> str:
    return str(uuid.uuid4())


def _valid_correlation_id() -> str:
    return str(uuid.uuid4())


def _make_ingestion_result(version_id: str | None = None) -> IngestionResult:
    """Build a successful IngestionResult."""
    vid = uuid.UUID(version_id) if version_id else uuid.uuid4()
    return IngestionResult(
        document_version_id=vid,
        chunks_count=3,
        embeddings_count=3,
        status="completed",
    )


# --------------------------------------------------------------------------- #
# 1. Worker registration
# --------------------------------------------------------------------------- #


class TestWorkerRegistration:
    def test_ingestion_job_registered(self) -> None:
        """run_document_ingestion must be in WorkerSettings.functions."""
        # The function may be wrapped by func(), so check the coroutine attribute
        job_names = []
        for fn in WorkerSettings.functions:
            if hasattr(fn, 'coroutine'):
                job_names.append(fn.coroutine.__name__)
            else:
                job_names.append(fn.__name__)
        assert "run_document_ingestion" in job_names

    def test_both_jobs_registered(self) -> None:
        """Both diagnostic and ingestion jobs must be registered."""
        job_names = []
        for fn in WorkerSettings.functions:
            if hasattr(fn, 'coroutine'):
                job_names.append(fn.coroutine.__name__)
            else:
                job_names.append(fn.__name__)
        assert "run_diagnostic_job" in job_names
        assert "run_document_ingestion" in job_names

    def test_function_count(self) -> None:
        """WorkerSettings.functions should have exactly 2 jobs."""
        assert len(WorkerSettings.functions) == 2


# --------------------------------------------------------------------------- #
# 2. Input validation
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestInputValidation:
    async def test_malformed_document_version_id(self) -> None:
        """Invalid UUID format raises ValueError before DB access."""
        ctx = _make_ctx(job_try=1)
        invalid_version = "not-a-uuid"
        correlation_id = _valid_correlation_id()

        with pytest.raises(ValueError, match="Invalid document_version_id"):
            await run_document_ingestion(ctx, invalid_version, correlation_id)

    async def test_malformed_correlation_id(self) -> None:
        """Invalid correlation ID raises InvalidCorrelationIdError before DB access."""
        ctx = _make_ctx(job_try=1)
        version_id = _valid_version_id()
        invalid_correlation = "not-a-uuid"

        with pytest.raises(InvalidCorrelationIdError):
            await run_document_ingestion(ctx, version_id, invalid_correlation)

    async def test_valid_inputs_proceed(self) -> None:
        """Valid UUIDs proceed to execution."""
        ctx = _make_ctx(job_try=1)
        version_id = _valid_version_id()
        correlation_id = _valid_correlation_id()

        with (
            patch("app.jobs.ingestion.async_session_factory") as mock_factory,
            patch("app.jobs.ingestion.create_embedding_provider"),
            patch("app.jobs.ingestion.IngestionOrchestrator") as mock_orch_class,
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_session

            mock_orch = AsyncMock()
            mock_orch.ingest_document_version = AsyncMock(
                return_value=_make_ingestion_result(version_id)
            )
            mock_orch_class.return_value = mock_orch

            result = await run_document_ingestion(ctx, version_id, correlation_id)

            assert result["document_version_id"] == version_id
            assert result["status"] == "completed"


# --------------------------------------------------------------------------- #
# 3. Successful ingestion flow
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestSuccessfulIngestion:
    async def test_returns_json_serializable_payload(self) -> None:
        """Success payload is JSON-serializable."""
        ctx = _make_ctx(job_try=1)
        version_id = _valid_version_id()
        correlation_id = _valid_correlation_id()

        with (
            patch("app.jobs.ingestion.async_session_factory") as mock_factory,
            patch("app.jobs.ingestion.create_embedding_provider"),
            patch("app.jobs.ingestion.IngestionOrchestrator") as mock_orch_class,
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_session

            mock_orch = AsyncMock()
            mock_orch.ingest_document_version = AsyncMock(
                return_value=_make_ingestion_result(version_id)
            )
            mock_orch_class.return_value = mock_orch

            result = await run_document_ingestion(ctx, version_id, correlation_id)

            # Verify JSON-serializable
            json_str = json.dumps(result)
            assert json_str is not None
            parsed = json.loads(json_str)
            assert parsed["document_version_id"] == version_id
            assert parsed["status"] == "completed"
            assert parsed["chunks_count"] == 3
            assert parsed["embeddings_count"] == 3

    async def test_commits_exactly_once(self) -> None:
        """Successful ingestion commits exactly once."""
        ctx = _make_ctx(job_try=1)
        version_id = _valid_version_id()
        correlation_id = _valid_correlation_id()

        with (
            patch("app.jobs.ingestion.async_session_factory") as mock_factory,
            patch("app.jobs.ingestion.create_embedding_provider"),
            patch("app.jobs.ingestion.IngestionOrchestrator") as mock_orch_class,
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_session

            mock_orch = AsyncMock()
            mock_orch.ingest_document_version = AsyncMock(
                return_value=_make_ingestion_result(version_id)
            )
            mock_orch_class.return_value = mock_orch

            await run_document_ingestion(ctx, version_id, correlation_id)

            mock_session.commit.assert_awaited_once()

    async def test_does_not_rollback_on_success(self) -> None:
        """Successful path does not call rollback."""
        ctx = _make_ctx(job_try=1)
        version_id = _valid_version_id()
        correlation_id = _valid_correlation_id()

        with (
            patch("app.jobs.ingestion.async_session_factory") as mock_factory,
            patch("app.jobs.ingestion.create_embedding_provider"),
            patch("app.jobs.ingestion.IngestionOrchestrator") as mock_orch_class,
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_session

            mock_orch = AsyncMock()
            mock_orch.ingest_document_version = AsyncMock(
                return_value=_make_ingestion_result(version_id)
            )
            mock_orch_class.return_value = mock_orch

            await run_document_ingestion(ctx, version_id, correlation_id)

            mock_session.rollback.assert_not_awaited()


# --------------------------------------------------------------------------- #
# 4. Retry semantics (transient errors)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestRetrySemantics:
    async def test_transient_error_retries_with_2s_delay_after_attempt_1(self) -> None:
        """Transient error on attempt 1 raises Retry(defer=2)."""
        ctx = _make_ctx(job_try=1)
        version_id = _valid_version_id()
        correlation_id = _valid_correlation_id()

        with (
            patch("app.jobs.ingestion.async_session_factory") as mock_factory,
            patch("app.jobs.ingestion.create_embedding_provider"),
            patch("app.jobs.ingestion.IngestionOrchestrator") as mock_orch_class,
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_session

            mock_orch = AsyncMock()
            mock_orch.ingest_document_version = AsyncMock(
                side_effect=TransientEmbeddingProviderError("transient failure")
            )
            mock_orch_class.return_value = mock_orch

            with pytest.raises(Retry) as exc_info:
                await run_document_ingestion(ctx, version_id, correlation_id)

            # ARQ Retry stores defer_score in milliseconds (2 seconds = 2000 ms)
            assert exc_info.value.defer_score == 2000
            mock_session.rollback.assert_awaited_once()
            mock_session.commit.assert_not_awaited()

    async def test_transient_error_retries_with_4s_delay_after_attempt_2(self) -> None:
        """Transient error on attempt 2 raises Retry(defer=4)."""
        ctx = _make_ctx(job_try=2)
        version_id = _valid_version_id()
        correlation_id = _valid_correlation_id()

        with (
            patch("app.jobs.ingestion.async_session_factory") as mock_factory,
            patch("app.jobs.ingestion.create_embedding_provider"),
            patch("app.jobs.ingestion.IngestionOrchestrator") as mock_orch_class,
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_session

            mock_orch = AsyncMock()
            mock_orch.ingest_document_version = AsyncMock(
                side_effect=TransientEmbeddingProviderError("transient failure")
            )
            mock_orch_class.return_value = mock_orch

            with pytest.raises(Retry) as exc_info:
                await run_document_ingestion(ctx, version_id, correlation_id)

            # ARQ Retry stores defer_score in milliseconds (4 seconds = 4000 ms)
            assert exc_info.value.defer_score == 4000
            mock_session.rollback.assert_awaited_once()
            mock_session.commit.assert_not_awaited()

    async def test_transient_error_on_attempt_3_does_not_retry(self) -> None:
        """Transient error on attempt 3 (final) re-raises without Retry."""
        ctx = _make_ctx(job_try=3)
        version_id = _valid_version_id()
        correlation_id = _valid_correlation_id()

        with (
            patch("app.jobs.ingestion.async_session_factory") as mock_factory,
            patch("app.jobs.ingestion.create_embedding_provider"),
            patch("app.jobs.ingestion.IngestionOrchestrator") as mock_orch_class,
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_session

            mock_orch = AsyncMock()
            original_error = TransientEmbeddingProviderError("final failure")
            mock_orch.ingest_document_version = AsyncMock(side_effect=original_error)
            mock_orch_class.return_value = mock_orch

            with pytest.raises(TransientEmbeddingProviderError) as exc_info:
                await run_document_ingestion(ctx, version_id, correlation_id)

            assert exc_info.value is original_error
            mock_session.rollback.assert_awaited_once()
            mock_session.commit.assert_not_awaited()


# --------------------------------------------------------------------------- #
# 5. Non-retryable errors (permanent failures)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestNonRetryableErrors:
    async def test_permanent_error_does_not_retry(self) -> None:
        """PermanentEmbeddingProviderError re-raises without Retry."""
        ctx = _make_ctx(job_try=1)
        version_id = _valid_version_id()
        correlation_id = _valid_correlation_id()

        with (
            patch("app.jobs.ingestion.async_session_factory") as mock_factory,
            patch("app.jobs.ingestion.create_embedding_provider"),
            patch("app.jobs.ingestion.IngestionOrchestrator") as mock_orch_class,
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_session

            mock_orch = AsyncMock()
            original_error = PermanentEmbeddingProviderError("permanent failure")
            mock_orch.ingest_document_version = AsyncMock(side_effect=original_error)
            mock_orch_class.return_value = mock_orch

            with pytest.raises(PermanentEmbeddingProviderError) as exc_info:
                await run_document_ingestion(ctx, version_id, correlation_id)

            assert exc_info.value is original_error
            mock_session.rollback.assert_awaited_once()
            mock_session.commit.assert_not_awaited()

    async def test_configuration_error_does_not_retry(self) -> None:
        """EmbeddingProviderConfigurationError re-raises without Retry."""
        ctx = _make_ctx(job_try=1)
        version_id = _valid_version_id()
        correlation_id = _valid_correlation_id()

        with (
            patch("app.jobs.ingestion.async_session_factory") as mock_factory,
            patch("app.jobs.ingestion.create_embedding_provider"),
            patch("app.jobs.ingestion.IngestionOrchestrator") as mock_orch_class,
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_session

            mock_orch = AsyncMock()
            original_error = EmbeddingProviderConfigurationError("config error")
            mock_orch.ingest_document_version = AsyncMock(side_effect=original_error)
            mock_orch_class.return_value = mock_orch

            with pytest.raises(EmbeddingProviderConfigurationError) as exc_info:
                await run_document_ingestion(ctx, version_id, correlation_id)

            assert exc_info.value is original_error
            mock_session.rollback.assert_awaited_once()
            mock_session.commit.assert_not_awaited()

    async def test_value_error_does_not_retry(self) -> None:
        """ValueError (missing document, blank content) re-raises without Retry."""
        ctx = _make_ctx(job_try=1)
        version_id = _valid_version_id()
        correlation_id = _valid_correlation_id()

        with (
            patch("app.jobs.ingestion.async_session_factory") as mock_factory,
            patch("app.jobs.ingestion.create_embedding_provider"),
            patch("app.jobs.ingestion.IngestionOrchestrator") as mock_orch_class,
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_session

            mock_orch = AsyncMock()
            original_error = ValueError("DocumentVersion not found")
            mock_orch.ingest_document_version = AsyncMock(side_effect=original_error)
            mock_orch_class.return_value = mock_orch

            with pytest.raises(ValueError) as exc_info:
                await run_document_ingestion(ctx, version_id, correlation_id)

            assert exc_info.value is original_error
            mock_session.rollback.assert_awaited_once()
            mock_session.commit.assert_not_awaited()

    async def test_unclassified_exception_does_not_retry(self) -> None:
        """Unclassified Exception re-raises without Retry."""
        ctx = _make_ctx(job_try=1)
        version_id = _valid_version_id()
        correlation_id = _valid_correlation_id()

        with (
            patch("app.jobs.ingestion.async_session_factory") as mock_factory,
            patch("app.jobs.ingestion.create_embedding_provider"),
            patch("app.jobs.ingestion.IngestionOrchestrator") as mock_orch_class,
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_session

            mock_orch = AsyncMock()
            original_error = RuntimeError("unclassified")
            mock_orch.ingest_document_version = AsyncMock(side_effect=original_error)
            mock_orch_class.return_value = mock_orch

            with pytest.raises(RuntimeError) as exc_info:
                await run_document_ingestion(ctx, version_id, correlation_id)

            assert exc_info.value is original_error
            mock_session.rollback.assert_awaited_once()
            mock_session.commit.assert_not_awaited()


# --------------------------------------------------------------------------- #
# 6. Correlation context binding
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestCorrelationContext:
    async def test_correlation_context_bound_during_execution(self) -> None:
        """Correlation ID is bound during job execution."""
        ctx = _make_ctx(job_try=1)
        version_id = _valid_version_id()
        correlation_id = _valid_correlation_id()

        captured_context: dict[str, str | None] = {}

        async def capture_context(*args: Any, **kwargs: Any) -> IngestionResult:
            from app.core.context import get_correlation_id
            captured_context["correlation_id"] = get_correlation_id()
            return _make_ingestion_result(version_id)

        with (
            patch("app.jobs.ingestion.async_session_factory") as mock_factory,
            patch("app.jobs.ingestion.create_embedding_provider"),
            patch("app.jobs.ingestion.IngestionOrchestrator") as mock_orch_class,
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_session

            mock_orch = AsyncMock()
            mock_orch.ingest_document_version = AsyncMock(side_effect=capture_context)
            mock_orch_class.return_value = mock_orch

            await run_document_ingestion(ctx, version_id, correlation_id)

            assert captured_context["correlation_id"] == correlation_id


# --------------------------------------------------------------------------- #
# 7. Logging safety (no sensitive data)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestLoggingSafety:
    async def test_no_sensitive_data_in_logs_on_success(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Success path logs only safe fields."""
        ctx = _make_ctx(job_try=1)
        version_id = _valid_version_id()
        correlation_id = _valid_correlation_id()

        with (
            patch("app.jobs.ingestion.async_session_factory") as mock_factory,
            patch("app.jobs.ingestion.create_embedding_provider"),
            patch("app.jobs.ingestion.IngestionOrchestrator") as mock_orch_class,
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_session

            mock_orch = AsyncMock()
            mock_orch.ingest_document_version = AsyncMock(
                return_value=_make_ingestion_result(version_id)
            )
            mock_orch_class.return_value = mock_orch

            await run_document_ingestion(ctx, version_id, correlation_id)

            # Verify no sensitive fields in log output
            log_output = caplog.text
            assert "secret" not in log_output.lower()
            assert "password" not in log_output.lower()
            assert "api_key" not in log_output.lower()
            assert "token" not in log_output.lower()

    async def test_no_sensitive_data_in_logs_on_failure(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Failure path logs only safe fields."""
        ctx = _make_ctx(job_try=1)
        version_id = _valid_version_id()
        correlation_id = _valid_correlation_id()

        with (
            patch("app.jobs.ingestion.async_session_factory") as mock_factory,
            patch("app.jobs.ingestion.create_embedding_provider"),
            patch("app.jobs.ingestion.IngestionOrchestrator") as mock_orch_class,
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_session

            mock_orch = AsyncMock()
            mock_orch.ingest_document_version = AsyncMock(
                side_effect=PermanentEmbeddingProviderError("permanent failure")
            )
            mock_orch_class.return_value = mock_orch

            with pytest.raises(PermanentEmbeddingProviderError):
                await run_document_ingestion(ctx, version_id, correlation_id)

            # Verify no sensitive fields in log output
            log_output = caplog.text
            assert "secret" not in log_output.lower()
            assert "password" not in log_output.lower()
            assert "api_key" not in log_output.lower()
            assert "token" not in log_output.lower()
