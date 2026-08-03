#!/usr/bin/env bash
# Agent Loop Configuration
# Source this file from all agent-loop scripts
#
# WP-AL-1B1: Configuration loaded via config_loader.py (NUL-delimited protocol).
# No eval, no generated shell sourcing, no machine-specific hardcoded defaults.

# NOTE: this file is sourced, not executed directly.
# Do NOT set -e here — let the caller control error handling.
set -uo pipefail

# Repository root (auto-detect from script location)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Isolated test repos may override the source root explicitly
# (production callers never set this).
if [[ -n "${AGENT_LOOP_SOURCE_ROOT:-}" ]]; then
  REPO_ROOT="$AGENT_LOOP_SOURCE_ROOT"
  export REPO_ROOT
fi

# Derive infrastructure root from actual Git root
_INFRA_ROOT="$(git -C "$REPO_ROOT" rev-parse --show-toplevel 2>/dev/null)" || {
  echo "INFRASTRUCTURE_ERROR: Cannot determine Git root for $REPO_ROOT" >&2
  return 2 2>/dev/null || exit 2
}
export FORGEMIND_AGENT_LOOP_ROOT="$_INFRA_ROOT"
unset _INFRA_ROOT

# Worktree safety: ensure we're in a worktree, not main repo
if [[ "$REPO_ROOT" == *"AIAutomation" ]] && [[ "$REPO_ROOT" != *"worktrees"* ]]; then
  echo "ERROR: agent-loop must run from worktree, not main repo" >&2
  echo "Expected path: .../worktrees/forgemind-agent-loop" >&2
  exit 1
fi

# Agent binaries (override via environment)
export RALPH_BIN="${RALPH_BIN:-}"
export OPENCODE_BIN="${OPENCODE_BIN:-}"

# State directories
export AGENT_STATE="${AGENT_STATE:-$REPO_ROOT/../state}"
export ARTIFACTS_DIR="$REPO_ROOT/.ralph-tui/artifacts"

# Required environment variables (must be set by caller)
if [[ -z "${AGENTLAB_ROOT:-}" ]]; then
  echo "INFRASTRUCTURE_ERROR: AGENTLAB_ROOT is not set" >&2
  return 2 2>/dev/null || exit 2
fi

if [[ -z "${FORGEMIND_MAIN_ROOT:-}" ]]; then
  echo "INFRASTRUCTURE_ERROR: FORGEMIND_MAIN_ROOT is not set" >&2
  return 2 2>/dev/null || exit 2
fi

# Project and gates config paths
_PROJECT_JSON="$REPO_ROOT/.agent-loop/project.json"
_GATES_JSON="$REPO_ROOT/.agent-loop/gates.json"

# Validate configuration files exist
if [[ ! -f "$_PROJECT_JSON" ]]; then
  echo "INFRASTRUCTURE_ERROR: Missing .agent-loop/project.json at $_PROJECT_JSON" >&2
  return 2 2>/dev/null || exit 2
fi

if [[ ! -f "$_GATES_JSON" ]]; then
  echo "INFRASTRUCTURE_ERROR: Missing .agent-loop/gates.json at $_GATES_JSON" >&2
  return 2 2>/dev/null || exit 2
fi

# Shared Python harness module
export HARNESS_PY="$SCRIPT_DIR/lib/harness.py"

# Config loader script
_CONFIG_LOADER="$SCRIPT_DIR/lib/config_loader.py"

# Validate gates.json first (separate from emit-null-env which only validates project.json)
_GATES_VALIDATION_ERR="$("$_CONFIG_LOADER" validate-gates "$_GATES_JSON" 2>&1)" || {
  echo "INFRASTRUCTURE_ERROR: gates.json validation failed" >&2
  return 2 2>/dev/null || exit 2
}
unset _GATES_VALIDATION_ERR

# Validate project.json and emit NUL-delimited environment
# Use temp file for NUL output (bash variables cannot hold NUL bytes)
_NUL_TMPFILE="$(mktemp)"
if ! "$_CONFIG_LOADER" emit-null-env "$_PROJECT_JSON" > "$_NUL_TMPFILE" 2>/dev/null; then
  echo "INFRASTRUCTURE_ERROR: config_loader.py emit-null-env failed" >&2
  rm -f "$_NUL_TMPFILE"
  return 2 2>/dev/null || exit 2
fi

# Parse NUL-delimited output from temp file
declare -a _NUL_PARTS=()
while IFS= read -r -d '' _part; do
  _NUL_PARTS+=("$_part")
done < "$_NUL_TMPFILE"
rm -f "$_NUL_TMPFILE"

# Emit exactly 11 key-value pairs (22 NUL-separated tokens + trailing NUL = 23 elements, last empty)
if [[ ${#_NUL_PARTS[@]} -lt 22 ]]; then
  echo "INFRASTRUCTURE_ERROR: config_loader.py emitted fewer than 22 tokens (${#_NUL_PARTS[@]})" >&2
  unset _NUL_PARTS
  return 2 2>/dev/null || exit 2
fi

# Assign values from fixed-order key-value pairs
for (( _i=0; _i<22; _i+=2 )); do
  _key="${_NUL_PARTS[$_i]}"
  _val="${_NUL_PARTS[$((_i+1))]}"
  case "$_key" in
    FORGEMIND_MAIN_ROOT)         export FORGEMIND_MAIN_ROOT="$_val" ;;
    FORGEMIND_AGENT_LOOP_ROOT)   export FORGEMIND_AGENT_LOOP_ROOT="$_val" ;;
    AGENTLAB_ROOT)               export AGENTLAB_ROOT="$_val" ;;
    SOURCE_WORKTREE_ROOT)        export SOURCE_WORKTREE_ROOT="$_val" ;;
    VALIDATION_WORKTREE_ROOT)    export VALIDATION_WORKTREE_ROOT="$_val" ;;
    RUNS_ROOT)                   export RUNS_ROOT="$_val" ;;
    PROJECT_ID)                  export PROJECT_ID="$_val" ;;
    REPOSITORY_NAME)             export REPOSITORY_NAME="$_val" ;;
    GLOBALLY_FORBIDDEN_PATHS)    export GLOBALLY_FORBIDDEN_PATHS="$_val" ;;
    APPROVAL_REQUIRED_PATHS)     export APPROVAL_REQUIRED_PATHS="$_val" ;;
    MAX_REPAIR_ITERATIONS)       export MAX_REPAIR_ITERATIONS="$_val" ;;
    *)
      echo "INFRASTRUCTURE_ERROR: Unknown key from config_loader: $_key" >&2
      unset _NUL_PARTS _key _val _i
      return 2 2>/dev/null || exit 2
      ;;
  esac
