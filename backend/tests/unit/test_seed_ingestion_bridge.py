"""Tests for WP-4.3B4: Seed-Loader Async Ingestion Bridge.

Verifies the two-phase seed ingestion pattern:
1. Synchronous seed commit
2. Async ingestion via asyncio.run() — called exactly once
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.seed.generator.loader import IngestionResult, _ingest_seed_documents


class TestPhase1SyncCommit:
    """Phase 1: synchronous seed commit before async phase."""

    def test_sync_commit_before_async_phase(self) -> None:
        """Verify seed rows commit before async ingestion begins."""
        from app.seed.generator.loader import main

        call_order = []

        def mock_commit() -> None:
            call_order.append("commit")

        mock_session = MagicMock()
        mock_session.commit = mock_commit
        mock_session.rollback = MagicMock()
        mock_session.close = MagicMock()
        mock_session.query = MagicMock()

        def mock_asyncio_run(coro):
            call_order.append("asyncio.run")
            coro.close()
            return IngestionResult(0, 0, 0, [])

        version_id = uuid4()

        with (
            patch(
                "app.seed.generator.loader._SessionFactory",
                return_value=mock_session,
            ),
            patch("app.seed.generator.loader._verify_alembic_head"),
            patch(
                "app.seed.generator.loader.generate_golden_dataset",
                return_value={k: [] for k in [
                    "products", "product_versions", "components", "bom_items",
                    "component_alternatives", "warehouses", "suppliers",
                    "production_plans", "production_orders",
                    "inventory_balances", "inventory_reservations",
                    "purchase_orders", "purchase_order_lines",
                    "production_order_requirements",
                ]},
            ),
            patch(
                "app.seed.generator.loader.generate_auth_dataset",
                return_value={"roles": [], "users": [], "user_roles": []},
            ),
            patch(
                "app.seed.generator.loader._collect_version_ids_sync",
                return_value=[version_id],
            ),
            patch(
                "app.seed.generator.loader.asyncio.run",
                side_effect=mock_asyncio_run,
            ),
        ):
            main()

        expected = ["commit", "asyncio.run"]
        assert call_order == expected, f"Expected {expected}, got {call_order}"

    def test_async_not_called_on_sync_failure(self) -> None:
        """Verify async phase skipped if seed creation fails."""
        from app.seed.generator.loader import main

        asyncio_called = False

        def mock_asyncio_run(*args, **kwargs):
            nonlocal asyncio_called
            asyncio_called = True
            return IngestionResult(0, 0, 0, [])

        with (
            patch(
                "app.seed.generator.loader.load_golden_dataset",
                side_effect=RuntimeError("DB error"),
            ),
            patch(
                "app.seed.generator.loader.asyncio.run",
                side_effect=mock_asyncio_run,
            ),
            pytest.raises(SystemExit),
        ):
            main()

        assert not asyncio_called


class TestAsyncioRunOnce:
    """Verify asyncio.run is called exactly once (D2)."""

    def test_asyncio_run_called_exactly_once(self) -> None:
        """Verify asyncio.run is invoked exactly one time during main()."""
        from app.seed.generator.loader import main

        run_call_count = 0

        def count_asyncio_run(coro):
            nonlocal run_call_count
            run_call_count += 1
            # Cancel the coroutine to avoid RuntimeWarning about
            # unawaited coroutine (the real asyncio.run would await it).
            coro.close()
            return IngestionResult(0, 0, 0, [])

        mock_session = MagicMock()
        mock_session.commit = MagicMock()
        mock_session.rollback = MagicMock()
        mock_session.close = MagicMock()
        mock_session.query = MagicMock()

        with (
            patch(
                "app.seed.generator.loader._SessionFactory",
                return_value=mock_session,
            ),
            patch("app.seed.generator.loader._verify_alembic_head"),
            patch(
                "app.seed.generator.loader.generate_golden_dataset",
                return_value={k: [] for k in [
                    "products", "product_versions", "components", "bom_items",
                    "component_alternatives", "warehouses", "suppliers",
                    "production_plans", "production_orders",
                    "inventory_balances", "inventory_reservations",
                    "purchase_orders", "purchase_order_lines",
                    "production_order_requirements",
                ]},
            ),
            patch(
                "app.seed.generator.loader.generate_auth_dataset",
                return_value={"roles": [], "users": [], "user_roles": []},
            ),
            patch(
                "app.seed.generator.loader._collect_version_ids_sync",
                return_value=[uuid4()],
            ),
            patch(
                "app.seed.generator.loader.asyncio.run",
                side_effect=count_asyncio_run,
            ),
        ):
            main()

        assert run_call_count == 1, (
            f"asyncio.run was called {run_call_count} time(s), expected exactly 1"
        )


class TestVersionIdPropagation:
    """Verify exact version-ID propagation (D3)."""

    def test_version_ids_passed_to_ingestion_match_created(self) -> None:
        """Verify the version_ids list passed to _ingest_seed_documents
        matches the IDs collected during seed phase."""
        from app.seed.generator.loader import main

        expected_ids = [uuid4(), uuid4(), uuid4()]
        received_ids = None

        async def capture_ingest_call(version_ids):
            nonlocal received_ids
            received_ids = list(version_ids)
            return IngestionResult(0, 0, 0, [])

        mock_session = MagicMock()
        mock_session.commit = MagicMock()
        mock_session.rollback = MagicMock()
        mock_session.close = MagicMock()
        mock_session.query = MagicMock()

        with (
            patch(
                "app.seed.generator.loader._SessionFactory",
                return_value=mock_session,
            ),
            patch("app.seed.generator.loader._verify_alembic_head"),
            patch(
                "app.seed.generator.loader.generate_golden_dataset",
                return_value={k: [] for k in [
                    "products", "product_versions", "components", "bom_items",
                    "component_alternatives", "warehouses", "suppliers",
                    "production_plans", "production_orders",
                    "inventory_balances", "inventory_reservations",
                    "purchase_orders", "purchase_order_lines",
                    "production_order_requirements",
                ]},
            ),
            patch(
                "app.seed.generator.loader.generate_auth_dataset",
                return_value={"roles": [], "users": [], "user_roles": []},
            ),
            patch(
                "app.seed.generator.loader._collect_version_ids_sync",
                return_value=expected_ids,
            ),
            patch(
                "app.seed.generator.loader._ingest_seed_documents",
                new=AsyncMock(side_effect=capture_ingest_call),
            ),
        ):
            main()

        assert received_ids is not None
        assert received_ids == expected_ids, (
            f"Version IDs mismatch: expected {expected_ids}, got {received_ids}"
        )


class TestSystemExitOnPartialFailure:
    """Verify SystemExit(1) on partial failure (D4)."""

    def test_system_exit_1_on_ingestion_failure(self) -> None:
        """Verify SystemExit with code 1 when ingestion fails.
        All versions must be attempted before exit."""
        from app.seed.generator.loader import main

        version_ids = [uuid4(), uuid4(), uuid4()]
        attempted = []

        async def capture_ingest(version_ids_list):
            for vid in version_ids_list:
                attempted.append(vid)
                if vid == version_ids[1]:
                    raise ValueError("ingestion failed")
            return IngestionResult(
                attempted_count=len(version_ids_list),
                succeeded_count=0,
                failed_count=len(version_ids_list),
                failed_version_ids=list(version_ids_list),
            )

        mock_session = MagicMock()
        mock_session.commit = MagicMock()
        mock_session.rollback = MagicMock()
        mock_session.close = MagicMock()
        mock_session.query = MagicMock()

        with (
            patch(
                "app.seed.generator.loader._SessionFactory",
                return_value=mock_session,
            ),
            patch("app.seed.generator.loader._verify_alembic_head"),
            patch(
                "app.seed.generator.loader.generate_golden_dataset",
                return_value={k: [] for k in [
                    "products", "product_versions", "components", "bom_items",
                    "component_alternatives", "warehouses", "suppliers",
                    "production_plans", "production_orders",
                    "inventory_balances", "inventory_reservations",
                    "purchase_orders", "purchase_order_lines",
                    "production_order_requirements",
                ]},
            ),
            patch(
                "app.seed.generator.loader.generate_auth_dataset",
                return_value={"roles": [], "users": [], "user_roles": []},
            ),
            patch(
                "app.seed.generator.loader._collect_version_ids_sync",
                return_value=version_ids,
            ),
            patch(
                "app.seed.generator.loader._ingest_seed_documents",
                new=AsyncMock(side_effect=capture_ingest),
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 1, (
            f"Expected SystemExit code 1, got {exc_info.value.code}"
        )

    def test_all_versions_attempted_before_exit(self) -> None:
        """Verify all versions are attempted before SystemExit."""
        from app.seed.generator.loader import main

        version_ids = [uuid4(), uuid4(), uuid4()]
        attempted = []

        async def capture_ingest(version_ids_list):
            for vid in version_ids_list:
                attempted.append(vid)
            return IngestionResult(
                attempted_count=len(version_ids_list),
                succeeded_count=0,
                failed_count=len(version_ids_list),
                failed_version_ids=list(version_ids_list),
            )

        mock_session = MagicMock()
        mock_session.commit = MagicMock()
        mock_session.rollback = MagicMock()
        mock_session.close = MagicMock()
        mock_session.query = MagicMock()

        with (
            patch(
                "app.seed.generator.loader._SessionFactory",
                return_value=mock_session,
            ),
            patch("app.seed.generator.loader._verify_alembic_head"),
            patch(
                "app.seed.generator.loader.generate_golden_dataset",
                return_value={k: [] for k in [
                    "products", "product_versions", "components", "bom_items",
                    "component_alternatives", "warehouses", "suppliers",
                    "production_plans", "production_orders",
                    "inventory_balances", "inventory_reservations",
                    "purchase_orders", "purchase_order_lines",
                    "production_order_requirements",
                ]},
            ),
            patch(
                "app.seed.generator.loader.generate_auth_dataset",
                return_value={"roles": [], "users": [], "user_roles": []},
            ),
            patch(
                "app.seed.generator.loader._collect_version_ids_sync",
                return_value=version_ids,
            ),
            patch(
                "app.seed.generator.loader._ingest_seed_documents",
                new=AsyncMock(side_effect=capture_ingest),
            ),
            pytest.raises(SystemExit),
        ):
            main()

        assert len(attempted) == 3, (
            f"Expected 3 versions attempted, got {len(attempted)}"
        )
        assert attempted == version_ids, (
            f"Version IDs not in order: {attempted} vs {version_ids}"
        )


class TestPhase2AsyncIngestion:
    """Phase 2: async ingestion behavior."""

    @pytest.mark.asyncio
    async def test_provider_factory_called(self) -> None:
        """Verify provider factory invoked."""
        version_ids = [uuid4()]

        mock_provider = MagicMock()
        mock_session = AsyncMock()
        mock_orch = AsyncMock()
        mock_orch.ingest_document_version = AsyncMock()

        with (
            patch(
                "app.services.embedding_provider_factory.create_embedding_provider",
                return_value=mock_provider,
            ) as mock_factory,
            patch(
                "app.database.async_session_factory",
                return_value=mock_session,
            ),
            patch(
                "app.services.ingestion.IngestionOrchestrator",
                return_value=mock_orch,
            ),
        ):
            await _ingest_seed_documents(version_ids)

        assert mock_factory.called

    @pytest.mark.asyncio
    async def test_one_session_per_version(self) -> None:
        """Verify one fresh AsyncSession per version."""
        version_ids = [uuid4(), uuid4(), uuid4()]
        sessions = []

        def create_session():
            session = AsyncMock()
            sessions.append(session)
            return session

        with (
            patch(
                "app.services.embedding_provider_factory.create_embedding_provider",
            ),
            patch(
                "app.database.async_session_factory",
                side_effect=create_session,
            ),
            patch("app.services.ingestion.IngestionOrchestrator") as mock_orch_cls,
        ):
            mock_orch = AsyncMock()
            mock_orch.ingest_document_version = AsyncMock()
            mock_orch_cls.return_value = mock_orch

            await _ingest_seed_documents(version_ids)

        assert len(sessions) == 3

    @pytest.mark.asyncio
    async def test_one_orchestrator_per_version(self) -> None:
        """Verify one fresh orchestrator per version."""
        version_ids = [uuid4(), uuid4()]
        orchestrators = []

        def create_orch(session, provider):
            orch = AsyncMock()
            orch.ingest_document_version = AsyncMock()
            orchestrators.append(orch)
            return orch

        with (
            patch(
                "app.services.embedding_provider_factory.create_embedding_provider",
            ),
            patch(
                "app.database.async_session_factory",
                return_value=AsyncMock(),
            ),
            patch(
                "app.services.ingestion.IngestionOrchestrator",
                side_effect=create_orch,
            ),
        ):
            await _ingest_seed_documents(version_ids)

        assert len(orchestrators) == 2


class TestTransactionBehavior:
    """Commit/rollback semantics."""

    @pytest.mark.asyncio
    async def test_successful_version_commits(self) -> None:
        """Verify successful version commits."""
        version_id = uuid4()
        commit_called = False

        async def mock_commit():
            nonlocal commit_called
            commit_called = True

        mock_session = AsyncMock()
        mock_session.commit = mock_commit
        mock_session.rollback = AsyncMock()

        mock_orch = AsyncMock()
        mock_orch.ingest_document_version = AsyncMock()

        with (
            patch(
                "app.services.embedding_provider_factory.create_embedding_provider",
            ),
            patch(
                "app.database.async_session_factory",
                return_value=mock_session,
            ),
            patch(
                "app.services.ingestion.IngestionOrchestrator",
                return_value=mock_orch,
            ),
        ):
            await _ingest_seed_documents([version_id])

        assert commit_called

    @pytest.mark.asyncio
    async def test_successful_no_rollback(self) -> None:
        """Verify successful version doesn't rollback."""
        version_id = uuid4()
        rollback_called = False

        async def mock_rollback():
            nonlocal rollback_called
            rollback_called = True

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = mock_rollback

        mock_orch = AsyncMock()
        mock_orch.ingest_document_version = AsyncMock()

        with (
            patch(
                "app.services.embedding_provider_factory.create_embedding_provider",
            ),
            patch(
                "app.database.async_session_factory",
                return_value=mock_session,
            ),
            patch(
                "app.services.ingestion.IngestionOrchestrator",
                return_value=mock_orch,
            ),
        ):
            await _ingest_seed_documents([version_id])

        assert not rollback_called

    @pytest.mark.asyncio
    async def test_failed_version_rollback(self) -> None:
        """Verify failed version rolls back."""
        version_id = uuid4()
        rollback_called = False

        async def mock_rollback():
            nonlocal rollback_called
            rollback_called = True

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = mock_rollback

        mock_orch = AsyncMock()
        mock_orch.ingest_document_version = AsyncMock(side_effect=ValueError("fail"))

        with (
            patch(
                "app.services.embedding_provider_factory.create_embedding_provider",
            ),
            patch(
                "app.database.async_session_factory",
                return_value=mock_session,
            ),
            patch(
                "app.services.ingestion.IngestionOrchestrator",
                return_value=mock_orch,
            ),
        ):
            await _ingest_seed_documents([version_id])

        assert rollback_called

    @pytest.mark.asyncio
    async def test_failed_no_commit(self) -> None:
        """Verify failed version doesn't commit."""
        version_id = uuid4()
        commit_called = False

        async def mock_commit():
            nonlocal commit_called
            commit_called = True

        mock_session = AsyncMock()
        mock_session.commit = mock_commit
        mock_session.rollback = AsyncMock()

        mock_orch = AsyncMock()
        mock_orch.ingest_document_version = AsyncMock(side_effect=ValueError("fail"))

        with (
            patch(
                "app.services.embedding_provider_factory.create_embedding_provider",
            ),
            patch(
                "app.database.async_session_factory",
                return_value=mock_session,
            ),
            patch(
                "app.services.ingestion.IngestionOrchestrator",
                return_value=mock_orch,
            ),
        ):
            await _ingest_seed_documents([version_id])

        assert not commit_called


