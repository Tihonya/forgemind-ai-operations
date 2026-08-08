#!/usr/bin/env bash
# Main entry point: operator runs one command
# Implements: bootstrap guard -> allocate -> implement -> verify -> review ->
#             optional one repair -> reverify -> report
#
# WP-AL-1C6 orchestration wiring:
# - review adapter invoked after initial verify PASS or FAIL (§9)
# - repair adapter invoked after review FAIL + action=repair (§10)
# - maximum ONE repair attempt enforced (§5.3)
# - DEC-C6-02: verification remains authoritative
# - DEC-C6-03: immutable verification evidence (per-phase snapshots + SHA-256)
# - DEC-C6-04: clean committed candidate precondition
# - No Git mutating/publishing/history-rewriting commands (§16.2)
#
# Passport is mandatory: orchestration always creates and validates a cycle
# passport.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/lib/artifacts.sh"
source "$SCRIPT_DIR/lib/guard.sh"

# Project identity (may be overridden via environment)
export PROJECT_ID="${PROJECT_ID:-forgemind}"

# WP-AL-1C6 §5.3: maximum one repair attempt. The manifest repair_budget may
# further narrow this but cannot widen it beyond 1.
MAX_REPAIR_ITERATIONS=1

# WP-AL-1C6 single repair-attempt counter (§5.3).
REPAIR_ATTEMPT=0
REPAIR_ACTOR_INVOCATIONS=0
REPAIR_ADAPTER_INVOCATIONS=0
REVERIFY_INVOCATIONS=0

# WP-AL-1C6 AJ: persist invocation counters to a deterministic artifact so
# harness scenario AJ can prove exactly one repair adapter, one repair actor,
# one reverify, and zero second-repair invocations. Written by
# finalize_and_exit() before exit.
write_invocation_counters() {
  if [[ -n "${RUN_DIR:-}" ]]; then
    "$PYTHON_BIN" "$HARNESS_PY" atomic_write "$RUN_DIR/reports/invocation-counters.json" "$(cat <<EOF
{
  "schema_version": "1.0",
  "run_id": "$RUN_ID",
  "story_id": "$STORY_ID",
  "repair_attempt": $REPAIR_ATTEMPT,
  "repair_adapter_invocations": $REPAIR_ADAPTER_INVOCATIONS,
  "repair_actor_invocations": $REPAIR_ACTOR_INVOCATIONS,
  "reverify_invocations": $REVERIFY_INVOCATIONS
}
EOF
)" 2>/dev/null || true
  fi
}

# Parse arguments
STORY_MANIFEST=""
DRY_RUN="${DRY_RUN:-false}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --manifest|-m)
      STORY_MANIFEST="$2"
      shift 2
      ;;
    --dry-run|-n)
      DRY_RUN="true"
      shift
      ;;
    --max-iterations)
      # WP-AL-1C6: the orchestration-level maximum is 1; a caller value can
      # only narrow it, never widen it (§5.3).
      if [[ "$2" -lt "$MAX_REPAIR_ITERATIONS" ]]; then
        MAX_REPAIR_ITERATIONS="$2"
      fi
      shift 2
      ;;
    --help|-h)
      echo "Usage: $0 [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --manifest, -m FILE      Story manifest JSON (required)"
      echo "  --dry-run, -n            Skip agent invocations, verify only"
      echo "  --max-iterations N       Max repair iterations (WP-AL-1C6 cap: 1)"
      echo "  --help, -h               Show this help"
      echo ""
      echo "Example:"
      echo "  $0 --manifest scripts/agent-loop/templates/story-prd.json"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$STORY_MANIFEST" ]]; then
  echo "ERROR: --manifest is required" >&2
  echo "Usage: $0 --manifest <story.json>" >&2
  exit 1
fi

if [[ ! -f "$STORY_MANIFEST" ]]; then
  echo "ERROR: manifest not found: $STORY_MANIFEST" >&2
  exit 1
fi

# ============================================================================
# Helper: always produce final-report.json before terminating.
# WP-AL-1C6: every terminal path publishes the final report; a reporting
# failure never masks the primary terminal status (exit code preserved).
# ============================================================================
finalize_and_exit() {
  local exit_code="$1"
  local label="$2"
  write_invocation_counters
  if [[ -n "${RUN_DIR:-}" ]]; then
    if ! run_phase_with_guard "report" "control-plane" "reporter" "" >/dev/null 2>&1; then
      echo "REPORT PHASE GUARD FAILED (non-fatal for exit code)" >&2
    fi
    if ! "$SCRIPT_DIR/report-story.sh" "$RUN_DIR" >/dev/null 2>&1; then
      echo "WARNING: report-story.sh failed; final-report.json may be absent" >&2
    fi
  fi
  echo ""
  echo "=========================================="
  echo "AGENT LOOP COMPLETE - $label"
  echo "=========================================="
  if [[ -n "${RUN_DIR:-}" ]]; then
    echo "Artifacts: $RUN_DIR"
  fi
  exit "$exit_code"
}

# ============================================================================
# PHASE: bootstrap guard (before passport exists)
# Validates: infrastructure worktree path, branch, git root, forbidden main worktree
# ============================================================================
echo "=========================================="
echo "AGENT LOOP - Bootstrap Guard"
echo "=========================================="

EXPECTED_BRANCH="$(git branch --show-current 2>/dev/null || echo "unknown")"
BOOTSTRAP_ERROR_DIR="$(mktemp -d /tmp/agent-loop-bootstrap-XXXXXX)"

if ! bootstrap_guard "$REPO_ROOT" "$EXPECTED_BRANCH" "allocate" "$BOOTSTRAP_ERROR_DIR"; then
  echo "BOOTSTRAP GUARD FAILED"
  if [[ -f "$BOOTSTRAP_ERROR_DIR/guard-error.json" ]]; then
    cat "$BOOTSTRAP_ERROR_DIR/guard-error.json"
  fi
  rm -rf "$BOOTSTRAP_ERROR_DIR"
  exit 2
