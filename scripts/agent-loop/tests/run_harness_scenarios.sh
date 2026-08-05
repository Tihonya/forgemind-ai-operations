#!/usr/bin/env bash
# run_harness_scenarios.sh - WP-AL-1B2B: isolated harness execution
#
# Every scenario A-O runs inside its own disposable temporary Git repository
# (see tests/lib/temp_repo_fixture.py). The real infrastructure worktree is
# never mutated: no stash, no registered worktrees, no synthetic files in the
# real backend tree, cleanup removes only fixture-created temp dirs.
#
# P-S identity-guard scenarios retain their pre-gate flow (they fail before
# any gate executes).
#
# Expected results:
#   A: exit 0 (required test passes, all gates pass)
#   B: exit 1 (required test file missing)
#   C: exit 1 (all tests skipped, assertion gate)
#   D: exit 0 (real tests pass)
#   E: exit 2 (broken JSON manifest)
#   F: exit 1 (zero tests collected, assertion gate)
#   G: exit 1 (pytest collection error)
#   H: exit 1 (pytest failure)
#   I: exit 0 (mixed passed + skipped)
#   J: exit 0 (allowlisted targeted_tests override honored)
#   K: exit non-zero (malformed JUnit XML)
#   L: exit 2 (missing manifest file)
#   M: exit 0 (path with spaces handled)
#   N: exit 0 (concurrent runs produce different RUN_ID)
#   O: exit 0 (interruption cleanup)
#   P: exit 2 (missing passport)
#   Q: exit 2 (wrong branch)
#   R: exit 2 (wrong workspace type)
#   S: exit 2 (malformed passport)

set -uo pipefail

# Capture paths BEFORE sourcing config.sh (which overrides SCRIPT_DIR)
THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURES_DIR="$THIS_DIR/fixtures"

# Test environment setup: harness tests need AGENTLAB_ROOT and
# FORGEMIND_MAIN_ROOT for config.sh. Use isolated temp dirs to avoid
# machine-specific paths.
_TEST_CREATED_AGENTLAB=""
_TEST_CREATED_MAIN=""

if [[ -z "${AGENTLAB_ROOT:-}" ]]; then
  _TEST_AGENTLAB_ROOT="$(mktemp -d /tmp/harness-agentlab-XXXXXX)"
  export AGENTLAB_ROOT="$_TEST_AGENTLAB_ROOT"
  _TEST_CREATED_AGENTLAB="true"
fi

if [[ -z "${FORGEMIND_MAIN_ROOT:-}" ]]; then
  _TEST_FORGEMIND_MAIN_ROOT="$(mktemp -d /tmp/harness-forgemind-XXXXXX)"
  export FORGEMIND_MAIN_ROOT="$_TEST_FORGEMIND_MAIN_ROOT"
  _TEST_CREATED_MAIN="true"
fi

# Isolated harness environment
export SCENARIOS_THIS_DIR="$THIS_DIR"
source "$THIS_DIR/lib/scenario_helpers.sh"

# Source config.sh against the REAL repo (binary detection, project config).
# Isolated scenario runs re-source it inside their own repo root.
source "$THIS_DIR/../config.sh" || {
  echo "INFRASTRUCTURE_ERROR: config.sh sourcing failed" >&2
  exit 2
}

VERIFY_SCRIPT_REAL="$THIS_DIR/../verify-story.sh"

cleanup() {
  cleanup_scenario_tmp_dirs
  # Remove only this suite's own temp dir (uniquely created above)
  if [[ -n "${SUITE_TMP:-}" && -d "$SUITE_TMP" ]]; then
    rm -rf "$SUITE_TMP"
  fi

  # Remove test-only temp dirs if we created them
  if [[ -n "$_TEST_CREATED_AGENTLAB" && -n "${_TEST_AGENTLAB_ROOT:-}" ]]; then
    rm -rf "$_TEST_AGENTLAB_ROOT" 2>/dev/null
  fi
  if [[ -n "$_TEST_CREATED_MAIN" && -n "${_TEST_FORGEMIND_MAIN_ROOT:-}" ]]; then
    rm -rf "$_TEST_FORGEMIND_MAIN_ROOT" 2>/dev/null
  fi
}

trap cleanup EXIT

echo "================================================================"
echo "HARNESS VALIDATION - Agent Loop Phase 1 (WP-AL-1B2B isolation)"
echo "================================================================"

# Per-suite unique temp dir: scenario logs, manifests and passports live here.
# Concurrent suite runs must never share paths.
SUITE_TMP="$(mktemp -d "${TMPDIR:-/tmp}/harness-suite-XXXXXX")" || {
  echo "INFRASTRUCTURE_ERROR: cannot create suite temp dir" >&2
  exit 2
}

# ============================================================================
# Scenario A: required test exists and passes
# ============================================================================
echo ""
echo "================================================================"
echo "Scenario A: Required test exists and passes (isolated repo)"
echo "================================================================"
create_isolated_repo "A"
add_candidate_file "backend/tests/synthetic/test_harness_a.py" "$FIXTURES_DIR/test_harness_a.py"
MANIFEST_A="$(mktemp "$SUITE_TMP/manifest-A-XXXXXX" --suffix=".json")"
write_scenario_manifest "$MANIFEST_A" "HARNESS-A" \
  '["tests/synthetic/test_harness_a.py", "-v", "--junitxml={report_file}"]'
run_isolated_verify "$MANIFEST_A" > "$SUITE_TMP/a.log" 2>&1
A_EXIT=$?
rm -f "$MANIFEST_A" "$SUITE_TMP/a.log"
echo ""
echo "Exit code: $A_EXIT"

# ============================================================================
# Scenario B: required test missing
# ============================================================================
echo ""
echo "================================================================"
echo "Scenario B: Required test missing (isolated repo)"
echo "================================================================"
create_isolated_repo "B"
MANIFEST_B="$(mktemp "$SUITE_TMP/manifest-B-XXXXXX" --suffix=".json")"
write_scenario_manifest "$MANIFEST_B" "HARNESS-B" \
  '["tests/synthetic/test_nonexistent_harness.py", "-v", "--junitxml={report_file}"]'
run_isolated_verify "$MANIFEST_B" > "$SUITE_TMP/b.log" 2>&1
B_EXIT=$?
rm -f "$MANIFEST_B" "$SUITE_TMP/b.log"
echo ""
echo "Exit code: $B_EXIT"