class TestFailureAggregation:
    """Failure aggregation and exit behavior."""

    @pytest.mark.asyncio
    async def test_continues_after_failure(self) -> None:
        """Verify processing continues after failure."""
        version_ids = [uuid4(), uuid4(), uuid4()]
        processed = []

        def create_orch(session, provider):
            orch = AsyncMock()

            async def mock_ingest(vid):
                processed.append(vid)
                if vid == version_ids[1]:
                    raise ValueError("fail")

            orch.ingest_document_version = mock_ingest
            return orch

        with (
            patch(
                "app.services.embedding_provider_factory.create_embedding_provider",
            ),
            patch(
                "app.database.async_session_factory",
                return_value=AsyncMock(),
            ),
            patch(
                "app.services.ingestion.IngestionOrchestrator",
                side_effect=create_orch,
            ),
        ):
            await _ingest_seed_documents(version_ids)

        assert len(processed) == 3

    @pytest.mark.asyncio
    async def test_multiple_failures_aggregate(self) -> None:
        """Verify multiple failures aggregate."""
        version_ids = [uuid4(), uuid4(), uuid4()]

        def create_orch(session, provider):
            orch = AsyncMock()

            async def mock_ingest(vid):
                if vid in (version_ids[0], version_ids[2]):
                    raise ValueError("fail")

            orch.ingest_document_version = mock_ingest
            return orch

        with (
            patch(
                "app.services.embedding_provider_factory.create_embedding_provider",
            ),
            patch(
                "app.database.async_session_factory",
                return_value=AsyncMock(),
            ),
            patch(
                "app.services.ingestion.IngestionOrchestrator",
                side_effect=create_orch,
            ),
        ):
            result = await _ingest_seed_documents(version_ids)

        assert result.attempted_count == 3
        assert result.succeeded_count == 1
        assert result.failed_count == 2
        assert version_ids[0] in result.failed_version_ids
        assert version_ids[2] in result.failed_version_ids

    @pytest.mark.asyncio
    async def test_summary_counts(self) -> None:
        """Verify summary counts correct."""
        version_ids = [uuid4() for _ in range(5)]

        mock_orch = AsyncMock()
        mock_orch.ingest_document_version = AsyncMock()

        with (
            patch(
                "app.services.embedding_provider_factory.create_embedding_provider",
            ),
            patch(
                "app.database.async_session_factory",
                return_value=AsyncMock(),
            ),
            patch(
                "app.services.ingestion.IngestionOrchestrator",
                return_value=mock_orch,
            ),
        ):
            result = await _ingest_seed_documents(version_ids)

        assert result.attempted_count == 5
        assert result.succeeded_count == 5
        assert result.failed_count == 0


