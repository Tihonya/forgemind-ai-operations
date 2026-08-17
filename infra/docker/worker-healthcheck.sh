#!/usr/bin/env bash
set -euo pipefail

# Worker healthcheck for the ForgeMind ARQ worker (WP-P7-02).
#
# ARQ writes its heartbeat to the Redis key:
#     {queue_name}:health-check
# (arq/constants.py health_check_key_suffix), with a TTL slightly longer
# than the heartbeat interval (~3600s). Existence of a well-formed
# heartbeat value means worker is alive; absence means the worker has not
# started or has stopped.
#
# This script is the repository-owned container healthcheck used by
# docker-compose.prod.yml. It performs a REAL Redis read — the worker
# is the queue consumer, so its liveness is defined by its heartbeat
# in Redis (the same mechanism the backend /health endpoint uses).
#
# Exit codes:
#   0  worker heartbeat present and well-formed
#   1  worker heartbeat absent / malformed / unreadable
#
# No secrets are printed. The heartbeat value is NOT printed in full
# (only a masked prefix is used internally; nothing is echoed on the
# healthy path).

QUEUE_NAME="${ARQ_QUEUE_NAME:-forgemind-tasks}"
REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"

HEARTBEAT_KEY="${QUEUE_NAME}:health-check"

# redis-cli is available in the worker image (redis-tools installed in
# infra/docker/worker.dockerfile).
# --no-auth-warning suppresses the password warning without printing it.
VALUE="$(redis-cli -u "${REDIS_URL}" --no-auth-warning GET "${HEARTBEAT_KEY}" 2>/dev/null || true)"

if [ -z "${VALUE}" ]; then
    exit 1
fi

# ARQ writes: "{datetime:%b-%d %H:%M:%S} j_complete=... j_failed=..."
case "${VALUE}" in
    *"j_complete="*"j_failed="*)
        exit 0
        ;;
    *)
        exit 1
        ;;
esac