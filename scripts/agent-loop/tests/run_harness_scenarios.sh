#!/usr/bin/env bash
# Run harness validation scenarios A-E
# Creates synthetic test files in backend/tests/synthetic/ as needed,
# runs verify-story.sh, then cleans up synthetic files.
#
# Scenario A: test file exists, passes -> PASS, exit 0
# Scenario B: test file missing -> FAIL, exit 1
# Scenario C: all tests skipped -> FAIL, exit 1
# Scenario D: real passing tests -> PASS, exit 0
# Scenario E: broken JSON manifest -> ERROR, exit 2

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
  
  "$PYTHON_BIN" -c "
import json, sys
manifest = {
    'story_id': sys.argv[1],
    'title': 'Harness Validation Scenario',
    'description': 'Synthetic test',
    'branch': 'chore/agent-loop-infrastructure',
    'gates': {
        'scope': {'required': True, 'enabled': True},
        'json_syntax': {'required': True, 'enabled': True},
        'targeted_tests': {'required': True, 'enabled': True, 'assertion_gate': True},
        'lint': {'required': True, 'enabled': True, 'scope_to_diff': True},
        'secrets': {'required': True, 'enabled': True, 'scope_to_diff': True},
        'git_diff_check': {'required': False, 'enabled': True}
    },
    'test_commands': {
        'targeted_args': sys.argv[2]
    }
}
with open(sys.argv[3], 'w') as f:
    json.dump(manifest, f, indent=2)
" "$story_id" "$targeted_args" "$output_file"
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
# Do NOT create any test file — it must be missing
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

echo ""
echo "================================================================"
echo "SUMMARY"
echo "================================================================"
echo "Scenario A exit code: $A_EXIT (expected: 0)"
echo "Scenario B exit code: $B_EXIT (expected: 1)"
echo "Scenario C exit code: $C_EXIT (expected: 1)"
echo "Scenario D exit code: $D_EXIT (expected: 0)"
echo "Scenario E exit code: $E_EXIT (expected: 2)"
echo ""

if [[ $A_EXIT -eq 0 && $B_EXIT -eq 1 && $C_EXIT -eq 1 && $D_EXIT -eq 0 && $E_EXIT -eq 2 ]]; then
  echo "ALL SCENARIOS PASSED"
  exit 0
else
  echo "SOME SCENARIOS FAILED"
  exit 1
fi
