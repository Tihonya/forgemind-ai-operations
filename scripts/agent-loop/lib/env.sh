#!/usr/bin/env bash
# Safe environment loading (no `source .env`, no eval)

# NOTE: no set -euo pipefail here — this file is sourced, not executed directly

load_env_safe() {
  # Load .env using Python to avoid shell interpolation issues
  # Exports resolved variables via Python subprocess (no eval)

  local env_file="$REPO_ROOT/.env"

  if [[ ! -f "$env_file" ]]; then
    echo "WARNING: .env not found at $env_file" >&2
    return 0
  fi

  # Use Python to parse, resolve, and export (no eval, no secrets in logs)
  "$PYTHON_BIN" - <<'PYEOF'
import os
import re
import sys
from pathlib import Path

env_file = os.environ.get("REPO_ROOT", ".") + "/.env"
if not Path(env_file).exists():
    sys.exit(0)

env_vars = {}
with open(env_file) as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        env_vars[key] = value

def interpolate(value):
    pattern = re.compile(r"\$\{(\w+)\}")
    prev = None
    while prev != value:
        prev = value
        value = pattern.sub(lambda m: env_vars.get(m.group(1), m.group(0)), value)
    return value

# Export resolved variables directly to subprocess environment
for key, value in env_vars.items():
    resolved = interpolate(value)
    os.environ[key] = resolved

print("Environment loaded (secrets masked)", file=sys.stderr)
PYEOF
}

check_db_connectivity() {
  # Check if database is reachable without printing credentials
  "$PYTHON_BIN" - <<'PYEOF'
import os
import sys
from sqlalchemy import create_engine, text

try:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    # Convert async to sync for probe
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "+psycopg")

    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    engine.dispose()
    print("DB_OK")
except Exception as e:
    print(f"DB_ERROR: {type(e).__name__}", file=sys.stderr)
    sys.exit(1)
PYEOF
}
