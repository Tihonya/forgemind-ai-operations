"""FastAPI application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware.correlation import CorrelationIdMiddleware
from app.config import settings
from app.core.build_info import get_build_info
from app.core.logging import configure_logging, get_logger


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
async def health_check() -> dict[str, str]:
    """Health check endpoint for container orchestration.

    Returns:
        dict: Status information indicating service health.
    """
    return {"status": "healthy"}


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
