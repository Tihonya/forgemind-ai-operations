#!/usr/bin/env bash
# Tests for infra/docker/worker-healthcheck.sh (WP-P7-02).
#
# These tests build a fake redis-cli into a temp directory and prepend it
# to PATH — no real Redis is required and no secrets are involved. The
# tests cover the liveness contract of the container healthcheck: only a
# well-formed ARQ heartbeat marks the worker as healthy.
#
# Run: bash scripts/tests/test_worker_healthcheck.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HEALTHCHECK="${SCRIPT_DIR}/../../infra/docker/worker-healthcheck.sh"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

# ---------------------------------------------------------------------------
# Fake redis-cli: GET <key> behaves according to FAKE_REDIS_MODE.
#   heartbeat -> prints FAKE_REDIS_VALUE
#   offline   -> prints nothing (empty)
#   malformed -> prints FAKE_REDIS_VALUE (the test supplies junk)
#   partial   -> prints FAKE_REDIS_VALUE
#   error     -> exits 1 with an error message on stderr
# ---------------------------------------------------------------------------
cat > "${TMP_DIR}/redis-cli" <<'EOF'
#!/usr/bin/env bash
# Arg shape: redis-cli -u <url> --no-auth-warning GET <key>
case "${FAKE_REDIS_MODE:-offline}" in
    heartbeat|malformed|partial)
        printf '%s' "${FAKE_REDIS_VALUE:-}"
        ;;
    offline)
        :
        ;;
    error)
        echo "simulated redis failure" >&2
        exit 1
        ;;
    *)
        exit 1
        ;;
esac
exit 0
EOF
chmod +x "${TMP_DIR}/redis-cli"

export PATH="${TMP_DIR}:${PATH}"

FAILURES=0
PASSES=0

assert_exit() {
    local label="$1"
    local expected="$2"
    local mode="$3"
    local value="${4:-}"

    local code
    code="$(FAKE_REDIS_MODE="${mode}" FAKE_REDIS_VALUE="${value}" bash "${HEALTHCHECK}" >/dev/null 2>&1; echo $?)"

    if [ "${code}" -eq "${expected}" ]; then
        PASSES=$((PASSES + 1))
        echo "ok   - ${label} (exit ${code})"
    else
        FAILURES=$((FAILURES + 1))
        echo "FAIL - ${label}: expected exit ${expected}, got ${code}" >&2
    fi
}

# ---------------------------------------------------------------------------
# Case 1: healthy — well-formed ARQ heartbeat value present
# ---------------------------------------------------------------------------
assert_exit "healthy heartbeat accepted" \
    0 "heartbeat" '{Aug-17 10:00:00} j_complete=12 j_failed=0 j_retried=0'

# ---------------------------------------------------------------------------
# Case 2: absent heartbeat — worker not started / stopped
# ---------------------------------------------------------------------------
assert_exit "absent heartbeat rejected" \
    1 "offline" ""

# ---------------------------------------------------------------------------
# Case 3: malformed heartbeat — must NOT be treated as healthy
# ---------------------------------------------------------------------------
assert_exit "malformed heartbeat rejected" \
    1 "malformed" "not-an-arq-heartbeat"

# ---------------------------------------------------------------------------
# Case 4: missing signature fields — must NOT be treated as healthy
# ---------------------------------------------------------------------------
assert_exit "heartbeat missing signature fields rejected" \
    1 "partial" "{Aug-17 10:00:00} j_complete=12"

# ---------------------------------------------------------------------------
# Case 5: redis-cli error — healthcheck must fail, not crash
# ---------------------------------------------------------------------------
assert_exit "redis-cli failure rejected" \
    1 "error" ""

echo ""
echo "result: ${PASSES} passed, ${FAILURES} failed"
if [ "${FAILURES}" -ne 0 ]; then
    exit 1
fi
exit 0
