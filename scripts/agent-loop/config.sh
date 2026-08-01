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

# Agent binaries
export RALPH_BIN="/run/media/toha/Virtual Staff/AgentLab/bin/ralph-agentlab"
export OPENCODE_BIN="/run/media/toha/Virtual Staff/AgentLab/bin/opencode-agentlab"

# State directories
export AGENT_STATE="/run/media/toha/Virtual Staff/AgentLab/state"
export ARTIFACTS_DIR="$REPO_ROOT/.ralph-tui/artifacts"

# Loop configuration
export MAX_REPAIR_ITERATIONS="${MAX_REPAIR_ITERATIONS:-3}"
export DRY_RUN="${DRY_RUN:-false}"

# Verification gates
export GATES_CONFIG="$SCRIPT_DIR/config.gates.json"

# Test configuration
# .venv is in the main repo, not in worktrees
MAIN_REPO="/run/media/toha/Virtual Staff/VScode/AIAutomation"
export PYTHON_BIN="$MAIN_REPO/.venv/bin/python"
export PYTEST_BIN="$MAIN_REPO/.venv/bin/pytest"
export RUFF_BIN="$MAIN_REPO/.venv/bin/ruff"
export MYPY_BIN="$MAIN_REPO/.venv/bin/mypy"

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
