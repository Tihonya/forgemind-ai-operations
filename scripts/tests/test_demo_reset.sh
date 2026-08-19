#!/usr/bin/env bash
# Tests for scripts/demo-reset.sh (WP-P7-03, DEC-056).
#
# Offline: exercises the fail-closed identity guards AND the run_reset
# execution path against throwaway compose files with a mocked `docker` on
# PATH. No real docker, no provider, no network, no destructive action.
#
# Coverage:
#   - static identity constants + `-p` pinning + absence of `down -v`;
#   - textual guard refusals (project name, DB name, Docker socket, env file);
#   - F4 resolved-Compose host-port refusals (short / host-IP / long syntax);
#   - F1 run_reset execution path: success, and failure of down / alembic /
#     seed / final health — each must exit non-zero and never print success;
#   - F2 volume-destruction boundary: only Demo PostgreSQL + Redis volumes are
#     removed, Caddy volumes are never touched, and mislabelled volumes are
#     refused.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESET_SCRIPT="${SCRIPT_DIR}/../demo-reset.sh"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DEMO_ENV_EXAMPLE="${REPO_ROOT}/infra/demo.env.example"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

FAILURES=0
PASSES=0
ok() { PASSES=$((PASSES + 1)); echo "ok   - $1"; }
fail() { FAILURES=$((FAILURES + 1)); echo "FAIL - $1" >&2; }

# ---------------------------------------------------------------------------
# Mock `docker` — controlled by a control directory. No real docker call can
# happen even if a guard regresses. Read-only `config --format json` returns a
# canned resolved compose; destructive/load-bearing subcommands can be made to
# fail via trigger files; `volume inspect`/`volume rm` are backed by per-volume
# label files so the F2 safety boundary can be exercised.
# ---------------------------------------------------------------------------
MOCK_BIN="${TMP_DIR}/bin"
mkdir -p "${MOCK_BIN}"
CTRL="${TMP_DIR}/ctrl"
mkdir -p "${CTRL}"
export MOCK_CTRL="${CTRL}"

cat > "${MOCK_BIN}/docker" <<'MOCK'
#!/usr/bin/env bash
CTRL="${MOCK_CTRL:?MOCK_CTRL unset}"
echo "docker $*" >> "${CTRL}/docker.log"
case "$*" in
  *"--format json"*)
    if [ -f "${CTRL}/ports.json" ]; then cat "${CTRL}/ports.json"; else cat "${CTRL}/valid.json"; fi
    exit 0 ;;
  *"down"*)
    [ -f "${CTRL}/fail.down" ] && exit 1; exit 0 ;;
  *"up -d postgres redis"*)
    [ -f "${CTRL}/fail.up" ] && exit 1; exit 0 ;;
  *"up -d"*)
    exit 0 ;;
  *"ps -q"*)
    printf 'mock-cid-0001\n'; exit 0 ;;
  *"exec -T backend python -m alembic upgrade head"*)
    [ -f "${CTRL}/fail.alembic" ] && exit 1; exit 0 ;;
  *"exec -T backend python -m app.seed.generator.main"*)
    [ -f "${CTRL}/fail.seed" ] && exit 1; exit 0 ;;
  *"exec -T backend curl"*)
    [ -f "${CTRL}/fail.health" ] && exit 1; exit 0 ;;
esac
case "$*" in
  *"inspect"*"Health.Status"*)
    printf 'healthy\n'; exit 0 ;;
esac
case "$*" in
  *"volume rm"*)
    printf '%s\n' "$3" >> "${CTRL}/removed.log"; exit 0 ;;
  *"volume inspect"*)
    name="$3"
    if [ -f "${CTRL}/volumes/${name}.project" ]; then
      case "$*" in
        *"com.docker.compose.project"*) cat "${CTRL}/volumes/${name}.project"; exit 0 ;;
        *"com.docker.compose.volume"*)  cat "${CTRL}/volumes/${name}.volume";  exit 0 ;;
        *) exit 0 ;;
      esac
    else
      exit 1
    fi ;;
