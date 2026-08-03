#!/usr/bin/env bash
# Deterministic verification gates (no agent involved)

set -uo pipefail  # NOTE: no -e, we handle errors per-gate

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/lib/artifacts.sh"
source "$SCRIPT_DIR/lib/env.sh"
source "$SCRIPT_DIR/lib/scope.sh"
source "$SCRIPT_DIR/lib/tests.sh"

# Track timing
START_TIME="$(date -Iseconds)"

# Temp files to clean up
TEMP_FILES=()

cleanup() {
  local exit_code=$?
  for f in "${TEMP_FILES[@]}"; do
    rm -f "$f" 2>/dev/null || true
  done
  if [[ -n "${SYNTHETIC_DIR:-}" && -d "$SYNTHETIC_DIR" ]]; then
    rm -rf "$SYNTHETIC_DIR" 2>/dev/null || true
  fi
  exit $exit_code
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Initialize artifacts directory (only if not already set by parent)
STORY_MANIFEST="${1:-}"
STORY_ID="${STORY_ID:-}"
RUN_ID="${RUN_ID:-}"
PASSPORT_FILE="${PASSPORT_FILE:-}"

# If passport file provided, validate it
if [[ -n "$PASSPORT_FILE" ]]; then
  source "$SCRIPT_DIR/lib/guard.sh"

  # Run phase guard for verify phase
  if ! phase_guard "$PASSPORT_FILE" "verify" "validation" "verifier" "${RUN_DIR:-.}"; then
    echo "VERIFICATION GATES BLOCKED BY IDENTITY GUARD"
    echo "See guard-error.json for details"
    exit 2
  fi

  echo "Identity guard validation passed for verify phase"
fi

# Early manifest validation — must happen BEFORE init_artifacts
MANIFEST_VALID="true"
MANIFEST_ERROR=""

if [[ -n "$STORY_MANIFEST" ]]; then
  if [[ ! -f "$STORY_MANIFEST" ]]; then
    MANIFEST_VALID="false"
    MANIFEST_ERROR="MANIFEST_MISSING|Manifest file does not exist: $STORY_MANIFEST"
  else
    VALIDATION_RESULT="$("$PYTHON_BIN" "$HARNESS_PY" validate "$STORY_MANIFEST" 2>&1)" || VALIDATION_RESULT="ERROR:UNEXPECTED|Validation script failed"

    if [[ "$VALIDATION_RESULT" == ERROR:* ]]; then
      MANIFEST_VALID="false"
      MANIFEST_ERROR="${VALIDATION_RESULT#ERROR:}"
    else
      # Extract story_id from OK:story_id
      STORY_ID="${VALIDATION_RESULT#OK:}"
    fi
  fi
fi

# If STORY_ID still empty, set to unknown (only when manifest not provided)
if [[ -z "$STORY_ID" ]]; then
  STORY_ID="unknown"
fi

# Initialize RUN_DIR
if [[ -z "$RUN_ID" ]]; then
  init_artifacts "$STORY_ID" > /dev/null
else
  RUN_DIR="${RUN_DIR:-}"
fi

# Fallback if RUN_DIR still empty
if [[ -z "$RUN_DIR" ]]; then
  init_artifacts "$STORY_ID" > /dev/null
fi

# Helper: atomic JSON write via harness.py
atomic_json_write() {
  local output_file="$1"
  local json_data="$2"
  "$PYTHON_BIN" "$HARNESS_PY" atomic_write "$output_file" "$json_data"
}

# Handle manifest validation failure — emit ERROR and exit immediately
if [[ "$MANIFEST_VALID" == "false" ]]; then
  echo "=========================================="
  echo "VERIFICATION GATES - Story: $STORY_ID"
  echo "Run directory: $RUN_DIR"
  echo "=========================================="
  echo ""
  echo "MANIFEST VALIDATION ERROR: $MANIFEST_ERROR"
  echo ""
  echo "Skipping all verification gates."
  echo ""

  # Parse error type and message
  ERROR_TYPE="${MANIFEST_ERROR%%|*}"
  ERROR_MSG="${MANIFEST_ERROR#*|}"

  # Generate verify-result.json with ERROR status
  END_TIME="$(date -Iseconds)"
  atomic_json_write "$RUN_DIR/reports/verify-result.json" "$(cat <<EOF
{
  "schema_version": "1.0",
  "run_id": "$RUN_ID",
  "story_id": "$STORY_ID",
  "started_at": "$START_TIME",
  "finished_at": "$END_TIME",
  "overall_status": "ERROR",
  "gates": [],
  "error": {
    "type": "$ERROR_TYPE",
    "message": "$ERROR_MSG",
    "details": "Manifest validation failed during early validation phase"
  }
}
EOF
)"

  echo "verify-result.json generated: $RUN_DIR/reports/verify-result.json"
  echo "OVERALL: ERROR"
  exit 2
