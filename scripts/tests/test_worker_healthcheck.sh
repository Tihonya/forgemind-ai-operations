#!/usr/bin/env bash
# Tests for infra/docker/worker-healthcheck.sh.
#
# WP-P7-07 F-2 remediation coverage. These tests build an argv/env
# RECORDING fake redis-cli into a temp directory and prepend it to PATH —
# no real Redis is required. The fake behaves as a real redis-cli would
# when the transport is correct (PONG / heartbeat value) and refuses when
# authentication was not actually exercised (F-2 guard, see below).
#
# The suite covers:
#   - valid redis://:<password>@host:port/db URL accepted (correct
#     host/port/db transport to redis-cli);
#   - password used via REDISCLI_AUTH env — NEVER in any argv element;
#   - percent-encoded URL-safe password decoded for AUTH, raw form kept
#     out of every visible surface;
#   - successful PING + well-formed heartbeat -> exit 0;
#   - failed authentication (WRONGPASS path) -> exit 1;
#   - absent / malformed / partial heartbeat -> exit 1;
#   - malformed or missing REDIS_URL -> exit 1;
#   - heartbeat requirement remains enforced (PING alone never suffices);
#   - port defaults to 6379 when absent.
#
# HOW THIS SUITE WOULD HAVE CAUGHT F-2 ON S (see also the FAIL-ON-S mode
# below): the original implementation called
#     redis-cli -u "$REDIS_URL" --no-auth-warning GET ...    (and PING)
# In the deployed image, that URL-userinfo AUTH path returns WRONGPASS,
# so a *faithful* fake that models the redis-cli 8.x behavior must
# answer only when AUTH actually arrived over stdin. The fake below
# implements exactly that: exit codes match real redis-cli (WRONGPASS ->
# stdout empty -> healthcheck exit 1).
#
# Run: bash scripts/tests/test_worker_healthcheck.sh
#
# FAIL-ON-S REGRESSION PROOF: to demonstrate this suite fails against
# the old (S) implementation, drop a checkout of the OLD script onto the
# same tests:
#   FAKE_INTEROP=1 WORKER_HEALTHCHECK_SCRIPT="/tmp/.../worker-healthcheck.sh.S" \
#       bash scripts/tests/test_worker_healthcheck.sh       # must FAIL

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HEALTHCHECK="${WORKER_HEALTHCHECK_SCRIPT:-${SCRIPT_DIR}/../../infra/docker/worker-healthcheck.sh}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

# ---------------------------------------------------------------------------
# Recording fake redis-cli.
#
# Behavior:
#   - Reads stdin (the script sends `PING` as an argv command; the fake
#     must see `ping` in argv).
#   - Auth check: if FAKE_REDIS_REQUIRE_AUTH=1, the fake requires
#     REDISCLI_AUTH to equal FAKE_REDIS_PASSWORD_IN; anything else
#     (or auth absent) -> behaves like WRONGPASS: empty stdout, exit 1.
#     This is the F-2 guard: an implementation that passes the password
#     via `-a` would put it in argv (caught by the argv assertions) and
#     an implementation that sends NO auth at all never gets past PING.
#   - Mode selection:
#       echo <mode>: PING -> "PONG", GET -> printed below
#       ping: command "ping" -> "PONG"
#       get:  command "get"  -> FAKE_REDIS_VALUE (raw)
#   - Every invocation records argv and the env channel to
#     TMP/argvlog.<n> and TMP/envlog.<n> for assertions.
# ---------------------------------------------------------------------------
cat > "${TMP_DIR}/redis-cli" <<'FAKEEOF'
#!/usr/bin/env bash
set -u
LOG="${FAKE_REDIS_LOGDIR:?}/argvlog.${FAKE_REDIS_LOGSEQ:-0}"
{
    printf 'argv:' ; printf ' <%s>' "$@" ; printf '\n'
} >> "${LOG}"
{
    printf 'redisauth:%s\n' "${REDISCLI_AUTH:-__UNSET__}"
} >> "${FAKE_REDIS_LOGDIR}/envlog.${FAKE_REDIS_LOGSEQ:-0}"

