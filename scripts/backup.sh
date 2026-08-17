#!/usr/bin/env bash
# ForgeMind backup/restore operations (WP-P7-02).
#
# Repository-owned missing pieces for the Phase 7 contract (PD-8):
#   - daily PostgreSQL pg_dump (compose backup profile does scheduling);
#   - seven-day retention (enforced here and in the backup loop);
#   - restore procedure (executable on a deployment host);
#   - restore rehearsal (runs restore to a THROWAWAY database so the
#     procedure can be rehearsed before production without touching the
#     production database).
#
# Usage:
#   ops/backup.sh backup    <outdir>   one manual postgres backup
#   ops/backup.sh prune     <bakdir> <days>   delete dumps older than N days
#   ops/backup.sh restore   <dump> <target-db>   restore into an existing DB
#   ops/backup.sh rehearse  <bakdir> <target-db>  restore + verify + drop scratch
#
# Environment (deployment host):
#   PGHOST / PGPORT / PGUSER / PGPASSWORD — as configured for the
#   deployment (or use --env-file when run via compose exec).
#
# NOTE (honest scope): the compose backup profile performs the daily
# pg_dump on the host via a bind-mounted ./backups directory; this file
# is the operational wrapper that an admin uses manually and that the
# restore rehearsal uses. Backups are NOT claimed verified here unless
# run against an authorized local/test environment.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    echo "Usage: $0 {backup|prune|restore|rehearse} ..." >&2
    exit 2
}

cmd="${1:-}"
[ -n "${cmd}" ] || usage
shift || true

case "${cmd}" in
    backup)
        outdir="${1:?usage: backup <outdir>}"
        mkdir -p "${outdir}"
        outfile="${outdir}/forgemind-$(date -u +%Y%m%d_%H%M%S).dump"
        pg_dump --format=custom --no-password \
            --file="${outfile}" --verbose
        chmod 600 "${outfile}"
        echo "backup written: ${outfile}"
        ;;

    prune)
        bakdir="${1:?usage: prune <bakdir> <days>}"
        days="${2:?usage: prune <bakdir> <days>}"
        # Delegates to the single authoritative retention primitive
        # shared with the compose scheduled cycle (scripts/backup-prune.sh).
        sh "${SCRIPT_DIR}/backup-prune.sh" "${bakdir}" "${days}"
        ;;

    restore)
        dump="${1:?usage: restore <dump> <target-db>}"
        target_db="${2:?usage: restore <dump> <target-db>}"
        pg_restore --dbname="${target_db}" --no-owner --no-privileges \
            --verbose "${dump}"
        echo "restored ${dump} into database ${target_db}"
        ;;

    rehearse)
        bakdir="${1:?usage: rehearse <bakdir> <target-db>}"
        target_db="${2:?usage: rehearse <bakdir> <target-db>}"
        latest="$(ls -1t "${bakdir}"/forgemind-*.dump 2>/dev/null | head -1 || true)"
        if [ -z "${latest}" ]; then
            echo "rehearsal FAILED: no backups found in ${bakdir}" >&2
            exit 1
        fi

        scratch_db="forgemind_rehearsal_$(date +%s)"
        cleanup() {
            dropdb --if-exists "${scratch_db}" >/dev/null 2>&1 || true
        }
        trap cleanup EXIT

        echo "rehearsal: creating scratch database ${scratch_db}"
        createdb "${scratch_db}"

        echo "rehearsal: restoring ${latest} into ${scratch_db}"
        pg_restore --dbname="${scratch_db}" --no-owner --no-privileges "${latest}"

        echo "rehearsal: verifying restored schema"
        CHECK_COUNT="$(psql -d "${scratch_db}" -tAc \
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema');")"
        echo "rehearsal: restored ${CHECK_COUNT} tables"

        echo "rehearsal: dropping scratch database ${scratch_db}"
        dropdb "${scratch_db}"
        trap - EXIT
        echo "RESTORE REHEARSAL PASSED"
        ;;

    *)
        usage
        ;;
esac

exit 0