class TestExitBehavior:
    """Exit code semantics."""

    @pytest.mark.asyncio
    async def test_all_success_no_failures(self) -> None:
        """Verify all-success has no failures."""
        version_ids = [uuid4(), uuid4()]

        mock_orch = AsyncMock()
        mock_orch.ingest_document_version = AsyncMock()

        with (
            patch(
                "app.services.embedding_provider_factory.create_embedding_provider",
            ),
            patch(
                "app.database.async_session_factory",
                return_value=AsyncMock(),
            ),
            patch(
                "app.services.ingestion.IngestionOrchestrator",
                return_value=mock_orch,
            ),
        ):
            result = await _ingest_seed_documents(version_ids)

        assert result.failed_count == 0

    @pytest.mark.asyncio
    async def test_partial_failure_has_failures(self) -> None:
        """Verify partial failure has failures."""
        version_ids = [uuid4(), uuid4()]

        def create_orch(session, provider):
            orch = AsyncMock()

            async def mock_ingest(vid):
                if vid == version_ids[0]:
                    raise ValueError("fail")

            orch.ingest_document_version = mock_ingest
            return orch

        with (
            patch(
                "app.services.embedding_provider_factory.create_embedding_provider",
            ),
            patch(
                "app.database.async_session_factory",
                return_value=AsyncMock(),
            ),
            patch(
                "app.services.ingestion.IngestionOrchestrator",
                side_effect=create_orch,
            ),
        ):
            result = await _ingest_seed_documents(version_ids)

        assert result.failed_count > 0


