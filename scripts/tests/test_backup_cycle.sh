#!/usr/bin/env bash
# Tests for scripts/backup-cycle.sh (WP-P7-02 remediation F-3).
#
# Proves the scheduled-cycle contract without a real PostgreSQL:
#   1. forced pg_dump failure:
#      - non-zero exit (CYCLE_ONCE=1);
#      - retention (prune) NOT invoked;
#      - no success marker printed;
#      - failed dump not retained as a valid backup (no .dump file
#        remains; the .part staging file is removed);
#      - state marker records "failed".
#   2. successful cycle:
#      - exactly one dump created;
#      - permissions 600;
#      - retention runs after success (a >RETENTION_DAYS dump is pruned);
#      - state marker records "ok";
#      - success is logged only after actual success.
#   3. bounded single-cycle exit codes (CYCLE_ONCE=1 — reserved for
#      tests/manual one-shot use, NOT for the Compose daemon under
#      `restart: unless-stopped`).
#
# Uses a mocked pg_dump on PATH; no real database is touched.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CYCLE_SCRIPT="${SCRIPT_DIR}/../backup-cycle.sh"
PRUNE_SCRIPT="${SCRIPT_DIR}/../backup-prune.sh"
HARNESS_DIR="$(mktemp -d)"
trap 'rm -rf "${HARNESS_DIR}"' EXIT

FAILURES=0
PASSES=0

ok() {
    PASSES=$((PASSES + 1))
    echo "ok   - $1"
}

fail() {
    FAILURES=$((FAILURES + 1))
    echo "FAIL - $1" >&2
}

# ---------------------------------------------------------------------------
# Shared harness pieces
# ---------------------------------------------------------------------------
BACKUP_DIR="${HARNESS_DIR}/backups"
mkdir -p "${BACKUP_DIR}"

_run_cycle() {
    # Run exactly one cycle with the given mock bin directory on PATH.
    local mock_bin="$1"
    PATH="${mock_bin}:${PATH}" \
        PGHOST=pg \
        POSTGRES_USER=forgemind \
        POSTGRES_DB=forgemind \
        BACKUP_DIR="${BACKUP_DIR}" \
        STATE_FILE="${BACKUP_DIR}/last_backup_state" \
        CYCLE_ONCE=1 \
        RETENTION_DAYS=7 \
        bash "${CYCLE_SCRIPT}"
}

_mock_pg_dump() {
    # $1: mode — ok|fail
    local mode="$1"
    local mock_bin="${HARNESS_DIR}/bin-${mode}"
    mkdir -p "${mock_bin}"
    cat > "${mock_bin}/pg_dump" <<EOF
#!/usr/bin/env bash
out=""
next=""
for arg in "\$@"; do
    case "\${arg}" in
        -f) next=out ;;
        *)   [ "\${next}" = out ] && { out="\${arg}"; next=""; } ;;
    esac
done
if [ "${mode}" = "fail" ]; then
    echo "pg_dump: simulated connection failure" >&2
    exit 3
fi
printf 'PGDMP' > "\${out}"
exit 0
EOF
    chmod +x "${mock_bin}/pg_dump"
    echo "${mock_bin}"
}

# ---------------------------------------------------------------------------
# Test 1..4: forced pg_dump failure
# ---------------------------------------------------------------------------
FAIL_BIN="$(_mock_pg_dump fail)"

# Pre-seed one OLD dump that retention WOULD delete if it ran after failure.
OLD_DUMP="${BACKUP_DIR}/forgemind-20250101_000000.dump"
printf 'OLD' > "${OLD_DUMP}"
touch -d "30 days ago" "${OLD_DUMP}"

set +e
FAIL_OUTPUT="$(_run_cycle "${FAIL_BIN}" 2>&1)"
FAIL_RC=$?
set -e

if [ "${FAIL_RC}" -ne 0 ]; then
    ok "pg_dump failure exits non-zero (got ${FAIL_RC})"
else
    fail "pg_dump failure exits non-zero (got 0)"
fi

if [ -f "${OLD_DUMP}" ]; then
    ok "retention NOT run after failed dump (old dump untouched)"
else
    fail "retention NOT run after failed dump (old dump was pruned)"
fi

if echo "${FAIL_OUTPUT}" | grep -q "SUCCESS"; then
    fail "no success marker after failed dump (SUCCESS present)"
else
    ok "no success marker after failed dump"
fi

if echo "${FAIL_OUTPUT}" | grep -q "FAILURE"; then
    ok "failure logged visibly"
else
    fail "failure logged visibly"
fi

if [ -s "${BACKUP_DIR}/last_backup_state" ] \
    && grep -q '^failed ' "${BACKUP_DIR}/last_backup_state"; then
    ok "state marker records failure"
else
    fail "state marker records failure"
fi

# No .dump file may remain from this cycle (partials removed). The only
# .dump present must be the pre-seeded old dump we planted.
STRANGE_DUMPS="$(find "${BACKUP_DIR}" -maxdepth 1 -name 'forgemind-*.dump' -type f ! -name 'forgemind-20250101_000000.dump')"
if [ -z "${STRANGE_DUMPS}" ]; then
    ok "failed dump not retained as a valid backup"
else
    fail "failed dump not retained as a valid backup (stray dump(s): ${STRANGE_DUMPS})"
fi

