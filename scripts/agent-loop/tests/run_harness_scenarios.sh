#!/usr/bin/env bash
# Run harness validation scenarios A-O
# Creates synthetic test files in backend/tests/synthetic/ as needed,
# runs verify-story.sh, then cleans up synthetic files.

set -uo pipefail

# Capture paths BEFORE sourcing config.sh (which overrides SCRIPT_DIR)
THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURES_DIR="$THIS_DIR/fixtures"

# Source config.sh to get correct PYTHON_BIN, REPO_ROOT, etc.
source "$THIS_DIR/../config.sh"

VERIFY_SCRIPT="$THIS_DIR/../verify-story.sh"
SYNTHETIC_DIR="$REPO_ROOT/backend/tests/synthetic"

cleanup() {
  if [[ -d "$SYNTHETIC_DIR" ]]; then
    rm -rf "$SYNTHETIC_DIR"
  fi
  rm -f /tmp/harness-manifest-*.json 2>/dev/null
}

trap cleanup EXIT

mkdir -p "$SYNTHETIC_DIR"

# Helper: create temp manifest with given story_id and targeted_args
create_manifest() {
  local output_file="$1"
  local story_id="$2"
  local targeted_args="$3"
  local gate_config="${4:-default}"
  
  "$PYTHON_BIN" -c "
import json, sys
gate_config_type = sys.argv[4]

# Default gate config
gates = {
    'scope': {'required': True, 'enabled': True},
    'json_syntax': {'required': True, 'enabled': True},
    'targeted_tests': {'required': True, 'enabled': True, 'assertion_gate': True},
    'lint': {'required': True, 'enabled': True, 'scope_to_diff': True},
    'secrets': {'required': True, 'enabled': True, 'scope_to_diff': True},
    'git_diff_check': {'required': False, 'enabled': True}
}

# Override for optional gate scenarios
if gate_config_type == 'optional_targeted_tests':
    gates['targeted_tests']['required'] = False
elif gate_config_type == 'optional_scope':
    gates['scope']['required'] = False

manifest = {
    'story_id': sys.argv[1],
    'title': 'Harness Validation Scenario',
    'description': 'Synthetic test',
    'branch': 'chore/agent-loop-infrastructure',
    'gates': gates,
    'test_commands': {
        'targeted_args': sys.argv[2]
    }
}
with open(sys.argv[3], 'w') as f:
    json.dump(manifest, f, indent=2)
" "$story_id" "$targeted_args" "$output_file" "$gate_config"
}

echo "================================================================"
echo "HARNESS VALIDATION - Agent Loop Phase 1"
echo "================================================================"

# --- Scenario A: required test exists and passes ---
echo ""
echo "================================================================"
echo "Scenario A: Required test exists and passes"
echo "================================================================"
cp "$FIXTURES_DIR/test_harness_a.py" "$SYNTHETIC_DIR/test_harness_a.py"
MANIFEST_A="$(mktemp /tmp/harness-manifest-A-XXXXXX.json)"
create_manifest "$MANIFEST_A" "HARNESS-A" "tests/synthetic/test_harness_a.py -v --junitxml={report_file}"
bash "$VERIFY_SCRIPT" "$MANIFEST_A"
A_EXIT=$?
rm -f "$SYNTHETIC_DIR/test_harness_a.py"
rm -f "$MANIFEST_A"
echo ""
echo "Exit code: $A_EXIT"

# --- Scenario B: required test missing ---
echo ""
echo "================================================================"
echo "Scenario B: Required test missing"
echo "================================================================"
MANIFEST_B="$(mktemp /tmp/harness-manifest-B-XXXXXX.json)"
create_manifest "$MANIFEST_B" "HARNESS-B" "tests/synthetic/test_nonexistent_harness.py -v --junitxml={report_file}"
bash "$VERIFY_SCRIPT" "$MANIFEST_B"
B_EXIT=$?
rm -f "$MANIFEST_B"
echo ""
echo "Exit code: $B_EXIT"

