"""Health and dependency-check response schemas.

Defines typed, validation-safe models for dependency health status.
No connection strings, credentials, or exception details are exposed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

# Dependency status enum: ok | error | unknown
DependencyStatus = Literal["ok", "error", "unknown"]


class DependencyCheck(BaseModel):
    """Result of a single dependency health check.

    Attributes:
        name: Dependency identifier (e.g., "postgresql", "redis", "alembic", "worker").
        status: Check outcome: "ok" = healthy, "error" = failed, "unknown" = not configured.
        latency_ms: Time taken to perform the check (milliseconds, non-negative).
        detail: Optional human-readable description or safe error summary.
            Never contains connection strings, credentials, or stack traces.
    """

    name: str = Field(..., description="Dependency name")
    status: DependencyStatus = Field(..., description="Check status")
    latency_ms: float = Field(..., ge=0.0, description="Check duration in milliseconds")
    detail: str | None = Field(None, description="Optional safe detail message")


class DependencyHealthSnapshot(BaseModel):
    """Aggregate snapshot of all dependency health checks.

    Attributes:
        timestamp: When the snapshot was taken (UTC).
        checks: List of individual dependency check results.
            Order is not guaranteed; consumers should look up by name.
        summary: Overall health status: "healthy" (all ok), "degraded" (some error),
            "unhealthy" (all critical deps error), "unknown" (no checks performed).
    """

    timestamp: datetime = Field(..., description="Snapshot timestamp (UTC)")
    checks: list[DependencyCheck] = Field(..., description="Individual check results")
    summary: Literal["healthy", "degraded", "unhealthy", "unknown"] = Field(
        ..., description="Overall health summary"
    )

    @classmethod
    def from_checks(cls, checks: list[DependencyCheck]) -> DependencyHealthSnapshot:
        """Build a snapshot from a list of checks, computing the summary.

        Args:
            checks: List of dependency check results.

        Returns:
            DependencyHealthSnapshot with computed summary field.
        """
        if not checks:
            summary: Literal["healthy", "degraded", "unhealthy", "unknown"] = "unknown"
        else:
            statuses = [c.status for c in checks]
            critical = ["postgresql", "redis"]  # Critical dependencies
            critical_errors = sum(
                1 for c in checks if c.name in critical and c.status == "error"
            )

            if all(s == "ok" for s in statuses):
                summary = "healthy"
            elif critical_errors == len(critical):
                summary = "unhealthy"
            else:
                summary = "degraded"

        return cls(
            timestamp=datetime.now(UTC),
            checks=checks,
            summary=summary,
        )
