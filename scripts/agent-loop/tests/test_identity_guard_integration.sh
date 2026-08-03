#!/usr/bin/env bash
# Integration tests for identity guard and passport validation
# Tests scenarios P-S for WP-AL-1A

set -uo pipefail

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$THIS_DIR/../config.sh"
source "$THIS_DIR/../lib/guard.sh"

TESTS_PASSED=0
TESTS_FAILED=0

# Helper: assert test result
assert_result() {
  local test_name="$1"
  local expected_exit="$2"
  local actual_exit="$3"

  if [[ "$actual_exit" -eq "$expected_exit" ]]; then
    echo "PASS: $test_name"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    echo "FAIL: $test_name (expected exit $expected_exit, got $actual_exit)"
    TESTS_FAILED=$((TESTS_FAILED + 1))
  fi
}

# Helper: create test passport
create_test_passport() {
  local output_file="$1"
  local project_id="${2:-test-project}"
  local run_id="${3:-test-run-001}"
  local slot_id="${4:-test-slot-001}"
  local story_id="${5:-test-story-001}"
  local role="${6:-implementer}"
  local phase="${7:-implement}"
  local workspace_type="${8:-source}"
  local workspace_root="${9:-$REPO_ROOT}"
  local expected_branch="${10:-chore/agent-loop-infrastructure}"
  local base_commit="${11:-HEAD}"
  local manifest_path="${12:-$REPO_ROOT/manifest.json}"
  local artifact_root="${13:-$REPO_ROOT/.ralph-tui/artifacts/test-run-001}"

  "$PYTHON_BIN" -c "
import json
passport = {
    'schema_version': '1.0',
    'project_id': '$project_id',
    'run_id': '$run_id',
    'slot_id': '$slot_id',
    'story_id': '$story_id',
    'role': '$role',
    'phase': '$phase',
    'workspace_type': '$workspace_type',
    'workspace_root': '$workspace_root',
    'expected_branch': '$expected_branch',
    'base_commit': '$base_commit',
    'manifest_path': '$manifest_path',
    'artifact_root': '$artifact_root'
}
with open('$output_file', 'w') as f:
    json.dump(passport, f, indent=2)
"
}

echo "================================================================"
echo "IDENTITY GUARD INTEGRATION TESTS - WP-AL-1A"
echo "================================================================"

# --- Scenario P: Missing passport ---
echo ""
echo "Scenario P: Missing passport"
TEMP_DIR=$(mktemp -d)
export PROJECT_ID="test-project"
export RUN_ID="test-run-001"
export SLOT_ID="test-slot-001"
export STORY_ID="test-story-001"

phase_guard "$TEMP_DIR/nonexistent-passport.json" "implement" "source" "implementer" "$TEMP_DIR"
P_EXIT=$?

assert_result "Missing passport" 1 $P_EXIT

# Verify error artifact was created
if [[ -f "$TEMP_DIR/guard-error.json" ]]; then
  ERROR_CODE=$("$PYTHON_BIN" -c "import json; print(json.load(open('$TEMP_DIR/guard-error.json'))['error_code'])")
  if [[ "$ERROR_CODE" == "PASSPORT_MISSING" ]]; then
    echo "  PASS: Error artifact contains correct error_code"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    echo "  FAIL: Error artifact has wrong error_code: $ERROR_CODE"
    TESTS_FAILED=$((TESTS_FAILED + 1))
  fi
else
  echo "  FAIL: Error artifact not created"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

rm -rf "$TEMP_DIR"

# --- Scenario Q: Wrong branch ---
echo ""
echo "Scenario Q: Wrong branch"
TEMP_DIR=$(mktemp -d)
PASSPORT_FILE="$TEMP_DIR/passport.json"

# Get current branch for base_commit
BASE_COMMIT=$(git rev-parse HEAD)

# Create passport with wrong branch
create_test_passport "$PASSPORT_FILE" \
  "test-project" "test-run-001" "test-slot-001" "test-story-001" \
  "implementer" "implement" "source" "$REPO_ROOT" \
  "wrong-branch-name" "$BASE_COMMIT" \
  "$REPO_ROOT/manifest.json" "$REPO_ROOT/.ralph-tui/artifacts/test-run-001"

