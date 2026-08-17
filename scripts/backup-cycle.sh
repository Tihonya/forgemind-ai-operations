#!/bin/sh
# ForgeMind scheduled backup-cycle primitive (WP-P7-02).
#
# POSIX-sh compatible (runs inside the postgres:16-alpine backup
# container on busybox ash AND on any deployment host). This is the ONE
# authoritative scheduled-backup implementation: the compose backup
# profile references it directly; scripts/backup.sh is the manual
# operator wrapper (backup / prune / restore / rehearse) and delegates
# its retention to scripts/backup-prune.sh — the same primitive used
# here.
#
# Guarantees (remediation F-3):
#   1. pg_dump failure STOPS the cycle: retention is NEVER run after a
#      failed dump.
#   2. partial/failed dump files never survive: dumps are written to
#      `<out>.part` and atomically renamed only after success, so a
#      failed dump can never be mistaken for a valid backup.
#   2b. hollow success is impossible: every post-dump step (chmod, size
#      verify, rename) is checked explicitly, so a pg_dump that exits 0
#      without producing a file can never be followed by a SUCCESS
#      message or a retention run.
#   3. successful dump is chmod 600 before the atomic rename.
#   4. success is logged ONLY after an actual successful dump.
#   5. failure is visible: the cycle writes a state marker
#      ($STATE_FILE, default /backups/last_backup_state) containing
#      "ok <epoch>" or "failed <epoch>", and logs the failure to
#      stderr. The backup service healthcheck reads the state marker.
#      The marker is non-secret (ok|failed + epoch only); its file
#      mode follows the container umask by design (no 0600 requirement
#      — it is not a secret-bearing artifact).
#   6. after a failure the cycle retries after RETRY_SLEEP (default
#      3600s) so a transient outage recovers without ever deleting
#      good backups; retention runs only on a successful cycle.
#
# Environment:
#   POSTGRES_USER / POSTGRES_DB / PGPASSWORD — as supplied by the
#     compose service (or the deployment environment).
#   PGHOST (default postgres) — dump source host.
#   BACKUP_DIR (default /backups) — output directory (bind-mounted).
#   STATE_FILE (default $BACKUP_DIR/last_backup_state).
#   SLEEP_SECONDS (default 86400) — interval between successful cycles.
#   RETRY_SLEEP (default 3600) — wait before retrying a failed cycle.
#   RETENTION_DAYS (default 7).
#   CYCLE_ONCE=1 — run exactly one cycle and exit 0 (success) or
#     non-zero (failure). Reserved for TESTS, manual one-shot
#     invocation, and controlled external execution ONLY. Docker's
#     `restart: unless-stopped` restarts the container after BOTH
#     exit 0 and exit non-zero, so CYCLE_ONCE=1 MUST NOT be enabled
#     on the long-running Compose backup daemon while that restart
#     policy remains configured: a clean bounded-cycle exit would
#     restart the container and re-dump in a tight loop (backup
#     storm), and a failing cycle would churn restarts.
#   Committed production mode intentionally leaves CYCLE_ONCE UNSET:
#     the scheduling loop is internal to this script — success sleeps
#     SLEEP_SECONDS (default 86400), failure sleeps RETRY_SLEEP
#     (default 3600) and retries. Because the process remains running,
#     the restart policy does not control ordinary daily scheduling;
#     it engages only if the process dies unexpectedly.
#
# No secrets are printed: pg_dump errors pass through without echoing
# credentials (PGPASSWORD is never interpolated into log lines).
set -eu

PGHOST="${PGHOST:-postgres}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
STATE_FILE="${STATE_FILE:-${BACKUP_DIR}/last_backup_state}"
SLEEP_SECONDS="${SLEEP_SECONDS:-86400}"
RETRY_SLEEP="${RETRY_SLEEP:-3600}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
CYCLE_ONCE="${CYCLE_ONCE:-0}"

SCRIPT_DIR="$(dirname "$0")"

prune_backups() {
    # Single authoritative retention implementation (scripts/backup-prune.sh).
    sh "${SCRIPT_DIR}/backup-prune.sh" "${BACKUP_DIR}" "${RETENTION_DAYS}"
}

mark_failed() {
    echo "failed $(date +%s)" > "${STATE_FILE}"
}

run_cycle() {
    ts="$(date -u +%Y%m%d_%H%M%S)"
    out="${BACKUP_DIR}/forgemind-${ts}.dump"
    partial="${out}.part"

    mkdir -p "${BACKUP_DIR}"
    echo "[backup] starting pg_dump at $(date -u +%Y-%m-%dT%H:%M:%SZ)"

    # 2. staged dump: partial files never match the valid-backup glob.
    # Every subsequent step is checked EXPLICITLY (busybox ash does not
    # reliably abort `then`-branch chains under set -e), so a failed
    # chmod/mv/verify can never be followed by a success message.
    if pg_dump -h "${PGHOST}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        -Fc -f "${partial}"; then
        :
    else
        rc=$?
        # 3. failed/partial dump is removed — never retained.
        rm -f "${partial}"
        mark_failed
        echo "[backup] FAILURE: pg_dump exited ${rc}; retention NOT run; retrying in ${RETRY_SLEEP}s" >&2
        return 1
    fi

    if ! chmod 600 "${partial}"; then
        rm -f "${partial}"
        mark_failed
        echo "[backup] FAILURE: could not set mode 600 on dump; retention NOT run" >&2
        return 1
    fi

    if [ ! -s "${partial}" ]; then
        rm -f "${partial}"
        mark_failed
        echo "[backup] FAILURE: produced dump file is missing or empty; retention NOT run" >&2
        return 1
    fi

    if ! mv "${partial}" "${out}"; then
        rm -f "${partial}"
        mark_failed
        echo "[backup] FAILURE: could not finalize dump file; retention NOT run" >&2
        return 1
    fi

    # 4. retention runs only after a verified successful dump.
    prune_backups
    echo "ok $(date +%s)" > "${STATE_FILE}"
    echo "[backup] SUCCESS: wrote ${out} (mode 600); retention cleanup done"
    return 0
}

while :; do
    if run_cycle; then
        if [ "${CYCLE_ONCE}" = "1" ]; then
            exit 0
        fi
        sleep "${SLEEP_SECONDS}"
    else
        if [ "${CYCLE_ONCE}" = "1" ]; then
            exit 1
        fi
        sleep "${RETRY_SLEEP}"
    fi
done
