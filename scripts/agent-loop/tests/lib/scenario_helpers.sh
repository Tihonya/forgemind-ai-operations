#!/usr/bin/env bash
# Shared helpers for harness scenario scripts (WP-AL-1B2B).
#
# Every scenario A-O runs inside its own disposable temporary Git repository
# built by tests/lib/temp_repo_fixture.py. The real infrastructure worktree is
# never mutated: no stash, no worktree registration, no synthetic files in
# the real backend tree, cleanup touches only fixture-created temp dirs.
#
# NOTE: this file is sourced; do not set -e here.

# --- Tool binary capture (must run BEFORE sourcing config.sh) ---------------
# config.sh honours pre-set binaries; isolated temp repos reuse the real
# toolchain. Only pre-set when actually found — an empty export would
# suppress config.sh's own .venv detection.
if [[ -z "${PYTHON_BIN:-}" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  else
    echo "INFRASTRUCTURE_ERROR: python3 not found" >&2
    exit 2
  fi
fi
export PYTHON_BIN
if [[ -z "${PYTEST_BIN:-}" ]] && command -v pytest >/dev/null 2>&1; then
  export PYTEST_BIN="$(command -v pytest)"
fi
if [[ -z "${RUFF_BIN:-}" ]] && command -v ruff >/dev/null 2>&1; then
  export RUFF_BIN="$(command -v ruff)"
fi
if [[ -z "${MYPY_BIN:-}" ]] && command -v mypy >/dev/null 2>&1; then
  export MYPY_BIN="$(command -v mypy)"
fi

# --- Paths -------------------------------------------------------------------
SCENARIOS_THIS_DIR="${SCENARIOS_THIS_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
FIXTURE_PY="$SCENARIOS_THIS_DIR/lib/temp_repo_fixture.py"
# tests/ -> agent-loop/ -> scripts/ -> repo root
REAL_REPO_ROOT="$(cd "$SCENARIOS_THIS_DIR/../../.." && pwd)"
VERIFY_SCRIPT="$SCENARIOS_THIS_DIR/../verify-story.sh"

# --- Temp dir registry (only fixture-created dirs are cleaned) ---------------
SCENARIO_TMP_DIRS=()

register_tmp_dir() {
  SCENARIO_TMP_DIRS+=("$1")
}

cleanup_scenario_tmp_dirs() {
  local d
  for d in "${SCENARIO_TMP_DIRS[@]:-}"; do
    if [[ -n "$d" && -d "$d" ]]; then
      "$PYTHON_BIN" "$FIXTURE_PY" remove "$d" >/dev/null 2>&1
      if [[ -d "$d" ]]; then
        echo "CLEANUP_WARNING: fixture temp dir could not be removed: $d" >&2
      fi
    fi
  done
}

# --- Isolated repo creation --------------------------------------------------
# Default gate overrides for scenario manifests (matches migrated fixtures):
# diff-scoped lint/secrets so the gates operate on the scenario's candidate
# diff. This is NOT a weakening: both gates remain required and enabled;
# only their inspection scope is the candidate change set.
DEFAULT_OVERRIDES_JSON='{"lint": {"scope_to_diff": true}, "secrets": {"scope_to_diff": true}}'
# create_isolated_repo <scenario_name>
#   Sets ISOLATED_REPO (temp repo path) and ISOLATED_BASE (base commit SHA).
#   An infrastructure failure here aborts the whole suite deterministically:
#   no scenario result would be trustworthy without isolation.
create_isolated_repo() {
  local scenario_name="$1"
  ISOLATED_REPO=""
  ISOLATED_REPO="$("$PYTHON_BIN" "$FIXTURE_PY" create --source-root "$REAL_REPO_ROOT" --scenario "$scenario_name" 2>&1)" || {
    echo "INFRASTRUCTURE_ERROR: failed to create isolated repo for $scenario_name" >&2
    echo "$ISOLATED_REPO" >&2
    exit 2
  }
  if [[ ! -d "$ISOLATED_REPO" ]]; then
    echo "INFRASTRUCTURE_ERROR: isolated repo path not a directory: $ISOLATED_REPO" >&2
    exit 2
  fi
  register_tmp_dir "$ISOLATED_REPO"
  ISOLATED_BASE="$("$PYTHON_BIN" "$FIXTURE_PY" base-sha --repo "$ISOLATED_REPO")" || {
    echo "INFRASTRUCTURE_ERROR: failed to read base SHA for $scenario_name" >&2
    exit 2
  }
  export AGENTLAB_ROOT="${AGENTLAB_ROOT:-/tmp/agent-loop-harness-agentlab}"
  export FORGEMIND_MAIN_ROOT="${FORGEMIND_MAIN_ROOT:-/tmp/agent-loop-harness-main}"
  mkdir -p "$AGENTLAB_ROOT" "$FORGEMIND_MAIN_ROOT" 2>/dev/null || true
  return 0
}

# add_candidate_file <rel_path> <source_file>
#   Copies a fixture file into the isolated repo as an uncommitted change.
add_candidate_file() {
  local rel_path="$1"
  local source_file="$2"
  "$PYTHON_BIN" "$FIXTURE_PY" add-file --repo "$ISOLATED_REPO" --rel "$rel_path" --src "$source_file"
}

# add_candidate_content <rel_path>  (content on stdin)
add_candidate_content() {
  local rel_path="$1"
  "$PYTHON_BIN" "$FIXTURE_PY" add-file --repo "$ISOLATED_REPO" --rel "$rel_path" --stdin
}

# write_scenario_manifest <output_path> <story_id> <targeted_args_as_json> [overrides_json] [allowed_json] [forbidden_json]
write_scenario_manifest() {
  local output_path="$1"
  local story_id="$2"
  local args_json="$3"
  local overrides_json="${4:-}"
  local allowed_json="${5:-}"
  local forbidden_json="${6:-}"

  # Defaults (no inline quoting inside parameter expansion)
  local default_allowed='["backend/**"]'
  local default_forbidden='[".env"]'
  [[ -z "$allowed_json" ]] && allowed_json="$default_allowed"
  [[ -z "$forbidden_json" ]] && forbidden_json="$default_forbidden"

  local -a arg_flags=()
  while IFS= read -r a; do
    # --arg=VALUE form so values starting with '-' are not parsed as flags
    [[ -n "$a" ]] && arg_flags+=("--arg=$a")
  done < <("$PYTHON_BIN" -c "import json,sys; [print(x) for x in json.loads(sys.argv[1])]" "$args_json")

  local -a allowed_flags=()
  while IFS= read -r p; do
    [[ -n "$p" ]] && allowed_flags+=("--allowed=$p")
  done < <("$PYTHON_BIN" -c "import json,sys; [print(x) for x in json.loads(sys.argv[1])]" "$allowed_json")

  local -a forbidden_flags=()
  while IFS= read -r p; do
    [[ -n "$p" ]] && forbidden_flags+=("--forbidden=$p")
  done < <("$PYTHON_BIN" -c "import json,sys; [print(x) for x in json.loads(sys.argv[1])]" "$forbidden_json")

  local -a override_flags=()
  # Merge DEFAULT_OVERRIDES_JSON with scenario-provided overrides (per-gate
  # keys from the scenario win) so every scenario keeps diff-scoped
  # lint/secrets unless it explicitly says otherwise.
  local merged_overrides
  merged_overrides="$("$PYTHON_BIN" -c '
import json, sys
defaults = json.loads(sys.argv[1])
extra = json.loads(sys.argv[2]) if sys.argv[2] else {}
for gate, cfg in extra.items():
    merged = dict(defaults.get(gate, {}))
    merged.update(cfg)
    defaults[gate] = merged
print(json.dumps(defaults))
' "$DEFAULT_OVERRIDES_JSON" "$overrides_json")"
  override_flags=("--overrides-json" "$merged_overrides")

  "$PYTHON_BIN" "$FIXTURE_PY" manifest \
    --repo "$ISOLATED_REPO" \
    --base "$ISOLATED_BASE" \
    --story-id "$story_id" \
    --output "$output_path" \
    "${arg_flags[@]}" \
    "${allowed_flags[@]}" \
    "${forbidden_flags[@]}" \
    "${override_flags[@]}"
}

# run_isolated_verify <manifest_path> [extra verify-story args...]
#   Runs the isolated repo's OWN copy of verify-story.sh (REPO_ROOT is
#   derived from the script location, so artifacts and gates operate on the
#   isolated repo, never on the real infrastructure worktree).
run_isolated_verify() {
  local manifest_path="$1"
  shift
  (
    cd "$ISOLATED_REPO" || exit 2
    bash "$ISOLATED_REPO/scripts/agent-loop/verify-story.sh" "$manifest_path" "$@"
  )
}