esac
exit 0
MOCK
chmod +x "${MOCK_BIN}/docker"
export PATH="${MOCK_BIN}:${PATH}"

# Resolved compose without any host-published postgres/redis ports (the
# committed demo compose resolves to this shape).
VALID_JSON='{"name":"forgemind-demo","services":{"postgres":{},"redis":{},"backend":{},"worker":{},"frontend":{},"caddy":{"ports":[{"mode":"ingress","target":80,"published":"80","protocol":"tcp"}]}}}'

# A valid demo env file (guards pass; only content is a placeholder).
DEMO_ENV="${TMP_DIR}/demo.env"
printf 'SECRET_KEY=placeholder-for-test-only\n' > "${DEMO_ENV}"

# A structurally correct demo compose (all textual guards pass).
CORRECT_COMPOSE='name: forgemind-demo
services:
  postgres:
    environment:
      POSTGRES_DB: forgemind_demo
      POSTGRES_USER: ${POSTGRES_USER:?POSTGRES_USER is required}
  backend:
    environment:
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/forgemind_demo
'
printf '%s\n' "${CORRECT_COMPOSE}" > "${TMP_DIR}/correct.yml"

# ---------------------------------------------------------------------------
# Control-directory helpers
# ---------------------------------------------------------------------------
reset_ctrl() {
    rm -rf "${CTRL}"
    mkdir -p "${CTRL}/volumes"
    printf '%s\n' "${VALID_JSON}" > "${CTRL}/valid.json"
    : > "${CTRL}/docker.log"
    : > "${CTRL}/removed.log"
}

set_fail() { touch "${CTRL}/fail.$1"; }

set_volume() {
    # set_volume <full-name> <project-label> <volume-label>
    mkdir -p "${CTRL}/volumes"
    printf '%s\n' "$2" > "${CTRL}/volumes/$1.project"
    printf '%s\n' "$3" > "${CTRL}/volumes/$1.volume"
}

set_ports_json() { printf '%s\n' "$1" > "${CTRL}/ports.json"; }

LAST_RC=0
LAST_OUT=""
run_reset() {
    # run_reset <compose-file> <env-file>
    local out="${TMP_DIR}/out.log"
    set +e
    DEMO_COMPOSE_FILE="$1" DEMO_ENV_FILE="$2" bash "${RESET_SCRIPT}" >"${out}" 2>&1
    LAST_RC=$?
    set -e
    LAST_OUT="$(cat "${out}")"
}

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
# 3. Destructive compose invocation is explicit (-p) and never uses `down -v`
# ---------------------------------------------------------------------------
if grep -qF -- '-p "${DEMO_PROJECT_NAME}"' "${RESET_SCRIPT}"; then
    ok "compose pins project via -p"
else
    fail "compose does not pin project via -p"
fi
if grep -q 'down -v' "${RESET_SCRIPT}"; then
    fail "demo-reset.sh still contains a broad 'down -v' (Caddy TLS state would be destroyed)"
else
    ok "no 'down -v' remains in demo-reset.sh"
fi

# ---------------------------------------------------------------------------
# 4. Textual guard refusals (fail before any docker invocation)
# ---------------------------------------------------------------------------
reset_ctrl

run_refusal() {
    local label="$1" content="$2"
    local comp="${TMP_DIR}/compose-${label// /_}.yml"
    printf '%s\n' "${content}" > "${comp}"
    run_reset "${comp}" "${DEMO_ENV}"
    if [ "${LAST_RC}" -eq 1 ] && printf '%s' "${LAST_OUT}" | grep -q 'refusing'; then
        ok "${label}"
    else
        fail "${label} (expected rc=1 refusing, got rc=${LAST_RC})"
    fi
}