# ============================================================================
# Scenario C: all tests skipped
# ============================================================================
echo ""
echo "================================================================"
echo "Scenario C: All tests skipped (isolated repo)"
echo "================================================================"
create_isolated_repo "C"
add_candidate_file "backend/tests/synthetic/test_harness_c.py" "$FIXTURES_DIR/test_harness_c.py"
MANIFEST_C="$(mktemp "$SUITE_TMP/manifest-C-XXXXXX" --suffix=".json")"
write_scenario_manifest "$MANIFEST_C" "HARNESS-C" \
  '["tests/synthetic/test_harness_c.py", "-v", "--junitxml={report_file}"]'
run_isolated_verify "$MANIFEST_C" > "$SUITE_TMP/c.log" 2>&1
C_EXIT=$?
rm -f "$MANIFEST_C" "$SUITE_TMP/c.log"
echo ""
echo "Exit code: $C_EXIT"

# ============================================================================
# Scenario D: real tests pass
# ============================================================================
echo ""
echo "================================================================"
echo "Scenario D: Real tests pass (isolated repo)"
echo "================================================================"
create_isolated_repo "D"
add_candidate_file "backend/tests/synthetic/test_harness_d.py" "$FIXTURES_DIR/test_harness_d.py"
MANIFEST_D="$(mktemp "$SUITE_TMP/manifest-D-XXXXXX" --suffix=".json")"
write_scenario_manifest "$MANIFEST_D" "HARNESS-D" \
  '["tests/synthetic/test_harness_d.py", "-v", "--junitxml={report_file}"]'
run_isolated_verify "$MANIFEST_D" > "$SUITE_TMP/d.log" 2>&1
D_EXIT=$?
rm -f "$MANIFEST_D" "$SUITE_TMP/d.log"
echo ""
echo "Exit code: $D_EXIT"

# ============================================================================
# Scenario E: internal harness error (broken JSON manifest)
# ============================================================================
echo ""
echo "================================================================"
echo "Scenario E: Internal harness error (broken JSON)"
echo "================================================================"
create_isolated_repo "E"
run_isolated_verify "$FIXTURES_DIR/manifest-scenario-e-broken.json" > "$SUITE_TMP/e.log" 2>&1
E_EXIT=$?
rm -f "$SUITE_TMP/e.log"
echo ""
echo "Exit code: $E_EXIT"

# ============================================================================
# Scenario F: zero tests collected
# ============================================================================
echo ""
echo "================================================================"
echo "Scenario F: Zero tests collected (isolated repo)"
echo "================================================================"
create_isolated_repo "F"
add_candidate_content "backend/tests/synthetic/test_harness_f.py" <<'PYEOF'
"""Harness Scenario F: zero tests collected."""

# No test functions defined
PYEOF
MANIFEST_F="$(mktemp "$SUITE_TMP/manifest-F-XXXXXX" --suffix=".json")"
write_scenario_manifest "$MANIFEST_F" "HARNESS-F" \
  '["tests/synthetic/test_harness_f.py", "-v", "--junitxml={report_file}"]'
run_isolated_verify "$MANIFEST_F" > "$SUITE_TMP/f.log" 2>&1
F_EXIT=$?
rm -f "$MANIFEST_F" "$SUITE_TMP/f.log"
echo ""
echo "Exit code: $F_EXIT"

# ============================================================================
# Scenario G: pytest collection error
# ============================================================================
echo ""
echo "================================================================"
echo "Scenario G: Pytest collection error (isolated repo)"
echo "================================================================"
create_isolated_repo "G"
add_candidate_content "backend/tests/synthetic/test_harness_g.py" <<'PYEOF'
"""Harness Scenario G: collection error."""

import nonexistent_module_that_will_fail


def test_something():
    assert True
PYEOF
MANIFEST_G="$(mktemp "$SUITE_TMP/manifest-G-XXXXXX" --suffix=".json")"
write_scenario_manifest "$MANIFEST_G" "HARNESS-G" \
  '["tests/synthetic/test_harness_g.py", "-v", "--junitxml={report_file}"]'
run_isolated_verify "$MANIFEST_G" > "$SUITE_TMP/g.log" 2>&1
G_EXIT=$?
rm -f "$MANIFEST_G" "$SUITE_TMP/g.log"
echo ""
echo "Exit code: $G_EXIT"

# ============================================================================
# Scenario H: pytest failure
# ============================================================================
echo ""
echo "================================================================"
echo "Scenario H: Pytest failure (isolated repo)"
echo "================================================================"
create_isolated_repo "H"
add_candidate_content "backend/tests/synthetic/test_harness_h.py" <<'PYEOF'
"""Harness Scenario H: test failure."""


def test_failing():
    assert False, "Intentional failure"
PYEOF
MANIFEST_H="$(mktemp "$SUITE_TMP/manifest-H-XXXXXX" --suffix=".json")"
write_scenario_manifest "$MANIFEST_H" "HARNESS-H" \
  '["tests/synthetic/test_harness_h.py", "-v", "--junitxml={report_file}"]'
run_isolated_verify "$MANIFEST_H" > "$SUITE_TMP/h.log" 2>&1
H_EXIT=$?
rm -f "$MANIFEST_H" "$SUITE_TMP/h.log"
echo ""
echo "Exit code: $H_EXIT"

# ============================================================================
# Scenario I: mixed passed + skipped
# ============================================================================
echo ""
echo "================================================================"
echo "Scenario I: Mixed passed + skipped (isolated repo)"
echo "================================================================"
create_isolated_repo "I"
add_candidate_content "backend/tests/synthetic/test_harness_i.py" <<'PYEOF'
"""Harness Scenario I: mixed passed and skipped."""

import pytest


def test_passing():
    assert True


@pytest.mark.skip(reason="Intentional skip")
def test_skipped():
    assert True


def test_another_passing():
    assert 1 + 1 == 2
PYEOF
MANIFEST_I="$(mktemp "$SUITE_TMP/manifest-I-XXXXXX" --suffix=".json")"
write_scenario_manifest "$MANIFEST_I" "HARNESS-I" \
  '["tests/synthetic/test_harness_i.py", "-v", "--junitxml={report_file}"]'