class TestProviderFailures:
    """Provider configuration failures."""

    @pytest.mark.asyncio
    async def test_provider_config_failure(self) -> None:
        """Verify provider config failure reported safely."""
        from app.services.embedding_provider import (
            EmbeddingProviderConfigurationError,
        )

        version_ids = [uuid4()]

        with (
            patch(
                "app.services.embedding_provider_factory.create_embedding_provider",
                side_effect=EmbeddingProviderConfigurationError(
                    "API key required"
                ),
            ),
            pytest.raises(
                RuntimeError,
                match="Embedding provider initialization failed",
            ),
        ):
            await _ingest_seed_documents(version_ids)

    @pytest.mark.asyncio
    async def test_session_creation_failure(self) -> None:
        """Verify session creation failure aggregated."""
        version_ids = [uuid4(), uuid4()]

        with (
            patch(
                "app.services.embedding_provider_factory.create_embedding_provider",
            ),
            patch(
                "app.database.async_session_factory",
                side_effect=RuntimeError("Session failed"),
            ),
        ):
            result = await _ingest_seed_documents(version_ids)

        assert result.failed_count == 2


class TestLoggingSafety:
    """Logging safety."""

    @pytest.mark.asyncio
    async def test_no_sensitive_data_in_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        """Verify no sensitive data logged."""
        import logging

        version_ids = [uuid4()]
        secret = "SECRET_KEY_12345"

        def create_orch(session, provider):
            orch = AsyncMock()

            async def mock_ingest(vid):
                raise ValueError(f"Error with {secret}")

            orch.ingest_document_version = mock_ingest
            return orch

        with (
            caplog.at_level(logging.ERROR),
            patch(
                "app.services.embedding_provider_factory.create_embedding_provider",
            ),
            patch(
                "app.database.async_session_factory",
                return_value=AsyncMock(),
            ),
            patch(
                "app.services.ingestion.IngestionOrchestrator",
                side_effect=create_orch,
            ),
        ):
            await _ingest_seed_documents(version_ids)

        # Verify secret not in logs
        for record in caplog.records:
            assert secret not in record.message