run_refusal "refuses wrong project name" 'name: forgemind
services:
  postgres:
    environment:
      POSTGRES_DB: forgemind_demo
  backend:
    environment:
      DATABASE_URL: postgresql+asyncpg://u:p@postgres:5432/forgemind_demo
'

run_refusal "refuses wrong database name" 'name: forgemind-demo
services:
  postgres:
    environment:
      POSTGRES_DB: forgemind
  backend:
    environment:
      DATABASE_URL: postgresql+asyncpg://u:p@postgres:5432/forgemind
'

run_refusal "refuses docker socket mount" 'name: forgemind-demo
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
# 5. Missing env file refuses
# ---------------------------------------------------------------------------
run_reset "${TMP_DIR}/correct.yml" "${TMP_DIR}/missing.env"
if [ "${LAST_RC}" -eq 1 ] && printf '%s' "${LAST_OUT}" | grep -q 'env file not found'; then
    ok "refuses missing demo env file"
else
    fail "missing env file not refused (rc=${LAST_RC})"
fi

# ---------------------------------------------------------------------------
# 6. F4 — resolved-Compose host-port refusals (short / host-IP / long syntax)
#    All forms collapse to a non-empty resolved postgres/redis ports list.
# ---------------------------------------------------------------------------
# short syntax 5432:5432 resolves to a published port on postgres
set_ports_json '{"name":"forgemind-demo","services":{"postgres":{"ports":[{"mode":"ingress","target":5432,"published":"5432","protocol":"tcp"}]},"redis":{}}}'
run_reset "${TMP_DIR}/correct.yml" "${DEMO_ENV}"
if [ "${LAST_RC}" -eq 1 ] && printf '%s' "${LAST_OUT}" | grep -q 'publishes host ports'; then
    ok "F4 refuses resolved short-syntax postgres host port"
else
    fail "F4 short-syntax postgres port not refused (rc=${LAST_RC})"
fi

# host-IP syntax 127.0.0.1:5432:5432 resolves with host_ip
set_ports_json '{"name":"forgemind-demo","services":{"postgres":{"ports":[{"mode":"ingress","host_ip":"127.0.0.1","target":5432,"published":"5432","protocol":"tcp"}]},"redis":{}}}'
run_reset "${TMP_DIR}/correct.yml" "${DEMO_ENV}"
if [ "${LAST_RC}" -eq 1 ] && printf '%s' "${LAST_OUT}" | grep -q 'publishes host ports'; then
    ok "F4 refuses resolved host-IP postgres host port"
else
    fail "F4 host-IP postgres port not refused (rc=${LAST_RC})"
fi

# long syntax published PostgreSQL
set_ports_json '{"name":"forgemind-demo","services":{"postgres":{"ports":[{"mode":"ingress","target":5432,"published":"5432","protocol":"tcp"}]},"redis":{}}}'
run_reset "${TMP_DIR}/correct.yml" "${DEMO_ENV}"
if [ "${LAST_RC}" -eq 1 ] && printf '%s' "${LAST_OUT}" | grep -q 'publishes host ports'; then
    ok "F4 refuses resolved long-syntax postgres host port"
else
    fail "F4 long-syntax postgres port not refused (rc=${LAST_RC})"
fi

# long syntax published Redis
set_ports_json '{"name":"forgemind-demo","services":{"postgres":{},"redis":{"ports":[{"mode":"ingress","target":6379,"published":"6379","protocol":"tcp"}]}}}'
run_reset "${TMP_DIR}/correct.yml" "${DEMO_ENV}"
if [ "${LAST_RC}" -eq 1 ] && printf '%s' "${LAST_OUT}" | grep -q 'publishes host ports'; then
    ok "F4 refuses resolved long-syntax redis host port"
else
    fail "F4 long-syntax redis port not refused (rc=${LAST_RC})"
fi

# committed (no ports) must PASS the host-port guard and proceed into run_reset
rm -f "${CTRL}/ports.json"