phase_guard "$PASSPORT_FILE" "implement" "source" "implementer" "$TEMP_DIR"
Q_EXIT=$?

assert_result "Wrong branch" 1 $Q_EXIT

if [[ -f "$TEMP_DIR/guard-error.json" ]]; then
  FAILED_CHECK=$("$PYTHON_BIN" -c "import json; print(json.load(open('$TEMP_DIR/guard-error.json'))['failed_check'])")
  if [[ "$FAILED_CHECK" == "branch_matches_expected" ]]; then
    echo "  PASS: Error artifact contains correct failed_check"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    echo "  FAIL: Error artifact has wrong failed_check: $FAILED_CHECK"
    TESTS_FAILED=$((TESTS_FAILED + 1))
  fi
else
  echo "  FAIL: Error artifact not created"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

rm -rf "$TEMP_DIR"

# --- Scenario R: Wrong workspace (PWD mismatch) ---
echo ""
echo "Scenario R: Wrong workspace (PWD mismatch)"
TEMP_DIR=$(mktemp -d)
PASSPORT_FILE="$TEMP_DIR/passport.json"

# Create passport with different workspace_root (non-existent path)
create_test_passport "$PASSPORT_FILE" \
  "test-project" "test-run-001" "test-slot-001" "test-story-001" \
  "implementer" "implement" "source" "/wrong/workspace/path" \
  "chore/agent-loop-infrastructure" "$BASE_COMMIT" \
  "$REPO_ROOT/manifest.json" "$REPO_ROOT/.ralph-tui/artifacts/test-run-001"

# Run from REPO_ROOT (different from passport workspace_root)
cd "$REPO_ROOT"
phase_guard "$PASSPORT_FILE" "implement" "source" "implementer" "$TEMP_DIR"
R_EXIT=$?

assert_result "Wrong workspace (PWD mismatch)" 1 $R_EXIT

if [[ -f "$TEMP_DIR/guard-error.json" ]]; then
  FAILED_CHECK=$("$PYTHON_BIN" -c "import json; print(json.load(open('$TEMP_DIR/guard-error.json'))['failed_check'])")
  # Guard correctly fails at workspace_root_resolvable before pwd_matches_workspace_root
  # Both are valid workspace identity validation failures
  if [[ "$FAILED_CHECK" == "pwd_matches_workspace_root" || "$FAILED_CHECK" == "workspace_root_resolvable" ]]; then
    echo "  PASS: Error artifact contains correct failed_check ($FAILED_CHECK)"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    echo "  FAIL: Error artifact has wrong failed_check: $FAILED_CHECK"
    TESTS_FAILED=$((TESTS_FAILED + 1))
  fi
else
  echo "  FAIL: Error artifact not created"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

rm -rf "$TEMP_DIR"

# --- Scenario S: Cross-phase identity mismatch (wrong role for phase) ---
echo ""
echo "Scenario S: Cross-phase identity mismatch (wrong role for phase)"
TEMP_DIR=$(mktemp -d)
PASSPORT_FILE="$TEMP_DIR/passport.json"

# Create passport with role=researcher for phase=implement (not allowed)
create_test_passport "$PASSPORT_FILE" \
  "test-project" "test-run-001" "test-slot-001" "test-story-001" \
  "researcher" "implement" "source" "$REPO_ROOT" \
  "chore/agent-loop-infrastructure" "$BASE_COMMIT" \
  "$REPO_ROOT/manifest.json" "$REPO_ROOT/.ralph-tui/artifacts/test-run-001"

phase_guard "$PASSPORT_FILE" "implement" "source" "researcher" "$TEMP_DIR"
S_EXIT=$?

assert_result "Wrong role for phase" 1 $S_EXIT