fi
rm -rf "$BOOTSTRAP_ERROR_DIR"
echo "Bootstrap guard passed"
echo ""

# ============================================================================
# PHASE: allocate (create passport)
# ============================================================================
echo "=========================================="
echo "AGENT LOOP - Allocate"
echo "=========================================="

# Extract story ID early for passport (before full manifest validation)
STORY_ID_PRELIM="$("$PYTHON_BIN" -c "
import json, sys
try:
    with open(sys.argv[1]) as f:
        data = json.load(f)
    print(data.get('story_id', 'unknown'))
except Exception:
    print('unknown')
" "$STORY_MANIFEST" 2>/dev/null || echo "unknown")"

export STORY_ID="$STORY_ID_PRELIM"

# Initialize artifacts + slot
init_artifacts "$STORY_ID" > /dev/null
init_slot_id > /dev/null

# Create passport file
PASSPORT_FILE="$RUN_DIR/reports/passport.json"
BASE_COMMIT="$(git rev-parse HEAD 2>/dev/null || echo "unknown")"

create_passport_file \
  "$PASSPORT_FILE" \
  "$PROJECT_ID" \
  "$RUN_ID" \
  "$SLOT_ID" \
  "$STORY_ID" \
  "implementer" \
  "allocate" \
  "control-plane" \
  "$REPO_ROOT" \
  "$EXPECTED_BRANCH" \
  "$BASE_COMMIT" \
  "$(realpath "$STORY_MANIFEST")" \
  "$RUN_DIR" \
  "" > /dev/null

export PASSPORT_FILE
echo "Passport created: $PASSPORT_FILE"
echo "  project_id: $PROJECT_ID"
echo "  run_id: $RUN_ID"
echo "  slot_id: $SLOT_ID"
echo "  story_id: $STORY_ID"
echo "  workspace_root: $REPO_ROOT"
echo "  expected_branch: $EXPECTED_BRANCH"
echo "  base_commit: $BASE_COMMIT"
echo ""

# Validate manifest JSON before processing
if ! "$PYTHON_BIN" "$HARNESS_PY" validate "$STORY_MANIFEST" 2>/dev/null | grep -q "^OK:"; then
  echo "ERROR: manifest is not valid JSON or is missing story_id: $STORY_MANIFEST" >&2

  # Create error report
  "$PYTHON_BIN" "$HARNESS_PY" atomic_write "$RUN_DIR/reports/verify-result.json" "$(cat <<EOF
{
  "schema_version": "1.0",
  "run_id": "$RUN_ID",
  "story_id": "$STORY_ID",
  "started_at": "$(date -Iseconds)",
  "finished_at": "$(date -Iseconds)",
  "overall_status": "ERROR",
  "gates": [],
  "error": "Invalid manifest JSON or missing story_id"
}
EOF
)"

  echo "verify-result.json generated: $RUN_DIR/reports/verify-result.json"
  echo "OVERALL: ERROR"
  exit 2
fi

# Extract confirmed story ID
STORY_ID="$("$PYTHON_BIN" "$HARNESS_PY" validate "$STORY_MANIFEST" | sed 's/^OK://')"
export STORY_ID

echo "=========================================="
echo "AGENT LOOP - Story: $STORY_ID"
echo "Manifest: $STORY_MANIFEST"
echo "Max iterations: $MAX_REPAIR_ITERATIONS"
echo "Dry run: $DRY_RUN"
echo "=========================================="

# ============================================================================
# Helper: phase boundary with guard
# ============================================================================
run_phase_with_guard() {
  local phase_name="$1"
  local expected_ws_type="$2"
  local expected_role="$3"
  local handler_cmd="$4"  # empty string if phase not yet implemented

  echo ""
  echo "--- Phase: $phase_name ---"

  # Update passport phase
  local tmp_passport
  tmp_passport="$(mktemp /tmp/passport-update-XXXXXX.json)"
  "$PYTHON_BIN" -c "
import json, sys
with open(sys.argv[1]) as f:
    p = json.load(f)
p['phase'] = sys.argv[2]
p['workspace_type'] = sys.argv[3]
p['role'] = sys.argv[4]
with open(sys.argv[5], 'w') as f:
    json.dump(p, f, indent=2)
" "$PASSPORT_FILE" "$phase_name" "$expected_ws_type" "$expected_role" "$tmp_passport"
  mv "$tmp_passport" "$PASSPORT_FILE"

  # Run phase guard
  if ! phase_guard "$PASSPORT_FILE" "$phase_name" "$expected_ws_type" "$expected_role" "$RUN_DIR"; then
    echo "IDENTITY GUARD FAILED at phase: $phase_name"
    if [[ -f "$RUN_DIR/guard-error.json" ]]; then
      cat "$RUN_DIR/guard-error.json"
    fi
    return 2
  fi

  # Check if handler exists
  if [[ -z "$handler_cmd" ]]; then
    echo "Phase $phase_name: not yet implemented (deterministic STOP)"
    # Write phase unavailability as informational, not error, since Phase 2 is pending
    "$PYTHON_BIN" "$HARNESS_PY" atomic_write "$RUN_DIR/reports/phase-${phase_name}-status.json" "$(cat <<EOF
{
  "schema_version": "1.0",
  "phase": "$phase_name",
  "status": "NOT_IMPLEMENTED",
  "message": "Phase $phase_name script not yet available (Phase 2 work)",
  "run_id": "$RUN_ID",
  "story_id": "$STORY_ID"
}
EOF
)"
    return 0
  fi

  # Execute handler
  eval "$handler_cmd"
  return $?
}

# ============================================================================
# Helper: write verify-context.json (§5.4)
# ============================================================================
write_verify_context() {
  local verify_type="$1"
  local attempt="$2"

  "$PYTHON_BIN" "$HARNESS_PY" atomic_write "$RUN_DIR/reports/verify-context.json" "$(cat <<EOF
{
  "schema_version": "1.0",
  "run_id": "$RUN_ID",
  "story_id": "$STORY_ID",
  "verify_type": "$verify_type",
  "attempt": $attempt,
  "generated_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
}
EOF
)"
}