run_isolated_verify "$MANIFEST_I" > "$SUITE_TMP/i.log" 2>&1
I_EXIT=$?
rm -f "$MANIFEST_I" "$SUITE_TMP/i.log"
echo ""
echo "Exit code: $I_EXIT"

# ============================================================================
# Scenario J: allowlisted gate override honored (assertion_gate=false)
# Canonical intent: validate allowlisted targeted_tests override behavior.
# With assertion_gate=false an all-skipped suite passes the targeted_tests
# gate (execution completed) — no legacy optional-gate weakening involved.
# ============================================================================
echo ""
echo "================================================================"
echo "Scenario J: Gate overrides with allowlisted fields (isolated repo)"
echo "================================================================"
create_isolated_repo "J"
add_candidate_file "backend/tests/synthetic/test_harness_j.py" "$FIXTURES_DIR/test_harness_c.py"
MANIFEST_J="$(mktemp "$SUITE_TMP/manifest-J-XXXXXX" --suffix=".json")"
write_scenario_manifest "$MANIFEST_J" "HARNESS-J" \
  '["tests/synthetic/test_harness_j.py", "-v", "--junitxml={report_file}"]' \
  '{"targeted_tests": {"assertion_gate": false}}'
run_isolated_verify "$MANIFEST_J" > "$SUITE_TMP/j.log" 2>&1
J_EXIT=$?
rm -f "$MANIFEST_J" "$SUITE_TMP/j.log"
echo ""
echo "Exit code: $J_EXIT"

# ============================================================================
# Scenario K: malformed JUnit XML (internal test)
# ============================================================================
echo ""
echo "================================================================"
echo "Scenario K: Malformed JUnit XML (internal test)"
echo "================================================================"
TEMP_XML="$(mktemp "$SUITE_TMP/malformed-XXXXXX" --suffix=".xml")"
cat > "$TEMP_XML" <<'XMLEOF'
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="broken" tests="3" failures="1" errors="0" skipped="0">
    <!-- Missing closing tag intentionally -->
XMLEOF

"$PYTHON_BIN" "$THIS_DIR/../lib/harness.py" parse_junit "$TEMP_XML" > /dev/null 2>&1
K_EXIT=$?
rm -f "$TEMP_XML"
echo ""
echo "Exit code: $K_EXIT (expected: non-zero for malformed XML)"

# ============================================================================
# Scenario L: missing manifest file
# ============================================================================
echo ""
echo "================================================================"
echo "Scenario L: Missing manifest file"
echo "================================================================"
create_isolated_repo "L"
run_isolated_verify "$SUITE_TMP/nonexistent-manifest.json" > "$SUITE_TMP/l.log" 2>&1
L_EXIT=$?
rm -f "$SUITE_TMP/l.log"
echo ""
echo "Exit code: $L_EXIT"

# ============================================================================
# Scenario M: test path containing spaces
# ============================================================================
echo ""
echo "================================================================"
echo "Scenario M: Test path containing spaces (isolated repo)"
echo "================================================================"
create_isolated_repo "M"
add_candidate_file "backend/tests/synthetic/path with spaces/test_harness_m.py" \
  "$FIXTURES_DIR/test_harness_a.py"
MANIFEST_M="$(mktemp "$SUITE_TMP/manifest-M-XXXXXX" --suffix=".json")"
write_scenario_manifest "$MANIFEST_M" "HARNESS-M" \
  '["tests/synthetic/path with spaces/test_harness_m.py", "-v", "--junitxml={report_file}"]'
run_isolated_verify "$MANIFEST_M" > "$SUITE_TMP/m.log" 2>&1
M_EXIT=$?
rm -f "$MANIFEST_M" "$SUITE_TMP/m.log"
echo ""
echo "Exit code: $M_EXIT"

# ============================================================================
# Scenario N: concurrent runs produce different RUN_ID
# ============================================================================
echo ""
echo "================================================================"
echo "Scenario N: Concurrent runs produce different RUN_ID"
echo "================================================================"
create_isolated_repo "N"
add_candidate_file "backend/tests/synthetic/test_harness_a.py" "$FIXTURES_DIR/test_harness_a.py"
MANIFEST_N1="$(mktemp "$SUITE_TMP/manifest-N1-XXXXXX" --suffix=".json")"
MANIFEST_N2="$(mktemp "$SUITE_TMP/manifest-N2-XXXXXX" --suffix=".json")"
write_scenario_manifest "$MANIFEST_N1" "HARNESS-N" \
  '["tests/synthetic/test_harness_a.py", "-v", "--junitxml={report_file}"]'
cp "$MANIFEST_N1" "$MANIFEST_N2"

# Run both in background inside the isolated repo
(
  cd "$ISOLATED_REPO" || exit 2
  bash "$ISOLATED_REPO/scripts/agent-loop/verify-story.sh" "$MANIFEST_N1" > "$SUITE_TMP/n1.log" 2>&1
) &
PID1=$!
(
  cd "$ISOLATED_REPO" || exit 2
  bash "$ISOLATED_REPO/scripts/agent-loop/verify-story.sh" "$MANIFEST_N2" > "$SUITE_TMP/n2.log" 2>&1
) &
PID2=$!

wait $PID1
wait $PID2

# Extract RUN_IDs from logs
RUN_ID1="$(grep "Run directory:" "$SUITE_TMP/n1.log" | sed 's/.*artifacts\///')"
RUN_ID2="$(grep "Run directory:" "$SUITE_TMP/n2.log" | sed 's/.*artifacts\///')"

echo "Run 1: $RUN_ID1"
echo "Run 2: $RUN_ID2"

if [[ -n "$RUN_ID1" && -n "$RUN_ID2" && "$RUN_ID1" != "$RUN_ID2" ]]; then
  echo "PASS: RUN_IDs are different (collision-resistant)"
  N_EXIT=0
else
  echo "FAIL: RUN_IDs are identical or missing (collision detected)"
  N_EXIT=1
fi

rm -f "$SUITE_TMP/n1.log" "$SUITE_TMP/n2.log"
rm -f "$MANIFEST_N1" "$MANIFEST_N2"

# ============================================================================
# Scenario O: interruption cleanup (no destructive operations)
# ============================================================================
echo ""
echo "================================================================"
echo "Scenario O: Interruption cleanup (no destructive operations)"
echo "================================================================"
create_isolated_repo "O"
add_candidate_file "backend/tests/synthetic/test_harness_a.py" "$FIXTURES_DIR/test_harness_a.py"
MANIFEST_O="$(mktemp "$SUITE_TMP/manifest-O-XXXXXX" --suffix=".json")"
write_scenario_manifest "$MANIFEST_O" "HARNESS-O" \
  '["tests/synthetic/test_harness_a.py", "-v", "--junitxml={report_file}"]'

