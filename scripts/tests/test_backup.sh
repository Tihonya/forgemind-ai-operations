#!/usr/bin/env bash
# Tests for scripts/backup.sh (WP-P7-02).
#
# Covers the operator contract without a real PostgreSQL:
#   - usage/argument handling;
#   - prune retention (find-based, real temp dir + real files);
#   - backup happy path with a mocked pg_dump;
#   - rehearsal failure surfaces broken/empty pools.
#
# restore/rehearse full paths script against a real throwaway DB (with
# real pg_restore/psql binaries) are NOT exercised here — that belongs
# to the separately bounded restore-rehearsal validation performed
# against an authorized local/test environment before production
# (Phase 7 section 10 gates).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SCRIPT="${SCRIPT_DIR}/../backup.sh"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

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

expect_code() {
    local label="$1" expected="$2"
    shift 2
    if "$@" >/dev/null 2>&1; then
        actual=0
    else
        actual=$?
    fi
    if [ "${actual}" -eq "${expected}" ]; then
        ok "${label}"
    else
        fail "${label} (expected ${expected}, got ${actual})"
    fi
}

# ---------------------------------------------------------------------------
# 1. Usage errors exit 2
# ---------------------------------------------------------------------------
expect_code "no args exits 2" 2 bash "${BACKUP_SCRIPT}"
expect_code "unknown command exits 2" 2 bash "${BACKUP_SCRIPT}" nope

# ---------------------------------------------------------------------------
# 2. backup writes a chmod-600 custom-format dump (mocked pg_dump)
# ---------------------------------------------------------------------------
MOCK_BIN="${TMP_DIR}/bin"
mkdir -p "${MOCK_BIN}"
cat > "${MOCK_BIN}/pg_dump" <<'EOF'
#!/usr/bin/env bash
# pg_dump --format=custom --no-password --file=OUT --verbose
out=""
for arg in "$@"; do
    case "${arg}" in
        --file=*) out="${arg#--file=}" ;;
    esac
done
[ -n "${out}" ] || exit 9
printf 'PGDMP' > "${out}"
exit 0
EOF
chmod +x "${MOCK_BIN}/pg_dump"

OUT="${TMP_DIR}/backups"
mkdir -p "${OUT}"
if PATH="${MOCK_BIN}:${PATH}" bash "${BACKUP_SCRIPT}" backup "${OUT}" >/dev/null 2>&1; then
    ok "backup succeeds with mocked pg_dump"
else
    fail "backup succeeds with mocked pg_dump"
fi

dump_count="$(find "${OUT}" -name 'forgemind-*.dump' -type f | wc -l | tr -d ' ')"
if [ "${dump_count}" = "1" ]; then
    ok "backup produced exactly one dump file"
else
    fail "backup produced exactly one dump file (got ${dump_count})"
fi

dump_file="$(find "${OUT}" -name 'forgemind-*.dump' -type f | head -1)"
if [ "$(stat -c '%a' "${dump_file}")" = "600" ]; then
    ok "dump file permissions are 600"
else
    fail "dump file permissions are 600"
fi

# ---------------------------------------------------------------------------
# 3. prune deletes only files older than N days
# ---------------------------------------------------------------------------
OUT2="${TMP_DIR}/prune"
mkdir -p "${OUT2}"
touch -d "10 days ago" "${OUT2}/forgemind-20260101.dump"
touch -d "2 days ago" "${OUT2}/forgemind-20260815.dump"
touch "${OUT2}/notabackup.txt"

bash "${BACKUP_SCRIPT}" prune "${OUT2}" 7 >/dev/null 2>&1

if [ ! -f "${OUT2}/forgemind-20260101.dump" ] && [ -f "${OUT2}/forgemind-20260815.dump" ] && [ -f "${OUT2}/notabackup.txt" ]; then
    ok "prune removes only >7-day dumps"
else
    fail "prune removes only >7-day dumps"
fi

# ---------------------------------------------------------------------------
# 4. rehearsal over an empty backup directory fails loudly
# ---------------------------------------------------------------------------
EMPTY="${TMP_DIR}/empty"
mkdir -p "${EMPTY}"
expect_code "rehearse over empty pool fails" 1 \
    env PGHOST=localhost bash "${BACKUP_SCRIPT}" rehearse "${EMPTY}" somedb

echo ""
echo "result: ${PASSES} passed, ${FAILURES} failed"
if [ "${FAILURES}" -ne 0 ]; then
    exit 1
fi
exit 0
