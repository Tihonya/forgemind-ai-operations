"""Database URL resolution for integration tests.

Supports both CI environment (env vars) and local development (.env fallback).
"""

import os
import re
import urllib.parse
from pathlib import Path


def get_test_database_url() -> str:
    """Resolve database URL with precedence:

    1. TEST_DATABASE_URL env var (if set)
    2. DATABASE_URL env var (if set)
    3. Local .env file fallback (if exists)
    4. Empty string (tests should skip)

    Does not catch broad exceptions around configuration parsing.
    Does not log credentials or full connection strings.
    """
    # 1. Check TEST_DATABASE_URL
    if url := os.environ.get("TEST_DATABASE_URL"):
        return url

    # 2. Check DATABASE_URL
    if url := os.environ.get("DATABASE_URL"):
        return url

    # 3. Local .env fallback
    test_file_dir = Path(__file__).resolve().parent
    env_file = test_file_dir.parent.parent / ".env"

    if not env_file.is_file():
        return ""

    # Parse .env and resolve placeholders
    env_vars: dict[str, str] = {}
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env_vars[key.strip()] = value.strip()

    def interpolate(value: str) -> str:
        pattern = re.compile(r"\$\{(\w+)\}")

        def replacer(match: re.Match[str]) -> str:
            var_name: str = match.group(1)
            return env_vars.get(var_name, match.group(0))

        prev: str | None = None
        while prev != value:
            prev = value
            value = pattern.sub(replacer, value)
        return value

    user = interpolate(env_vars.get("POSTGRES_USER", ""))
    password = interpolate(env_vars.get("POSTGRES_PASSWORD", ""))
    host = "localhost"
    port = interpolate(env_vars.get("POSTGRES_PORT", "5432"))
    db = interpolate(env_vars.get("POSTGRES_DB", ""))

    # URL-encode password for special characters
    password_encoded = urllib.parse.quote_plus(password)

    return f"postgresql+asyncpg://{user}:{password_encoded}@{host}:{port}/{db}"