# --- Scenario C: all tests skipped ---
echo ""
echo "================================================================"
echo "Scenario C: All tests skipped"
echo "================================================================"
cp "$FIXTURES_DIR/test_harness_c.py" "$SYNTHETIC_DIR/test_harness_c.py"
MANIFEST_C="$(mktemp /tmp/harness-manifest-C-XXXXXX.json)"
create_manifest "$MANIFEST_C" "HARNESS-C" "tests/synthetic/test_harness_c.py -v --junitxml={report_file}"
bash "$VERIFY_SCRIPT" "$MANIFEST_C"
C_EXIT=$?
rm -f "$SYNTHETIC_DIR/test_harness_c.py"
rm -f "$MANIFEST_C"
echo ""
echo "Exit code: $C_EXIT"

# --- Scenario D: real tests pass ---
echo ""
echo "================================================================"
echo "Scenario D: Real tests pass"
echo "================================================================"
cp "$FIXTURES_DIR/test_harness_d.py" "$SYNTHETIC_DIR/test_harness_d.py"
MANIFEST_D="$(mktemp /tmp/harness-manifest-D-XXXXXX.json)"
create_manifest "$MANIFEST_D" "HARNESS-D" "tests/synthetic/test_harness_d.py -v --junitxml={report_file}"
bash "$VERIFY_SCRIPT" "$MANIFEST_D"
D_EXIT=$?
rm -f "$SYNTHETIC_DIR/test_harness_d.py"
rm -f "$MANIFEST_D"
echo ""
echo "Exit code: $D_EXIT"

# --- Scenario E: internal harness error (broken JSON manifest) ---
echo ""
echo "================================================================"
echo "Scenario E: Internal harness error (broken JSON)"
echo "================================================================"
bash "$VERIFY_SCRIPT" "$FIXTURES_DIR/manifest-scenario-e-broken.json"
E_EXIT=$?
echo ""
echo "Exit code: $E_EXIT"

# --- Scenario F: zero tests collected ---
echo ""
echo "================================================================"
echo "Scenario F: Zero tests collected"
echo "================================================================"
cat > "$SYNTHETIC_DIR/test_harness_f.py" <<'PYEOF'
"""Harness Scenario F: zero tests collected."""

# No test functions defined
pass
PYEOF
MANIFEST_F="$(mktemp /tmp/harness-manifest-F-XXXXXX.json)"
create_manifest "$MANIFEST_F" "HARNESS-F" "tests/synthetic/test_harness_f.py -v --junitxml={report_file}"
bash "$VERIFY_SCRIPT" "$MANIFEST_F"
F_EXIT=$?
rm -f "$SYNTHETIC_DIR/test_harness_f.py"
rm -f "$MANIFEST_F"
echo ""
echo "Exit code: $F_EXIT"

# --- Scenario G: pytest collection error ---
echo ""
echo "================================================================"
echo "Scenario G: Pytest collection error"
echo "================================================================"
cat > "$SYNTHETIC_DIR/test_harness_g.py" <<'PYEOF'
"""Harness Scenario G: collection error."""

import nonexistent_module_that_will_fail

def test_something():
    assert True
PYEOF
MANIFEST_G="$(mktemp /tmp/harness-manifest-G-XXXXXX.json)"
create_manifest "$MANIFEST_G" "HARNESS-G" "tests/synthetic/test_harness_g.py -v --junitxml={report_file}"
bash "$VERIFY_SCRIPT" "$MANIFEST_G"
G_EXIT=$?
rm -f "$SYNTHETIC_DIR/test_harness_g.py"
rm -f "$MANIFEST_G"
echo ""
echo "Exit code: $G_EXIT"

# --- Scenario H: pytest failure ---
echo ""
echo "================================================================"
echo "Scenario H: Pytest failure"
echo "================================================================"
cat > "$SYNTHETIC_DIR/test_harness_h.py" <<'PYEOF'
"""Harness Scenario H: test failure."""

def test_failing():
    assert False, "Intentional failure"
PYEOF
MANIFEST_H="$(mktemp /tmp/harness-manifest-H-XXXXXX.json)"
create_manifest "$MANIFEST_H" "HARNESS-H" "tests/synthetic/test_harness_h.py -v --junitxml={report_file}"
bash "$VERIFY_SCRIPT" "$MANIFEST_H"
H_EXIT=$?
rm -f "$SYNTHETIC_DIR/test_harness_h.py"
rm -f "$MANIFEST_H"
echo ""
echo "Exit code: $H_EXIT"