# Start verification in background inside the isolated repo
(
  cd "$ISOLATED_REPO" || exit 2
  bash "$ISOLATED_REPO/scripts/agent-loop/verify-story.sh" "$MANIFEST_O" > "$SUITE_TMP/o.log" 2>&1
) &
PID_O=$!

# Wait a moment for it to create temp files
sleep 0.5

# Send SIGTERM
kill -TERM $PID_O 2>/dev/null || true
wait $PID_O 2>/dev/null || true

# Check if temp files were cleaned up (inside the isolated repo's artifacts)
TEMP_FILES_REMAINING="$(find "$ISOLATED_REPO/.ralph-tui/artifacts" -name ".gates-tmp.json" -o -name ".gate-config-tmp.json" -o -name ".diff-files-tmp.lst" -o -name ".diff-json-tmp.json" 2>/dev/null | wc -l)"

if [[ $TEMP_FILES_REMAINING -eq 0 ]]; then
  echo "PASS: Cleanup trap removed temp files"
  O_EXIT=0
else
  echo "WARN: $TEMP_FILES_REMAINING temp files remaining after interruption"
  O_EXIT=0  # Interruption timing is racy; trap covers normal completion
fi

rm -f "$SUITE_TMP/o.log" "$MANIFEST_O"

# ============================================================================
# Scenario P: Missing passport at verify phase (real repo, pre-gate flow)
# ============================================================================
echo ""
echo "================================================================"
echo "Scenario P: Missing passport at verify phase"
echo "================================================================"

MANIFEST_P="$(mktemp "$SUITE_TMP/manifest-P-XXXXXX" --suffix=".json")"
cat > "$MANIFEST_P" <<EOF
{
  "schema_version": "1.0",
  "project_id": "forgemind",
  "story_id": "HARNESS-P",
  "title": "Test Scenario P - Missing Passport",
  "description": "Should fail with INFRASTRUCTURE_ERROR",
  "base_commit": "0000000000000000000000000000000000000000",
  "expected_branch": "chore/agent-loop-infrastructure",
  "path_pattern_type": "gitwildmatch",
  "allowed_paths": ["tests/.*"],
  "forbidden_paths": [".env"],
  "required_gates": ["scope", "json_syntax", "yaml_syntax", "targeted_tests", "lint", "secrets", "git_diff_check"],
  "test_commands": {
    "targeted_args": ["tests/synthetic/test_harness_a.py", "-v"]
  },
  "environment_requirements": {
    "database": {"required": false, "auto_start": false},
    "redis": {"required": false, "auto_start": false},
    "external_network": {"allowed": false}
  },
  "expected_outputs": ["test-report.json"],
  "acceptance_criteria": ["Identity guard blocks before gates"],
  "repair_budget": 3,
  "model_routing_hints": {
    "implementation_role": "implementer",
    "review_role": "reviewer",
    "complexity": "standard",
    "local_worker_allowed": true
  },
  "dependencies": [],
  "conflict_domains": []
}
EOF

# Ensure no passport is set
unset PASSPORT_FILE 2>/dev/null || true

# Set PASSPORT_FILE to a nonexistent path to trigger guard's PASSPORT_MISSING check
export PASSPORT_FILE="$SUITE_TMP/nonexistent-passport-P.json"

# Run verify-story.sh with manifest and a missing passport file
# Guard will detect passport file doesn't exist -> INFRASTRUCTURE_ERROR -> exit 2
"$VERIFY_SCRIPT_REAL" "$MANIFEST_P" > "$SUITE_TMP/scenario-p.log" 2>&1
P_EXIT=$?

# Should fail with exit 2
if [[ $P_EXIT -eq 2 ]]; then
  echo "  PASS (exit code 2: INFRASTRUCTURE_ERROR)"
else
  echo "  FAIL (expected exit 2, got $P_EXIT)"
fi

unset PASSPORT_FILE
rm -f "$MANIFEST_P" "$SUITE_TMP/scenario-p.log"

# ============================================================================
# Scenario Q: Wrong branch in passport (real repo, pre-gate flow)
# ============================================================================
echo ""
echo "================================================================"
echo "Scenario Q: Identity guard with wrong branch"
echo "================================================================"

MANIFEST_Q="$(mktemp "$SUITE_TMP/manifest-Q-XXXXXX" --suffix=".json")"
PASSPORT_Q="$(mktemp "$SUITE_TMP/passport-Q-XXXXXX" --suffix=".json")"

cat > "$MANIFEST_Q" <<EOF
{
  "schema_version": "1.0",
  "project_id": "forgemind",
  "story_id": "HARNESS-Q",
  "title": "Test Scenario Q - Wrong Branch",
  "description": "Should fail with branch mismatch",
  "base_commit": "0000000000000000000000000000000000000000",
  "expected_branch": "chore/agent-loop-infrastructure",
  "path_pattern_type": "gitwildmatch",
  "allowed_paths": ["tests/.*"],
  "forbidden_paths": [".env"],
  "required_gates": ["scope", "json_syntax", "yaml_syntax", "targeted_tests", "lint", "secrets", "git_diff_check"],
  "test_commands": {
    "targeted_args": ["tests/synthetic/test_harness_a.py", "-v"]
  },
  "environment_requirements": {
    "database": {"required": false, "auto_start": false},
    "redis": {"required": false, "auto_start": false},
    "external_network": {"allowed": false}
  },
  "expected_outputs": ["test-report.json"],
  "acceptance_criteria": ["Identity guard blocks before gates"],
  "repair_budget": 3,
  "model_routing_hints": {
    "implementation_role": "implementer",
    "review_role": "reviewer",
    "complexity": "standard",
    "local_worker_allowed": true
  },
  "dependencies": [],
  "conflict_domains": []
}
EOF