PARTIALS="$(find "${BACKUP_DIR}" -maxdepth 1 -name '*.dump.part' -type f | wc -l | tr -d ' ')"
if [ "${PARTIALS}" = "0" ]; then
    ok "partial staging file removed after failure"
else
    fail "partial staging file removed after failure (${PARTIALS} partials)"
fi

# ---------------------------------------------------------------------------
# Test 5..9: successful cycle
# ---------------------------------------------------------------------------
# Remove the failure state first.
rm -f "${BACKUP_DIR}/last_backup_state"

OK_BIN="$(_mock_pg_dump ok)"
set +e
OK_OUTPUT="$(_run_cycle "${OK_BIN}" 2>&1)"
OK_RC=$?
set -e

if [ "${OK_RC}" -eq 0 ]; then
    ok "successful cycle exits 0"
else
    fail "successful cycle exits 0 (got ${OK_RC})"
fi

DUMP_COUNT="$(find "${BACKUP_DIR}" -maxdepth 1 -name 'forgemind-*.dump' -type f | wc -l | tr -d ' ')"
# The old pre-seeded dump was > 7 days old and MUST have been pruned by
# the retention step that runs after success.
if [ ! -f "${OLD_DUMP}" ]; then
    ok "retention runs after successful dump"
else
    fail "retention runs after successful dump (old dump survived)"
fi

if [ "${DUMP_COUNT}" = "1" ]; then
    ok "successful cycle produced exactly one dump"
else
    fail "successful cycle produced exactly one dump (got ${DUMP_COUNT})"
fi

NEW_DUMP="$(find "${BACKUP_DIR}" -maxdepth 1 -name 'forgemind-*.dump' -type f | head -1)"
if [ "$(stat -c '%a' "${NEW_DUMP}")" = "600" ]; then
    ok "successful dump is mode 600"
else
    fail "successful dump is mode 600 (got $(stat -c '%a' "${NEW_DUMP}"))"
fi

if [ -s "${BACKUP_DIR}/last_backup_state" ] \
    && grep -q '^ok ' "${BACKUP_DIR}/last_backup_state"; then
    ok "state marker records success"
else
    fail "state marker records success"
fi

if echo "${OK_OUTPUT}" | grep -q "SUCCESS"; then
    ok "success logged after actual success"
else
    fail "success logged after actual success"
fi

# ---------------------------------------------------------------------------
# Test 10: bounded single-cycle exit codes (CYCLE_ONCE=1): non-zero on
# failure (proven above), zero on success. The harness runs every cycle
# with CYCLE_ONCE=1 only to force a deterministic exit for assertions;
# Docker restart behavior is NOT asserted here, and CYCLE_ONCE=1 is not
# part of the production daemon configuration.
# ---------------------------------------------------------------------------
# Partial staging files must be gone.
PARTIALS_AFTER_OK="$(find "${BACKUP_DIR}" -maxdepth 1 -name '*.dump.part' -type f | wc -l | tr -d ' ')"
if [ "${PARTIALS_AFTER_OK}" = "0" ]; then
    ok "no staging partials remain after success"
else
    fail "no staging partials remain after success (${PARTIALS_AFTER_OK} partials)"
fi

# ---------------------------------------------------------------------------
# Test 11: hollow-success guard — pg_dump exits 0 but produces NOTHING.
# (The busybox-ash defect class: chmod/mv/rename failing silently under
# set -e must never lead to a SUCCESS message.)
# ---------------------------------------------------------------------------
HOLLOW_BIN="${HARNESS_DIR}/bin-hollow"
mkdir -p "${HOLLOW_BIN}"
cat > "${HOLLOW_BIN}/pg_dump" <<'EOF'
#!/usr/bin/env bash
# pg_dump exits 0 but writes no output file (simulated broken toolchain).
exit 0
EOF
chmod +x "${HOLLOW_BIN}/pg_dump"

rm -f "${BACKUP_DIR}/last_backup_state"
set +e
HOLLOW_OUTPUT="$(_run_cycle "${HOLLOW_BIN}" 2>&1)"
HOLLOW_RC=$?
set -e

if [ "${HOLLOW_RC}" -ne 0 ]; then
    ok "hollow success (exit 0, no file) is treated as failure"
else
    fail "hollow success (exit 0, no file) is treated as failure (rc=0)"
fi

if echo "${HOLLOW_OUTPUT}" | grep -q "SUCCESS"; then
    fail "hollow success must not print SUCCESS"
else
    ok "hollow success must not print SUCCESS"
fi

if [ -s "${BACKUP_DIR}/last_backup_state" ] \
    && grep -q '^failed ' "${BACKUP_DIR}/last_backup_state"; then
    ok "hollow success records failure state"
else
    fail "hollow success records failure state"
fi

HOLLOW_DUMP_COUNT="$(find "${BACKUP_DIR}" -maxdepth 1 -name 'forgemind-*.dump' -type f | wc -l | tr -d ' ')"
# The only surviving .dump must be the one from the earlier successful
# cycle (the hollow cycle produced nothing).
if [ "${HOLLOW_DUMP_COUNT}" = "1" ]; then
    ok "hollow success leaves the previous valid backup intact"
else
    fail "hollow success leaves the previous valid backup intact (got ${HOLLOW_DUMP_COUNT})"
fi

echo ""
echo "result: ${PASSES} passed, ${FAILURES} failed"
if [ "${FAILURES}" -ne 0 ]; then
    exit 1
fi
exit 0
