#!/bin/sh
# ForgeMind backup retention primitive (WP-P7-02).
#
# THE single authoritative retention implementation. Used by:
#   - scripts/backup-cycle.sh (compose scheduled backup profile);
#   - scripts/backup.sh prune (manual operator tool).
#
# Deletes ONLY files named forgemind-*.dump directly inside <bakdir>
# that are strictly older than <days> days (find -mtime +N). POSIX-sh
# compatible (busybox ash safe).
#
# Usage:
#   backup-prune.sh <bakdir> <days>
#
# Glob: forgemind-*.dump — staged partial files (*.dump.part) can never
# be pruned as if they were valid backups.
set -eu

bakdir="${1:?usage: backup-prune.sh <bakdir> <days>}"
days="${2:?usage: backup-prune.sh <bakdir> <days>}"

echo "deleting backups older than ${days} days in ${bakdir}"
find "${bakdir}" -maxdepth 1 -name 'forgemind-*.dump' -type f \
    -mtime "+${days}" -print -delete

exit 0