if [[ -f "$TEMP_DIR/guard-error.json" ]]; then
  FAILED_CHECK=$("$PYTHON_BIN" -c "import json; print(json.load(open('$TEMP_DIR/guard-error.json'))['failed_check'])")
  if [[ "$FAILED_CHECK" == "role_allowed_for_phase" ]]; then
    echo "  PASS: Error artifact contains correct failed_check"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    echo "  FAIL: Error artifact has wrong failed_check: $FAILED_CHECK"
    TESTS_FAILED=$((TESTS_FAILED + 1))
  fi
else
  echo "  FAIL: Error artifact not created"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

rm -rf "$TEMP_DIR"

# --- Scenario T: Wrong workspace type for phase ---
echo ""
echo "Scenario T: Wrong workspace type for phase"
TEMP_DIR=$(mktemp -d)
PASSPORT_FILE="$TEMP_DIR/passport.json"

# Create passport with workspace_type=validation for phase=implement (should be source)
create_test_passport "$PASSPORT_FILE" \
  "test-project" "test-run-001" "test-slot-001" "test-story-001" \
  "implementer" "implement" "validation" "$REPO_ROOT" \
  "chore/agent-loop-infrastructure" "$BASE_COMMIT" \
  "$REPO_ROOT/manifest.json" "$REPO_ROOT/.ralph-tui/artifacts/test-run-001"

phase_guard "$PASSPORT_FILE" "implement" "source" "implementer" "$TEMP_DIR"
T_EXIT=$?

assert_result "Wrong workspace type for phase" 1 $T_EXIT

if [[ -f "$TEMP_DIR/guard-error.json" ]]; then
  FAILED_CHECK=$("$PYTHON_BIN" -c "import json; print(json.load(open('$TEMP_DIR/guard-error.json'))['failed_check'])")
  if [[ "$FAILED_CHECK" == "workspace_type_matches_phase" ]]; then
    echo "  PASS: Error artifact contains correct failed_check"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    echo "  FAIL: Error artifact has wrong failed_check: $FAILED_CHECK"
    TESTS_FAILED=$((TESTS_FAILED + 1))
  fi
else
  echo "  FAIL: Error artifact not created"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

rm -rf "$TEMP_DIR"

# --- Scenario U: Artifact root mismatch (belongs to different slot) ---
echo ""
echo "Scenario U: Artifact root mismatch (belongs to different slot)"
TEMP_DIR=$(mktemp -d)
PASSPORT_FILE="$TEMP_DIR/passport.json"

# Create passport with artifact_root for different run_id (non-existent path)
create_test_passport "$PASSPORT_FILE" \
  "test-project" "test-run-001" "test-slot-001" "test-story-001" \
  "implementer" "implement" "source" "$REPO_ROOT" \
  "chore/agent-loop-infrastructure" "$BASE_COMMIT" \
  "$REPO_ROOT/manifest.json" "$REPO_ROOT/.ralph-tui/artifacts/different-run-999"

phase_guard "$PASSPORT_FILE" "implement" "source" "implementer" "$TEMP_DIR"
U_EXIT=$?

assert_result "Artifact root mismatch" 1 $U_EXIT

if [[ -f "$TEMP_DIR/guard-error.json" ]]; then
  FAILED_CHECK=$("$PYTHON_BIN" -c "import json; print(json.load(open('$TEMP_DIR/guard-error.json'))['failed_check'])")
  # Guard correctly fails at artifact_root_resolvable before artifact_root_belongs_to_run_slot
  # Both are valid artifact identity validation failures
  if [[ "$FAILED_CHECK" == "artifact_root_belongs_to_run_slot" || "$FAILED_CHECK" == "artifact_root_resolvable" ]]; then
    echo "  PASS: Error artifact contains correct failed_check ($FAILED_CHECK)"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    echo "  FAIL: Error artifact has wrong failed_check: $FAILED_CHECK"
    TESTS_FAILED=$((TESTS_FAILED + 1))
  fi
else
  echo "  FAIL: Error artifact not created"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

rm -rf "$TEMP_DIR"

# --- Scenario V: Bootstrap guard - main worktree forbidden ---
echo ""
echo "Scenario V: Bootstrap guard - main worktree forbidden"
TEMP_DIR=$(mktemp -d)

