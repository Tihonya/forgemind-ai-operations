"""Build information and version metadata for ForgeMind backend.

Provides an immutable, typed BuildInfo value object that aggregates application
version, Git SHA, environment, and application name from deployment metadata,
environment variables, and the configuration layer.

Usage:
    from app.core.build_info import get_build_info

    info = get_build_info()
    print(info.version, info.git_sha)

    # With overrides (for testing or runtime injection):
    info = get_build_info(version_override="1.2.3", git_sha_override="abc1234")

This module does not execute subprocess commands at import time. Git SHA
resolution is deferred until explicitly requested via get_build_info() or
_resolve_git_sha().
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version

from app.config import settings


@dataclass(frozen=True)
class BuildInfo:
    """Immutable build information value object.

    Attributes:
        application_name: The package/application name (e.g., "forgemind-backend").
        version: Application version string (from package metadata or fallback).
        git_sha: Git commit SHA (full or short, lowercase hex) or "unknown".
        environment: Runtime environment (e.g., "development", "production").
    """

    application_name: str
    version: str
    git_sha: str
    environment: str


def _get_version() -> str:
    """Resolve application version from installed package metadata.

    Returns:
        Version string from importlib.metadata, or "0.0.0-dev" fallback for
        editable installs or when the package is not formally installed.
    """
    try:
        return version("forgemind-backend")
    except PackageNotFoundError:
        # Fallback for editable installs, local development, or tests
        # where the package metadata is not available.
        return "0.0.0-dev"


def _normalize_git_sha(value: str) -> str:
    """Normalize a Git SHA to lowercase hexadecimal or return "unknown".

    Accepts full (40-char) or short (7+ char) SHAs. Rejects non-hex characters,
    empty strings, and values outside the valid length range.

    Args:
        value: Raw SHA string (may contain whitespace, mixed case).

    Returns:
        Normalized lowercase hex SHA, or "unknown" if invalid.
    """
    normalized = value.strip().lower()
    if 7 <= len(normalized) <= 40 and all(c in "0123456789abcdef" for c in normalized):
        return normalized
    return "unknown"


def _resolve_git_sha(env_var: str = "FORGEMIND_GIT_SHA") -> str:
    """Resolve Git SHA with priority: environment variable > git command > "unknown".

    Resolution order:
    1. Explicit environment variable (FORGEMIND_GIT_SHA by default).
    2. Local Git repository lookup via subprocess (bounded timeout, no shell).
    3. "unknown" fallback when Git is unavailable or the command fails.

    Args:
        env_var: Name of the environment variable to check first.

    Returns:
        Normalized Git SHA string (lowercase hex) or "unknown".
    """
    # Priority 1: explicit environment variable
    sha_from_env = os.getenv(env_var)
    if sha_from_env:
        return _normalize_git_sha(sha_from_env)

    # Priority 2: local Git repository lookup
    git_cmd = shutil.which("git")
    if not git_cmd:
        return "unknown"
    try:
        result = subprocess.run(  # noqa: S603
            [git_cmd, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
            shell=False,
        )
        if result.returncode == 0 and result.stdout:
            return _normalize_git_sha(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        # Git executable not found, command timed out, or other OS-level error.
        pass

    # Priority 3: fallback
    return "unknown"


def get_build_info(
    *,
    application_name: str | None = None,
    version_override: str | None = None,
    git_sha_override: str | None = None,
    environment_override: str | None = None,
) -> BuildInfo:
    """Build a BuildInfo instance with optional overrides for test injection.

    All resolution logic is deferred until this function is called. No subprocess
    commands or environment probes execute at module import time.

    Args:
        application_name: Override for the application name (default: "forgemind-backend").
        version_override: Override for the version (default: auto-detected from package metadata).
        git_sha_override: Override for the Git SHA (default: auto-detected from env var or git).
        environment_override: Override for the environment (default: from Settings).

    Returns:
        Immutable BuildInfo value object.
    """
    return BuildInfo(
        application_name=application_name or "forgemind-backend",
        version=version_override or _get_version(),
        git_sha=git_sha_override or _resolve_git_sha(),
        environment=environment_override or settings.environment,
    )