fi

# Temporary file for gate results (passed to Python at end)
GATES_JSON_TMP="$RUN_DIR/verify/.gates-tmp.json"
echo '[]' > "$GATES_JSON_TMP"
TEMP_FILES+=("$GATES_JSON_TMP")

# Load gate configuration from manifest
GATE_CONFIG_TMP="$RUN_DIR/verify/.gate-config-tmp.json"
if [[ -n "$STORY_MANIFEST" && -f "$STORY_MANIFEST" ]]; then
  "$PYTHON_BIN" "$HARNESS_PY" load_gate_config "$STORY_MANIFEST" > "$GATE_CONFIG_TMP" 2>/dev/null || echo '{}' > "$GATE_CONFIG_TMP"
else
  echo '{}' > "$GATE_CONFIG_TMP"
fi
TEMP_FILES+=("$GATE_CONFIG_TMP")

echo "=========================================="
echo "VERIFICATION GATES - Story: $STORY_ID"
echo "Run directory: $RUN_DIR"
echo "=========================================="

# Overall status tracking
# PASS: all required gates PASS
# FAIL: any required gate FAIL
# ERROR: internal harness failure
# SKIP: gate skipped (clean tree, not a failure for required gates)
OVERALL_STATUS="PASS"
INTERNAL_ERROR=""

# Helper to get gate config
get_gate_required() {
  local gate_name="$1"
  "$PYTHON_BIN" -c "
import json, sys
gates = json.load(open(sys.argv[1]))
gate_name = sys.argv[2]
if gate_name in gates:
    print('true' if gates[gate_name].get('required', True) else 'false')
else:
    print('true')  # Default to required if not specified
" "$GATE_CONFIG_TMP" "$gate_name" 2>/dev/null || echo "true"
}

get_gate_enabled() {
  local gate_name="$1"
  "$PYTHON_BIN" -c "
import json, sys
gates = json.load(open(sys.argv[1]))
gate_name = sys.argv[2]
if gate_name in gates:
    print('true' if gates[gate_name].get('enabled', True) else 'false')
else:
    print('true')  # Default to enabled if not specified
" "$GATE_CONFIG_TMP" "$gate_name" 2>/dev/null || echo "true"
}

get_gate_scope_to_diff() {
  local gate_name="$1"
  "$PYTHON_BIN" -c "
import json, sys
gates = json.load(open(sys.argv[1]))
gate_name = sys.argv[2]
if gate_name in gates:
    print('true' if gates[gate_name].get('scope_to_diff', False) else 'false')
else:
    print('false')  # Default to false if not specified
" "$GATE_CONFIG_TMP" "$gate_name" 2>/dev/null || echo "false"
}

# Helper to add gate result to JSON
add_gate_result() {
  local gate_name="$1"
  local status="$2"
  local details="${3:-}"

  "$PYTHON_BIN" - "$GATES_JSON_TMP" "$gate_name" "$status" "$details" <<'PYEOF'
import json
import sys

gates_file = sys.argv[1]
gate_name = sys.argv[2]
status = sys.argv[3]
details = sys.argv[4] if len(sys.argv) > 4 else ""

with open(gates_file) as f:
    gates = json.load(f)

gates.append({
    "name": gate_name,
    "status": status,
    "details": details
})

with open(gates_file, 'w') as f:
    json.dump(gates, f, indent=2)
PYEOF
}

# Update overall status based on gate status
# SKIP is treated as PASS for required gates (clean tree = nothing to verify = OK)
update_overall_status() {
  local gate_name="$1"
  local gate_status="$2"
  local gate_required="$3"

  # For required gates, FAIL leads to overall FAIL
  # SKIP is acceptable (means nothing to verify)
  if [[ "$gate_required" == "true" ]]; then
    if [[ "$gate_status" == "FAIL" ]]; then
      export OVERALL_STATUS="FAIL"
    fi
  fi
}