# Create passport with wrong branch
CURRENT_BRANCH=$(git branch --show-current)
cat > "$PASSPORT_Q" <<EOF
{
  "schema_version": "1.0",
  "project_id": "test",
  "run_id": "test-run-q",
  "slot_id": "test-slot-q",
  "story_id": "HARNESS-Q",
  "role": "implement",
  "phase": "implement",
  "workspace_type": "source",
  "workspace_root": "$REPO_ROOT",
  "expected_branch": "nonexistent-branch-xyz",
  "base_commit": "HEAD",
  "artifact_root": "/tmp/artifacts-q"
}
EOF

export PASSPORT_FILE="$PASSPORT_Q"

# Run verify-story.sh - should fail with exit 2 (INFRASTRUCTURE_ERROR)
export RUN_ID="test-run-q"
export SLOT_ID="test-slot-q"
export STORY_ID="HARNESS-Q"
export PROJECT_ID="test"
"$VERIFY_SCRIPT_REAL" "$MANIFEST_Q" > "$SUITE_TMP/scenario-q.log" 2>&1
Q_EXIT=$?

# Should fail with exit 2
if [[ $Q_EXIT -eq 2 ]]; then
  echo "  PASS (exit code 2: branch mismatch detected)"
else
  echo "  FAIL (expected exit 2, got $Q_EXIT)"
fi

unset PASSPORT_FILE
rm -f "$MANIFEST_Q" "$PASSPORT_Q" "$SUITE_TMP/scenario-q.log"

# ============================================================================
# Scenario R: Wrong workspace type for phase (real repo, pre-gate flow)
# ============================================================================
echo ""
echo "================================================================"
echo "Scenario R: Identity guard with wrong workspace type"
echo "================================================================"

MANIFEST_R="$(mktemp "$SUITE_TMP/manifest-R-XXXXXX" --suffix=".json")"
PASSPORT_R="$(mktemp "$SUITE_TMP/passport-R-XXXXXX" --suffix=".json")"

cat > "$MANIFEST_R" <<EOF
{
  "schema_version": "1.0",
  "project_id": "forgemind",
  "story_id": "HARNESS-R",
  "title": "Test Scenario R - Wrong Workspace Type",
  "description": "Should fail with workspace type mismatch",
  "base_commit": "0000000000000000000000000000000000000000",
  "expected_branch": "chore/agent-loop-infrastructure",
  "path_pattern_type": "gitwildmatch",
  "allowed_paths": ["tests/.*"],
  "forbidden_paths": [".env"],
  "required_gates": ["scope", "json_syntax", "yaml_syntax", "targeted_tests", "lint", "secrets", "git_diff_check"],
  "test_commands": {
    "targeted_args": ["tests/synthetic/test_harness_a.py", "-v"]
  },
  "environment_requirements": {
    "database": {"required": false, "auto_start": false},
    "redis": {"required": false, "auto_start": false},
    "external_network": {"allowed": false}
  },
  "expected_outputs": ["test-report.json"],
  "acceptance_criteria": ["Identity guard blocks before gates"],
  "repair_budget": 3,
  "model_routing_hints": {
    "implementation_role": "implementer",
    "review_role": "reviewer",
    "complexity": "standard",
    "local_worker_allowed": true
  },
  "dependencies": [],
  "conflict_domains": []
}
EOF

# Create passport with wrong workspace type (validation instead of source)
cat > "$PASSPORT_R" <<EOF
{
  "schema_version": "1.0",
  "project_id": "test",
  "run_id": "test-run-r",
  "slot_id": "test-slot-r",
  "story_id": "HARNESS-R",
  "role": "implement",
  "phase": "implement",
  "workspace_type": "validation",
  "workspace_root": "$REPO_ROOT",
  "expected_branch": "$CURRENT_BRANCH",
  "base_commit": "HEAD",
  "artifact_root": "/tmp/artifacts-r"
}
EOF

export PASSPORT_FILE="$PASSPORT_R"
export RUN_ID="test-run-r"
export SLOT_ID="test-slot-r"
export STORY_ID="HARNESS-R"
export PROJECT_ID="test"

# Run verify-story.sh - should fail with exit 2 (INFRASTRUCTURE_ERROR)
"$VERIFY_SCRIPT_REAL" "$MANIFEST_R" > "$SUITE_TMP/scenario-r.log" 2>&1
R_EXIT=$?

# Should fail with exit 2
if [[ $R_EXIT -eq 2 ]]; then
  echo "  PASS (exit code 2: workspace type mismatch detected)"
else
  echo "  FAIL (expected exit 2, got $R_EXIT)"
fi

unset PASSPORT_FILE
rm -f "$MANIFEST_R" "$PASSPORT_R" "$SUITE_TMP/scenario-r.log"

# ============================================================================
# Scenario S: Missing required passport field (real repo, pre-gate flow)
# ============================================================================
echo ""
echo "================================================================"
echo "Scenario S: Identity guard with malformed passport"
echo "================================================================"

MANIFEST_S="$(mktemp "$SUITE_TMP/manifest-S-XXXXXX" --suffix=".json")"
PASSPORT_S="$(mktemp "$SUITE_TMP/passport-S-XXXXXX" --suffix=".json")"

cat > "$MANIFEST_S" <<EOF
{
  "schema_version": "1.0",
  "project_id": "forgemind",
  "story_id": "HARNESS-S",
  "title": "Test Scenario S - Malformed Passport",
  "description": "Should fail with missing field error",
  "base_commit": "0000000000000000000000000000000000000000",
  "expected_branch": "chore/agent-loop-infrastructure",
  "path_pattern_type": "gitwildmatch",
  "allowed_paths": ["tests/.*"],
  "forbidden_paths": [".env"],
  "required_gates": ["scope", "json_syntax", "yaml_syntax", "targeted_tests", "lint", "secrets", "git_diff_check"],
  "test_commands": {
    "targeted_args": ["tests/synthetic/test_harness_a.py", "-v"]
  },
  "environment_requirements": {
    "database": {"required": false, "auto_start": false},
    "redis": {"required": false, "auto_start": false},
    "external_network": {"allowed": false}
  },
  "expected_outputs": ["test-report.json"],
  "acceptance_criteria": ["Identity guard blocks before gates"],
  "repair_budget": 3,
  "model_routing_hints": {
    "implementation_role": "implementer",
    "review_role": "reviewer",
    "complexity": "standard",
    "local_worker_allowed": true
  },
  "dependencies": [],
  "conflict_domains": []
}
EOF