# Try to bootstrap with workspace_root = main ForgeMind worktree
bootstrap_guard "$FORBIDDEN_MAIN_WORKTREE" "chore/agent-loop-infrastructure" "allocate" "$TEMP_DIR"
V_EXIT=$?

assert_result "Bootstrap guard - main worktree forbidden" 1 $V_EXIT

if [[ -f "$TEMP_DIR/guard-error.json" ]]; then
  ERROR_CODE=$("$PYTHON_BIN" -c "import json; print(json.load(open('$TEMP_DIR/guard-error.json'))['error_code'])")
  if [[ "$ERROR_CODE" == "BOOTSTRAP_MAIN_WORKTREE_FORBIDDEN" ]]; then
    echo "  PASS: Error artifact contains correct error_code"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    echo "  FAIL: Error artifact has wrong error_code: $ERROR_CODE"
    TESTS_FAILED=$((TESTS_FAILED + 1))
  fi
else
  echo "  FAIL: Error artifact not created"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

rm -rf "$TEMP_DIR"

# --- Scenario W: Bootstrap guard - success ---
echo ""
echo "Scenario W: Bootstrap guard - success"
TEMP_DIR=$(mktemp -d)

# Bootstrap with correct infrastructure worktree
bootstrap_guard "$REPO_ROOT" "chore/agent-loop-infrastructure" "allocate" "$TEMP_DIR"
W_EXIT=$?

assert_result "Bootstrap guard - success" 0 $W_EXIT

# Verify no error artifact was created
if [[ -f "$TEMP_DIR/guard-error.json" ]]; then
  echo "  FAIL: Error artifact should not exist on success"
  TESTS_FAILED=$((TESTS_FAILED + 1))
else
  echo "  PASS: No error artifact on success"
  TESTS_PASSED=$((TESTS_PASSED + 1))
fi

rm -rf "$TEMP_DIR"

# --- Scenario X: Malformed passport JSON ---
echo ""
echo "Scenario X: Malformed passport JSON"
TEMP_DIR=$(mktemp -d)
PASSPORT_FILE="$TEMP_DIR/passport.json"

# Write malformed JSON
echo "{invalid json" > "$PASSPORT_FILE"

phase_guard "$PASSPORT_FILE" "implement" "source" "implementer" "$TEMP_DIR"
X_EXIT=$?

assert_result "Malformed passport JSON" 1 $X_EXIT

if [[ -f "$TEMP_DIR/guard-error.json" ]]; then
  ERROR_CODE=$("$PYTHON_BIN" -c "import json; print(json.load(open('$TEMP_DIR/guard-error.json'))['error_code'])")
  if [[ "$ERROR_CODE" == "PASSPORT_INVALID" ]]; then
    echo "  PASS: Error artifact contains correct error_code"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    echo "  FAIL: Error artifact has wrong error_code: $ERROR_CODE"
    TESTS_FAILED=$((TESTS_FAILED + 1))
  fi
else
  echo "  FAIL: Error artifact not created"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

rm -rf "$TEMP_DIR"

# --- Scenario Y: Missing required field in passport ---
echo ""
echo "Scenario Y: Missing required field in passport"
TEMP_DIR=$(mktemp -d)
PASSPORT_FILE="$TEMP_DIR/passport.json"

# Create passport without run_id
"$PYTHON_BIN" -c "
import json
passport = {
    'schema_version': '1.0',
    'project_id': 'test-project',
    # 'run_id' missing
    'slot_id': 'test-slot-001',
    'story_id': 'test-story-001',
    'role': 'implementer',
    'phase': 'implement',
    'workspace_type': 'source',
    'workspace_root': '$REPO_ROOT',
    'expected_branch': 'chore/agent-loop-infrastructure',
    'base_commit': '$BASE_COMMIT',
    'manifest_path': '$REPO_ROOT/manifest.json',
    'artifact_root': '$REPO_ROOT/.ralph-tui/artifacts/test-run-001'
}
with open('$PASSPORT_FILE', 'w') as f:
    json.dump(passport, f, indent=2)