# Gate 1: Scope check
echo ""
echo "[GATE 1] Scope check..."
scope_required="$(get_gate_required "scope")"
scope_enabled="$(get_gate_enabled "scope")"

if [[ "$scope_enabled" == "false" ]]; then
  echo "  DISABLED"
  add_gate_result "scope" "DISABLED" ""
else
  scope_output="$(check_scope "$STORY_MANIFEST" 2>&1)" || true
  scope_exit=$?
  echo "$scope_output" > "$RUN_DIR/verify/scope.log"

  if [[ "$scope_output" == *"NO_CHANGES"* ]]; then
    echo "  SKIP (clean working tree, no changes to verify)"
    add_gate_result "scope" "SKIP" "Clean working tree"
    # SKIP is acceptable for required gates — nothing to verify
    update_overall_status "scope" "SKIP" "$scope_required"
  elif [[ $scope_exit -eq 0 ]]; then
    echo "  PASS"
    add_gate_result "scope" "PASS" ""
    update_overall_status "scope" "PASS" "$scope_required"
  else
    echo "  FAIL - see $RUN_DIR/verify/scope.log"
    add_gate_result "scope" "FAIL" "Scope violation"
    update_overall_status "scope" "FAIL" "$scope_required"
  fi
fi

# Gate 2: JSON syntax (check modified/created JSON files)
echo ""
echo "[GATE 2] JSON syntax..."
json_required="$(get_gate_required "json_syntax")"
json_enabled="$(get_gate_enabled "json_syntax")"

if [[ "$json_enabled" == "false" ]]; then
  echo "  DISABLED"
  add_gate_result "json_syntax" "DISABLED" ""