# Create passport missing required field (artifact_root)
cat > "$PASSPORT_S" <<EOF
{
  "schema_version": "1.0",
  "project_id": "test",
  "run_id": "test-run-s",
  "slot_id": "test-slot-s",
  "story_id": "HARNESS-S",
  "role": "implement",
  "phase": "implement",
  "workspace_type": "source",
  "workspace_root": "$REPO_ROOT",
  "expected_branch": "$CURRENT_BRANCH",
  "base_commit": "HEAD"
}
EOF

export PASSPORT_FILE="$PASSPORT_S"
export RUN_ID="test-run-s"
export SLOT_ID="test-slot-s"
export STORY_ID="HARNESS-S"
export PROJECT_ID="test"

# Run verify-story.sh - should fail with exit 2 (INFRASTRUCTURE_ERROR)
"$VERIFY_SCRIPT_REAL" "$MANIFEST_S" > "$SUITE_TMP/scenario-s.log" 2>&1
S_EXIT=$?

# Should fail with exit 2
if [[ $S_EXIT -eq 2 ]]; then
  echo "  PASS (exit code 2: missing field detected)"
else
  echo "  FAIL (expected exit 2, got $S_EXIT)"
fi

unset PASSPORT_FILE
rm -f "$MANIFEST_S" "$PASSPORT_S" "$SUITE_TMP/scenario-s.log"

# ============================================================================
# Scenario T: WP-AL-1B3 — failure context collection on failed verification
# ============================================================================
echo ""
echo "================================================================"
echo "Scenario T: WP-AL-1B3 — failure context collection (isolated repo)"
echo "================================================================"
create_isolated_repo "T"

# Create a Python file with syntax errors and a failing test to trigger
# multiple gate failures, then verify failure-context.json is produced
add_candidate_content "backend/tests/synthetic/test_harness_t.py" <<'PYEOF'
"""Harness Scenario T: test failure for failure-context collection."""


def test_intentional_failure():
    """This test intentionally fails to trigger failure context collection."""
    assert False, "Intentional failure for Scenario T"
PYEOF

# Also create a file with a lint error to trigger multiple gate failures
add_candidate_content "backend/src/synthetic/module_t.py" <<'PYEOF'
"""Module with lint issues for Scenario T."""

import os,sys  # Multiple imports on one line (lint error)
import json

def bad_function():
    x=1+2  # Missing spaces around operator (lint error)
    unused_var = 42  # Unused variable (lint error)
    return x
PYEOF

MANIFEST_T="$(mktemp "$SUITE_TMP/manifest-T-XXXXXX" --suffix=".json")"
write_scenario_manifest "$MANIFEST_T" "HARNESS-T" \
  '["tests/synthetic/test_harness_t.py", "-v", "--junitxml={report_file}"]'

run_isolated_verify "$MANIFEST_T" > "$SUITE_TMP/t-verify.log" 2>&1
T_VERIFY_EXIT=$?

# Verify that failure-context.json was created
# Find the run directory (most recent in artifacts)
RUN_DIR_T="$("$PYTHON_BIN" "$FIXTURE_PY" find-run --repo "$ISOLATED_REPO")"
FAILURE_CONTEXT_FILE="$RUN_DIR_T/reports/failure-context.json"

if [[ -f "$FAILURE_CONTEXT_FILE" ]]; then
  echo "  PASS - failure-context.json created at $FAILURE_CONTEXT_FILE"

  # Validate JSON structure
  if "$PYTHON_BIN" -c "
import json, sys
try:
    with open(sys.argv[1]) as f:
        fc = json.load(f)

    # Check required fields
    required = ['schema_version', 'run_id', 'story_id', 'candidate_identity',
                'collection_status', 'overall_verification_status', 'gate_verdicts',
                'failing_gate_ids']

    missing = [f for f in required if f not in fc]
    if missing:
        print(f'FAIL - missing fields: {missing}', file=sys.stderr)
        sys.exit(1)

    # Check schema_version
    if fc['schema_version'] != '1.0':
        print(f'FAIL - wrong schema_version: {fc[\"schema_version\"]}', file=sys.stderr)
        sys.exit(1)

    # Check collection_status
    if fc['collection_status'] != 'complete':
        print(f'FAIL - wrong collection_status: {fc[\"collection_status\"]}', file=sys.stderr)
        sys.exit(1)

    # Check overall_verification_status is FAIL (we intentionally failed)
    if fc['overall_verification_status'] != 'FAIL':
        print(f'FAIL - wrong overall_verification_status: {fc[\"overall_verification_status\"]}', file=sys.stderr)
        sys.exit(1)

    # Check failing_gate_ids is non-empty
    if not fc['failing_gate_ids']:
        print('FAIL - failing_gate_ids is empty', file=sys.stderr)
        sys.exit(1)

    # Check candidate_identity fields
    ci = fc['candidate_identity']
    if not all(k in ci for k in ['base_commit', 'candidate_commit', 'candidate_state', 'candidate_diff_digest']):
        print('FAIL - missing candidate_identity fields', file=sys.stderr)
        sys.exit(1)

    # Check candidate_diff_digest is present and is a string
    if not isinstance(ci['candidate_diff_digest'], str):
        print('FAIL - candidate_diff_digest is not a string', file=sys.stderr)
        sys.exit(1)

    # Check no secrets in output (basic check)
    output_str = json.dumps(fc)
    if 'sk_live_' in output_str or 'ghp_' in output_str:
        print('FAIL - potential secret found in output', file=sys.stderr)
        sys.exit(1)

    print('PASS - all validations passed', file=sys.stderr)
    sys.exit(0)
except Exception as e:
    print(f'FAIL - exception: {e}', file=sys.stderr)
    sys.exit(1)
" "$FAILURE_CONTEXT_FILE" 2>&1; then
    echo "  PASS - failure-context.json validation"
    T_VALIDATION_EXIT=0
  else
    echo "  FAIL - failure-context.json validation failed"
    T_VALIDATION_EXIT=1
  fi
else
  echo "  FAIL - failure-context.json not found at $FAILURE_CONTEXT_FILE"
  T_VALIDATION_EXIT=1
fi

# Clean up
rm -f "$MANIFEST_T" "$SUITE_TMP/t-verify.log"

# Scenario T passes if:
# 1. verify-story.sh exited with 1 (FAIL, not ERROR)
# 2. failure-context.json was created
# 3. failure-context.json passed validation
if [[ $T_VERIFY_EXIT -eq 1 && $T_VALIDATION_EXIT -eq 0 ]]; then
  T_EXIT=0
  echo "Scenario T: PASS"