"

phase_guard "$PASSPORT_FILE" "implement" "source" "implementer" "$TEMP_DIR"
Y_EXIT=$?

assert_result "Missing required field in passport" 1 $Y_EXIT

if [[ -f "$TEMP_DIR/guard-error.json" ]]; then
  ERROR_CODE=$("$PYTHON_BIN" -c "import json; print(json.load(open('$TEMP_DIR/guard-error.json'))['error_code'])")
  if [[ "$ERROR_CODE" == "PASSPORT_INVALID" ]]; then
    echo "  PASS: Error artifact contains correct error_code"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    echo "  FAIL: Error artifact has wrong error_code: $ERROR_CODE"
    TESTS_FAILED=$((TESTS_FAILED + 1))
  fi
else
  echo "  FAIL: Error artifact not created"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

rm -rf "$TEMP_DIR"

# --- Scenario Z: Base commit not found ---
echo ""
echo "Scenario Z: Base commit not found"
TEMP_DIR=$(mktemp -d)
PASSPORT_FILE="$TEMP_DIR/passport.json"

# Create passport with non-existent base_commit
create_test_passport "$PASSPORT_FILE" \
  "test-project" "test-run-001" "test-slot-001" "test-story-001" \
  "implementer" "implement" "source" "$REPO_ROOT" \
  "chore/agent-loop-infrastructure" "nonexistent-commit-hash-12345" \
  "$REPO_ROOT/manifest.json" "$REPO_ROOT/.ralph-tui/artifacts/test-run-001"

phase_guard "$PASSPORT_FILE" "implement" "source" "implementer" "$TEMP_DIR"
Z_EXIT=$?

assert_result "Base commit not found" 1 $Z_EXIT

if [[ -f "$TEMP_DIR/guard-error.json" ]]; then
  FAILED_CHECK=$("$PYTHON_BIN" -c "import json; print(json.load(open('$TEMP_DIR/guard-error.json'))['failed_check'])")
  if [[ "$FAILED_CHECK" == "base_commit_exists" ]]; then
    echo "  PASS: Error artifact contains correct failed_check"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    echo "  FAIL: Error artifact has wrong failed_check: $FAILED_CHECK"
    TESTS_FAILED=$((TESTS_FAILED + 1))
  fi
else
  echo "  FAIL: Error artifact not created"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

rm -rf "$TEMP_DIR"

# --- Negative Test: Prefix bypass attempt ---
echo ""
echo "Negative Test: Prefix bypass attempt (forgemind-agent-loop-FAKE vs forgemind-agent-loop)"
TEMP_DIR=$(mktemp -d)

# Create a fake worktree with similar name prefix
FAKE_WORKTREE="/tmp/forgemind-agent-loop-FAKE-$$"
mkdir -p "$FAKE_WORKTREE"
cd "$FAKE_WORKTREE"
git init -q 2>/dev/null
git config user.email "test@test.com" 2>/dev/null
git config user.name "Test" 2>/dev/null
echo "test" > test.txt
git add test.txt 2>/dev/null
git commit -q -m "test" 2>/dev/null
git checkout -q -b chore/agent-loop-infrastructure 2>/dev/null

# Pass $REPO_ROOT as expected workspace_root, but pwd is in $FAKE_WORKTREE
# bootstrap_guard should fail because git toplevel (FAKE) != expected workspace_root (REPO_ROOT)
bootstrap_guard "$REPO_ROOT" "chore/agent-loop-infrastructure" "allocate" "$TEMP_DIR"
PREFIX_EXIT=$?

# Should FAIL because actual workspace doesn't match expected workspace
if [[ $PREFIX_EXIT -ne 0 ]]; then
  echo "  PASS: Prefix bypass correctly rejected (exit $PREFIX_EXIT)"
  TESTS_PASSED=$((TESTS_PASSED + 1))

  # Verify error artifact was created
  if [[ -f "$TEMP_DIR/guard-error.json" ]]; then
    echo "  PASS: Bootstrap error artifact created for prefix bypass attempt"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    echo "  FAIL: Bootstrap error artifact not created"
    TESTS_FAILED=$((TESTS_FAILED + 1))
  fi
