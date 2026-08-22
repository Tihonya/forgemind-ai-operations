#!/usr/bin/env bash
set -euo pipefail

# Worker healthcheck for the ForgeMind ARQ worker.
#
# WP-P7-07 F-2 remediation history:
#   The previous implementation ran `redis-cli -u "$REDIS_URL" ...` (URL
#   userinfo AUTH). Against the deployed redis:7-alpine server this path
#   fails with `AUTH failed: WRONGPASS` although the identical password
#   works via redis-py (the application client) and via explicit
#   `-h/-p/-a` parameters. The healthcheck therefore reported unhealthy
#   forever (FailingStreak grew without bound) although the worker was
#   alive. The URL-userinfo AUTH path is simply not reliable across the
#   redis-cli/client-vs-server versions matrix, so it is no longer used.
#
# THIS SCRIPT:
#   1. parses REDIS_URL deterministically with Python urllib.parse
#      (python3 is present in the worker image; no fragile shell
#      substring parsing; percent-encoded URL-safe passwords accepted);
#   2. connects with explicit `-h/-p/-n` parameters and authenticates via
#      the REDISCLI_AUTH environment variable — the password NEVER
#      appears in a process argument list;
#   3. fails closed: malformed/missing REDIS_URL, non-PONG reply
#      (NOAUTH/WRONGPASS/refused), absent or malformed heartbeat all
#      exit 1 with fixed-text stderr messages only (no secrets echoed).
#
# The original liveness contract is preserved: the ARQ heartbeat key
# {queue}:health-check must exist and be well-formed (ARQ writes
# "{datetime:%b-%d %H:%M:%S} j_complete=... j_failed=..." with a TTL).
#
# Exit codes:
#   0  Redis reachable, AUTH accepted, heartbeat present and well-formed
#   1  anything else

QUEUE_NAME="${ARQ_QUEUE_NAME:-forgemind-tasks}"
# WP-P7-07: fail closed on missing configuration — no implicit localhost
# fallback (a default target could mask misconfiguration or, with a
# local Redis present, produce a false healthy).
REDIS_URL="${REDIS_URL-}"

HEARTBEAT_KEY="${QUEUE_NAME}:health-check"

# ---------------------------------------------------------------------------
# Deterministic REDIS_URL parsing (Release 1 form: redis://:<password>@host:port/0)
#
# python3 reads REDIS_URL from its OWN environment (already set by the
# compose service environment), so the URL never crosses an argv boundary
# — not even argv of the parser helper itself. python3 writes one
# tab-separated line to a pipe (kernel memory); the parent shell reads it
# straight into variables before the pipeline closes. The password never
# reaches this script's stdout/stderr (the process substitution consumes
# it) and never appears in any argv.
# ---------------------------------------------------------------------------
read -r REDIS_HOST REDIS_PORT REDIS_DB REDIS_PASSWORD < <(
    python3 - <<'PYEOF'
import os, sys
from urllib.parse import urlsplit, unquote

url = os.environ.get("REDIS_URL", "")
if not url:
    sys.exit(2)  # missing/empty
try:
    p = urlsplit(url)
except ValueError:
    sys.exit(3)  # unparsable (e.g. bad IPv6 literal)
if p.scheme != "redis":
    sys.exit(4)  # wrong scheme
if p.hostname is None:
    sys.exit(5)  # no TCP host (unix-socket forms unsupported here)
if p.username not in (None, ""):
    sys.exit(6)  # user-scoped credentials are not an approved shape

password = "" if p.password is None else unquote(p.password)
# URL-safe alphabet only: raw whitespace/control/quotes/backslash are not
# transportable across the pipe-field protocol and are not approved forms.
if any(ch in " \t\x00\r\n'\"\\" for ch in password):
    sys.exit(7)  # credential outside the URL-safe alphabet

try:
    port = p.port if p.port is not None else 6379
    if not (1 <= port <= 65535):
        raise ValueError
except ValueError:
    sys.exit(8)  # non-numeric/invalid port

db = p.path[1:] if len(p.path) > 1 else "0"
if not db.isdigit():
    sys.exit(9)  # non-numeric DB segment

sys.stdout.write(f"{p.hostname}\t{port}\t{db}\t{password}\n")
PYEOF
) || { echo "worker-healthcheck: malformed or unsupported REDIS_URL" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Redis connectivity + authentication probe.
# A successful PING must return exactly "PONG"; NOAUTH/WRONGPASS/connection
# failures produce no stdout here and fail below.
# ---------------------------------------------------------------------------
probe_redis() {
    if [ -n "${REDIS_PASSWORD:-}" ]; then
        REDISCLI_AUTH="${REDIS_PASSWORD}" redis-cli \
            -h "${REDIS_HOST}" -p "${REDIS_PORT}" -n "${REDIS_DB}" \
            --no-auth-warning "$@" 2>/dev/null || true
    else
        redis-cli \
            -h "${REDIS_HOST}" -p "${REDIS_PORT}" -n "${REDIS_DB}" \
            "$@" 2>/dev/null || true
    fi
}

PONG_REPLY="$(probe_redis PING)"
if [ "${PONG_REPLY}" != "PONG" ]; then
    exit 1
fi

# ---------------------------------------------------------------------------
# ARQ worker heartbeat (originally committed liveness contract).
# The key/value are single argv elements; the value is never echoed.
# ---------------------------------------------------------------------------
HEARTBEAT_VALUE="$(probe_redis GET "${HEARTBEAT_KEY}")"
case "${HEARTBEAT_VALUE}" in
    *"j_complete="*"j_failed="*)
        exit 0
        ;;
    *)
        exit 1
        ;;
esac