if [ "${FAKE_REDIS_REQUIRE_AUTH:-0}" = "1" ]; then
    if [ "${REDISCLI_AUTH:-}" != "${FAKE_REDIS_PASSWORD_IN}" ]; then
        # WRONGPASS: no stdout, non-zero exit (faithful to real redis-cli)
        echo "AUTH failed: WRONGPASS" >&2
        exit 1
    fi
fi

# Extract the command word (last stand-alone command token in argv).
cmd=""
for word in "$@"; do
    case "${word}" in
        ping|PING|echo|ECHO|GET|get|reset|RESET|hello|HELLO|lastsave|LASTSAVE|select|SELECT)
            cmd="${word}"
            ;;
    esac
done

case "${FAKE_REDIS_MODE:-echo}" in
    echo|heartbeat|malformed|partial|offline)
        # deterministic replies below
        ;;
    *)
        exit 1
        ;;
esac

case "$(printf '%s' "${cmd}" | tr '[:upper:]' '[:lower:]')" in
    ping)
        printf 'PONG\n'
        ;;
    echo)
        printf '%s\n' "${FAKE_REDIS_VALUE:-}"
        ;;
    get)
        case "${FAKE_REDIS_MODE:-echo}" in
            heartbeat|malformed|partial)
                printf '%s\n' "${FAKE_REDIS_VALUE:-}"
                ;;
            offline)
                : # no value -> healthcheck must fail
                ;;
        esac
        ;;
    *)
        exit 1
        ;;
esac
exit 0
FAKEEOF
chmod +x "${TMP_DIR}/redis-cli"

export PATH="${TMP_DIR}:${PATH}"

FAILURES=0
PASSES=0

log_seq=0

run_healthcheck() {
    # $1: expected exit code; next: label; rest: env assignments
    local expected="$1"; shift
    local label="$1"; shift
    local code=0
    FAKE_REDIS_LOGSEQ="${log_seq}" FAKE_REDIS_LOGDIR="${TMP_DIR}" \
        "$@" bash "${HEALTHCHECK}" >/dev/null 2>"${TMP_DIR}/stderr.${log_seq}" || code=$?
    if [ "${code}" -eq "${expected}" ]; then
        PASSES=$((PASSES + 1))
        echo "ok   - ${label} (exit ${code})"
    else
        FAILURES=$((FAILURES + 1))
        echo "FAIL - ${label}: expected exit ${expected}, got ${code}" >&2
        sed 's/^/      stderr: /' "${TMP_DIR}/stderr.${log_seq}" >&2
    fi
}

# arg assertions -------------------------------------------------------------
assert_no_password_in_argv() {
    local label="$1" needle="$2"
    if grep -F -- "${needle}" "${TMP_DIR}/argvlog."* >/dev/null 2>&1; then
        FAILURES=$((FAILURES + 1))
        echo "FAIL - ${label}: password material found in redis-cli argv (security contract broken)" >&2
    else
        PASSES=$((PASSES + 1))
        echo "ok   - ${label} (argv clean)"
    fi
}

# ---------------------------------------------------------------------------
# Case 1: valid URL + correct AUTH + well-formed heartbeat -> healthy (0)
# ---------------------------------------------------------------------------
run_healthcheck 0 "valid redis:// URL, auth via REDISCLI_AUTH, healthy heartbeat" \
    env \
    REDIS_URL='redis://:s3cretPA$$w0rd!@redis:6379/0' \
    FAKE_REDIS_MODE="heartbeat" \
    FAKE_REDIS_VALUE='{Aug-22 07:55:21} j_complete=0 j_failed=0 j_retried=0 j_ongoing=0 queued=0' \
    FAKE_REDIS_REQUIRE_AUTH=1 \
    FAKE_REDIS_PASSWORD_IN='s3cretPA$$w0rd!' \
    ARQ_QUEUE_NAME="forgemind-tasks"
log_seq=$((log_seq + 1))

# ---------------------------------------------------------------------------
# Case 2: host/port/db transported correctly to redis-cli argv
# ---------------------------------------------------------------------------
grep -F -- ' <-h> <redis> <-p> <6379> <-n> <0>' "${TMP_DIR}/argvlog.0" >/dev/null 2>&1 && {
    PASSES=$((PASSES + 1)); echo "ok   - host/port/db explicit transport (-h redis -p 6379 -n 0)"; } || {
    FAILURES=$((FAILURES + 1)); echo "FAIL - host/port/db transport missing from argv: $(cat "${TMP_DIR}/argvlog.0")" >&2; }