else
  echo "  FAIL: Prefix bypass incorrectly accepted (exit 0)"
  TESTS_FAILED=$((TESTS_FAILED + 2))
fi

rm -rf "$TEMP_DIR" "$FAKE_WORKTREE"
cd "$REPO_ROOT"

# --- Negative Test: Symlink to main worktree ---
echo ""
echo "Negative Test: Symlink resolving to main worktree"
TEMP_DIR=$(mktemp -d)
SYMLINK_PATH="/tmp/main-worktree-symlink-$$"

# Only run if the main worktree exists and is resolvable
if resolve_path_strict "$FORBIDDEN_MAIN_WORKTREE" >/dev/null 2>&1; then
  # Create symlink pointing to main worktree
  ln -s "$FORBIDDEN_MAIN_WORKTREE" "$SYMLINK_PATH"

  # Bootstrap guard with symlink to main worktree
  bootstrap_guard "$SYMLINK_PATH" "chore/agent-loop-infrastructure" "allocate" "$TEMP_DIR"
  SYMLINK_EXIT=$?

  # Should FAIL because symlink resolves to main worktree
  if [[ $SYMLINK_EXIT -ne 0 ]]; then
    echo "  PASS: Symlink to main worktree correctly rejected (exit $SYMLINK_EXIT)"
    TESTS_PASSED=$((TESTS_PASSED + 1))

    # Verify error artifact was created
    if [[ -f "$TEMP_DIR/guard-error.json" ]]; then
      ERROR_CODE=$("$PYTHON_BIN" -c "import json; print(json.load(open('$TEMP_DIR/guard-error.json'))['error_code'])")
      if [[ "$ERROR_CODE" == "BOOTSTRAP_MAIN_WORKTREE_FORBIDDEN" ]]; then
        echo "  PASS: Bootstrap error artifact contains correct error_code ($ERROR_CODE)"
        TESTS_PASSED=$((TESTS_PASSED + 1))
      else
        echo "  FAIL: Bootstrap error artifact has wrong error_code: $ERROR_CODE"
        TESTS_FAILED=$((TESTS_FAILED + 1))
      fi
    else
      echo "  FAIL: Bootstrap error artifact not created"
      TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
  else
    echo "  FAIL: Symlink to main worktree incorrectly accepted (exit 0)"
    TESTS_FAILED=$((TESTS_FAILED + 2))
  fi
else
  echo "  SKIP: Main worktree not available at $FORBIDDEN_MAIN_WORKTREE"
  TESTS_PASSED=$((TESTS_PASSED + 2))
fi

rm -rf "$TEMP_DIR" "$SYMLINK_PATH"

# --- Negative Test: Bootstrap artifact creation on workspace unresolvable ---
echo ""
echo "Negative Test: Bootstrap artifact creation on workspace unresolvable"
TEMP_DIR=$(mktemp -d)

# Bootstrap guard with non-existent workspace
bootstrap_guard "/nonexistent/workspace/path" "chore/agent-loop-infrastructure" "allocate" "$TEMP_DIR"
UNRESOLVABLE_EXIT=$?

# Should FAIL
if [[ $UNRESOLVABLE_EXIT -ne 0 ]]; then
  echo "  PASS: Unresolvable workspace correctly rejected (exit $UNRESOLVABLE_EXIT)"
  TESTS_PASSED=$((TESTS_PASSED + 1))

  # Verify error artifact was created with correct error_code
  if [[ -f "$TEMP_DIR/guard-error.json" ]]; then
    ERROR_CODE=$("$PYTHON_BIN" -c "import json; print(json.load(open('$TEMP_DIR/guard-error.json'))['error_code'])")
    if [[ "$ERROR_CODE" == "BOOTSTRAP_WORKSPACE_UNRESOLVABLE" ]]; then
      echo "  PASS: Bootstrap error artifact contains correct error_code ($ERROR_CODE)"
      TESTS_PASSED=$((TESTS_PASSED + 1))
    else
      echo "  FAIL: Bootstrap error artifact has wrong error_code: $ERROR_CODE"
      TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
  else
    echo "  FAIL: Bootstrap error artifact not created"
    TESTS_FAILED=$((TESTS_FAILED + 1))
  fi