# ---------------------------------------------------------------------------
# 6b. No destructive docker invocation occurred during guard refusals (only
#     read-only `config --format json` is allowed before the execution path).
# ---------------------------------------------------------------------------
if grep -qE ' down( |$)| up -d| exec -T|volume rm' "${CTRL}/docker.log"; then
    fail "destructive docker invocation detected during guard refusals: $(grep -E ' down( |$)| up -d| exec -T|volume rm' "${CTRL}/docker.log")"
else
    ok "no destructive docker invocation during guard refusals"
fi

# ---------------------------------------------------------------------------
# F1/F2 execution-path tests. All use the correct compose + valid env so the
# guards pass and the script reaches run_reset. The mock `docker` is driven by
# control files to simulate success and each load-bearing failure.
# ---------------------------------------------------------------------------

setup_healthy_volumes() {
    set_volume "forgemind-demo_demo_postgres_data" "forgemind-demo" "demo_postgres_data"
    set_volume "forgemind-demo_demo_redis_data" "forgemind-demo" "demo_redis_data"
}

assert_no_success_message() {
    local label="$1"
    if printf '%s' "${LAST_OUT}" | grep -q 'reset completed successfully'; then
        fail "${label}: printed 'reset completed successfully' on failure"
        return 1
    fi
    if printf '%s' "${LAST_OUT}" | grep -q 'reset generation complete'; then
        fail "${label}: printed 'reset generation complete' on failure"
        return 1
    fi
    ok "${label}: no success message on failure"
}

# 7. F1-A — successful mocked reset exits 0 and prints success
reset_ctrl
setup_healthy_volumes
run_reset "${TMP_DIR}/correct.yml" "${DEMO_ENV}"
if [ "${LAST_RC}" -eq 0 ] && printf '%s' "${LAST_OUT}" | grep -q 'reset completed successfully' && printf '%s' "${LAST_OUT}" | grep -q 'reset generation complete'; then
    ok "F1 successful mocked reset exits 0 and prints success"
else
    fail "F1 successful reset failed (rc=${LAST_RC}, out=${LAST_OUT})"
fi
# F2 — only PG + Redis volumes removed, Caddy never touched
REMOVED="$(cat "${CTRL}/removed.log" 2>/dev/null || true)"
if printf '%s\n' "${REMOVED}" | grep -q 'demo_caddy'; then
    fail "F2 a Caddy volume was passed to docker volume rm"
else
    ok "F2 no Caddy volume removed"
fi
for expect in "forgemind-demo_demo_postgres_data" "forgemind-demo_demo_redis_data"; do
    if printf '%s\n' "${REMOVED}" | grep -qF "${expect}"; then
        ok "F2 removed expected demo data volume ${expect}"
    else
        fail "F2 expected volume ${expect} was not removed"
    fi
done
REMOVED_COUNT=0
if [ -s "${CTRL}/removed.log" ]; then
    REMOVED_COUNT="$(wc -l < "${CTRL}/removed.log")"
fi
if [ "${REMOVED_COUNT}" -eq 2 ]; then
    ok "F2 exactly two volumes removed (PG + Redis)"
else
    fail "F2 expected exactly 2 removed volumes, got ${REMOVED_COUNT}: ${REMOVED}"
fi

# 8. F1-B — failure of destructive/stop stage (down) exits non-zero
reset_ctrl
setup_healthy_volumes
set_fail down
run_reset "${TMP_DIR}/correct.yml" "${DEMO_ENV}"
if [ "${LAST_RC}" -ne 0 ]; then
    ok "F1 'down' failure exits non-zero (rc=${LAST_RC})"
else
    fail "F1 'down' failure did not exit non-zero"
fi
assert_no_success_message "F1 down failure"

# 9. F1-C — failure of alembic upgrade head exits non-zero
reset_ctrl
setup_healthy_volumes
set_fail alembic
run_reset "${TMP_DIR}/correct.yml" "${DEMO_ENV}"
if [ "${LAST_RC}" -ne 0 ]; then
    ok "F1 'alembic upgrade head' failure exits non-zero (rc=${LAST_RC})"