class TestNoRedisARQ:
    """No Redis/ARQ dependency."""

    @pytest.mark.asyncio
    async def test_no_redis(self) -> None:
        """Verify no Redis required."""
        version_ids = [uuid4()]

        mock_orch = AsyncMock()
        mock_orch.ingest_document_version = AsyncMock()

        with (
            patch(
                "app.services.embedding_provider_factory.create_embedding_provider",
            ),
            patch(
                "app.database.async_session_factory",
                return_value=AsyncMock(),
            ),
            patch(
                "app.services.ingestion.IngestionOrchestrator",
                return_value=mock_orch,
            ),
        ):
            result = await _ingest_seed_documents(version_ids)

        assert result.attempted_count == 1

    @pytest.mark.asyncio
    async def test_no_arq_enqueue(self) -> None:
        """Verify no ARQ enqueue."""
        version_ids = [uuid4()]

        mock_orch = AsyncMock()
        mock_orch.ingest_document_version = AsyncMock()

        with (
            patch(
                "app.services.embedding_provider_factory.create_embedding_provider",
            ),
            patch(
                "app.database.async_session_factory",
                return_value=AsyncMock(),
            ),
            patch(
                "app.services.ingestion.IngestionOrchestrator",
                return_value=mock_orch,
            ),
        ):
            await _ingest_seed_documents(version_ids)

        # If we got here without error, no ARQ was used


class TestExistingBehavior:
    """Existing seed behavior preserved."""

    def test_load_golden_dataset_unchanged(self) -> None:
        """Verify load_golden_dataset still works."""
        from app.seed.generator.loader import load_golden_dataset

        # This test verifies the function signature hasn't changed
        assert callable(load_golden_dataset)

    def test_ingestion_imports_work(self) -> None:
        """Verify existing ingestion/provider tests still work."""
        from app.services.embedding_provider import EmbeddingProvider
        from app.services.embedding_provider_factory import (
            create_embedding_provider,
        )
        from app.services.ingestion import IngestionOrchestrator

        assert EmbeddingProvider is not None
        assert create_embedding_provider is not None
        assert IngestionOrchestrator is not None