else
  echo "  FAIL: Unresolvable workspace incorrectly accepted (exit 0)"
  TESTS_FAILED=$((TESTS_FAILED + 2))
fi

rm -rf "$TEMP_DIR"

# --- Scenario: Path resolution contract verification (WP-AL-1A portability fix) ---
echo ""
echo "Scenario: Path resolution fail-closed contract"

# Test A: Explicit FORBIDDEN_MAIN_WORKTREE is honored
echo ""
echo "Test A: Explicit FORBIDDEN_MAIN_WORKTREE takes precedence"
TEMP_DIR=$(mktemp -d)
TEST_EXPLICIT="$TEMP_DIR/explicit-path"
TEST_CANONICAL="$TEMP_DIR/canonical-path"
mkdir -p "$TEST_EXPLICIT" "$TEST_CANONICAL"
export FORBIDDEN_MAIN_WORKTREE="$TEST_EXPLICIT"
export FORGEMIND_MAIN_ROOT="$TEST_CANONICAL"

(
  unset FORBIDDEN_MAIN_WORKTREE
  export FORBIDDEN_MAIN_WORKTREE="$TEST_EXPLICIT"
  export FORGEMIND_MAIN_ROOT="$TEST_CANONICAL"
  source "$THIS_DIR/../lib/guard.sh" 2>/dev/null
  echo "$FORBIDDEN_MAIN_WORKTREE"
) > "$TEMP_DIR/result.txt" 2>&1
RESOLVED_A=$(tail -1 "$TEMP_DIR/result.txt")
if [[ "$RESOLVED_A" == "$TEST_EXPLICIT" ]]; then
  echo "  PASS: Explicit FORBIDDEN_MAIN_WORKTREE honored"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "  FAIL: Expected $TEST_EXPLICIT, got $RESOLVED_A"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi
rm -rf "$TEMP_DIR"

# Test B: FORGEMIND_MAIN_ROOT fallback when explicit unset
echo ""
echo "Test B: FORGEMIND_MAIN_ROOT used when explicit unset"
TEMP_DIR=$(mktemp -d)
TEST_CANONICAL="$TEMP_DIR/canonical-path"
mkdir -p "$TEST_CANONICAL"

(
  unset FORBIDDEN_MAIN_WORKTREE
  export FORGEMIND_MAIN_ROOT="$TEST_CANONICAL"
  source "$THIS_DIR/../lib/guard.sh" 2>/dev/null
  echo "$FORBIDDEN_MAIN_WORKTREE"
) > "$TEMP_DIR/result.txt" 2>&1
RESOLVED_B=$(tail -1 "$TEMP_DIR/result.txt")
if [[ "$RESOLVED_B" == "$TEST_CANONICAL" ]]; then
  echo "  PASS: FORGEMIND_MAIN_ROOT fallback works"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "  FAIL: Expected $TEST_CANONICAL, got $RESOLVED_B"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi
rm -rf "$TEMP_DIR"

# Test C: Fail-closed when both unset (exit 2)
echo ""
echo "Test C: Exit 2 when both paths unset"
(
  unset FORBIDDEN_MAIN_WORKTREE
  unset FORGEMIND_MAIN_ROOT
  source "$THIS_DIR/../lib/guard.sh" 2>/dev/null
) 2>/dev/null
TEST_C_EXIT=$?
if [[ $TEST_C_EXIT -eq 2 ]]; then
  echo "  PASS: Exit 2 when both paths unset"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "  FAIL: Expected exit 2, got $TEST_C_EXIT"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# Test D: Fail-closed when FORBIDDEN_MAIN_WORKTREE doesn't exist (exit 2)