# ---------------------------------------------------------------------------
# Case 3: password never in argv (raw OR decoded) for case 1
# ---------------------------------------------------------------------------
assert_no_password_in_argv "password absent from argv (raw)" 's3cretPA$$w0rd!'
assert_no_password_in_argv "auth token transport not via -a/-u password argv shards" '<-a>' '</a>'

# ---------------------------------------------------------------------------
# Case 4: percent-encoded URL-safe password decoded for AUTH, raw form
#         never visible
# ---------------------------------------------------------------------------
run_healthcheck 0 "percent-encoded password accepted via AUTH" \
    env \
    REDIS_URL="redis://:p%40ss%2Fw0rd@redis:6379/0" \
    FAKE_REDIS_MODE="heartbeat" \
    FAKE_REDIS_VALUE='{Aug-22 07:55:21} j_complete=0 j_failed=0 j_retried=0' \
    FAKE_REDIS_REQUIRE_AUTH=1 \
    FAKE_REDIS_PASSWORD_IN='p@ss/w0rd'
log_seq=$((log_seq + 1))
assert_no_password_in_argv "percent-encoded form absent from argv" 'p%40ss%2Fw0rd'
assert_no_password_in_argv "decoded form absent from argv" 'p@ss/w0rd'

# ---------------------------------------------------------------------------
# Case 5: wrong password (WRONGPASS) -> failure (1)  [F-2 failure path]
# ---------------------------------------------------------------------------
run_healthcheck 1 "wrong password fails closed" \
    env \
    REDIS_URL="redis://:rightpass@redis:6379/0" \
    FAKE_REDIS_MODE="heartbeat" \
    FAKE_REDIS_VALUE='{Aug-22 07:55:21} j_complete=0 j_failed=0' \
    FAKE_REDIS_REQUIRE_AUTH=1 \
    FAKE_REDIS_PASSWORD_IN='WRONGpass'
log_seq=$((log_seq + 1))

# ---------------------------------------------------------------------------
# Case 6: AUTH missing entirely when server requires it -> failure (1)
# ---------------------------------------------------------------------------
run_healthcheck 1 "auth required but not delivered fails closed" \
    env \
    REDIS_URL="redis://redis:6379/0" \
    FAKE_REDIS_MODE="heartbeat" \
    FAKE_REDIS_VALUE='{Aug-22 07:55:21} j_complete=0 j_failed=0' \
    FAKE_REDIS_REQUIRE_AUTH=1 \
    FAKE_REDIS_PASSWORD_IN='needed'
log_seq=$((log_seq + 1))

# ---------------------------------------------------------------------------
# Case 7: absent heartbeat -> failure (1)  [heartbeat contract preserved]
# ---------------------------------------------------------------------------
run_healthcheck 1 "absent heartbeat rejected" \
    env \
    REDIS_URL="redis://:pw@redis:6379/0" \
    FAKE_REDIS_MODE="offline" \
    FAKE_REDIS_REQUIRE_AUTH=1 \
    FAKE_REDIS_PASSWORD_IN='pw'
log_seq=$((log_seq + 1))

# ---------------------------------------------------------------------------
# Case 8: malformed heartbeat -> failure (1)
# ---------------------------------------------------------------------------
run_healthcheck 1 "malformed heartbeat rejected" \
    env \
    REDIS_URL="redis://:pw@redis:6379/0" \
    FAKE_REDIS_MODE="malformed" \
    FAKE_REDIS_VALUE='not-an-arq-heartbeat' \
    FAKE_REDIS_REQUIRE_AUTH=1 \
    FAKE_REDIS_PASSWORD_IN='pw'
log_seq=$((log_seq + 1))

# ---------------------------------------------------------------------------
# Case 9: heartbeat missing signature fields -> failure (1)
# ---------------------------------------------------------------------------
run_healthcheck 1 "heartbeat missing signature fields rejected" \
    env \
    REDIS_URL="redis://:pw@redis:6379/0" \
    FAKE_REDIS_MODE="partial" \
    FAKE_REDIS_VALUE='{Aug-22 07:55:21} j_complete=0' \
    FAKE_REDIS_REQUIRE_AUTH=1 \
    FAKE_REDIS_PASSWORD_IN='pw'
