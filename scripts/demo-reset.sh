#!/usr/bin/env bash
# ForgeMind Demo Reset (WP-P7-03, DEC-056) — operator-level, full disposable
# demo-environment reset.
#
# Destroys and recreates ONLY the isolated Release 1 Demo environment
# (Compose project ``forgemind-demo``, database ``forgemind_demo``). It has
# NO authority over the production stack and refuses to run unless the demo
# identity is confirmed by multiple independent fail-closed guards.
#
# Reset sequence (deterministic, disposable):
#   validate demo identity  ->  acquire reset lock  ->  stop demo stack
#   ->  destroy ONLY Demo PostgreSQL + Redis volumes (Caddy TLS/ACME state is
#   preserved)  ->  start infra  ->  alembic upgrade head (empty DB)
#   ->  canonical Golden seed  ->  start full stack  ->  health/baseline
#   verify  ->  report  ->  release lock.
#
# There is NO in-app reset API and NO selective row-deletion: the demo
# database and Redis state are destroyed and rebuilt from scratch. Old demo
# workflow/audit/session history is intentionally discarded across a reset.
#
# Caddy TLS/ACME state (demo_caddy_data / demo_caddy_config) is infrastructure
# identity, NOT disposable demo business data, and is deliberately PRESERVED
# across a business reset so a reset does not force a fresh certificate
# issuance (DEC-056: demo BUSINESS/RUNTIME data is disposable; TLS identity
# may persist across business resets).
#
# No secrets are printed. The demo identity constants below are hard-coded
# and MUST NOT be overridden by the caller.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ---------------------------------------------------------------------------
# Canonical Demo identity (single source of truth). The identity VALUES below
# (project name, database name) are hard-coded and MUST NOT be overridden by
# the caller. The compose-file PATH and env-file PATH may be overridden via
# environment for testing only; the guards validate the CONTENT of whatever
# compose file is pointed at against the hard-coded identity, so a wrong path
# is still refused.
# ---------------------------------------------------------------------------
DEMO_COMPOSE_FILE="${DEMO_COMPOSE_FILE:-docker-compose.demo.yml}"
DEMO_PROJECT_NAME="forgemind-demo"
DEMO_DB_NAME="forgemind_demo"