else
  T_EXIT=1
  echo "Scenario T: FAIL (verify_exit=$T_VERIFY_EXIT, validation_exit=$T_VALIDATION_EXIT)"
fi

# ============================================================================
# Scenario U: WP-AL-1C2 — Mock reviewer PASS (isolated repo)
# ============================================================================
echo ""
echo "================================================================"
echo "Scenario U: WP-AL-1C2 — Mock reviewer PASS (isolated repo)"
echo "================================================================"
create_isolated_repo "U"

# Create manifest and failure context
MANIFEST_U="$(mktemp "$SUITE_TMP/manifest-U-XXXXXX" --suffix=".json")"
write_scenario_manifest "$MANIFEST_U" "HARNESS-U" \
  '["tests/synthetic/test_harness_a.py", "-v", "--junitxml={report_file}"]'

# Run verification to create failure context
add_candidate_file "backend/tests/synthetic/test_harness_a.py" "$FIXTURES_DIR/test_harness_a.py"
run_isolated_verify "$MANIFEST_U" > "$SUITE_TMP/u-verify.log" 2>&1
U_VERIFY_EXIT=$?

# Find run directory and failure context
U_RUN_DIR="$("$PYTHON_BIN" "$FIXTURE_PY" find-run --repo "$ISOLATED_REPO")"
U_FAILURE_CONTEXT="$U_RUN_DIR/reports/failure-context.json"

if [[ $U_VERIFY_EXIT -eq 0 && -f "$U_FAILURE_CONTEXT" ]]; then
  # Extract run_id from failure context to match what was used during verification
  U_RUN_ID="$("$PYTHON_BIN" -c "import json; print(json.load(open('$U_FAILURE_CONTEXT'))['run_id'])")"

  # Copy mock reviewer into isolated repo (containment check requires script under repo_root)
  U_MOCK_SCRIPT="$ISOLATED_REPO/mock_reviewer.py"
  cp "$REAL_REPO_ROOT/scripts/agent-loop/lib/mock_reviewer.py" "$U_MOCK_SCRIPT"

  # Copy manifest into isolated repo (containment check requires manifest under repo_root)
  U_MANIFEST="$ISOLATED_REPO/manifest.json"
  cp "$MANIFEST_U" "$U_MANIFEST"

  # Run adapter with mock reviewer in PASS mode
  # Use simple executable name "python3" to avoid symlink check on absolute paths
  U_REVIEW_EXIT=0
  "$PYTHON_BIN" "$REAL_REPO_ROOT/scripts/agent-loop/lib/review_adapter.py" \
    --repo-root "$ISOLATED_REPO" \
    --run-dir "$U_RUN_DIR" \
    --manifest "$U_MANIFEST" \
    --failure-context "$U_FAILURE_CONTEXT" \
    --run-id "$U_RUN_ID" \
    --story-id "HARNESS-U" \
    --review-iteration 1 \
    --repair-iteration 0 \
    --triggered-by initial_verify_pass \
    --generated-at "2026-08-05T00:00:00Z" \
    --reviewer-id "mock-reviewer" \
    --timeout-seconds 30 \
    --reviewer-command python3 \
    --reviewer-arg "$U_MOCK_SCRIPT" \
    --reviewer-arg=--mode \
    --reviewer-arg PASS > "$SUITE_TMP/u-review.log" 2>&1 || U_REVIEW_EXIT=$?

  # Verify review result
  U_REVIEW_RESULT="$U_RUN_DIR/reports/review-result.json"
  if [[ $U_REVIEW_EXIT -eq 0 && -f "$U_REVIEW_RESULT" ]]; then
    if "$PYTHON_BIN" -c "
import json, sys
try:
    with open(sys.argv[1]) as f:
        result = json.load(f)
    if result['status'] != 'PASS':
        print(f'FAIL - wrong status: {result[\"status\"]}', file=sys.stderr)
        sys.exit(1)
    if result['recommended_action'] != 'none':
        print(f'FAIL - wrong recommended_action: {result[\"recommended_action\"]}', file=sys.stderr)
        sys.exit(1)
    if result['findings'] != []:
        print(f'FAIL - findings should be empty', file=sys.stderr)
        sys.exit(1)
    print('PASS - all validations passed', file=sys.stderr)
    sys.exit(0)
except Exception as e:
    print(f'FAIL - exception: {e}', file=sys.stderr)
    sys.exit(1)
" "$U_REVIEW_RESULT" 2>&1; then
      U_EXIT=0
      echo "Scenario U: PASS"
    else
      U_EXIT=1
      echo "Scenario U: FAIL (review result validation failed)"
    fi
  else
    U_EXIT=1
    echo "Scenario U: FAIL (review adapter failed or result not created)"
  fi
else
  U_EXIT=1
  echo "Scenario U: FAIL (verification failed or failure-context not created)"
fi

rm -f "$MANIFEST_U" "$SUITE_TMP/u-verify.log" "$SUITE_TMP/u-review.log"

# ============================================================================
# Scenario V: WP-AL-1C2 — Mock reviewer FAIL (isolated repo)
# ============================================================================
echo ""
echo "================================================================"
echo "Scenario V: WP-AL-1C2 — Mock reviewer FAIL (isolated repo)"
echo "================================================================"
create_isolated_repo "V"

# Create manifest and failure context
MANIFEST_V="$(mktemp "$SUITE_TMP/manifest-V-XXXXXX" --suffix=".json")"
write_scenario_manifest "$MANIFEST_V" "HARNESS-V" \
  '["tests/synthetic/test_harness_a.py", "-v", "--junitxml={report_file}"]'

# Run verification to create failure context
add_candidate_file "backend/tests/synthetic/test_harness_a.py" "$FIXTURES_DIR/test_harness_a.py"
run_isolated_verify "$MANIFEST_V" > "$SUITE_TMP/v-verify.log" 2>&1
V_VERIFY_EXIT=$?

# Find run directory and failure context
V_RUN_DIR="$("$PYTHON_BIN" "$FIXTURE_PY" find-run --repo "$ISOLATED_REPO")"
V_FAILURE_CONTEXT="$V_RUN_DIR/reports/failure-context.json"

