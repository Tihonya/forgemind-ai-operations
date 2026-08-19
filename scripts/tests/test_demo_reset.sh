#!/usr/bin/env bash
# Tests for scripts/demo-reset.sh fail-closed guards (WP-P7-03, DEC-056).
#
# Offline: exercises the identity guards against throwaway compose files with
# a mocked `docker` on PATH. No real docker, no provider, no network, no
# destructive action.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESET_SCRIPT="${SCRIPT_DIR}/../demo-reset.sh"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

FAILURES=0
PASSES=0

ok() { PASSES=$((PASSES + 1)); echo "ok   - $1"; }
fail() { FAILURES=$((FAILURES + 1)); echo "FAIL - $1" >&2; }

# Mock `docker` so no real docker call can happen even if a guard regresses.
MOCK_BIN="${TMP_DIR}/bin"
mkdir -p "${MOCK_BIN}"
DOCKER_LOG="${TMP_DIR}/docker.log"
cat > "${MOCK_BIN}/docker" <<EOF
#!/usr/bin/env bash
echo "docker \$*" >> "${DOCKER_LOG}"
exit 0
EOF
chmod +x "${MOCK_BIN}/docker"
export PATH="${MOCK_BIN}:${PATH}"

# A valid demo env file (guards pass; only content is a placeholder).
DEMO_ENV="${TMP_DIR}/demo.env"
printf 'SECRET_KEY=placeholder-for-test-only\n' > "${DEMO_ENV}"

# A structurally correct demo compose (all guards would pass).
CORRECT_COMPOSE='
name: forgemind-demo
services:
  postgres:
    environment:
      POSTGRES_DB: forgemind_demo
      POSTGRES_USER: ${POSTGRES_USER:?POSTGRES_USER is required}
  backend:
    environment:
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/forgemind_demo
'

# ---------------------------------------------------------------------------
# 1. Script present and executable
# ---------------------------------------------------------------------------
if [ -f "${RESET_SCRIPT}" ] && [ -x "${RESET_SCRIPT}" ]; then
    ok "demo-reset.sh exists and is executable"
else
    fail "demo-reset.sh missing or not executable"
fi

# ---------------------------------------------------------------------------
# 2. Identity constants are hard-coded (not caller-overridable)
# ---------------------------------------------------------------------------
if grep -qF 'DEMO_PROJECT_NAME="forgemind-demo"' "${RESET_SCRIPT}"; then
    ok "project name hard-coded to forgemind-demo"
else
    fail "project name is not hard-coded"
fi
if grep -qF 'DEMO_DB_NAME="forgemind_demo"' "${RESET_SCRIPT}"; then
    ok "database name hard-coded to forgemind_demo"
else
    fail "database name is not hard-coded"
fi

# ---------------------------------------------------------------------------
# 3. Destructive compose invocation is explicit (-f demo file, -p project)
# ---------------------------------------------------------------------------
if grep -qF -- '-p "${DEMO_PROJECT_NAME}"' "${RESET_SCRIPT}"; then
    ok "compose pins project via -p"
else
    fail "compose does not pin project via -p"
fi
if grep -qF -- 'down -v' "${RESET_SCRIPT}"; then
    ok "reset destroys volumes (down -v)"
else
    fail "reset does not destroy volumes"
fi

# ---------------------------------------------------------------------------
# 4. Guard refusals (throwaway compose files, mocked docker)
# ---------------------------------------------------------------------------
run_refusal() {
    local label="$1" content="$2"
    local comp="${TMP_DIR}/compose-${label// /_}.yml"
    printf '%s\n' "${content}" > "${comp}"
    set +e
    DEMO_COMPOSE_FILE="${comp}" DEMO_ENV_FILE="${DEMO_ENV}" \
        bash "${RESET_SCRIPT}" >"${TMP_DIR}/out.log" 2>&1
    local rc=$?
    set -e
    if [ "${rc}" -eq 1 ] && grep -q 'refusing' "${TMP_DIR}/out.log"; then
        ok "${label}"
    else
        fail "${label} (expected rc=1 refusing, got rc=${rc})"
    fi
}

run_refusal "refuses wrong project name" '
name: forgemind
services:
  postgres:
    environment:
      POSTGRES_DB: forgemind_demo
  backend:
    environment:
      DATABASE_URL: postgresql+asyncpg://u:p@postgres:5432/forgemind_demo
'

run_refusal "refuses wrong database name" '
name: forgemind-demo
services:
  postgres:
    environment:
      POSTGRES_DB: forgemind
  backend:
    environment:
      DATABASE_URL: postgresql+asyncpg://u:p@postgres:5432/forgemind
'

run_refusal "refuses host-published postgres port" '
name: forgemind-demo
services:
  postgres:
    ports:
      - "5432:5432"
    environment:
      POSTGRES_DB: forgemind_demo
  backend:
    environment:
      DATABASE_URL: postgresql+asyncpg://u:p@postgres:5432/forgemind_demo
'

run_refusal "refuses docker socket mount" '
name: forgemind-demo
services:
  postgres:
    environment:
      POSTGRES_DB: forgemind_demo
  backend:
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      DATABASE_URL: postgresql+asyncpg://u:p@postgres:5432/forgemind_demo
'

# ---------------------------------------------------------------------------
# 5. Missing env file refuses (correct compose, missing env)
# ---------------------------------------------------------------------------
printf '%s\n' "${CORRECT_COMPOSE}" > "${TMP_DIR}/correct.yml"
set +e
DEMO_COMPOSE_FILE="${TMP_DIR}/correct.yml" DEMO_ENV_FILE="${TMP_DIR}/missing.env" \
    bash "${RESET_SCRIPT}" >"${TMP_DIR}/out-missing.log" 2>&1
rc_missing=$?
set -e
if [ "${rc_missing}" -eq 1 ] && grep -q 'env file not found' "${TMP_DIR}/out-missing.log"; then
    ok "refuses missing demo env file"
else
    fail "missing env file not refused (rc=${rc_missing})"
fi

# ---------------------------------------------------------------------------
# 6. No docker call may occur during any refusal (guards ran first)
# ---------------------------------------------------------------------------
if [ ! -s "${DOCKER_LOG}" ]; then
    ok "no docker invocation during guard refusals"
else
    fail "docker was invoked during guard refusals: $(cat "${DOCKER_LOG}")"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo "----"
echo "demo reset guard tests: ${PASSES} passed, ${FAILURES} failed"
if [ "${FAILURES}" -gt 0 ]; then
    exit 1
fi