# Resolve the compose file path (absolute or repo-relative).
if [[ "${DEMO_COMPOSE_FILE}" = /* ]]; then
    DEMO_COMPOSE_PATH="${DEMO_COMPOSE_FILE}"
else
    DEMO_COMPOSE_PATH="${REPO_ROOT}/${DEMO_COMPOSE_FILE}"
fi

# The operator's demo environment file (real secrets, never committed).
# Default path mirrors infra/demo.env.example; override only via
# DEMO_ENV_FILE if the operator keeps it elsewhere.
DEMO_ENV_FILE="${DEMO_ENV_FILE:-${REPO_ROOT}/infra/demo.env}"

# Lock file serializes reset attempts (flock); a second concurrent reset
# fails fast instead of overlapping.
LOCK_FILE="${LOCK_FILE:-/tmp/forgemind-demo-reset.lock}"

log() { printf '[demo-reset] %s\n' "$*"; }
fail() { printf '[demo-reset] ERROR: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Fail-closed identity guards (each independent; all must pass).
# ---------------------------------------------------------------------------

guard_compose_file() {
    local compose="${DEMO_COMPOSE_PATH}"
    if [ ! -f "${compose}" ]; then
        fail "demo compose file not found: ${DEMO_COMPOSE_FILE}"
    fi
    log "guard: compose file = ${DEMO_COMPOSE_FILE}"
}

guard_project_name() {
    local compose="${DEMO_COMPOSE_PATH}"
    local declared
    declared="$(awk '$1=="name:"{print $2; exit}' "${compose}")"
    if [ "${declared}" != "${DEMO_PROJECT_NAME}" ]; then
        fail "compose project name '${declared}' != expected '${DEMO_PROJECT_NAME}'; refusing (production target?)"
    fi
    log "guard: project name = ${DEMO_PROJECT_NAME}"
}

guard_db_name() {
    local compose="${DEMO_COMPOSE_PATH}"
    # The demo DB name is hard-coded in the compose (POSTGRES_DB and
    # DATABASE_URL). Verify both carry forgemind_demo and not the default
    # production database name.
    if ! grep -q "POSTGRES_DB: ${DEMO_DB_NAME}" "${compose}"; then
        fail "demo compose does not pin POSTGRES_DB=${DEMO_DB_NAME}; refusing"
    fi
    if ! grep -q "5432/${DEMO_DB_NAME}" "${compose}"; then
        fail "demo compose DATABASE_URL does not target ${DEMO_DB_NAME}; refusing"
    fi
    log "guard: database name = ${DEMO_DB_NAME}"
}

guard_env_file() {
    if [ ! -f "${DEMO_ENV_FILE}" ]; then
        fail "demo env file not found: ${DEMO_ENV_FILE} (copy infra/demo.env.example and fill real values)"
    fi
    log "guard: env file = ${DEMO_ENV_FILE}"
}

# Host-port guard — resolved Compose state (NOT textual grep). A textual
# grep misses host-IP syntax ("127.0.0.1:5432:5432") and long syntax
# ("- target: 5432\n  published: 5432"). Resolving the Compose config into
# JSON and inspecting the resolved postgres/redis services catches every
# published-port form. Requires python3 (part of the deployment host
# tooling assumption). Fails closed on any resolution/parse error.
guard_no_host_ports() {
    local json tmp
    json="$(docker compose --env-file "${DEMO_ENV_FILE}" \
        -f "${DEMO_COMPOSE_PATH}" \
        -p "${DEMO_PROJECT_NAME}" \
        config --format json 2>/dev/null)" \
        || fail "failed to resolve demo compose config for host-port validation"

    [ -n "${json}" ] || fail "resolved demo compose config is empty; refusing"

    tmp="$(mktemp)"
    printf '%s\n' "${json}" > "${tmp}"

    python3 -c '
import json, sys
with open(sys.argv[1]) as f:
    data = json.load(f)
services = data.get("services", {})
bad = [s for s in ("postgres", "redis") if (services.get(s, {}).get("ports") or [])]
if bad:
    raise SystemExit("resolved demo compose publishes host ports on: " + ", ".join(bad))
' "${tmp}"
    local rc=$?
    rm -f "${tmp}"
    if [ "${rc}" -ne 0 ]; then
        fail "resolved demo compose publishes host ports on postgres/redis; refusing"
    fi
    log "guard: no host-published postgres/redis ports (resolved compose)"
}

guard_no_docker_socket() {
    local compose="${DEMO_COMPOSE_PATH}"
    if grep -q '/var/run/docker.sock' "${compose}"; then
        fail "demo compose mounts the Docker socket; refusing"
    fi
    log "guard: no Docker socket mount"
}

assert_demo_identity() {
    guard_compose_file
    guard_project_name
    guard_db_name
    guard_env_file
    guard_no_host_ports
    guard_no_docker_socket
}

# ---------------------------------------------------------------------------
# Compose wrapper: every destructive operation is pinned to the demo file,
# project, and env file. There is no unqualified `docker compose` invocation.
# ---------------------------------------------------------------------------
compose() {
    docker compose --env-file "${DEMO_ENV_FILE}" \
        -f "${DEMO_COMPOSE_PATH}" \
        -p "${DEMO_PROJECT_NAME}" "$@"
}

# ---------------------------------------------------------------------------
# Bounded data-volume destruction (F2). Removes ONLY the named demo business
# data volume (PostgreSQL or Redis). The Caddy TLS/ACME volumes are NEVER
# touched. Safety boundary: the volume's Docker Compose labels must BOTH match
# the expected demo identity exactly before removal — project label == the
# hard-coded demo project, and the compose-volume label == the exact logical
# volume name. Any disagreement (missing/wrong labels, production-labelled
# volume, unexpected volume) FAILS CLOSED. An absent volume is treated as an
# already-fresh state and skipped.
# ---------------------------------------------------------------------------
remove_demo_data_volume() {
    local logical="$1"
    local full="${DEMO_PROJECT_NAME}_${logical}"

    if ! docker volume inspect "${full}" >/dev/null 2>&1; then
        log "demo data volume '${full}' not present (fresh state); nothing to remove"
        return 0
    fi

    local project_label volume_label
    project_label="$(docker volume inspect "${full}" --format '{{index .Labels "com.docker.compose.project"}}' 2>/dev/null || true)"
    volume_label="$(docker volume inspect "${full}" --format '{{index .Labels "com.docker.compose.volume"}}' 2>/dev/null || true)"

    if [ "${project_label}" != "${DEMO_PROJECT_NAME}" ]; then
        fail "volume '${full}' project label '${project_label}' != '${DEMO_PROJECT_NAME}'; refusing to remove"
    fi
    if [ "${volume_label}" != "${logical}" ]; then
        fail "volume '${full}' compose-volume label '${volume_label}' != '${logical}'; refusing to remove"
    fi

    log "removing demo data volume '${full}' (labels verified)"
    docker volume rm "${full}"
}

wait_for_healthy() {
    local service="$1" timeout="${2:-120}"
    local waited=0
    while [ "${waited}" -lt "${timeout}" ]; do
        local cid
        cid="$(compose ps -q "${service}" 2>/dev/null || true)"
        if [ -n "${cid}" ]; then
            local status
            status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${cid}" 2>/dev/null || true)"
            if [ "${status}" = "healthy" ]; then
                return 0
            fi
        fi
        waited=$((waited + 5))
        sleep 5
    done
    fail "service '${service}' did not become healthy within ${timeout}s"
}

# ---------------------------------------------------------------------------
# Reset orchestration. Runs with `set -e` ACTIVE (called directly from main,
# NOT as an `if` condition), so any failing load-bearing command terminates
# non-zero and the EXIT trap releases the lock. No false success is possible.
# ---------------------------------------------------------------------------
run_reset() {
    log "reset started (demo identity confirmed)"

    log "stopping demo stack (containers + networks; volumes preserved)"
    compose down

    log "destroying demo business data volumes (PostgreSQL + Redis only; Caddy TLS preserved)"
    remove_demo_data_volume demo_postgres_data
    remove_demo_data_volume demo_redis_data

    log "starting demo infrastructure (postgres + redis)"
    compose up -d postgres redis
    wait_for_healthy postgres
    wait_for_healthy redis

    log "starting backend for migration/seed (empty ${DEMO_DB_NAME} database)"
    compose up -d backend
    wait_for_healthy backend

    log "applying migrations: alembic upgrade head"
    compose exec -T backend python -m alembic upgrade head

    log "running canonical Golden seed"
    compose exec -T backend python -m app.seed.generator.main

    log "starting full demo stack (worker, frontend, caddy)"
    compose up -d worker frontend caddy
    wait_for_healthy backend
    wait_for_healthy worker

    log "verifying backend health"
    compose exec -T backend curl -fsS http://127.0.0.1:8000/health >/dev/null

    log "reset completed successfully (clean ${DEMO_DB_NAME} demo generation)"
}

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
main() {
    assert_demo_identity

    # Serialize reset attempts. flock fails fast if another reset is running.
    exec 9>"${LOCK_FILE}"
    if ! flock -n 9; then
        fail "another demo reset is already in progress (lock ${LOCK_FILE})"
    fi

    # Release the lock on ANY exit path (success, failure, signal).
    trap 'flock -u 9 2>/dev/null || true' EXIT

    log "reset lock acquired (${LOCK_FILE})"

    # run_reset is invoked DIRECTLY (not as an `if` condition) so `set -e`
    # remains active: any failure inside aborts non-zero before the success
    # message below is reached.
    run_reset

    log "reset generation complete"
}

main "$@"