done
unset _NUL_PARTS _key _val _i

unset _PROJECT_JSON _GATES_JSON _CONFIG_LOADER

# Test configuration
# Auto-detect .venv from Git common directory (no machine-specific hardcoded paths)
_MAIN_REPO=""
if command -v git &>/dev/null; then
  _COMMON_DIR="$(git -C "$REPO_ROOT" rev-parse --git-common-dir 2>/dev/null)" || true
  if [[ -n "$_COMMON_DIR" ]]; then
    # --git-common-dir returns path relative to worktree or absolute
    if [[ "$_COMMON_DIR" != /* ]]; then
      _COMMON_DIR="$REPO_ROOT/$_COMMON_DIR"
    fi
    # .venv is at the main repo root (parent of .git common dir)
    _MAIN_REPO="$(cd "$_COMMON_DIR/.." 2>/dev/null && pwd)" || true
  fi
fi
unset _COMMON_DIR

# Tool binaries: honor pre-set values (isolated test environments), else detect.
# Missing required binary -> deterministic infrastructure error.
if [[ -n "${PYTHON_BIN:-}" ]]; then
  if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "INFRASTRUCTURE_ERROR: PYTHON_BIN is set but not executable: $PYTHON_BIN" >&2
    return 2 2>/dev/null || exit 2
  fi
  export PYTHON_BIN
elif [[ -n "$_MAIN_REPO" && -x "$_MAIN_REPO/.venv/bin/python" ]]; then
  export PYTHON_BIN="$_MAIN_REPO/.venv/bin/python"
elif command -v python3 &>/dev/null; then
  export PYTHON_BIN="$(command -v python3)"
else
  echo "INFRASTRUCTURE_ERROR: Python not found. Set PYTHON_BIN or ensure python3 is in PATH" >&2
  unset _MAIN_REPO
  return 2 2>/dev/null || exit 2
fi

if [[ -n "${PYTEST_BIN:-}" ]]; then
  if [[ ! -x "$PYTEST_BIN" ]]; then
    echo "INFRASTRUCTURE_ERROR: PYTEST_BIN is set but not executable: $PYTEST_BIN" >&2
    return 2 2>/dev/null || exit 2
  fi
  export PYTEST_BIN
elif [[ -n "$_MAIN_REPO" && -x "$_MAIN_REPO/.venv/bin/pytest" ]]; then
  export PYTEST_BIN="$_MAIN_REPO/.venv/bin/pytest"
elif command -v pytest &>/dev/null; then
  export PYTEST_BIN="$(command -v pytest)"
else
  echo "INFRASTRUCTURE_ERROR: pytest not found. Set PYTEST_BIN or ensure pytest is in PATH" >&2
  unset _MAIN_REPO
  return 2 2>/dev/null || exit 2
fi

if [[ -n "${RUFF_BIN:-}" ]]; then
  if [[ ! -x "$RUFF_BIN" ]]; then
    echo "INFRASTRUCTURE_ERROR: RUFF_BIN is set but not executable: $RUFF_BIN" >&2
    return 2 2>/dev/null || exit 2
  fi
  export RUFF_BIN
elif [[ -n "$_MAIN_REPO" && -x "$_MAIN_REPO/.venv/bin/ruff" ]]; then
  export RUFF_BIN="$_MAIN_REPO/.venv/bin/ruff"
elif command -v ruff &>/dev/null; then
  export RUFF_BIN="$(command -v ruff)"
else
  export RUFF_BIN=""
fi

if [[ -n "${MYPY_BIN:-}" ]]; then
  if [[ ! -x "$MYPY_BIN" ]]; then
    echo "INFRASTRUCTURE_ERROR: MYPY_BIN is set but not executable: $MYPY_BIN" >&2
    return 2 2>/dev/null || exit 2
  fi
  export MYPY_BIN
elif [[ -n "$_MAIN_REPO" && -x "$_MAIN_REPO/.venv/bin/mypy" ]]; then
  export MYPY_BIN="$_MAIN_REPO/.venv/bin/mypy"
elif command -v mypy &>/dev/null; then
  export MYPY_BIN="$(command -v mypy)"
else
  export MYPY_BIN=""
fi

unset _MAIN_REPO

# Safety: no auto-commit
export AUTO_COMMIT="false"

# Loop configuration
export DRY_RUN="${DRY_RUN:-false}"

echo "Agent Loop Config loaded"
echo "  REPO_ROOT: $REPO_ROOT"
echo "  MAX_REPAIR_ITERATIONS: $MAX_REPAIR_ITERATIONS"
echo "  DRY_RUN: $DRY_RUN"