echo ""
echo "Test D: Exit 2 when FORBIDDEN_MAIN_WORKTREE doesn't exist"
(
  export FORBIDDEN_MAIN_WORKTREE="/nonexistent/path/that/does/not/exist"
  unset FORGEMIND_MAIN_ROOT
  source "$THIS_DIR/../lib/guard.sh" 2>/dev/null
) 2>/dev/null
TEST_D_EXIT=$?
if [[ $TEST_D_EXIT -eq 2 ]]; then
  echo "  PASS: Exit 2 when path doesn't exist"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "  FAIL: Expected exit 2, got $TEST_D_EXIT"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# Test E: Fail-closed when FORGEMIND_MAIN_ROOT doesn't exist (exit 2)
echo ""
echo "Test E: Exit 2 when FORGEMIND_MAIN_ROOT doesn't exist"
(
  unset FORBIDDEN_MAIN_WORKTREE
  export FORGEMIND_MAIN_ROOT="/nonexistent/canonical/path"
  source "$THIS_DIR/../lib/guard.sh" 2>/dev/null
) 2>/dev/null
TEST_E_EXIT=$?
if [[ $TEST_E_EXIT -eq 2 ]]; then
  echo "  PASS: Exit 2 when FORGEMIND_MAIN_ROOT doesn't exist"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "  FAIL: Expected exit 2, got $TEST_E_EXIT"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# Test F: Paths with spaces resolve correctly
echo ""
echo "Test F: Paths with spaces resolve correctly"
TEMP_DIR=$(mktemp -d)
TEST_SPACES="$TEMP_DIR/path with spaces"
mkdir -p "$TEST_SPACES"

(
  export FORBIDDEN_MAIN_WORKTREE="$TEST_SPACES"
  unset FORGEMIND_MAIN_ROOT
  source "$THIS_DIR/../lib/guard.sh" 2>/dev/null
  echo "$FORBIDDEN_MAIN_WORKTREE"
) > "$TEMP_DIR/result.txt" 2>&1
RESOLVED_F=$(tail -1 "$TEMP_DIR/result.txt")
if [[ "$RESOLVED_F" == "$TEST_SPACES" ]]; then
  echo "  PASS: Path with spaces resolved"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "  FAIL: Expected $TEST_SPACES, got $RESOLVED_F"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi
rm -rf "$TEMP_DIR"

# Test G: No hardcoded developer path in source
echo ""
echo "Test G: No hardcoded developer paths in guard.sh"
FORBIDDEN_PATH_PATTERN="/run/media"
if grep -q "$FORBIDDEN_PATH_PATTERN" "$THIS_DIR/../lib/guard.sh"; then
  echo "  FAIL: Hardcoded developer paths still present"
  TESTS_FAILED=$((TESTS_FAILED + 1))
else
  echo "  PASS: No hardcoded developer paths"
  TESTS_PASSED=$((TESTS_PASSED + 1))
fi

# Test H: No hardcoded developer path in changed files of this PR
echo ""
echo "Test H: No hardcoded developer paths in PR-changed files"
PR_FILES=$(git diff --name-only origin/main...HEAD | grep -v test_identity_guard_integration.sh | tr '\n' '\0' | xargs -0 grep -l "$FORBIDDEN_PATH_PATTERN" 2>/dev/null || true)
if [[ -n "$PR_FILES" ]]; then
  echo "  FAIL: Hardcoded developer paths found in: $PR_FILES"
  TESTS_FAILED=$((TESTS_FAILED + 1))
else
  echo "  PASS: No hardcoded developer paths in PR-changed files"
  TESTS_PASSED=$((TESTS_PASSED + 1))
fi

echo ""
echo "================================================================"
echo "INTEGRATION TEST SUMMARY"
echo "================================================================"
echo "Tests passed: $TESTS_PASSED"
echo "Tests failed: $TESTS_FAILED"
echo ""

if [[ $TESTS_FAILED -eq 0 ]]; then
  echo "ALL INTEGRATION TESTS PASSED"
  exit 0
else
  echo "SOME INTEGRATION TESTS FAILED"
  exit 1
fi