# ============================================================================
# Helper: DEC-C6-03 snapshot publication
#
# Copies the canonical working artifacts to immutable per-phase snapshots,
# computes SHA-256 of each snapshot, and re-reads the published copy to verify
# the hash. Publishes an evidence manifest (evidence-manifest.<phase>.json)
# binding snapshot paths to their hashes.
#
# Exits: 0 = all required evidence published and hash-verified
#        1 = publication/hash failure (caller must fail closed)
# ============================================================================
publish_verify_snapshots() {
  local phase="$1"  # "initial" or "reverify"
  local manifest_out="$RUN_DIR/reports/evidence-manifest.${phase}.json"
  local sha_bin
  sha_bin="$(command -v sha256sum || command -v shasum || true)"

  "$PYTHON_BIN" - "$RUN_DIR" "$phase" "$manifest_out" "$RUN_ID" "$STORY_ID" "$sha_bin" <<'SNAP_EOF'
import hashlib
import json
import os
import shutil
import subprocess
import sys

run_dir, phase, manifest_out, run_id, story_id, sha_bin = sys.argv[1:7]
reports = os.path.join(run_dir, "reports")

entries = {}
failures = []

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def publish(src_name, dst_name, required):
    src = os.path.join(reports, src_name)
    dst = os.path.join(reports, dst_name)
    if not os.path.isfile(src):
        if required:
            failures.append(f"missing required source artifact: {src_name}")
        return
    try:
        shutil.copyfile(src, dst)
    except OSError as e:
        failures.append(f"snapshot copy failed for {src_name}: {e}")
        return
    # Hash the published (immutable) copy
    try:
        digest = sha256_file(dst)
    except OSError as e:
        failures.append(f"hash computation failed for {dst_name}: {e}")
        return
    # Independent verification via external sha256 tooling when available
    if sha_bin:
        try:
            if "sha256sum" in sha_bin:
                out = subprocess.run(
                    [sha_bin, dst], capture_output=True, text=True, check=False
                )
                tool_digest = out.stdout.split()[0] if out.returncode == 0 else ""
            else:
                out = subprocess.run(
                    [sha_bin, "-a", "256", dst], capture_output=True, text=True, check=False
                )
                tool_digest = out.stdout.split()[-1] if out.returncode == 0 else ""
            if tool_digest and tool_digest != digest:
                failures.append(
                    f"hash verification mismatch for {dst_name}: "
                    f"python={digest} tool={tool_digest}"
                )
                return
        except (OSError, IndexError):
            pass  # tool unavailable; python digest stands
    # Re-read and verify the immutable copy is byte-stable with the source
    try:
        if sha256_file(src) != digest:
            failures.append(f"source changed during publication: {src_name}")
            return
    except OSError as e:
        failures.append(f"re-read verification failed for {src_name}: {e}")
        return
    entries[dst_name] = {
        "path": f"reports/{dst_name}",
        "sha256": digest,
        "source": f"reports/{src_name}",
        "immutable": True,
    }

publish("verify-result.json", f"verify-result.{phase}.json", required=True)
# failure-context is collected on both PASS and FAIL exits (N1); it is
# required evidence for review/repair requests when present.
publish("failure-context.json", f"failure-context.{phase}.json", required=False)

if failures:
    print("SNAPSHOT_PUBLICATION_FAILED: " + "; ".join(failures), file=sys.stderr)
    sys.exit(1)

manifest = {
    "schema_version": "1.0",
    "run_id": run_id,
    "story_id": story_id,
    "phase": phase,
    "snapshots": entries,
}
try:
    tmp = manifest_out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, manifest_out)
except OSError as e:
    print(f"SNAPSHOT_PUBLICATION_FAILED: manifest write failed: {e}", file=sys.stderr)
    sys.exit(1)

print(f"Snapshot publication ({phase}): OK ({len(entries)} artifact(s))")
for name, entry in sorted(entries.items()):
    print(f"  {name}: sha256={entry['sha256']}")
SNAP_EOF
}

# ============================================================================
# Helper: verify published snapshot hashes still match evidence manifests.
# Used before review/repair bind to immutable evidence and before
# VERIFIED_AFTER_REPAIR is reported (DEC-C6-03: later reverify must never
# silently invalidate evidence referenced by review/repair).
# Exits: 0 = valid, 1 = invalid or missing
# ============================================================================
verify_immutable_evidence() {
  local manifest_path="$1"
  "$PYTHON_BIN" - "$RUN_DIR" "$manifest_path" <<'VERIFY_EV_EOF'
import hashlib
import json
import os
import sys

run_dir, manifest_path = sys.argv[1], sys.argv[2]
if not os.path.isfile(manifest_path):
    print(f"EVIDENCE_INVALID: manifest missing: {manifest_path}", file=sys.stderr)
    sys.exit(1)
try:
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
except (OSError, json.JSONDecodeError) as e:
    print(f"EVIDENCE_INVALID: manifest unreadable: {e}", file=sys.stderr)
    sys.exit(1)

snapshots = manifest.get("snapshots", {})
if not isinstance(snapshots, dict) or not snapshots:
    print("EVIDENCE_INVALID: manifest has no snapshots", file=sys.stderr)
    sys.exit(1)

for name, entry in sorted(snapshots.items()):
    path = os.path.join(run_dir, entry.get("path", name))
    expected = entry.get("sha256", "")
    if not os.path.isfile(path):
        print(f"EVIDENCE_INVALID: snapshot missing: {name}", file=sys.stderr)
        sys.exit(1)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    if h.hexdigest() != expected:
        print(
            f"EVIDENCE_INVALID: hash mismatch for {name}: "
            f"expected {expected}, got {h.hexdigest()}",
            file=sys.stderr,
        )
        sys.exit(1)
print(f"EVIDENCE_VALID: {len(snapshots)} snapshot(s) hash-verified")
VERIFY_EV_EOF
}

