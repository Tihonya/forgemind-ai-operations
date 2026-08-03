#!/usr/bin/env bash
# Main entry point: operator runs one command
# Implements: bootstrap guard -> allocate -> implement -> verify -> review -> repair loop -> report
#
# Passport is mandatory: orchestration always creates and validates a cycle passport.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/lib/artifacts.sh"
source "$SCRIPT_DIR/lib/guard.sh"

# Project identity (may be overridden via environment)
export PROJECT_ID="${PROJECT_ID:-forgemind}"

# Parse arguments
STORY_MANIFEST=""
DRY_RUN="${DRY_RUN:-false}"
ITERATION=0

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
      MAX_REPAIR_ITERATIONS="$2"
      shift 2
      ;;
    --help|-h)
      echo "Usage: $0 [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --manifest, -m FILE      Story manifest JSON (required)"
      echo "  --dry-run, -n            Skip agent invocations, verify only"
      echo "  --max-iterations N       Max repair iterations (default: 3)"
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
# MAIN LOOP
# ============================================================================

while [[ $ITERATION -le $MAX_REPAIR_ITERATIONS ]]; do
  echo ""
  echo "=== Iteration $ITERATION ==="

  # Phase: implement (iteration 0) or repair (iteration > 0)
  if [[ $ITERATION -eq 0 ]]; then
    if [[ "$DRY_RUN" == "true" ]]; then
      echo "[DRY RUN] Skipping implementation"
    else
      if ! run_phase_with_guard "implement" "source" "implementer" ""; then
        exit 2
      fi
      echo "  TODO: invoke Ralph with story manifest"
    fi
  else
    if ! run_phase_with_guard "repair" "source" "repair" ""; then
      exit 2
    fi
    echo "  TODO: invoke OpenCode with failure context"
  fi

  # Phase: verify
  if ! run_phase_with_guard "verify" "validation" "verifier" ""; then
    exit 2
  fi

  echo "[STEP 2] Verification..."
  # Export variables for subprocesses
  export DRY_RUN
  export RUN_DIR
  export RUN_ID
  export STORY_ID
  export PASSPORT_FILE

  if "$SCRIPT_DIR/verify-story.sh" "$STORY_MANIFEST"; then
    echo ""
    echo "VERIFICATION PASSED"

    # Phase: review (Phase 2 - not yet implemented)
    if [[ "$DRY_RUN" == "true" ]]; then
      echo "[DRY RUN] Skipping review"
    else
      if ! run_phase_with_guard "review" "validation" "reviewer" ""; then
        exit 2
      fi
    fi

    # Phase: report
    if ! run_phase_with_guard "report" "control-plane" "reporter" ""; then
      exit 2
    fi

    # Generate final report
    "$SCRIPT_DIR/report-story.sh" "$RUN_DIR"

    echo ""
    echo "=========================================="
    echo "AGENT LOOP COMPLETE - ACCEPTED"
    echo "=========================================="
    echo "Artifacts: $RUN_DIR"
    echo "Passport: $PASSPORT_FILE"
    exit 0
  fi

  echo ""
  echo "VERIFICATION FAILED"

  # In dry-run mode, do not enter repair loop
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY RUN] Skipping repair iterations"
    "$SCRIPT_DIR/report-story.sh" "$RUN_DIR"
    echo ""
    echo "=========================================="
    echo "DRY RUN COMPLETE - VERIFICATION FAILED"
    echo "=========================================="
    echo "Artifacts: $RUN_DIR"
    exit 1
  fi

  ITERATION=$((ITERATION + 1))

  if [[ $ITERATION -gt $MAX_REPAIR_ITERATIONS ]]; then
    echo ""
    echo "MAX REPAIR ITERATIONS EXHAUSTED"

    # Phase: report
    run_phase_with_guard "report" "control-plane" "reporter" "" || true

    # Generate final report
    "$SCRIPT_DIR/report-story.sh" "$RUN_DIR"

    echo ""
    echo "=========================================="
    echo "AGENT LOOP COMPLETE - REPAIR EXHAUSTED"
    echo "=========================================="
    echo "Artifacts: $RUN_DIR"
    exit 1
  fi

  echo "Preparing repair iteration $ITERATION..."
done