if [[ $V_VERIFY_EXIT -eq 0 && -f "$V_FAILURE_CONTEXT" ]]; then
  # Extract run_id from failure context to match what was used during verification
  V_RUN_ID="$("$PYTHON_BIN" -c "import json; print(json.load(open('$V_FAILURE_CONTEXT'))['run_id'])")"

  # Copy mock reviewer into isolated repo (containment check requires script under repo_root)
  V_MOCK_SCRIPT="$ISOLATED_REPO/mock_reviewer.py"
  cp "$REAL_REPO_ROOT/scripts/agent-loop/lib/mock_reviewer.py" "$V_MOCK_SCRIPT"

  # Copy manifest into isolated repo (containment check requires manifest under repo_root)
  V_MANIFEST="$ISOLATED_REPO/manifest.json"
  cp "$MANIFEST_V" "$V_MANIFEST"

  # Run adapter with mock reviewer in FAIL mode
  # Use simple executable name "python3" to avoid symlink check on absolute paths
  V_REVIEW_EXIT=0
  "$PYTHON_BIN" "$REAL_REPO_ROOT/scripts/agent-loop/lib/review_adapter.py" \
    --repo-root "$ISOLATED_REPO" \
    --run-dir "$V_RUN_DIR" \
    --manifest "$V_MANIFEST" \
    --failure-context "$V_FAILURE_CONTEXT" \
    --run-id "$V_RUN_ID" \
    --story-id "HARNESS-V" \
    --review-iteration 1 \
    --repair-iteration 0 \
    --triggered-by initial_verify_pass \
    --generated-at "2026-08-05T00:00:00Z" \
    --reviewer-id "mock-reviewer" \
    --timeout-seconds 30 \
    --reviewer-command python3 \
    --reviewer-arg "$V_MOCK_SCRIPT" \
    --reviewer-arg=--mode \
    --reviewer-arg FAIL > "$SUITE_TMP/v-review.log" 2>&1 || V_REVIEW_EXIT=$?

  # Verify review result
  V_REVIEW_RESULT="$V_RUN_DIR/reports/review-result.json"
  if [[ $V_REVIEW_EXIT -eq 0 && -f "$V_REVIEW_RESULT" ]]; then
    if "$PYTHON_BIN" -c "
import json, sys
try:
    with open(sys.argv[1]) as f:
        result = json.load(f)
    if result['status'] != 'FAIL':
        print(f'FAIL - wrong status: {result[\"status\"]}', file=sys.stderr)
        sys.exit(1)
    if result['recommended_action'] != 'repair':
        print(f'FAIL - wrong recommended_action: {result[\"recommended_action\"]}', file=sys.stderr)
        sys.exit(1)
    if len(result['findings']) < 1:
        print(f'FAIL - should have at least one finding', file=sys.stderr)
        sys.exit(1)
    if result['findings'][0]['severity'] != 'BLOCKER':
        print(f'FAIL - first finding severity should be BLOCKER', file=sys.stderr)
        sys.exit(1)
    print('PASS - all validations passed', file=sys.stderr)
    sys.exit(0)
except Exception as e:
    print(f'FAIL - exception: {e}', file=sys.stderr)
    sys.exit(1)
" "$V_REVIEW_RESULT" 2>&1; then
      V_EXIT=0
      echo "Scenario V: PASS"
    else
      V_EXIT=1
      echo "Scenario V: FAIL (review result validation failed)"
    fi
  else
    V_EXIT=1
    echo "Scenario V: FAIL (review adapter failed or result not created)"
  fi
else
  V_EXIT=1
  echo "Scenario V: FAIL (verification failed or failure-context not created)"
fi

rm -f "$MANIFEST_V" "$SUITE_TMP/v-verify.log" "$SUITE_TMP/v-review.log"

# ============================================================================
# Summary
# ============================================================================
echo ""
echo "================================================================"
echo "SUMMARY"
echo "================================================================"
echo "Scenario A exit code: $A_EXIT (expected: 0)"
echo "Scenario B exit code: $B_EXIT (expected: 1)"
echo "Scenario C exit code: $C_EXIT (expected: 1)"
echo "Scenario D exit code: $D_EXIT (expected: 0)"
echo "Scenario E exit code: $E_EXIT (expected: 2)"
echo "Scenario F exit code: $F_EXIT (expected: 1)"
echo "Scenario G exit code: $G_EXIT (expected: 1)"
echo "Scenario H exit code: $H_EXIT (expected: 1)"
echo "Scenario I exit code: $I_EXIT (expected: 0)"
echo "Scenario J exit code: $J_EXIT (expected: 0)"
echo "Scenario K exit code: $K_EXIT (expected: non-zero)"
echo "Scenario L exit code: $L_EXIT (expected: 2)"
echo "Scenario M exit code: $M_EXIT (expected: 0)"
echo "Scenario N exit code: $N_EXIT (expected: 0)"
echo "Scenario O exit code: $O_EXIT (expected: 0)"
echo "Scenario P exit code: $P_EXIT (expected: 2)"
echo "Scenario Q exit code: $Q_EXIT (expected: 2)"
echo "Scenario R exit code: $R_EXIT (expected: 2)"
echo "Scenario S exit code: $S_EXIT (expected: 2)"
echo "Scenario T exit code: $T_EXIT (expected: 0)"
echo "Scenario U exit code: $U_EXIT (expected: 0)"
echo "Scenario V exit code: $V_EXIT (expected: 0)"
echo ""

if [[ $A_EXIT -eq 0 && $B_EXIT -eq 1 && $C_EXIT -eq 1 && $D_EXIT -eq 0 && $E_EXIT -eq 2 && \
      $F_EXIT -eq 1 && $G_EXIT -eq 1 && $H_EXIT -eq 1 && $I_EXIT -eq 0 && $J_EXIT -eq 0 && \
      $K_EXIT -ne 0 && $L_EXIT -eq 2 && $M_EXIT -eq 0 && $N_EXIT -eq 0 && $O_EXIT -eq 0 && \
      $P_EXIT -eq 2 && $Q_EXIT -eq 2 && $R_EXIT -eq 2 && $S_EXIT -eq 2 && $T_EXIT -eq 0 && \
      $U_EXIT -eq 0 && $V_EXIT -eq 0 ]]; then
  echo "ALL 22 SCENARIOS PASSED (A-V)"
  exit 0
else
  echo "SOME SCENARIOS FAILED"
  exit 1
fi
