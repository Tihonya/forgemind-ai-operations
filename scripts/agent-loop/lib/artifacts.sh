#!/usr/bin/env bash
# Artifact directory management
#
# NOTE: no set -euo pipefail here — this file is sourced, not executed directly

init_artifacts() {
  local story_id="${1:-unknown}"
  local timestamp
  # Collision-resistant: nanoseconds + PID
  timestamp="$(date +%Y%m%d_%H%M%S_%N)_$$"
  export RUN_ID="${story_id}_${timestamp}"
  export RUN_DIR="$ARTIFACTS_DIR/$RUN_ID"

  mkdir -p "$RUN_DIR"/{verify,review,repair,reports}

  # Return RUN_DIR on stdout for callers that need it
  echo "$RUN_DIR"
}

# Initialize slot ID (collision-resistant: timestamp + PID + random)
init_slot_id() {
  local slot_id
  slot_id="slot-$(date +%s)-$$_$RANDOM"
  export SLOT_ID="$slot_id"
  echo "$SLOT_ID"
}

# Create passport file
create_passport_file() {
  local passport_file="$1"
  local project_id="${2:-forgemind}"
  local run_id="${3:-$RUN_ID}"
  local slot_id="${4:-$SLOT_ID}"
  local story_id="${5:-$STORY_ID}"
  local role="${6:-implementer}"
  local phase="${7:-implement}"
  local workspace_type="${8:-source}"
  local workspace_root="${9:-$REPO_ROOT}"
  local expected_branch="${10:-$(git branch --show-current 2>/dev/null || echo "unknown")}"
  local base_commit="${11:-$(git rev-parse HEAD 2>/dev/null || echo "unknown")}"
  local manifest_path="${12:-}"
  local artifact_root="${13:-$RUN_DIR}"
  local candidate_commit="${14:-}"

  "$PYTHON_BIN" "$SCRIPT_DIR/lib/passport.py" create \
    "$project_id" "$run_id" "$slot_id" "$story_id" \
    "$role" "$phase" "$workspace_type" "$workspace_root" \
    "$expected_branch" "$base_commit" "$manifest_path" \
    "$artifact_root" "$candidate_commit" > "$passport_file"

  export PASSPORT_FILE="$passport_file"
  echo "$passport_file"
}

log_artifact() {
  local category="$1"
  local filename="$2"
  local content="$3"

  local target="$RUN_DIR/$category/$filename"
  echo "$content" > "$target"
  echo "$target"
}

get_latest_run() {
  if [[ ! -d "$ARTIFACTS_DIR" ]]; then
    echo ""
    return
  fi

  ls -t "$ARTIFACTS_DIR" 2>/dev/null | head -1
}