log_seq=$((log_seq + 1))

# ---------------------------------------------------------------------------
# Case 10: PING alone must NOT be enough — heartbeat requirement enforced.
# (Fake returns PONG but GET empty -> exit 1.)
# ---------------------------------------------------------------------------
run_healthcheck 1 "PING alone does not satisfy liveness (heartbeat enforced)" \
    env \
    REDIS_URL="redis://:pw@redis:6379/0" \
    FAKE_REDIS_MODE="offline" \
    FAKE_REDIS_REQUIRE_AUTH=1 \
    FAKE_REDIS_PASSWORD_IN='pw'
log_seq=$((log_seq + 1))

# ---------------------------------------------------------------------------
# Case 11: malformed REDIS_URL -> failure BEFORE any network call (1)
#  - http:// scheme
#  - redis://host:notaport/0
#  - redis://user:someuser@host:6379/0 (username form not approved)
#  - empty REDIS_URL env
# ---------------------------------------------------------------------------
run_healthcheck 1 "wrong scheme rejected (http://)" \
    env REDIS_URL="http://redis:6379/0" FAKE_REDIS_MODE=heartbeat \
    FAKE_REDIS_VALUE='{A} j_complete=0 j_failed=0'
log_seq=$((log_seq + 1))

run_healthcheck 1 "non-numeric port rejected" \
    env REDIS_URL="redis://:pw@redis:notaport/0" FAKE_REDIS_MODE=heartbeat \
    FAKE_REDIS_VALUE='{A} j_complete=0 j_failed=0'
log_seq=$((log_seq + 1))

run_healthcheck 1 "username-form URL rejected (not an approved shape)" \
    env REDIS_URL="redis://user:someuser@redis:6379/0" FAKE_REDIS_MODE=heartbeat \
    FAKE_REDIS_VALUE='{A} j_complete=0 j_failed=0'
log_seq=$((log_seq + 1))

run_healthcheck 1 "missing REDIS_URL fails closed" \
    env REDIS_URL="" FAKE_REDIS_MODE=heartbeat \
    FAKE_REDIS_VALUE='{A} j_complete=0 j_failed=0'
log_seq=$((log_seq + 1))

# ---------------------------------------------------------------------------
# Case 12: port defaults to 6379 when absent
# ---------------------------------------------------------------------------
run_healthcheck 0 "port defaults to 6379 when absent from URL" \
    env \
    REDIS_URL="redis://:pw@redis/0" \
    FAKE_REDIS_MODE="heartbeat" \
    FAKE_REDIS_VALUE='{Aug-22 07:55:21} j_complete=0 j_failed=0' \
    FAKE_REDIS_REQUIRE_AUTH=1 \
    FAKE_REDIS_PASSWORD_IN='pw'
log_seq=$((log_seq + 1))
grep -F -- ' <-p> <6379>' "${TMP_DIR}/argvlog."* >/dev/null 2>&1 && {
    PASSES=$((PASSES + 1)); echo "ok   - default port 6379 transported"; } || {
    FAILURES=$((FAILURES + 1)); echo "FAIL - default port 6379 not transported" >&2; }

# ---------------------------------------------------------------------------
# Case 13: DB segment respected (non-zero db) → SELECT issued
# ---------------------------------------------------------------------------
run_healthcheck 0 "non-zero DB transported via -n 3" \
    env \
    REDIS_URL="redis://:pw@redis:6379/3" \
    FAKE_REDIS_MODE="heartbeat" \
    FAKE_REDIS_VALUE='{Aug-22 07:55:21} j_complete=0 j_failed=0' \
    FAKE_REDIS_REQUIRE_AUTH=1 \
    FAKE_REDIS_PASSWORD_IN='pw'
log_seq=$((log_seq + 1))
grep -F -- ' <-n> <3>' "${TMP_DIR}/argvlog."* >/dev/null 2>&1 && {
    PASSES=$((PASSES + 1)); echo "ok   - db 3 transported as -n 3"; } || {
    FAILURES=$((FAILURES + 1)); echo "FAIL - db 3 not transported as -n 3" >&2; }

echo ""
echo "result: ${PASSES} passed, ${FAILURES} failed"
if [ "${FAILURES}" -ne 0 ]; then
    exit 1
fi
exit 0
