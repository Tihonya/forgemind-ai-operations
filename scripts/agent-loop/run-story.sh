#!/usr/bin/env bash
# Main entry point: operator runs one command
# Implements: verify -> (optional) repair loop -> report

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/lib/artifacts.sh"

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

# Validate manifest JSON before processing
if ! "$PYTHON_BIN" "$HARNESS_PY" validate "$STORY_MANIFEST" 2>/dev/null | grep -q "^OK:"; then
  echo "ERROR: manifest is not valid JSON or is missing story_id: $STORY_MANIFEST" >&2

  # Initialize artifacts for error report
  STORY_ID="unknown"
  init_artifacts "$STORY_ID" > /dev/null

  # Create error report
  mkdir -p "$RUN_DIR/reports"
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

# Extract story ID
STORY_ID="$("$PYTHON_BIN" "$HARNESS_PY" validate "$STORY_MANIFEST" | sed 's/^OK://')"

echo "=========================================="
echo "AGENT LOOP - Story: $STORY_ID"
echo "Manifest: $STORY_MANIFEST"
echo "Max iterations: $MAX_REPAIR_ITERATIONS"
echo "Dry run: $DRY_RUN"
echo "=========================================="

# Initialize artifacts (call directly, not in subshell, so exports propagate)
init_artifacts "$STORY_ID" > /dev/null

# Main loop
while [[ $ITERATION -le $MAX_REPAIR_ITERATIONS ]]; do
  echo ""
  echo "--- Iteration $ITERATION ---"

  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY RUN] Skipping agent invocation"
  else
    # Implementation step (only on first iteration)
    if [[ $ITERATION -eq 0 ]]; then
      echo "[STEP 1] Implementation (Ralph)..."
      echo "  TODO: invoke Ralph with story manifest"
      # TODO: $RALPH_BIN --manifest "$STORY_MANIFEST" > "$RUN_DIR/reports/implementation.log" 2>&1
    else
      # Repair step
      echo "[STEP 1] Repair iteration..."
      echo "  TODO: invoke OpenCode with failure context"
      # TODO: invoke repair
    fi
  fi

  # Verification step
  echo "[STEP 2] Verification..."
  # Export variables for subprocesses
  export DRY_RUN
  export RUN_DIR
  export RUN_ID
  export STORY_ID
  if "$SCRIPT_DIR/verify-story.sh" "$STORY_MANIFEST"; then
    echo ""
    echo "VERIFICATION PASSED"

    if [[ "$DRY_RUN" == "true" ]]; then
      echo "[DRY RUN] Skipping review"
    else
      # Review step (Phase 2)
      echo "[STEP 3] Review..."
      echo "  TODO: invoke OpenCode for independent review"
      # TODO: "$SCRIPT_DIR/review-story.sh" "$STORY_MANIFEST"
    fi

    # Generate final report
    "$SCRIPT_DIR/report-story.sh" "$RUN_DIR"

    echo ""
    echo "=========================================="
    echo "AGENT LOOP COMPLETE - ACCEPTED"
    echo "=========================================="
    echo "Artifacts: $RUN_DIR"
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
  echo "  TODO: collect failure context and invoke repair agent"
done
