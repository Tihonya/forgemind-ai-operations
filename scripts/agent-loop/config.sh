#!/usr/bin/env bash
# Agent Loop Configuration
# Source this file from all agent-loop scripts

# NOTE: this file is sourced, not executed directly.
# Do NOT set -e here — let the caller control error handling.
set -uo pipefail

# Repository root (auto-detect from script location)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

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

# Loop configuration
export MAX_REPAIR_ITERATIONS="${MAX_REPAIR_ITERATIONS:-3}"
export DRY_RUN="${DRY_RUN:-false}"

# Verification gates config
export GATES_CONFIG="$SCRIPT_DIR/config.gates.json"

# Shared Python harness module
export HARNESS_PY="$SCRIPT_DIR/lib/harness.py"

# Test configuration
# .venv is in the main repo, not in worktrees
# Override via environment variables or use command -v fallback
MAIN_REPO="${MAIN_REPO:-/run/media/toha/Virtual Staff/VScode/AIAutomation}"

if [[ -x "$MAIN_REPO/.venv/bin/python" ]]; then
  export PYTHON_BIN="$MAIN_REPO/.venv/bin/python"
elif command -v python3 &>/dev/null; then
  export PYTHON_BIN="$(command -v python3)"
else
  echo "ERROR: Python not found. Set PYTHON_BIN or ensure python3 is in PATH" >&2
  exit 1
fi

if [[ -x "$MAIN_REPO/.venv/bin/pytest" ]]; then
  export PYTEST_BIN="$MAIN_REPO/.venv/bin/pytest"
elif command -v pytest &>/dev/null; then
  export PYTEST_BIN="$(command -v pytest)"
else
  echo "ERROR: pytest not found. Set PYTEST_BIN or ensure pytest is in PATH" >&2
  exit 1
fi

if [[ -x "$MAIN_REPO/.venv/bin/ruff" ]]; then
  export RUFF_BIN="$MAIN_REPO/.venv/bin/ruff"
elif command -v ruff &>/dev/null; then
  export RUFF_BIN="$(command -v ruff)"
else
  export RUFF_BIN=""
fi

if [[ -x "$MAIN_REPO/.venv/bin/mypy" ]]; then
  export MYPY_BIN="$MAIN_REPO/.venv/bin/mypy"
elif command -v mypy &>/dev/null; then
  export MYPY_BIN="$(command -v mypy)"
else
  export MYPY_BIN=""
fi

# Safety: no auto-commit
export AUTO_COMMIT="false"

# Forbidden patterns (regex)
export FORBIDDEN_PATHS=(
  '\.env$'
  '\.env\..*'
  '.*credentials.*'
  '.*secret.*\.key$'
  'forgemind_project_source_of_truth/.*'
  'docker-compose\.yml$'
  'backend/alembic/versions/.*'
)

# Allowed paths for current story (can be overridden by story manifest)
export ALLOWED_PATHS=(
  'backend/tests/.*'
  'scripts/agent-loop/.*'
  '\.gitignore$'
  'docs/.*'
  'README\.md$'
)

echo "Agent Loop Config loaded"
echo "  REPO_ROOT: $REPO_ROOT"
echo "  MAX_REPAIR_ITERATIONS: $MAX_REPAIR_ITERATIONS"
echo "  DRY_RUN: $DRY_RUN"