else
    fail "F1 alembic failure did not exit non-zero"
fi
assert_no_success_message "F1 alembic failure"

# 10. F1-D — failure of canonical Golden seed exits non-zero
reset_ctrl
setup_healthy_volumes
set_fail seed
run_reset "${TMP_DIR}/correct.yml" "${DEMO_ENV}"
if [ "${LAST_RC}" -ne 0 ]; then
    ok "F1 seed failure exits non-zero (rc=${LAST_RC})"
else
    fail "F1 seed failure did not exit non-zero"
fi
assert_no_success_message "F1 seed failure"

# 11. F1-E — failure of final backend health curl exits non-zero
reset_ctrl
setup_healthy_volumes
set_fail health
run_reset "${TMP_DIR}/correct.yml" "${DEMO_ENV}"
if [ "${LAST_RC}" -ne 0 ]; then
    ok "F1 final health-curl failure exits non-zero (rc=${LAST_RC})"
else
    fail "F1 health-curl failure did not exit non-zero"
fi
assert_no_success_message "F1 health failure"

# ---------------------------------------------------------------------------
# 12. F2 — volume-destruction safety boundary
# ---------------------------------------------------------------------------

# 12a. Wrong project label (production "forgemind") refuses; nothing removed
reset_ctrl
set_volume "forgemind-demo_demo_postgres_data" "forgemind" "demo_postgres_data"
set_volume "forgemind-demo_demo_redis_data" "forgemind-demo" "demo_redis_data"
run_reset "${TMP_DIR}/correct.yml" "${DEMO_ENV}"
if [ "${LAST_RC}" -eq 1 ] && printf '%s' "${LAST_OUT}" | grep -q 'refusing to remove'; then
    ok "F2 wrong project label (production) refuses removal"
else
    fail "F2 wrong project label not refused (rc=${LAST_RC})"
fi
if [ ! -s "${CTRL}/removed.log" ]; then
    ok "F2 production-labelled volume was not removed"
else
    fail "F2 production-labelled volume was removed: $(cat "${CTRL}/removed.log")"
fi

# 12b. Wrong logical-volume label refuses; nothing removed
reset_ctrl
set_volume "forgemind-demo_demo_postgres_data" "forgemind-demo" "postgres_data"
set_volume "forgemind-demo_demo_redis_data" "forgemind-demo" "demo_redis_data"
run_reset "${TMP_DIR}/correct.yml" "${DEMO_ENV}"
if [ "${LAST_RC}" -eq 1 ] && printf '%s' "${LAST_OUT}" | grep -q 'refusing to remove'; then
    ok "F2 wrong logical-volume label refuses removal"
else
    fail "F2 wrong logical-volume label not refused (rc=${LAST_RC})"
fi
if [ ! -s "${CTRL}/removed.log" ]; then
    ok "F2 wrong-label volume was not removed"
else
    fail "F2 wrong-label volume was removed: $(cat "${CTRL}/removed.log")"
fi

# 12c. Missing PG/Redis volumes is deterministic and safe (fresh state)
reset_ctrl
# no set_volume calls -> both data volumes absent
run_reset "${TMP_DIR}/correct.yml" "${DEMO_ENV}"
if [ "${LAST_RC}" -eq 0 ] && printf '%s' "${LAST_OUT}" | grep -q 'reset generation complete'; then
    ok "F2 missing data volumes treated as fresh state (reset succeeds)"
else
    fail "F2 missing-volume reset failed (rc=${LAST_RC})"
fi
if [ ! -s "${CTRL}/removed.log" ]; then
    ok "F2 nothing removed when volumes absent"
else
    fail "F2 removed volumes despite absent state: $(cat "${CTRL}/removed.log")"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo "----"
echo "demo reset guard tests: ${PASSES} passed, ${FAILURES} failed"
if [ "${FAILURES}" -gt 0 ]; then
    exit 1
fi
