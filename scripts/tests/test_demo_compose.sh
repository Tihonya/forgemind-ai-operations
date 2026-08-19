#!/usr/bin/env bash
# Tests for the isolated Demo Compose profile (WP-P7-03, DEC-056).
#
# Offline, read-only: verifies the Demo Compose file and demo env template
# carry the required isolation identity and no secrets. No docker, no
# provider, no network.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

DEMO_COMPOSE="${REPO_ROOT}/docker-compose.demo.yml"
DEMO_ENV_EXAMPLE="${REPO_ROOT}/infra/demo.env.example"

FAILURES=0
PASSES=0

ok() { PASSES=$((PASSES + 1)); echo "ok   - $1"; }
fail() { FAILURES=$((FAILURES + 1)); echo "FAIL - $1" >&2; }

assert_contains() {
    local label="$1" needle="$2" file="$3"
    if grep -qF -- "${needle}" "${file}"; then
        ok "${label}"
    else
        fail "${label} (missing: ${needle})"
    fi
}

assert_not_contains() {
    local label="$1" needle="$2" file="$3"
    if ! grep -qF -- "${needle}" "${file}"; then
        ok "${label}"
    else
        fail "${label} (unexpected: ${needle})"
    fi
}

# ---------------------------------------------------------------------------
# 1. Compose file present
# ---------------------------------------------------------------------------
if [ -f "${DEMO_COMPOSE}" ]; then ok "demo compose file exists"; else fail "demo compose file missing"; fi
if [ -f "${DEMO_ENV_EXAMPLE}" ]; then ok "demo env template exists"; else fail "demo env template missing"; fi

# ---------------------------------------------------------------------------
# 2. Isolated project identity
# ---------------------------------------------------------------------------
assert_contains "compose project name is forgemind-demo" "name: forgemind-demo" "${DEMO_COMPOSE}"

# ---------------------------------------------------------------------------
# 3. Hard-coded demo database name (not production forgemind, not configurable)
# ---------------------------------------------------------------------------
assert_contains "POSTGRES_DB pinned to forgemind_demo" "POSTGRES_DB: forgemind_demo" "${DEMO_COMPOSE}"
assert_contains "DATABASE_URL targets forgemind_demo" "5432/forgemind_demo" "${DEMO_COMPOSE}"
assert_not_contains "demo DB is not the production default name" "5432/forgemind\"" "${DEMO_COMPOSE}"

# ---------------------------------------------------------------------------
# 4. Distinct demo volumes
# ---------------------------------------------------------------------------
assert_contains "distinct demo postgres volume" "demo_postgres_data" "${DEMO_COMPOSE}"
assert_contains "distinct demo redis volume" "demo_redis_data" "${DEMO_COMPOSE}"
assert_contains "distinct demo caddy data volume" "demo_caddy_data" "${DEMO_COMPOSE}"
assert_contains "distinct demo caddy config volume" "demo_caddy_config" "${DEMO_COMPOSE}"

# ---------------------------------------------------------------------------
# 5. PostgreSQL / Redis never published to host ports
# ---------------------------------------------------------------------------
assert_not_contains "no host-published postgres port" '"5432:5432"' "${DEMO_COMPOSE}"
assert_not_contains "no host-published redis port" '"6379:6379"' "${DEMO_COMPOSE}"

# ---------------------------------------------------------------------------
# 6. No Docker socket mount
# ---------------------------------------------------------------------------
assert_not_contains "no docker socket mount" "/var/run/docker.sock" "${DEMO_COMPOSE}"

# ---------------------------------------------------------------------------
# 7. ENVIRONMENT=production (real security behavior, no weakened demo mode)
# ---------------------------------------------------------------------------
assert_contains "demo runs ENVIRONMENT=production" "ENVIRONMENT: production" "${DEMO_COMPOSE}"

# ---------------------------------------------------------------------------
# 8. Demo env template carries placeholders only (no real secrets)
# ---------------------------------------------------------------------------
for var in SECRET_KEY POSTGRES_PASSWORD REDIS_PASSWORD OPENAI_API_KEY OPENROUTER_API_KEY; do
    line="$(grep -E "^${var}=" "${DEMO_ENV_EXAMPLE}" || true)"
    if [ -z "${line}" ]; then
        fail "demo env template missing ${var}"
        continue
    fi
    if printf '%s' "${line}" | grep -qE 'REPLACE_WITH|replace-with'; then
        ok "demo env ${var} is a placeholder"
    else
        fail "demo env ${var} looks like a real value: ${line}"
    fi
done

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo "----"
echo "demo compose tests: ${PASSES} passed, ${FAILURES} failed"
if [ "${FAILURES}" -gt 0 ]; then
    exit 1
fi