# ============================================================================
# Helper: DEC-C6-04 clean-baseline inspection
#
# Distinguishes (per the merged plan §5.7 / §10.2, using the plan's exact
# distinction):
#   - dirty tracked baseline (modified/staged/deleted tracked files)
#     → repair MUST NOT proceed
#   - pre-existing non-ignored untracked paths
#     → recorded and passed to the repair adapter as baseline exclusions
#       (the WP-AL-1C5 adapter's approved mechanism for untracked artifacts)
#   - staged changes (git diff --cached) → dirty
#   - HEAD must resolve to a valid commit
# Read-only Git operations only (§16.2).
# Writes reports/dirty-baseline.json when dirty; exits 0 clean, 1 dirty,
# 2 inspection failure.
# ============================================================================
check_clean_baseline() {
  local reason_context="$1"
  local baseline_artifact="$RUN_DIR/reports/baseline-check.json"

  (cd "$REPO_ROOT" && git status --porcelain=v1 2>/dev/null) > "$RUN_DIR/verify/.baseline-status.txt" 2>&1
  local status_exit=$?
  (cd "$REPO_ROOT" && git diff --cached --name-status 2>/dev/null) > "$RUN_DIR/verify/.baseline-cached.txt" 2>&1
  local cached_exit=$?
  local head_sha
  head_sha="$(cd "$REPO_ROOT" && git rev-parse HEAD 2>/dev/null)" || head_sha=""

  if [[ $status_exit -ne 0 || $cached_exit -ne 0 || -z "$head_sha" ]]; then
    echo "BASELINE INSPECTION FAILED (git read-only inspection error)" >&2
    return 2
  fi

  "$PYTHON_BIN" - \
    "$RUN_DIR/verify/.baseline-status.txt" \
    "$RUN_DIR/verify/.baseline-cached.txt" \
    "$head_sha" \
    "$reason_context" \
    "$baseline_artifact" \
    "$RUN_DIR" \
    "$RUN_ID" \
    "$STORY_ID" <<'BASELINE_EOF'
import json
import os
import sys
from datetime import datetime, timezone

status_file, cached_file, head_sha, reason_context, artifact_path, run_dir, run_id, story_id = sys.argv[1:9]

tracked_dirty = []
untracked = []
with open(status_file, encoding="utf-8") as f:
    for line in f:
        line = line.rstrip("\n")
        if len(line) < 4:
            continue
        x, y = line[0], line[1]
        path = line[3:]
        if x == "?" and y == "?":
            untracked.append(path)
            continue
        # Unmerged in either column
        if x == "U" or y == "U" or (x == "D" and y == "D") or (x == "A" and y == "A"):
            tracked_dirty.append(path)
            continue
        # Staged change (index column) or worktree modification of tracked file
        if x not in (" ", "?", "!") or y in ("M", "D", "T", "R", "C"):
            tracked_dirty.append(path)

staged = []
with open(cached_file, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            staged.append(line)

dirty = bool(tracked_dirty) or bool(staged)
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

record = {
    "schema_version": "1.0",
    "run_id": run_id,
    "story_id": story_id,
    "checked_at": now,
    "context": reason_context,
    "head_commit": head_sha,
    "dirty_tracked_paths": sorted(tracked_dirty),
    "staged_paths": sorted(staged),
    "pre_existing_untracked_paths": sorted(untracked),
    "clean": not dirty,
}

os.makedirs(os.path.join(run_dir, "reports"), exist_ok=True)
tmp = artifact_path + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(record, f, indent=2, sort_keys=True)
    f.write("\n")
os.replace(tmp, artifact_path)

if dirty:
    # Deterministic DIRTY_BASELINE evidence artifact (DEC-C6-04)
    dirty_path = os.path.join(run_dir, "reports", "dirty-baseline.json")
    dirty_record = {
        "schema_version": "1.0",
        "run_id": run_id,
        "story_id": story_id,
        "detected_at": now,
        "context": reason_context,
        "reason": "dirty tracked baseline (DEC-C6-04)",
        "dirty_tracked_paths": sorted(tracked_dirty),
        "staged_paths": sorted(staged),
        "head_commit": head_sha,
        "baseline_check_artifact": "reports/baseline-check.json",
    }
    tmp2 = dirty_path + ".tmp"
    with open(tmp2, "w", encoding="utf-8") as f:
        json.dump(dirty_record, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp2, dirty_path)
    print("DIRTY_BASELINE detected: " + "; ".join(sorted(tracked_dirty + staged)))
    sys.exit(1)

print(f"Baseline clean (untracked pre-existing: {len(untracked)})")
sys.exit(0)
BASELINE_EOF
}

# ============================================================================
# Helper: invoke review adapter (§9.3)
# References the immutable failure-context snapshot (DEC-C6-03).
# Returns: 0 adapter OK; 1 adapter invocation/result failure; 2 guard failure
# ============================================================================
invoke_review() {
  local triggered_by="$1"
  # Environment-based deterministic configuration (§9.4)
  local review_mode="${REVIEWER_MODE:-PASS}"
  local reviewer_bin="${REVIEWER_BIN:-$PYTHON_BIN}"
  local reviewer_id="${REVIEWER_ID:-mock-reviewer}"
  local review_timeout="${REVIEW_TIMEOUT:-30}"

  if ! run_phase_with_guard "review" "validation" "reviewer" ""; then
    echo "REVIEW PHASE GUARD FAILED"
    return 2
  fi

  echo "[STEP 3] Review (triggered_by=$triggered_by, mode=$review_mode)..."

  local fc_snapshot="$RUN_DIR/reports/failure-context.initial.json"
  if [[ ! -f "$fc_snapshot" ]]; then
    echo "ERROR: immutable failure-context snapshot missing before review (DEC-C6-03/N1)" >&2
    return 1
  fi

  # Reviewer command composition. The default reviewer is the deterministic
  # mock reviewer (mock_reviewer.py); the script path is passed to the
  # reviewer as --reviewer-arg (plan §9.3), REVIEWER_BIN may override the
  # executable (e.g. python3 to avoid symlink rejection). The mock reviewer
  # script path is always passed unless REVIEWER_SCRIPT is set (production
  # reviewer override).
  local reviewer_cmd="$reviewer_bin"
  local -a reviewer_arg_flags=()
  if [[ -z "${REVIEWER_SCRIPT:-}" ]]; then
    reviewer_arg_flags+=(--reviewer-arg="$SCRIPT_DIR/lib/mock_reviewer.py")
  else
    reviewer_arg_flags+=(--reviewer-arg="$REVIEWER_SCRIPT")
  fi

  "$PYTHON_BIN" "$SCRIPT_DIR/lib/review_adapter.py" \
    --repo-root "$REPO_ROOT" \
    --run-dir "$RUN_DIR" \
    --manifest "$STORY_MANIFEST" \
    --failure-context "$fc_snapshot" \
    --run-id "$RUN_ID" \
    --story-id "$STORY_ID" \
    --review-iteration 1 \
    --repair-iteration 0 \
    --triggered-by "$triggered_by" \
    --generated-at "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
    --reviewer-id "$reviewer_id" \
    --timeout-seconds "$review_timeout" \
    --reviewer-command "$reviewer_cmd" \
    ${reviewer_arg_flags[@]+"${reviewer_arg_flags[@]}"} \
    --reviewer-arg=--mode \
    --reviewer-arg "$review_mode"
  local adapter_exit=$?

  if [[ $adapter_exit -ne 0 ]]; then
    echo "Review adapter invocation failed (exit $adapter_exit)"
    return 1
  fi
  return 0
}

# ============================================================================
# Helper: invoke repair adapter (§10.3)
# Builds the repair request against immutable snapshots (DEC-C6-03) and passes
# pre-existing untracked paths as baseline exclusions (DEC-C6-04 / WP-AL-1C5
# approved mechanism).
# Returns: 0 adapter ran (result must still be interpreted); 1 invocation
# failure; 2 request-build failure
# ============================================================================
invoke_repair() {
  local repair_mode="${REPAIR_ACTOR_MODE:-REPAIRED}"
  local repair_actor_bin="${REPAIR_ACTOR_BIN:-$PYTHON_BIN}"
  local repair_timeout="${REPAIR_TIMEOUT:-120}"
  local max_repair_budget="$1"

  if ! run_phase_with_guard "repair" "source" "repair" ""; then
    echo "REPAIR PHASE GUARD FAILED"
    return 2
  fi

  echo "[STEP 4] Repair (attempt=1, mode=$repair_mode)..."

  # Build repair request from immutable evidence
  local fc_snapshot="$RUN_DIR/reports/failure-context.initial.json"
  local vr_snapshot="$RUN_DIR/reports/verify-result.initial.json"
  local review_result_file="$RUN_DIR/reports/review-result.json"
  local request_out="$RUN_DIR/repair/repair-request.json"
  mkdir -p "$RUN_DIR/repair"

  "$PYTHON_BIN" - \
    "$RUN_DIR" "$fc_snapshot" "$vr_snapshot" "$review_result_file" \
    "$RUN_ID" "$STORY_ID" "$max_repair_budget" "$request_out" \
    "$SCRIPT_DIR/lib" "$STORY_MANIFEST" "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" <<'REQ_EOF'
import json
import sys
from pathlib import Path

(run_dir, fc_path, vr_path, rr_path, run_id, story_id,
 max_attempts_str, request_out, lib_dir) = sys.argv[1:10]

sys.path.insert(0, lib_dir)
from repair_contract import build_repair_request

fc = json.loads(Path(fc_path).read_text(encoding="utf-8"))

# Orchestrator-provided scope: the manifest's allowed_paths govern repair
# permissions; actor-created untracked artifacts outside allowed_paths are
# enforcement violations (never silently widened here).
manifest_allowed = ["backend/**"]
manifest_forbidden = [".env"]
try:
    with open(sys.argv[10], encoding="utf-8") as f:
        manifest = json.load(f)
    if isinstance(manifest.get("allowed_paths"), list):
        manifest_allowed = manifest["allowed_paths"]
    if isinstance(manifest.get("forbidden_paths"), list):
        manifest_forbidden = manifest["forbidden_paths"]
except (OSError, json.JSONDecodeError):
    pass

request = build_repair_request(
    run_dir=Path(run_dir),
    failure_context_path=Path(fc_path),
    verify_result_path=Path(vr_path),
    review_result_path=Path(rr_path),
    run_id=run_id,
    story_id=story_id,
    attempt=1,
    max_attempts=int(max_attempts_str),
    source_revision=fc["candidate_identity"]["base_commit"],
    failure_class="verification_fail",
    failure_summary="Initial verification failed; review recommended repair",
    allowed_paths=manifest_allowed,
    forbidden_paths=manifest_forbidden,
    requested_action="fix_verification",
    generated_at=sys.argv[11],
)
tmp = request_out + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(request, f, indent=2, sort_keys=True)
    f.write("\n")
import os
os.replace(tmp, request_out)
print("repair-request.json built (references immutable snapshots)")
REQ_EOF
  local build_exit=$?
  if [[ $build_exit -ne 0 ]]; then
    echo "REPAIR REQUEST BUILD FAILED" >&2
    return 2
  fi

  # Actor command composition. The default repair actor is the deterministic
  # mock repair actor (mock_repair_actor.py); the script path is passed to
  # the adapter as --actor-arg (plan §10.3), REPAIR_ACTOR_BIN may override
  # the executable (e.g. python3 to avoid symlink rejection). The mock repair
  # actor script path is always passed unless REPAIR_ACTOR_SCRIPT is set.
  local actor_cmd="$repair_actor_bin"
  local -a actor_extra_args=()
  if [[ -z "${REPAIR_ACTOR_SCRIPT:-}" ]]; then
    actor_extra_args+=(--actor-arg="$SCRIPT_DIR/lib/mock_repair_actor.py")
  else
    actor_extra_args+=(--actor-arg="$REPAIR_ACTOR_SCRIPT")
  fi

  # Baseline exclusions: pre-existing untracked paths recorded by the
  # clean-baseline check (DEC-C6-04). Actor-created new untracked paths are
  # NOT excluded — they remain subject to adapter enforcement.
  local -a exclusion_flags=()
  if [[ -f "$RUN_DIR/reports/baseline-check.json" ]]; then
    while IFS= read -r p; do
      [[ -n "$p" ]] && exclusion_flags+=(--baseline-exclusion "$p")
    done < <("$PYTHON_BIN" -c "
import json, sys
try:
    data = json.load(open(sys.argv[1]))
    for p in data.get('pre_existing_untracked_paths', []):
        print(p)
except Exception:
    pass
" "$RUN_DIR/reports/baseline-check.json")
  fi

  # WP-AL-1C6 test seam: REPAIR_ACTOR_MODIFY supplies --modify paths to the
  # repair actor (mock_repair_actor REPAIRED requires at least one --modify).
  # This is a narrow test/dogfooding seam, not a production repair-contract
  # change. Production repair actors receive their own modify paths from their
  # implementation; the mock actor needs them supplied externally.
  local -a modify_flags=()
  if [[ -n "${REPAIR_ACTOR_MODIFY:-}" ]]; then
    while IFS= read -r p; do
      [[ -n "$p" ]] && modify_flags+=(--actor-arg=--modify --actor-arg="$p")
    done <<< "$REPAIR_ACTOR_MODIFY"
  fi

  REPAIR_ADAPTER_INVOCATIONS=$((REPAIR_ADAPTER_INVOCATIONS + 1))
  REPAIR_ACTOR_INVOCATIONS=$((REPAIR_ACTOR_INVOCATIONS + 1))
  REPAIR_ATTEMPT=$((REPAIR_ATTEMPT + 1))

  "$PYTHON_BIN" "$SCRIPT_DIR/lib/repair_adapter.py" \
    --repo-root "$REPO_ROOT" \
    --run-dir "$RUN_DIR" \
    --repair-request "$request_out" \
    --actor-command "$actor_cmd" \
    ${actor_extra_args[@]+"${actor_extra_args[@]}"} \
    --actor-arg=--mode \
    --actor-arg "$repair_mode" \
    ${modify_flags[@]+"${modify_flags[@]}"} \
    ${exclusion_flags[@]+"${exclusion_flags[@]}"} \
    --timeout-seconds "$repair_timeout" \
    --max-output-bytes 4096 \
    --completed-at "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  local adapter_exit=$?

  if [[ $adapter_exit -gt 1 ]]; then
    echo "Repair adapter invocation failed (exit $adapter_exit)"
    return 1
  fi
  # adapter_exit 0 or 1: repair-adapter-result.json published either way;
  # interpretation happens from the artifact (plan §10.5).
  return 0
}

# ============================================================================
# MAIN ORCHESTRATION
# ============================================================================

echo ""
echo "=== WP-AL-1C6 Orchestration ==="

# Phase: implement (candidate committed externally; WP-AL-1C6 does not commit)
if [[ "$DRY_RUN" == "true" ]]; then
  echo "[DRY RUN] Skipping implementation"
else
  if ! run_phase_with_guard "implement" "source" "implementer" ""; then
    exit 2
  fi
  echo "  Candidate implementation expected as committed revision (DEC-C6-04)."
fi

# DEC-C6-04: pre-verify preflight when repair_budget > 0.
# If repair might be needed, verify the committed candidate + clean baseline
# BEFORE entering the verify phase. If repair_budget == 0, repair is not
# possible and the preflight is skipped (plan §5.7).
REPAIR_BUDGET_PREFLIGHT="$(python3 -c "
import json, sys
try:
    with open(sys.argv[1]) as f:
        data = json.load(f)
    budget = data.get('repair_budget', 1)
    print(budget if isinstance(budget, int) and not isinstance(budget, bool) else 1)
except Exception:
    print(1)
" "$STORY_MANIFEST" 2>/dev/null || echo 1)"

if [[ "$REPAIR_BUDGET_PREFLIGHT" -gt 0 ]]; then
  echo "[STEP 1.5] Pre-verify baseline preflight (DEC-C6-04, repair_budget=$REPAIR_BUDGET_PREFLIGHT)..."
  check_clean_baseline "pre_verify_preflight"
  PREFLIGHT_EXIT=$?
  if [[ $PREFLIGHT_EXIT -eq 1 ]]; then
    finalize_and_exit 1 "DIRTY_BASELINE (pre-verify preflight: repair-capable flow requires clean baseline)"
  elif [[ $PREFLIGHT_EXIT -eq 2 ]]; then
    finalize_and_exit 1 "INFRASTRUCTURE_ERROR (pre-verify baseline inspection failed)"
  fi
  echo "  Pre-verify preflight passed (clean baseline confirmed)"
fi

# Phase: initial verify
if ! run_phase_with_guard "verify" "validation" "verifier" ""; then
  exit 2
fi

echo "[STEP 2] Initial Verification..."
export DRY_RUN RUN_DIR RUN_ID STORY_ID PASSPORT_FILE

# Write verify-context for initial verify (attempt=0)
write_verify_context "initial" 0

# Run initial verify
"$SCRIPT_DIR/verify-story.sh" "$STORY_MANIFEST"
VERIFY_EXIT=$?

# DEC-C6-03: publish immutable initial snapshots (fail closed on failure)
if ! publish_verify_snapshots "initial"; then
  echo "SNAPSHOT PUBLICATION FAILED (initial) - INFRASTRUCTURE_ERROR" >&2
  finalize_and_exit 1 "INFRASTRUCTURE_ERROR (snapshot publication failure)"
fi

if [[ $VERIFY_EXIT -eq 0 ]]; then
  echo ""
  echo "VERIFICATION PASSED"
  VERIFY_STATUS="PASS"
elif [[ $VERIFY_EXIT -eq 2 ]]; then
  echo ""
  echo "VERIFICATION ERROR"
  VERIFY_STATUS="ERROR"
else
  echo ""
  echo "VERIFICATION FAILED"
  VERIFY_STATUS="FAIL"
fi

# Handle verify ERROR (exit 2 → INFRASTRUCTURE_ERROR, report published)
if [[ "$VERIFY_STATUS" == "ERROR" ]]; then
  finalize_and_exit 1 "INFRASTRUCTURE_ERROR (initial verify exit 2)"
fi

# In dry-run mode, skip review/repair
if [[ "$DRY_RUN" == "true" ]]; then
  echo "[DRY RUN] Skipping review/repair"
  if ! run_phase_with_guard "report" "control-plane" "reporter" ""; then
    exit 2
  fi
  "$SCRIPT_DIR/report-story.sh" "$RUN_DIR"
  echo ""
  echo "=========================================="
  echo "DRY RUN COMPLETE - $VERIFY_STATUS"
  echo "=========================================="
  echo "Artifacts: $RUN_DIR"
  if [[ "$VERIFY_STATUS" == "PASS" ]]; then
    exit 0
  else
    exit 1
  fi
fi

# Determine triggered_by for review (§5.2)
if [[ "$VERIFY_STATUS" == "PASS" ]]; then
  TRIGGERED_BY="initial_verify_pass"
else
  TRIGGERED_BY="initial_verify_fail"
fi

# Phase: review
if ! invoke_review "$TRIGGERED_BY"; then
  finalize_and_exit 1 "INFRASTRUCTURE_ERROR (review adapter invocation failed)"
fi

# Parse review result (fail closed if unreadable)
REVIEW_STATUS="$("$PYTHON_BIN" -c "
import json, sys
try:
    data = json.load(open(sys.argv[1]))
    status = data.get('status')
    print(status if isinstance(status, str) else 'INVALID')
except Exception:
    print('INVALID')
" "$RUN_DIR/reports/review-result.json")"
RECOMMENDED_ACTION="$("$PYTHON_BIN" -c "
import json, sys
try:
    data = json.load(open(sys.argv[1]))
    action = data.get('recommended_action')
    print(action if isinstance(action, str) else 'none')
except Exception:
    print('none')
" "$RUN_DIR/reports/review-result.json")"

echo ""
echo "REVIEW RESULT: status=$REVIEW_STATUS, action=$RECOMMENDED_ACTION"

# Handle malformed/invalid review result → INFRASTRUCTURE_ERROR (§9.5)
if [[ "$REVIEW_STATUS" == "INVALID" ]]; then
  finalize_and_exit 1 "INFRASTRUCTURE_ERROR (malformed review-result)"
fi

# Handle review ERROR (§9.5 / Appendix B)
if [[ "$REVIEW_STATUS" == "ERROR" ]]; then
  if [[ "$RECOMMENDED_ACTION" == "human_review" ]]; then
    finalize_and_exit 1 "HUMAN_REVIEW_REQUIRED (review ERROR + human_review)"
  fi
  finalize_and_exit 1 "INFRASTRUCTURE_ERROR (review ERROR)"
fi

# Handle review PASS
if [[ "$REVIEW_STATUS" == "PASS" ]]; then
  if [[ "$VERIFY_STATUS" == "PASS" ]]; then
    # verify PASS + review PASS → ACCEPTED
    finalize_and_exit 0 "ACCEPTED"
  else
    # verify FAIL + review PASS → VERIFICATION_FAILED (DEC-C6-02)
    finalize_and_exit 1 "VERIFICATION_FAILED (review PASS cannot override verify FAIL)"
  fi
fi

# Handle review FAIL
if [[ "$REVIEW_STATUS" == "FAIL" ]]; then
  if [[ "$RECOMMENDED_ACTION" == "human_review" ]]; then
    finalize_and_exit 1 "HUMAN_REVIEW_REQUIRED (review FAIL + human_review)"
  fi

  if [[ "$RECOMMENDED_ACTION" != "repair" ]]; then
    # action=none (or unrecognized): no repair authorized
    if [[ "$VERIFY_STATUS" == "PASS" ]]; then
      finalize_and_exit 1 "REVIEW_REJECTED"
    else
      finalize_and_exit 1 "VERIFICATION_FAILED"
    fi
  fi

  # Repair authorized — enforce repair_budget and the single-attempt cap.
  # The manifest repair_budget may narrow but never widen the cap (§5.3).
  REPAIR_BUDGET="$("$PYTHON_BIN" -c "
import json, sys
try:
    data = json.load(open(sys.argv[1]))
    budget = data.get('repair_budget', 1)
    print(budget if isinstance(budget, int) and not isinstance(budget, bool) else 1)
except Exception:
    print(1)
" "$STORY_MANIFEST")"

  EFFECTIVE_REPAIRS=$((REPAIR_BUDGET < MAX_REPAIR_ITERATIONS ? REPAIR_BUDGET : MAX_REPAIR_ITERATIONS))

  if [[ $EFFECTIVE_REPAIRS -le 0 || $REPAIR_ATTEMPT -ge $EFFECTIVE_REPAIRS ]]; then
    # repair_budget=0 or attempt cap exhausted → no repair (OW-63)
    finalize_and_exit 1 "VERIFICATION_FAILED (repair not permitted: budget=$REPAIR_BUDGET, attempts=$REPAIR_ATTEMPT)"
  fi

  # DEC-C6-04: pre-repair clean-baseline check
  echo "[STEP 4.5] Pre-repair baseline check (DEC-C6-04)..."
  check_clean_baseline "pre_repair"
  BASELINE_EXIT=$?
  if [[ $BASELINE_EXIT -eq 1 ]]; then
    finalize_and_exit 1 "DIRTY_BASELINE (repair blocked before actor invocation)"
  elif [[ $BASELINE_EXIT -eq 2 ]]; then
    finalize_and_exit 1 "INFRASTRUCTURE_ERROR (baseline inspection failed)"
  fi

  # Invoke repair (single attempt; REPAIR_ATTEMPT incremented inside)
  if ! invoke_repair "$EFFECTIVE_REPAIRS"; then
    finalize_and_exit 1 "INFRASTRUCTURE_ERROR (repair adapter invocation failed)"
  fi

  # Parse repair adapter result (plan §10.5: repair-adapter-result.json)
  ADAPTER_RESULT_FILE="$RUN_DIR/repair/repair-adapter-result.json"
  ADAPTER_STATUS="$("$PYTHON_BIN" -c "
import json, sys
try:
    data = json.load(open(sys.argv[1]))
    status = data.get('adapter_status')
    print(status if isinstance(status, str) else 'ADAPTER_INTERNAL_ERROR')
except Exception:
    print('ADAPTER_INTERNAL_ERROR')
" "$ADAPTER_RESULT_FILE")"
  REPAIR_STATUS="$("$PYTHON_BIN" -c "
import json, sys
try:
    data = json.load(open(sys.argv[1]))
    summary = data.get('repair_result_summary') or {}
    status = summary.get('status')
    print(status if isinstance(status, str) else 'N/A')
except Exception:
    print('N/A')
" "$ADAPTER_RESULT_FILE")"

  echo ""
  echo "REPAIR RESULT: adapter_status=$ADAPTER_STATUS, status=$REPAIR_STATUS"

  # Repair result interpretation (§10.5 / Appendix C)
  if [[ "$ADAPTER_STATUS" != "ADAPTER_SUCCESS" ]]; then
    finalize_and_exit 1 "REPAIR_ADAPTER_FAILURE ($ADAPTER_STATUS)"
  fi
  if [[ "$REPAIR_STATUS" == "NO_CHANGE" ]]; then
    finalize_and_exit 1 "REPAIR_NO_CHANGE"
  fi
  if [[ "$REPAIR_STATUS" == "ERROR" ]]; then
    # Actor returned valid status=ERROR; adapter published it (scenario AD).
    # NOT an adapter failure; fail closed with no reverify.
    finalize_and_exit 1 "INFRASTRUCTURE_ERROR (repair actor status=ERROR)"
  fi
  if [[ "$REPAIR_STATUS" != "REPAIRED" ]]; then
    finalize_and_exit 1 "REPAIR_ADAPTER_FAILURE (unexpected repair status: $REPAIR_STATUS)"
  fi

  # REPAIRED → exactly one reverify (§5.1)
  echo ""
  echo "[STEP 5] Reverify..."

  if ! run_phase_with_guard "reverify" "validation" "verifier" ""; then
    finalize_and_exit 1 "INFRASTRUCTURE_ERROR (reverify phase guard failed)"
  fi

  # Write verify-context for reverify (attempt=1)
  write_verify_context "reverify" 1

  REVERIFY_INVOCATIONS=$((REVERIFY_INVOCATIONS + 1))
  "$SCRIPT_DIR/verify-story.sh" "$STORY_MANIFEST"
  REVERIFY_EXIT=$?

  # DEC-C6-03: publish immutable reverify snapshots (fail closed)
  if ! publish_verify_snapshots "reverify"; then
    echo "SNAPSHOT PUBLICATION FAILED (reverify) - INFRASTRUCTURE_ERROR" >&2
    finalize_and_exit 1 "INFRASTRUCTURE_ERROR (reverify snapshot publication failure)"
  fi

  if [[ $REVERIFY_EXIT -eq 0 ]]; then
    REVERIFY_STATUS="PASS"
  elif [[ $REVERIFY_EXIT -eq 2 ]]; then
    REVERIFY_STATUS="ERROR"
  else
    REVERIFY_STATUS="FAIL"
  fi
  echo ""
  echo "REVERIFY RESULT: $REVERIFY_STATUS"

  if [[ "$REVERIFY_STATUS" == "ERROR" ]]; then
    finalize_and_exit 1 "INFRASTRUCTURE_ERROR (reverify exit 2)"
  fi
  if [[ "$REVERIFY_STATUS" != "PASS" ]]; then
    finalize_and_exit 1 "REPAIR_FAILED_REVERIFY"
  fi

  # Reverify PASS: VERIFIED_AFTER_REPAIR requires ALL adapter-success evidence
  # valid (§5.1). Validate reconciliation + permission enforcement from the
  # published adapter result and re-verify immutable initial evidence hashes.
  EVIDENCE_OK="$("$PYTHON_BIN" -c "
import json, sys
sys.path.insert(0, sys.argv[2])
from report_final_status import valid_repair_evidence
try:
    data = json.load(open(sys.argv[1]))
except Exception:
    data = None
print('valid' if valid_repair_evidence(data) else 'invalid')
" "$ADAPTER_RESULT_FILE" "$SCRIPT_DIR/lib")"

  if [[ "$EVIDENCE_OK" != "valid" ]]; then
    finalize_and_exit 1 "INFRASTRUCTURE_ERROR (adapter-success evidence invalid after reverify)"
  fi
  if ! verify_immutable_evidence "$RUN_DIR/reports/evidence-manifest.initial.json"; then
    finalize_and_exit 1 "INFRASTRUCTURE_ERROR (immutable initial evidence invalidated)"
  fi

  finalize_and_exit 0 "VERIFIED_AFTER_REPAIR"
fi

# Unreachable: review status outside PASS/FAIL/ERROR/INVALID
finalize_and_exit 1 "INFRASTRUCTURE_ERROR (unhandled review status: $REVIEW_STATUS)"
