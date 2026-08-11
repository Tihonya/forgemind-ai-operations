"""ARQ Worker configuration for ForgeMind background jobs."""

from typing import Any
from urllib.parse import urlparse

from arq import func
from arq.connections import RedisSettings
from arq.cron import cron

from app.ai.workflow.reconciler import (
    CRON_TIMEOUT_SECONDS,
    RECONCILER_INTERVAL_SECONDS,
    reconcile_stale_pending_runs,
)
from app.ai.workflow.worker import workflow_retry, workflow_start
from app.config import settings
from app.jobs.diagnostics import run_diagnostic_job
from app.jobs.ingestion import run_document_ingestion


async def startup(ctx: dict[str, object]) -> None:
    """Worker startup hook.

    Args:
        ctx: ARQ worker context dictionary.
    """
    ctx["state"] = "started"


async def shutdown(ctx: dict[str, object]) -> None:
    """Worker shutdown hook.

    Args:
        ctx: ARQ worker context dictionary.
    """
    ctx["state"] = "stopped"


def _parse_redis_url(url: str) -> tuple[str, int, int, str | None]:
    """Parse Redis URL into components.

    Args:
        url: Redis connection URL.

    Returns:
        Tuple of (host, port, db, password).
    """
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    db = int(parsed.path.lstrip("/") or 0)
    password = parsed.password
    return host, port, db, password


def _build_redis_settings() -> Any:
    """Build ARQ RedisSettings from app config without connecting.

    Used by the reconciler to create its own pool.
    """
    return RedisSettings(
        host=_redis_host,
        port=_redis_port,
        database=_redis_db,
        password=_redis_password,
    )


_redis_host, _redis_port, _redis_db, _redis_password = _parse_redis_url(settings.redis_url)


class WorkerSettings:
    """ARQ worker settings for ForgeMind background task processing."""

    functions: list[Any] = [
        run_diagnostic_job,
        func(run_document_ingestion, keep_result=300, max_tries=3),
        # WP-REC-03F D5 §5: workflow worker functions.
        # keep_result=0 — no ARQ result key stored (D5 §6).
        # max_tries=1 — no ARQ automatic retry (D5 §6).
        # timeout from settings.arq_job_timeout (D5 §6).
        func(
            workflow_start,
            keep_result=0,
            max_tries=1,
            timeout=settings.arq_job_timeout,
        ),
        func(
            workflow_retry,
            keep_result=0,
            max_tries=1,
            timeout=settings.arq_job_timeout,
        ),
    ]
    on_startup = startup
    on_shutdown = shutdown
    queue_name = settings.arq_queue_name
    job_timeout = settings.arq_job_timeout
    redis_settings = RedisSettings(
        host=_redis_host,
        port=_redis_port,
        database=_redis_db,
        password=_redis_password,
    )
    # WP-REC-03F D6 §4: Reconciler cron job registration.
    cron_jobs = [
        cron(
            reconcile_stale_pending_runs,
            hour=None,
            minute=None,
            second=RECONCILER_INTERVAL_SECONDS,
            timeout=CRON_TIMEOUT_SECONDS,
            unique=True,
        ),
    ]
