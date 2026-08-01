#!/usr/bin/env bash
# Artifact directory management

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
