# Build stage for dependencies
FROM python:3.12-slim AS builder

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency specification and a stub package so hatchling can build
COPY backend/pyproject.toml ./backend/
RUN mkdir -p ./backend/app && touch ./backend/app/__init__.py

# Install Python dependencies from the builder context
WORKDIR /app/backend
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir ".[dev]"

# Development stage
FROM python:3.12-slim AS development

WORKDIR /app

# Install runtime system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/uvicorn /usr/local/bin/uvicorn

# Copy application code
COPY backend/app/ ./backend/app/
COPY backend/pyproject.toml ./backend/
# Alembic packaging (develop/compose parity): seed head verification
# (loader._find_alembic_ini) expects backend/alembic.ini alongside the
# backend package, and alembic's script_location resolves relative to it.
COPY backend/alembic.ini ./backend/alembic.ini
COPY backend/alembic/ ./backend/alembic/

# Set Python path
ENV PYTHONPATH=/app/backend
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Development/CI image default: deterministic offline embeddings for the
# seeded Golden RAG corpus (never used in production). The production
# stage enforces EMBEDDING_PROVIDER=openai through the deployment
# environment and rejects fakes fail-closed (provider factory).
ENV EMBEDDING_PROVIDER=fake

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Production stage
FROM python:3.12-slim AS production

WORKDIR /app

# Install runtime system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/uvicorn /usr/local/bin/uvicorn

# Copy application code
COPY backend/app/ ./app/
# Alembic packaging (production seed path): loader._find_alembic_ini
# resolves <module_root>/alembic.ini where module_root = /app in this
# stage, and alembic's script_location %(here)s/alembic resolves the
# migration tree at /app/alembic.
COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic/ ./alembic/

# Set Python path
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV ENVIRONMENT=production

# Non-root user
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command.
# Release 1 host has 2 vCPU (DEC-057, 2026-08-21): 2 workers, one per
# vCPU. ARQ handles background work separately; the Redis-backed
# distributed rate limiter already prevents per-process budget
# multiplication. The development stage command is unchanged.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
