"""FastAPI application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import router as auth_router
from app.api.middleware.correlation import CorrelationIdMiddleware
from app.config import settings
from app.core.build_info import get_build_info
from app.core.context import get_correlation_id
from app.core.dataset_metadata import CHECKSUM_ALGORITHM, DATASET_VERSION, EXPECTED_CHECKSUM
from app.core.logging import configure_logging, get_logger
from app.database import get_async_session
from app.schemas.dataset import DatasetStatusResponse
from app.schemas.diagnostic import DiagnosticCreateResponse, DiagnosticJobResponse
from app.services.dataset_integrity import DatasetIntegrityService
from app.services.dependency_health import check_all_dependencies
from app.services.diagnostic_jobs import enqueue_diagnostic_job, get_diagnostic_job


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

# Authentication router (WP-2.6)
app.include_router(auth_router, prefix=settings.api_v1_prefix)


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
            detail = check.detail or ""
            if check.status == "ok" and detail.startswith("revision "):
                revision = detail[len("revision ") :]
                checks[pk] = revision if revision else "unknown"
            else:
                checks[pk] = "unknown"

        elif check.name in ("postgresql", "redis"):
            if check.status == "ok":
                checks[pk] = "ok"
            else:
                detail = check.detail if check.detail else "unavailable"
                checks[pk] = f"error: {detail}"

        else:
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
    """Enqueue a diagnostic background job."""
    correlation_id = get_correlation_id()
    if correlation_id is None:  # pragma: no cover - middleware invariant
        raise RuntimeError("Correlation ID is not bound in request context")
    return await enqueue_diagnostic_job(correlation_id=correlation_id)


@app.get(
    f"{settings.api_v1_prefix}/system/diagnostics/{{job_id}}",
    response_model=DiagnosticJobResponse,
    status_code=200,
    tags=["System"],
)
async def get_diagnostic_status(job_id: UUID) -> DiagnosticJobResponse:
    """Retrieve diagnostic job status and results."""
    result = await get_diagnostic_job(job_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "diagnostic_job_not_found",
                "job_id": str(job_id),
            },
        )
    return result


@app.get(
    f"{settings.api_v1_prefix}/system/dataset/status",
    response_model=DatasetStatusResponse,
    status_code=200,
    tags=["System"],
)
async def get_dataset_status(
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> DatasetStatusResponse:
    """Verify Golden Dataset integrity.

    Computes a semantic checksum of the current database state and compares it
    against the expected checksum for the approved Golden Dataset fixture.

    Status semantics:
    - ``valid``: all collections match the approved fixture exactly
    - ``invalid``: dataset exists but differs semantically
    - ``not_loaded``: all Golden Dataset business tables are empty

    Infrastructure failures return HTTP 500 (not ``not_loaded``).
    """
    try:
        service = DatasetIntegrityService(session)
        counts = await service.get_entity_counts()
        all_zero = all(count == 0 for count in counts.values())

        if all_zero:
            return DatasetStatusResponse(
                status="not_loaded",
                dataset_version=DATASET_VERSION,
                checksum_algorithm=CHECKSUM_ALGORITHM,
                expected_checksum=EXPECTED_CHECKSUM,
                actual_checksum=None,
            )

        actual_checksum = await service.compute_actual_checksum()
        status: Literal["valid", "invalid"] = (
            "valid" if actual_checksum == EXPECTED_CHECKSUM else "invalid"
        )

        return DatasetStatusResponse(
            status=status,
            dataset_version=DATASET_VERSION,
            checksum_algorithm=CHECKSUM_ALGORITHM,
            expected_checksum=EXPECTED_CHECKSUM,
            actual_checksum=actual_checksum,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "dataset_integrity_verification_failed",
                "message": "Dataset integrity verification failed due to an internal error.",
            },
        ) from e


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint providing API information."""
    return {
        "name": "ForgeMind AI Operations",
        "version": app.version,
        "docs": "/docs",
    }