else
  json_errors=0
  json_details=""
  while IFS= read -r f; do
    # Skip test fixture files (may be intentionally broken for testing)
    if [[ "$f" == */fixtures/* ]]; then
      continue
    fi
    if [[ -n "$f" && -f "$f" ]]; then
      if ! check_json_syntax "$f" > "$RUN_DIR/verify/json_$(basename "$f").log" 2>&1; then
        echo "  FAIL: $f"
        json_errors=$((json_errors + 1))
        json_details="$json_details $f"
      fi
    fi
  done < <(git diff --name-only HEAD 2>/dev/null | grep '\.json$' || true)

  if [[ $json_errors -eq 0 ]]; then
    echo "  PASS (no JSON syntax errors)"
    add_gate_result "json_syntax" "PASS" ""
    update_overall_status "json_syntax" "PASS" "$json_required"
  else
    echo "  FAIL ($json_errors files with syntax errors)"
    add_gate_result "json_syntax" "FAIL" "$json_errors files$json_details"
    update_overall_status "json_syntax" "FAIL" "$json_required"
  fi
fi

# Gate 3: Targeted tests
echo ""
echo "[GATE 3] Targeted tests..."
tests_required="$(get_gate_required "targeted_tests")"
tests_enabled="$(get_gate_enabled "targeted_tests")"

if [[ "$tests_enabled" == "false" ]]; then
  echo "  DISABLED"
  add_gate_result "targeted_tests" "DISABLED" ""
else
  # Load env for test execution
  load_env_safe 2>/dev/null || true

  # Check if test file exists before running
  test_args_json="$("$PYTHON_BIN" "$HARNESS_PY" load_test_args "$STORY_MANIFEST" 2>/dev/null || echo "[]")"
  test_path=""
  if [[ "$test_args_json" != "[]" && -n "$test_args_json" ]]; then
    test_path="$("$PYTHON_BIN" -c "import json,sys; args=json.loads(sys.argv[1]); print(next((a for a in args if a.startswith('tests/') or a.startswith('test_')), ''))" "$test_args_json" 2>/dev/null || echo "")"
  fi

  test_file_exists="true"
  if [[ -n "$test_path" && ! -f "$REPO_ROOT/backend/$test_path" ]]; then
    test_file_exists="false"
  fi

  if [[ "$test_file_exists" == "false" ]]; then
    # Missing test file
    if [[ "$tests_required" == "true" ]]; then
      echo "  FAIL (test file not found, gate is required)"
      add_gate_result "targeted_tests" "FAIL" "Test file not found: $test_path"
      update_overall_status "targeted_tests" "FAIL" "$tests_required"
    else
      echo "  SKIP (test file not found, gate is optional)"
      add_gate_result "targeted_tests" "SKIP" "Test file not found: $test_path"
      # Optional SKIP doesn't affect overall status
    fi
  else
    # Run tests (pass manifest, not args — tests.sh loads args as JSON array)
    if run_targeted_tests "$STORY_MANIFEST" > "$RUN_DIR/verify/tests.log" 2>&1; then
      echo "  PASS"
      add_gate_result "targeted_tests" "PASS" ""
      update_overall_status "targeted_tests" "PASS" "$tests_required"
    else
      test_exit=$?
      if [[ $test_exit -eq 2 ]]; then
        # All tests skipped
        if [[ "$tests_required" == "true" ]]; then
          echo "  FAIL (all tests skipped, gate is required)"
          add_gate_result "targeted_tests" "FAIL" "All tests skipped"
          update_overall_status "targeted_tests" "FAIL" "$tests_required"
        else
          echo "  SKIP (all tests skipped, gate is optional)"
          add_gate_result "targeted_tests" "SKIP" "All tests skipped"
        fi
      else
        echo "  FAIL - see $RUN_DIR/verify/tests.log"
        add_gate_result "targeted_tests" "FAIL" "See tests.log"
        update_overall_status "targeted_tests" "FAIL" "$tests_required"
      fi
    fi
  fi
fi

# Gate 4: Lint (scoped to diff)
echo ""
echo "[GATE 4] Lint (ruff + mypy)..."
lint_required="$(get_gate_required "lint")"
lint_enabled="$(get_gate_enabled "lint")"
lint_scope_to_diff="$(get_gate_scope_to_diff "lint")"

if [[ "$lint_enabled" == "false" ]]; then
  echo "  DISABLED"
  add_gate_result "lint" "DISABLED" ""
else
  py_files_in_diff="$(git diff --name-only HEAD 2>/dev/null | grep '\.py$' || true)"

  if [[ "${DRY_RUN:-false}" == "true" ]]; then
    # In dry-run mode, always scope to diff
    if [[ -z "$py_files_in_diff" ]]; then
      echo "  PASS (no Python files in diff, dry-run mode)"
      add_gate_result "lint" "PASS" "No Python files in diff"
      update_overall_status "lint" "PASS" "$lint_required"
    else
      if run_lint > "$RUN_DIR/verify/lint.log" 2>&1; then
        echo "  PASS"
        add_gate_result "lint" "PASS" ""
        update_overall_status "lint" "PASS" "$lint_required"
      else
        echo "  FAIL - see $RUN_DIR/verify/lint.log"
        add_gate_result "lint" "FAIL" "See lint.log"
        update_overall_status "lint" "FAIL" "$lint_required"
      fi
    fi
  elif [[ "$lint_scope_to_diff" == "true" && -z "$py_files_in_diff" ]]; then
    echo "  PASS (no Python files in diff, scope_to_diff=true)"
    add_gate_result "lint" "PASS" "No Python files in diff"
    update_overall_status "lint" "PASS" "$lint_required"
  else
    if run_lint > "$RUN_DIR/verify/lint.log" 2>&1; then
      echo "  PASS"
      add_gate_result "lint" "PASS" ""
      update_overall_status "lint" "PASS" "$lint_required"
    else
      echo "  FAIL - see $RUN_DIR/verify/lint.log"
      add_gate_result "lint" "FAIL" "See lint.log"
      update_overall_status "lint" "FAIL" "$lint_required"
    fi
  fi
fi

# Gate 5: Secrets (scoped to diff)
echo ""
echo "[GATE 5] Secrets scan..."
secrets_required="$(get_gate_required "secrets")"
secrets_enabled="$(get_gate_enabled "secrets")"
secrets_scope_to_diff="$(get_gate_scope_to_diff "secrets")"

if [[ "$secrets_enabled" == "false" ]]; then
  echo "  DISABLED"
  add_gate_result "secrets" "DISABLED" ""
else
  diff_files="$(git diff --name-only HEAD 2>/dev/null || echo "")"

  if [[ "${DRY_RUN:-false}" == "true" ]]; then
    # In dry-run mode, always scope to diff
    if [[ -z "$diff_files" ]]; then
      echo "  PASS (no files in diff, dry-run mode)"
      add_gate_result "secrets" "PASS" "No files in diff"
      update_overall_status "secrets" "PASS" "$secrets_required"
    else
      # Scan only diff files
      secrets_found=""
      while IFS= read -r f; do
        if [[ -f "$f" ]]; then
          for pattern in 'sk_live_[a-zA-Z0-9]+' 'sk_test_[a-zA-Z0-9]+' 'ghp_[a-zA-Z0-9]{36}' '-----BEGIN PRIVATE KEY-----' 'password[[:space:]]*=[[:space:]]*['"'"'"][^'"'"'"]{8,}['"'"'"]' 'api_key[[:space:]]*=[[:space:]]*['"'"'"][^'"'"'"]+['"'"'"]' 'secret[[:space:]]*=[[:space:]]*['"'"'"][^'"'"'"]+['"'"'"]'; do
            if grep -qE "$pattern" "$f" 2>/dev/null; then
              secrets_found="Potential secret in $f matching pattern: $pattern"
              break 2
            fi
          done
        fi
      done <<< "$diff_files"

      if [[ -n "$secrets_found" ]]; then
        echo "  FAIL - $secrets_found"
        add_gate_result "secrets" "FAIL" "$secrets_found"
        update_overall_status "secrets" "FAIL" "$secrets_required"
      else
        echo "  PASS (no secrets detected in diff)"
        add_gate_result "secrets" "PASS" ""
        update_overall_status "secrets" "PASS" "$secrets_required"
      fi
    fi
  elif [[ "$secrets_scope_to_diff" == "true" && -z "$diff_files" ]]; then
    echo "  PASS (no files in diff, scope_to_diff=true)"
    add_gate_result "secrets" "PASS" "No files in diff"
    update_overall_status "secrets" "PASS" "$secrets_required"
  else
    # Scan files
    secrets_found=""
    if [[ "$secrets_scope_to_diff" == "true" ]]; then
      # Scan only diff files
      files_to_scan="$diff_files"
    else
      # Scan all tracked files
      files_to_scan="$(git ls-files 2>/dev/null || echo "")"
    fi

    if [[ -n "$files_to_scan" ]]; then
      while IFS= read -r f; do
        if [[ -f "$f" ]]; then
          for pattern in 'sk_live_[a-zA-Z0-9]+' 'sk_test_[a-zA-Z0-9]+' 'ghp_[a-zA-Z0-9]{36}' '-----BEGIN PRIVATE KEY-----' 'password[[:space:]]*=[[:space:]]*['"'"'"][^'"'"'"]{8,}['"'"'"]' 'api_key[[:space:]]*=[[:space:]]*['"'"'"][^'"'"'"]+['"'"'"]' 'secret[[:space:]]*=[[:space:]]*['"'"'"][^'"'"'"]+['"'"'"]'; do
            if grep -qE "$pattern" "$f" 2>/dev/null; then
              secrets_found="Potential secret in $f matching pattern: $pattern"
              break 2
            fi
          done
        fi
      done <<< "$files_to_scan"
    fi

    if [[ -n "$secrets_found" ]]; then
      echo "  FAIL - $secrets_found"
      add_gate_result "secrets" "FAIL" "$secrets_found"
      update_overall_status "secrets" "FAIL" "$secrets_required"
    else
      echo "  PASS (no secrets detected)"
      add_gate_result "secrets" "PASS" ""
      update_overall_status "secrets" "PASS" "$secrets_required"
    fi
  fi
fi

# Gate 6: git diff --check (optional by default)
echo ""
echo "[GATE 6] git diff --check..."
diff_check_required="$(get_gate_required "git_diff_check")"
diff_check_enabled="$(get_gate_enabled "git_diff_check")"

if [[ "$diff_check_enabled" == "false" ]]; then
  echo "  DISABLED"
  add_gate_result "git_diff_check" "DISABLED" ""
else
  if git diff --check > "$RUN_DIR/verify/diff_check.log" 2>&1; then
    echo "  PASS"
    add_gate_result "git_diff_check" "PASS" ""
    update_overall_status "git_diff_check" "PASS" "$diff_check_required"
  else
    echo "  FAIL - see $RUN_DIR/verify/diff_check.log"
    add_gate_result "git_diff_check" "FAIL" "Whitespace errors"
    update_overall_status "git_diff_check" "FAIL" "$diff_check_required"
  fi
fi

# Summary
echo ""
echo "=========================================="
echo "VERIFICATION SUMMARY"
echo "=========================================="

# Read gates from JSON for display
"$PYTHON_BIN" - "$GATES_JSON_TMP" <<'PYEOF'
import json
import sys

gates_file = sys.argv[1]
with open(gates_file) as f:
    gates = json.load(f)

for gate in gates:
    print(f"  {gate['name']}: {gate['status']}")
PYEOF

END_TIME="$(date -Iseconds)"

# Determine final overall status
# Check if any required gate had ERROR
any_error="$("$PYTHON_BIN" -c "
import json, sys
gates_file = sys.argv[1]
gate_config_file = sys.argv[2]

with open(gates_file) as f:
    gates = json.load(f)
with open(gate_config_file) as f:
    gate_config = json.load(f)

for gate in gates:
    gate_name = gate['name']
    gate_status = gate['status']
    is_required = gate_config.get(gate_name, {}).get('required', True)

    if is_required and gate_status == 'ERROR':
        print('true')
        sys.exit(0)

print('false')
" "$GATES_JSON_TMP" "$GATE_CONFIG_TMP" 2>/dev/null || echo "false")"

if [[ "$any_error" == "true" ]]; then
  OVERALL_STATUS="ERROR"
elif [[ "$OVERALL_STATUS" != "ERROR" ]]; then
  # Check if all required gates passed or were skipped (clean tree)
  all_required_pass="$("$PYTHON_BIN" -c "
import json, sys
gates_file = sys.argv[1]
gate_config_file = sys.argv[2]

with open(gates_file) as f:
    gates = json.load(f)
with open(gate_config_file) as f:
    gate_config = json.load(f)

for gate in gates:
    gate_name = gate['name']
    gate_status = gate['status']
    is_required = gate_config.get(gate_name, {}).get('required', True)

    if is_required and gate_status not in ['PASS', 'DISABLED', 'SKIP']:
        print('false')
        sys.exit(0)

print('true')
" "$GATES_JSON_TMP" "$GATE_CONFIG_TMP" 2>/dev/null || echo "false")"

  if [[ "$all_required_pass" == "true" ]]; then
    OVERALL_STATUS="PASS"
  else
    OVERALL_STATUS="FAIL"
  fi
fi

# Generate verify-result.json using Python with proper data passing
"$PYTHON_BIN" - "$GATES_JSON_TMP" "$STORY_ID" "$RUN_ID" "$START_TIME" "$END_TIME" "$OVERALL_STATUS" "$INTERNAL_ERROR" "$RUN_DIR/reports/verify-result.json" <<'PYEOF'
import json
import sys

gates_file = sys.argv[1]
story_id = sys.argv[2]
run_id = sys.argv[3]
started_at = sys.argv[4]
finished_at = sys.argv[5]
overall_status = sys.argv[6]
internal_error = sys.argv[7] if len(sys.argv) > 7 and sys.argv[7] else None
output_file = sys.argv[8]

with open(gates_file) as f:
    gates = json.load(f)

result = {
    "schema_version": "1.0",
    "run_id": run_id if run_id else "unknown",
    "story_id": story_id,
    "started_at": started_at,
    "finished_at": finished_at,
    "overall_status": overall_status,
    "gates": gates
}

if internal_error:
    result["error"] = internal_error

with open(output_file, 'w') as f:
    json.dump(result, f, indent=2)
PYEOF

echo ""
echo "verify-result.json generated: $RUN_DIR/reports/verify-result.json"

if [[ "$OVERALL_STATUS" == "PASS" ]]; then
  echo "OVERALL: PASS"
  exit 0
elif [[ "$OVERALL_STATUS" == "ERROR" ]]; then
  echo "OVERALL: ERROR"
  exit 2
else
  echo "OVERALL: FAIL"
  exit 1
fi