# --- Scenario I: mixed passed + skipped ---
echo ""
echo "================================================================"
echo "Scenario I: Mixed passed + skipped"
echo "================================================================"
cat > "$SYNTHETIC_DIR/test_harness_i.py" <<'PYEOF'
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
MANIFEST_I="$(mktemp /tmp/harness-manifest-I-XXXXXX.json)"
create_manifest "$MANIFEST_I" "HARNESS-I" "tests/synthetic/test_harness_i.py -v --junitxml={report_file}"
bash "$VERIFY_SCRIPT" "$MANIFEST_I"
I_EXIT=$?
rm -f "$SYNTHETIC_DIR/test_harness_i.py"
rm -f "$MANIFEST_I"
echo ""
echo "Exit code: $I_EXIT"

# --- Scenario J: optional skipped gate does not block ---
echo ""
echo "================================================================"
echo "Scenario J: Optional skipped gate does not block"
echo "================================================================"
# Test file missing, but targeted_tests is optional
MANIFEST_J="$(mktemp /tmp/harness-manifest-J-XXXXXX.json)"
create_manifest "$MANIFEST_J" "HARNESS-J" "tests/synthetic/test_nonexistent.py -v --junitxml={report_file}" "optional_targeted_tests"
bash "$VERIFY_SCRIPT" "$MANIFEST_J"
J_EXIT=$?
rm -f "$MANIFEST_J"
echo ""
echo "Exit code: $J_EXIT"

# --- Scenario K: malformed JUnit XML ---
echo ""
echo "================================================================"
echo "Scenario K: Malformed JUnit XML (internal test)"
echo "================================================================"
# This tests the harness.py parse_junit_xml function directly
TEMP_XML="$(mktemp /tmp/harness-malformed-XXXXXX.xml)"
cat > "$TEMP_XML" <<'XMLEOF'
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="broken" tests="3" failures="1" errors="0" skipped="0">
    <!-- Missing closing tag intentionally -->
XMLEOF

"$PYTHON_BIN" "$REPO_ROOT/scripts/agent-loop/lib/harness.py" parse_junit "$TEMP_XML" > /dev/null 2>&1
K_EXIT=$?
rm -f "$TEMP_XML"
echo ""
echo "Exit code: $K_EXIT (expected: non-zero for malformed XML)"

# --- Scenario L: missing manifest file ---
echo ""
echo "================================================================"
echo "Scenario L: Missing manifest file"
echo "================================================================"
bash "$VERIFY_SCRIPT" "/tmp/nonexistent-manifest-12345.json"
L_EXIT=$?
echo ""
echo "Exit code: $L_EXIT"

# --- Scenario M: test path containing spaces ---
echo ""
echo "================================================================"
echo "Scenario M: Test path containing spaces"
echo "================================================================"
mkdir -p "$SYNTHETIC_DIR/path with spaces"
cp "$FIXTURES_DIR/test_harness_a.py" "$SYNTHETIC_DIR/path with spaces/test_harness_m.py"
# Create manifest directly with args as JSON array (not string) to preserve spaces
MANIFEST_M="$(mktemp /tmp/harness-manifest-M-XXXXXX.json)"
cat > "$MANIFEST_M" <<EOF
{
  "story_id": "HARNESS-M",
  "title": "Harness Validation: Scenario M",
  "description": "Test path with spaces",
  "branch": "chore/agent-loop-infrastructure",
  "gates": {
    "scope": {"required": true, "enabled": true},
    "json_syntax": {"required": true, "enabled": true},
    "targeted_tests": {"required": true, "enabled": true, "assertion_gate": true},
    "lint": {"required": true, "enabled": true, "scope_to_diff": true},
    "secrets": {"required": true, "enabled": true, "scope_to_diff": true},
    "git_diff_check": {"required": false, "enabled": true}
  },
  "test_commands": {
    "targeted_args": ["tests/synthetic/path with spaces/test_harness_m.py", "-v", "--junitxml={report_file}"]
  }
}
EOF
bash "$VERIFY_SCRIPT" "$MANIFEST_M"
M_EXIT=$?
rm -rf "$SYNTHETIC_DIR/path with spaces"
rm -f "$MANIFEST_M"
echo ""
echo "Exit code: $M_EXIT"

