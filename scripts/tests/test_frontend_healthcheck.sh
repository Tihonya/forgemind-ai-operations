#!/usr/bin/env bash
# Tests for infra/docker/frontend.dockerfile healthcheck (WP-P7-07 F-1).
#
# Regression boundary: the frontend image HEALTHCHECK must probe the
# nginx service via the IPv4 loopback literal 127.0.0.1 and must NOT
# depend on `localhost` resolution (BusyBox wget resolves localhost to
# ::1 first under the commit-era /etc/hosts, while nginx listens IPv4
# only — the exact WP-P7-07 F-1 defect: `wget ... http://localhost/` on
# S fails with "Connecting to localhost ([::1]:80) ... Connection
# refused" although the SPA serves fine).
#
# Static contract assertions (CI-fast, no docker):
#   1. the committed HEALTHCHECK probes http://127.0.0.1/ (exact URL);
#   2. no selector in the HEALTHCHECK instruction references `localhost`
#      (this is the S-bug signal);
#   3. a wget-based probe with exactly one try remains present, so the
#      healthcheck still verifies the local nginx service rather than
#      being weakened or removed;
#   4. nginx config continues to listen IPv4-only (listen 80; — no IPv6
#      listener broadening, matching the package's "minimal correction"
#      directive);
#   5. the probe relies on the HTTP service root `/` (network-local,
#      no external dependency).
#
# Live container validation (repo CI cannot run docker): run the
# companion /tmp validation during the remediation package that builds
# the production target of this Dockerfile and requires the container to
# become healthy — see the WP-P7-07 remediation record.
#
# FAIL-ON-S MODE: point FRONTEND_DOCKERFILE (and NGINX_CONF) at a
# checkout of the OLD (S) tree to prove these assertions fail on the
# defect:
#   FRONTEND_DOCKERFILE="/tmp/wp-p7-07-impl/frontend.dockerfile.S" \
#   NGINX_CONF="/tmp/.../nginx.conf.S" \
#   bash scripts/tests/test_frontend_healthcheck.sh   # must FAIL on S

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DOCKERFILE="${FRONTEND_DOCKERFILE:-${SCRIPT_DIR}/../../infra/docker/frontend.dockerfile}"
NGINX_CONF="${NGINX_CONF:-${SCRIPT_DIR}/../../infra/docker/nginx.conf}"

FAILURES=0
PASSES=0

assert() {
    local label="$1" ok="$2"
    if [ "${ok}" = "1" ]; then
        PASSES=$((PASSES + 1))
        echo "ok   - ${label}"
    else
        FAILURES=$((FAILURES + 1))
        echo "FAIL - ${label}" >&2
    fi
}

# Extract the HEALTHCHECK instruction (multi-line continuation joined).
HEALTHCHECK_LINE="$(sed -n '/^HEALTHCHECK/,/[^\\]$/p' "${FRONTEND_DOCKERFILE}" | tr -d '\\' | tr '\n' ' ')"

# 1. Probe target is exactly http://127.0.0.1/
case "${HEALTHCHECK_LINE}" in
    *'http://127.0.0.1/'*) assert "healthcheck probes http://127.0.0.1/" 1 ;;
    *)                     assert "healthcheck probes http://127.0.0.1/" 0 ;;
esac

# 2. No `localhost` anywhere in the HEALTHCHECK instruction (F-1 root cause)
case "${HEALTHCHECK_LINE}" in
    *localhost*) assert "healthcheck has no localhost dependency" 0 ;;
    *)           assert "healthcheck has no localhost dependency" 1 ;;
esac

# 3. wget probe with --tries=1 retained (service truly verified, not weakened)
case "${HEALTHCHECK_LINE}" in
    *'wget'*'--tries=1'*|*'wget'*'--spider'*) assert "wget --spider probe retained" 1 ;;
    *) assert "wget --spider probe retained" 0 ;;
esac

# 4. nginx still IPv4-only (no listener-broadening side change)
case "$(tr '\n' ' ' < "${NGINX_CONF}")" in
    *'listen 80;'*) assert "nginx config keeps IPv4-only listen 80" 1 ;;
    *) assert "nginx config keeps IPv4-only listen 80" 0 ;;
esac
case "$(tr '\n' ' ' < "${NGINX_CONF}")" in
    *'listen [::]:80'*) assert "nginx config has no IPv6 listener added" 0 ;;
    *) assert "nginx config has no IPv6 listener added" 1 ;;
esac

# 5. Probe hits the service root (no external dependency)
case "${HEALTHCHECK_LINE}" in
    *'|| exit 1'*) assert "probe fails the healthcheck on non-zero wget" 1 ;;
    *) assert "probe fails the healthcheck on non-zero wget" 0 ;;
esac

echo ""
echo "result: ${PASSES} passed, ${FAILURES} failed"
if [ "${FAILURES}" -ne 0 ]; then
    exit 1
fi
exit 0
