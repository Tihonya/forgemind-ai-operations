"""Unit tests for health check endpoint."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.schemas.health import DependencyCheck, DependencyHealthSnapshot


@pytest.fixture
def healthy_snapshot() -> DependencyHealthSnapshot:
    """Create a healthy snapshot for testing."""
    checks = [
        DependencyCheck(
            name="postgresql", status="ok", latency_ms=2.5, detail="SELECT 1 succeeded"
        ),
        DependencyCheck(name="redis", status="ok", latency_ms=1.2, detail="PING succeeded"),
        DependencyCheck(name="alembic", status="ok", latency_ms=5.1, detail="revision abc12345"),
        DependencyCheck(name="worker", status="ok", latency_ms=0.8, detail="worker alive"),
    ]
    return DependencyHealthSnapshot(
        checks=checks,
        summary="healthy",
        timestamp=datetime(2026, 7, 15, 14, 0, 0, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_health_check(
    client: AsyncClient, healthy_snapshot: DependencyHealthSnapshot
) -> None:
    """Test that health endpoint returns 200 with dependency status."""
    with patch("app.main.check_all_dependencies", new=AsyncMock(return_value=healthy_snapshot)):
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient) -> None:
    """Test that root endpoint returns API information."""
    response = await client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert data["name"] == "ForgeMind AI Operations"
    assert "version" in data
    assert "docs" in data
    assert data["docs"] == "/docs"