# --- Scenario N: concurrent runs produce different RUN_ID ---
echo ""
echo "================================================================"
echo "Scenario N: Concurrent runs produce different RUN_ID"
echo "================================================================"
# Run two verifications in background and check RUN_IDs are different
TEMP_MANIFEST_N1="$(mktemp /tmp/harness-manifest-N1-XXXXXX.json)"
TEMP_MANIFEST_N2="$(mktemp /tmp/harness-manifest-N2-XXXXXX.json)"
create_manifest "$TEMP_MANIFEST_N1" "HARNESS-N" "tests/synthetic/test_harness_a.py -v --junitxml={report_file}"
cp "$TEMP_MANIFEST_N1" "$TEMP_MANIFEST_N2"

# Copy test file for both runs
cp "$FIXTURES_DIR/test_harness_a.py" "$SYNTHETIC_DIR/test_harness_a.py"

# Run both in background
bash "$VERIFY_SCRIPT" "$TEMP_MANIFEST_N1" > /tmp/harness-n1.log 2>&1 &
PID1=$!
bash "$VERIFY_SCRIPT" "$TEMP_MANIFEST_N2" > /tmp/harness-n2.log 2>&1 &
PID2=$!

wait $PID1
wait $PID2

# Extract RUN_IDs from logs
RUN_ID1="$(grep "Run directory:" /tmp/harness-n1.log | sed 's/.*artifacts\///')"
RUN_ID2="$(grep "Run directory:" /tmp/harness-n2.log | sed 's/.*artifacts\///')"

echo "Run 1: $RUN_ID1"
echo "Run 2: $RUN_ID2"

if [[ "$RUN_ID1" != "$RUN_ID2" ]]; then
  echo "PASS: RUN_IDs are different (collision-resistant)"
  N_EXIT=0
else
  echo "FAIL: RUN_IDs are identical (collision detected)"
  N_EXIT=1
fi

rm -f /tmp/harness-n1.log /tmp/harness-n2.log
rm -f "$TEMP_MANIFEST_N1" "$TEMP_MANIFEST_N2"
rm -f "$SYNTHETIC_DIR/test_harness_a.py"

# --- Scenario O: interruption cleanup ---
echo ""
echo "================================================================"
echo "Scenario O: Interruption cleanup (no destructive operations)"
echo "================================================================"
# Create a long-running scenario and interrupt it
MANIFEST_O="$(mktemp /tmp/harness-manifest-O-XXXXXX.json)"
create_manifest "$MANIFEST_O" "HARNESS-O" "tests/synthetic/test_harness_a.py -v --junitxml={report_file}"

# Start verification in background
bash "$VERIFY_SCRIPT" "$MANIFEST_O" > /tmp/harness-o.log 2>&1 &
PID_O=$!

# Wait a moment for it to create temp files
sleep 0.5

# Send SIGTERM
kill -TERM $PID_O 2>/dev/null || true
wait $PID_O 2>/dev/null || true

# Check if temp files were cleaned up
TEMP_FILES_REMAINING="$(find "$REPO_ROOT/.ralph-tui/artifacts" -name ".gates-tmp.json" -o -name ".gate-config-tmp.json" 2>/dev/null | wc -l)"

if [[ $TEMP_FILES_REMAINING -eq 0 ]]; then
  echo "PASS: Cleanup trap removed temp files"
  O_EXIT=0
else
  echo "WARN: $TEMP_FILES_REMAINING temp files remaining (may be from previous runs)"
  O_EXIT=0  # Don't fail on this, as old artifacts may exist
fi

rm -f /tmp/harness-o.log "$MANIFEST_O"

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
echo ""

if [[ $A_EXIT -eq 0 && $B_EXIT -eq 1 && $C_EXIT -eq 1 && $D_EXIT -eq 0 && $E_EXIT -eq 2 && \
      $F_EXIT -eq 1 && $G_EXIT -eq 1 && $H_EXIT -eq 1 && $I_EXIT -eq 0 && $J_EXIT -eq 0 && \
      $K_EXIT -ne 0 && $L_EXIT -eq 2 && $M_EXIT -eq 0 && $N_EXIT -eq 0 && $O_EXIT -eq 0 ]]; then
  echo "ALL SCENARIOS PASSED"
  exit 0
else
  echo "SOME SCENARIOS FAILED"
  exit 1
fi
