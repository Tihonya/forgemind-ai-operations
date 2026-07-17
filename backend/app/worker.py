"""ARQ Worker configuration for ForgeMind background jobs."""

from typing import Any
from urllib.parse import urlparse

from arq.connections import RedisSettings

from app.config import settings
from app.jobs.diagnostics import run_diagnostic_job


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


_redis_host, _redis_port, _redis_db, _redis_password = _parse_redis_url(settings.redis_url)


class WorkerSettings:
    """ARQ worker settings for ForgeMind background task processing."""

    functions: list[Any] = [run_diagnostic_job]
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
