"""FastAPI application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware.correlation import CorrelationIdMiddleware
from app.config import settings
from app.core.build_info import get_build_info
from app.core.context import get_correlation_id
from app.core.logging import configure_logging, get_logger
from app.schemas.diagnostic import DiagnosticCreateResponse
from app.services.dependency_health import check_all_dependencies
from app.services.diagnostic_jobs import enqueue_diagnostic_job


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown events."""
    # Startup
    configure_logging(level=settings.log_level)
    logger = get_logger("app.main")
    build_info = get_build_info()
    logger.info(
        "application_startup",
        application_name=build_info.application_name,
        version=build_info.version,
        git_sha=build_info.git_sha,
        environment=build_info.environment,
    )
    yield
    # Shutdown


app = FastAPI(
    title="ForgeMind AI Operations",
    description="Supply Risk Intelligence API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Correlation ID middleware (outermost — runs first on every request)
app.add_middleware(CorrelationIdMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, Any]:
    """Real health check endpoint with dependency status.

    Returns:
        dict: Health status with flat-string dependency checks and correlation ID.
              The public contract (plan §11.1) uses flat string values, not structured
              objects. Internal DependencyCheck objects are mapped to public strings.

              Public key mapping:
              - "alembic" → "alembic_revision"
              - All other internal names match their public keys
    """
    snapshot = await check_all_dependencies()
    correlation_id = get_correlation_id()

    # Approved public contract (plan §11.1) exposes exactly:
    #   "healthy" | "degraded" | "unhealthy"
    # The internal DependencyHealthSnapshot.summary Literal also includes
    # "unknown" (only when checks list is empty — unreachable in production,
    # but reachable in tests). Map it to "degraded" deterministically so we
    # do not silently extend the public API beyond the approved contract.
    public_status = snapshot.summary
    if public_status == "unknown":
        public_status = "degraded"

    # Public contract: "alembic" → "alembic_revision" (plan §11.1).
    public_key_map = {"alembic": "alembic_revision"}

    # Build checks dict with flat string values per §11.1 contract
    checks: dict[str, Any] = {"backend": "ok"}

    for check in snapshot.checks:
        pk = public_key_map.get(check.name, check.name)

        # Map internal DependencyCheck to public flat string
        if check.name == "worker":
            # worker: ok → "ok", anything else → "unavailable"
            checks[pk] = "ok" if check.status == "ok" else "unavailable"

        elif check.name == "alembic":
            # alembic_revision: extract revision hash from detail on success.
            # The dependency service produces detail exactly as
            # "revision {hash}" (dependency_health.py:141). Only accept the
            # revision when the detail actually starts with that prefix —
            # do not silently strip arbitrary occurrences inside the string.
            detail = check.detail or ""
            if check.status == "ok" and detail.startswith("revision "):
                revision = detail[len("revision "):]
                checks[pk] = revision if revision else "unknown"
            else:
                checks[pk] = "unknown"

        elif check.name in ("postgresql", "redis"):
            # postgresql/redis: ok → "ok", error → "error: <sanitized detail>"
            if check.status == "ok":
                checks[pk] = "ok"
            else:
                # Use already-sanitized detail from DependencyCheck
                # Fallback to "unavailable" when detail is missing
                detail = check.detail if check.detail else "unavailable"
                checks[pk] = f"error: {detail}"

        else:
            # Fallback for any future checks: preserve status as-is
            checks[pk] = check.status

    return {
        "status": public_status,
        "timestamp": snapshot.timestamp.isoformat(),
        "correlation_id": correlation_id,
        "checks": checks,
    }


@app.post(
    f"{settings.api_v1_prefix}/system/diagnostics",
    response_model=DiagnosticCreateResponse,
    status_code=202,
    tags=["System"],
)
async def enqueue_diagnostic() -> DiagnosticCreateResponse:
    """Enqueue a diagnostic background job.

    Approved public contract (plan §11.1):

        POST /api/v1/system/diagnostics → HTTP 202
        {
            "job_id":         "<uuid>",
            "correlation_id": "<uuid-v4>",
            "status":         "pending"
        }

    The correlation_id is inherited from ``CorrelationIdMiddleware``
    (already bound to the current request context). The service creates a
    pending ``DiagnosticJob`` row, commits it, then enqueues the ARQ task
    in a fresh Redis pool. If enqueue fails, the row is transitioned to
    ``failed`` with a safe bounded error message and HTTP 503 is returned.
    """
    correlation_id = get_correlation_id()
    # Middleware is guaranteed to have bound a canonical UUID-v4.
    # Defensive: fail loudly if middleware behaviour regresses.
    if correlation_id is None:  # pragma: no cover - middleware invariant
        raise RuntimeError("Correlation ID is not bound in request context")
    return await enqueue_diagnostic_job(correlation_id=correlation_id)


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint providing API information.

    Returns:
        dict: API metadata including name and version.
    """
    return {
        "name": "ForgeMind AI Operations",
        "version": app.version,
        "docs": "/docs",
    }
