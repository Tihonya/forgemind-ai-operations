#!/usr/bin/env bash
# Deterministic verification gates (no agent involved)
#
# WP-AL-1B2B canonical gate wiring:
#   - all gates operate on the candidate diff vs the manifest base_commit
#     (committed/staged/working-tree changes + untracked files);
#   - scope gate is manifest-driven (allowed_paths/forbidden_paths,
#     gitwildmatch) and its failure propagates — no exit-code masking;
#   - yaml_syntax gate executes over changed YAML files;
#   - lint honours scope_to_diff by linting only changed Python files;
#   - secrets honours scope_to_diff by scanning only changed files and
#     reports rule identifiers only (never matched secret values);
#   - the summary marks any required gate that never executed as ERROR
#     instead of silently passing it.

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

# If passport file provided, validate it.
# Runs AFTER RUN_DIR exists so guard-error.json is contained inside the run's
# artifact root, never the repository cwd. Still a pre-gate check: any guard
# failure exits 2 before a gate executes.
if [[ -n "$PASSPORT_FILE" ]]; then
  source "$SCRIPT_DIR/lib/guard.sh"

  # Run phase guard for verify phase
  if ! phase_guard "$PASSPORT_FILE" "verify" "validation" "verifier" "$RUN_DIR"; then
    echo "VERIFICATION GATES BLOCKED BY IDENTITY GUARD"
    echo "See $RUN_DIR/guard-error.json for details"
    exit 2
  fi

  echo "Identity guard validation passed for verify phase"
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

get_gate_assertion_gate() {
  "$PYTHON_BIN" -c "
import json, sys
gates = json.load(open(sys.argv[1]))
gate = gates.get('targeted_tests', {})
print('true' if gate.get('assertion_gate', True) else 'false')
" "$GATE_CONFIG_TMP" 2>/dev/null || echo "true"
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

# ----------------------------------------------------------------------------
# Candidate diff enumeration (shared by scope/lint/secrets/json/yaml gates)
# Candidate diff = changes + untracked files vs manifest base_commit.
# ----------------------------------------------------------------------------
BASE_COMMIT="$("$PYTHON_BIN" -c "
import json, sys
try:
    print(json.load(open(sys.argv[1])).get('base_commit', ''))
except Exception:
    print('')
" "$STORY_MANIFEST" 2>/dev/null || echo "")"

DIFF_FILES_TMP="$RUN_DIR/verify/.diff-files-tmp.lst"
TEMP_FILES+=("$DIFF_FILES_TMP")

DIFF_ENUM_STATUS="OK"
DIFF_JSON_TMP="$RUN_DIR/verify/.diff-json-tmp.json"
TEMP_FILES+=("$DIFF_JSON_TMP")

if "$PYTHON_BIN" "$HARNESS_PY" list_diff_files "$REPO_ROOT" "$BASE_COMMIT" > "$DIFF_JSON_TMP" 2>/dev/null; then
  "$PYTHON_BIN" -c "
import json, sys
data = json.load(open(sys.argv[1]))
for p in data.get('files', []):
    print(p)
" "$DIFF_JSON_TMP" > "$DIFF_FILES_TMP"
else
  DIFF_ENUM_STATUS="ERROR"
  : > "$DIFF_FILES_TMP"
fi

echo ""
echo "Candidate diff enumeration: $DIFF_ENUM_STATUS ($(wc -l < "$DIFF_FILES_TMP") file(s))"

if [[ "$DIFF_ENUM_STATUS" == "ERROR" ]]; then
  echo "INFRASTRUCTURE_ERROR: candidate diff enumeration failed (base_commit=$BASE_COMMIT)"
  INTERNAL_ERROR="DIFF_ENUMERATION_FAILED|Candidate diff could not be computed against base_commit"
  OVERALL_STATUS="ERROR"
fi

# ----------------------------------------------------------------------------
# Gate 1: Scope check (manifest-driven; failure propagates)
# ----------------------------------------------------------------------------
echo ""
echo "[GATE 1] Scope check..."
scope_required="$(get_gate_required "scope")"
scope_enabled="$(get_gate_enabled "scope")"

if [[ "$DIFF_ENUM_STATUS" == "ERROR" ]]; then
  echo "  ERROR - candidate diff unavailable"
  add_gate_result "scope" "ERROR" "Candidate diff enumeration failed"
  OVERALL_STATUS="ERROR"
elif [[ "$scope_enabled" == "false" ]]; then
  echo "  DISABLED"
  add_gate_result "scope" "DISABLED" ""
else
  scope_output="$(check_scope "$STORY_MANIFEST")"
  scope_exit=$?
  echo "$scope_output" > "$RUN_DIR/verify/scope.log"

  if [[ "$scope_output" == *"NO_CHANGES"* ]]; then
    echo "  SKIP (no candidate changes, nothing to verify)"
    add_gate_result "scope" "SKIP" "No candidate changes vs base_commit"
    # SKIP is acceptable for required gates — nothing to verify
    update_overall_status "scope" "SKIP" "$scope_required"
  elif [[ $scope_exit -eq 0 ]]; then
    echo "  PASS"
    add_gate_result "scope" "PASS" ""
    update_overall_status "scope" "PASS" "$scope_required"
  elif [[ $scope_exit -eq 1 ]]; then
    echo "  FAIL - see $RUN_DIR/verify/scope.log"
    add_gate_result "scope" "FAIL" "Scope violation"
    update_overall_status "scope" "FAIL" "$scope_required"
  else
    echo "  ERROR - see $RUN_DIR/verify/scope.log"
    add_gate_result "scope" "ERROR" "Scope gate infrastructure error"
    OVERALL_STATUS="ERROR"
  fi
fi

# ----------------------------------------------------------------------------
# Gate 2: JSON syntax (candidate-diff JSON files)
# ----------------------------------------------------------------------------
echo ""
echo "[GATE 2] JSON syntax..."
json_required="$(get_gate_required "json_syntax")"
json_enabled="$(get_gate_enabled "json_syntax")"

if [[ "$DIFF_ENUM_STATUS" == "ERROR" ]]; then
  echo "  ERROR - candidate diff unavailable"
  add_gate_result "json_syntax" "ERROR" "Candidate diff enumeration failed"
  OVERALL_STATUS="ERROR"
elif [[ "$json_enabled" == "false" ]]; then
  echo "  DISABLED"
  add_gate_result "json_syntax" "DISABLED" ""
else
  json_errors=0
  json_details=""
  json_checked=0
  while IFS= read -r f; do
    # Skip test fixture files (may be intentionally broken for testing)
    if [[ "$f" == */fixtures/* ]]; then
      continue
    fi
    case "$f" in
      *.json) ;;
      *) continue ;;
    esac
    if [[ -n "$f" && -f "$f" ]]; then
      json_checked=$((json_checked + 1))
      if ! check_json_syntax "$f" > "$RUN_DIR/verify/json_$(basename "$f").log" 2>&1; then
        echo "  FAIL: $f"
        json_errors=$((json_errors + 1))
        json_details="$json_details $f"
      fi
    fi
  done < "$DIFF_FILES_TMP"

  if [[ $json_errors -eq 0 ]]; then
    echo "  PASS ($json_checked JSON file(s) checked)"
    add_gate_result "json_syntax" "PASS" ""
    update_overall_status "json_syntax" "PASS" "$json_required"
  else
    echo "  FAIL ($json_errors files with syntax errors)"
    add_gate_result "json_syntax" "FAIL" "$json_errors files$json_details"
    update_overall_status "json_syntax" "FAIL" "$json_required"
  fi
fi

# ----------------------------------------------------------------------------
# Gate 3: YAML syntax (candidate-diff YAML files)
# ----------------------------------------------------------------------------
echo ""
echo "[GATE 3] YAML syntax..."
yaml_required="$(get_gate_required "yaml_syntax")"
yaml_enabled="$(get_gate_enabled "yaml_syntax")"

if [[ "$DIFF_ENUM_STATUS" == "ERROR" ]]; then
  echo "  ERROR - candidate diff unavailable"
  add_gate_result "yaml_syntax" "ERROR" "Candidate diff enumeration failed"
  OVERALL_STATUS="ERROR"
elif [[ "$yaml_enabled" == "false" ]]; then
  echo "  DISABLED"
  add_gate_result "yaml_syntax" "DISABLED" ""
else
  yaml_errors=0
  yaml_details=""
  yaml_checked=0
  while IFS= read -r f; do
    case "$f" in
      *.yaml|*.yml) ;;
      *) continue ;;
    esac
    if [[ -n "$f" && -f "$f" ]]; then
      yaml_checked=$((yaml_checked + 1))
      if ! check_yaml_syntax "$f" > "$RUN_DIR/verify/yaml_$(basename "$f").log" 2>&1; then
        echo "  FAIL: $f"
        yaml_errors=$((yaml_errors + 1))
        yaml_details="$yaml_details $f"
      fi
    fi
  done < "$DIFF_FILES_TMP"

  if [[ $yaml_checked -eq 0 ]]; then
    echo "  SKIP (no YAML files in candidate diff)"
    add_gate_result "yaml_syntax" "SKIP" "No YAML files in candidate diff"
    update_overall_status "yaml_syntax" "SKIP" "$yaml_required"
  elif [[ $yaml_errors -eq 0 ]]; then
    echo "  PASS ($yaml_checked YAML file(s) checked)"
    add_gate_result "yaml_syntax" "PASS" ""
    update_overall_status "yaml_syntax" "PASS" "$yaml_required"
  else
    echo "  FAIL ($yaml_errors files with syntax errors)"
    add_gate_result "yaml_syntax" "FAIL" "$yaml_errors files$yaml_details"
    update_overall_status "yaml_syntax" "FAIL" "$yaml_required"
  fi
fi

# ----------------------------------------------------------------------------
# Gate 4: Targeted tests
# ----------------------------------------------------------------------------
echo ""
echo "[GATE 4] Targeted tests..."
tests_required="$(get_gate_required "targeted_tests")"
tests_enabled="$(get_gate_enabled "targeted_tests")"
tests_assertion_gate="$(get_gate_assertion_gate)"

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
    echo "  FAIL (test file not found, gate is required)"
    add_gate_result "targeted_tests" "FAIL" "Test file not found: $test_path"
    update_overall_status "targeted_tests" "FAIL" "$tests_required"
  else
    # Run tests (pass manifest, not args — tests.sh loads args as JSON array)
    if run_targeted_tests "$STORY_MANIFEST" "$tests_assertion_gate" > "$RUN_DIR/verify/tests.log" 2>&1; then
      echo "  PASS"
      add_gate_result "targeted_tests" "PASS" ""
      update_overall_status "targeted_tests" "PASS" "$tests_required"
    else
      test_exit=$?
      if [[ $test_exit -eq 2 ]]; then
        # All tests skipped / zero collected with assertion gate on
        echo "  FAIL (assertion gate: no assertions executed)"
        add_gate_result "targeted_tests" "FAIL" "Assertion gate: zero passed"
        update_overall_status "targeted_tests" "FAIL" "$tests_required"
      else
        echo "  FAIL - see $RUN_DIR/verify/tests.log"
        add_gate_result "targeted_tests" "FAIL" "See tests.log"
        update_overall_status "targeted_tests" "FAIL" "$tests_required"
      fi
    fi
  fi
fi

# ----------------------------------------------------------------------------
# Gate 5: Lint (ruff + mypy) — honours scope_to_diff
# ----------------------------------------------------------------------------
echo ""
echo "[GATE 5] Lint (ruff + mypy)..."
lint_required="$(get_gate_required "lint")"
lint_enabled="$(get_gate_enabled "lint")"
lint_scope_to_diff="$(get_gate_scope_to_diff "lint")"

if [[ "$DIFF_ENUM_STATUS" == "ERROR" ]]; then
  echo "  ERROR - candidate diff unavailable"
  add_gate_result "lint" "ERROR" "Candidate diff enumeration failed"
  OVERALL_STATUS="ERROR"
elif [[ "$lint_enabled" == "false" ]]; then
  echo "  DISABLED"
  add_gate_result "lint" "DISABLED" ""
else
  lint_files=()
  if [[ "$lint_scope_to_diff" == "true" ]]; then
    while IFS= read -r f; do
      case "$f" in
        backend/*.py)
          # Candidate diff paths are repo-root-relative; run_lint executes
          # from backend/, so pass backend-relative paths.
          if [[ -f "$REPO_ROOT/$f" ]]; then
            lint_files+=("${f#backend/}")
          fi
          ;;
      esac
    done < "$DIFF_FILES_TMP"

    if [[ ${#lint_files[@]} -eq 0 ]]; then
      echo "  PASS (no Python files in candidate diff, scope_to_diff=true)"
      add_gate_result "lint" "PASS" "No Python files in candidate diff"
      update_overall_status "lint" "PASS" "$lint_required"
    else
      if run_lint "${lint_files[@]}" > "$RUN_DIR/verify/lint.log" 2>&1; then
        echo "  PASS (${#lint_files[@]} file(s) linted, scope_to_diff=true)"
        add_gate_result "lint" "PASS" "scope_to_diff: ${#lint_files[@]} file(s)"
        update_overall_status "lint" "PASS" "$lint_required"
      else
        echo "  FAIL - see $RUN_DIR/verify/lint.log"
        add_gate_result "lint" "FAIL" "See lint.log"
        update_overall_status "lint" "FAIL" "$lint_required"
      fi
    fi
  else
    # Full-project lint semantics
    if run_lint > "$RUN_DIR/verify/lint.log" 2>&1; then
      echo "  PASS (full project)"
      add_gate_result "lint" "PASS" ""
      update_overall_status "lint" "PASS" "$lint_required"
    else
      echo "  FAIL - see $RUN_DIR/verify/lint.log"
      add_gate_result "lint" "FAIL" "See lint.log"
      update_overall_status "lint" "FAIL" "$lint_required"
    fi
  fi
fi

# ----------------------------------------------------------------------------
# Gate 6: Secrets scan — honours scope_to_diff
# Reports rule identifiers only; never prints matched secret values.
# ----------------------------------------------------------------------------
echo ""
echo "[GATE 6] Secrets scan..."
secrets_required="$(get_gate_required "secrets")"
secrets_enabled="$(get_gate_enabled "secrets")"
secrets_scope_to_diff="$(get_gate_scope_to_diff "secrets")"

if [[ "$DIFF_ENUM_STATUS" == "ERROR" ]]; then
  echo "  ERROR - candidate diff unavailable"
  add_gate_result "secrets" "ERROR" "Candidate diff enumeration failed"
  OVERALL_STATUS="ERROR"
elif [[ "$secrets_enabled" == "false" ]]; then
  echo "  DISABLED"
  add_gate_result "secrets" "DISABLED" ""
else
  # Secrets scan via Python: rule identifiers only (no secret values).
  SECRETS_LIST_TMP="$RUN_DIR/verify/.secrets-files-tmp.lst"
  TEMP_FILES+=("$SECRETS_LIST_TMP")

  if [[ "$secrets_scope_to_diff" == "true" ]]; then
    # Candidate diff files only (paths relative to repo root).
    cp "$DIFF_FILES_TMP" "$SECRETS_LIST_TMP"
    secrets_mode="candidate_diff"
  else
    # Full-repo semantics: all tracked files + candidate-diff files.
    git ls-files -z 2>/dev/null | tr '\0' '\n' > "$SECRETS_LIST_TMP" || : > "$SECRETS_LIST_TMP"
    cat "$DIFF_FILES_TMP" >> "$SECRETS_LIST_TMP"
    sort -u -o "$SECRETS_LIST_TMP" "$SECRETS_LIST_TMP"
    secrets_mode="full_repository"
  fi

  secrets_verdict_tmp="$RUN_DIR/verify/.secrets-verdict-tmp.json"
  TEMP_FILES+=("$secrets_verdict_tmp")

  "$PYTHON_BIN" - "$REPO_ROOT" "$SECRETS_LIST_TMP" "$secrets_mode" <<'PYEOF' > "$secrets_verdict_tmp"
import json
import re
import sys
from pathlib import Path

repo_root = Path(sys.argv[1])
list_file = sys.argv[2]
mode = sys.argv[3]

# Ordered rule table: identifier + compiled pattern.
RULES = [
    ("stripe_live_key", re.compile(r"sk_live_[A-Za-z0-9]+")),
    ("stripe_test_key", re.compile(r"sk_test_[A-Za-z0-9]+")),
    ("github_personal_token", re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("password_assignment", re.compile(r"password\s*=\s*['\"][^'\"]{8,}['\"]", re.IGNORECASE)),
    ("api_key_assignment", re.compile(r"api_key\s*=\s*['\"][^'\"]+['\"]", re.IGNORECASE)),
    ("secret_assignment", re.compile(r"secret\s*=\s*['\"][^'\"]+['\"]", re.IGNORECASE)),
]

files = []
try:
    with open(list_file) as fh:
        files = [line.rstrip("\n") for line in fh if line.strip()]
except OSError:
    pass

findings = []
for rel in files:
    p = repo_root / rel
    if not p.is_file():
        continue
    try:
        text = p.read_text(errors="ignore")
    except OSError:
        continue
    for rule_id, pattern in RULES:
        for lineno, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                findings.append({
                    "file": rel,
                    "rule": rule_id,
                    "line": lineno,
                    "classification": "potential_secret",
                })
                break  # one finding per rule per file is enough

print(json.dumps({"mode": mode, "findings": findings}))
PYEOF

  secrets_found_count="$("$PYTHON_BIN" -c "import json,sys; print(len(json.load(open(sys.argv[1])).get('findings', [])))" "$secrets_verdict_tmp" 2>/dev/null || echo "-1")"

  # Human-readable evidence (file, rule, line, classification — no values)
  "$PYTHON_BIN" -c "
import json, sys
verdict = json.load(open(sys.argv[1]))
for f in verdict.get('findings', []):
    print(f\"{f['file']}:{f['line']} rule={f['rule']} classification={f['classification']}\")
" "$secrets_verdict_tmp" > "$RUN_DIR/verify/secrets.log" 2>/dev/null || true
  echo "  mode: $secrets_mode" >> "$RUN_DIR/verify/secrets.log" 2>/dev/null || true

  if [[ "$secrets_found_count" == "-1" ]]; then
    echo "  ERROR - secrets scanner failed"
    add_gate_result "secrets" "ERROR" "Secrets scanner infrastructure error"
    OVERALL_STATUS="ERROR"
  elif [[ "$secrets_found_count" -gt 0 ]]; then
    first_finding="$("$PYTHON_BIN" -c "
import json, sys
f = json.load(open(sys.argv[1])).get('findings', [{}])[0]
print(f\"{f.get('file','?')}:{f.get('line','?')} rule={f.get('rule','?')}\")
" "$secrets_verdict_tmp" 2>/dev/null || echo "unknown")"
    echo "  FAIL - $secrets_found_count finding(s), first: $first_finding (see secrets.log)"
    add_gate_result "secrets" "FAIL" "$secrets_found_count finding(s): $first_finding"
    update_overall_status "secrets" "FAIL" "$secrets_required"
  else
    echo "  PASS (no secrets detected, mode=$secrets_mode)"
    add_gate_result "secrets" "PASS" "mode=$secrets_mode"
    update_overall_status "secrets" "PASS" "$secrets_required"
  fi
fi

# ----------------------------------------------------------------------------
# Gate 7: git diff --check
# ----------------------------------------------------------------------------
echo ""
echo "[GATE 7] git diff --check..."
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

# Determine final overall status.
# Rules:
#   - any gate ERROR → overall ERROR
#   - any required gate FAIL → overall FAIL
#   - any required gate that never executed (absent from results) → ERROR
#   - otherwise → PASS (SKIP/DISABLED are acceptable)
FINAL_STATUS="$("$PYTHON_BIN" -c "
import json, sys

with open(sys.argv[1]) as f:
    gates = json.load(f)
with open(sys.argv[2]) as f:
    gate_config = json.load(f)

statuses = {g['name']: g['status'] for g in gates}

for g in gates:
    if g['status'] == 'ERROR':
        print('ERROR')
        sys.exit(0)

required_gates = [name for name, cfg in gate_config.items()
                  if cfg.get('required', True)]

for name in required_gates:
    status = statuses.get(name)
    if status is None:
        print('ERROR')
        sys.exit(0)

failed = [name for name in required_gates
          if statuses.get(name) not in ('PASS', 'DISABLED', 'SKIP')]
if failed:
    print('FAIL')
else:
    print('PASS')
" "$GATES_JSON_TMP" "$GATE_CONFIG_TMP" 2>/dev/null || echo "ERROR")"

if [[ -n "$INTERNAL_ERROR" ]]; then
  OVERALL_STATUS="ERROR"
elif [[ "$FINAL_STATUS" == "ERROR" ]]; then
  OVERALL_STATUS="ERROR"
elif [[ "$FINAL_STATUS" == "FAIL" || "$OVERALL_STATUS" == "FAIL" ]]; then
  OVERALL_STATUS="FAIL"
else
  OVERALL_STATUS="PASS"
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

# ============================================================================
# WP-AL-1B3: Failure context collection
# ============================================================================
echo ""
echo "[POST-GATE] Collecting failure context..."

FAILURE_CONTEXT_SCRIPT="$SCRIPT_DIR/lib/failure_context.py"
FAILURE_CONTEXT_OUTPUT="$RUN_DIR/reports/failure-context.json"

if [[ -f "$FAILURE_CONTEXT_SCRIPT" ]]; then
  if "$PYTHON_BIN" "$FAILURE_CONTEXT_SCRIPT" collect \
      --run-dir "$RUN_DIR" \
      --repo-root "$REPO_ROOT" \
      --manifest "$STORY_MANIFEST" \
      --output "$FAILURE_CONTEXT_OUTPUT" 2>> "$RUN_DIR/verify/.failure-context-collector.log"; then
    echo "  SUCCESS - failure-context.json written"
  else
    COLLECTOR_EXIT=$?
    echo "  FAILED - collector exited with code $COLLECTOR_EXIT"
    echo "  See $RUN_DIR/verify/.failure-context-collector.log"

    # Emit safe infrastructure-error artifact (collector failure)
    # Do not recursively invoke the collector
    "$PYTHON_BIN" -c "
import json, sys
from datetime import datetime

error_artifact = {
    'schema_version': '1.0',
    'run_id': sys.argv[1] if len(sys.argv) > 1 else 'unknown',
    'story_id': sys.argv[2] if len(sys.argv) > 2 else 'unknown',
    'generated_at': datetime.utcnow().isoformat() + 'Z',
    'candidate_identity': {
        'base_commit': '',
        'candidate_commit': None,
        'candidate_state': 'working_tree',
        'candidate_diff_digest': '0' * 64
    },
    'collection_status': 'failed',
    'collection_errors': [
        {
            'artifact_id': 'failure_context_collector',
            'error_code': 'COLLECTOR_FAILED',
            'safe_summary': 'Failure context collector exited with non-zero status'
        }
    ],
    'overall_verification_status': 'ERROR',
    'gate_verdicts': {},
    'failing_gate_ids': [],
    'repair_guidance': [],
    'artifact_refs': {
        'verify_result': 'reports/verify-result.json',
        'gate_logs': []
    },
    'limits': {
        'max_excerpt_lines': 50,
        'max_excerpt_bytes': 4096,
        'max_diagnostics_per_gate': 10,
        'max_total_diagnostics': 50
    },
    'redaction_applied': False,
    'redaction_count': 0
}

with open(sys.argv[3], 'w') as f:
    json.dump(error_artifact, f, indent=2)
" "$RUN_ID" "$STORY_ID" "$FAILURE_CONTEXT_OUTPUT" 2>/dev/null || true

    # Override OVERALL_STATUS to ERROR (collector failure)
    OVERALL_STATUS="ERROR"
    echo "  OVERALL: ERROR (collector failure)"
    exit 2
  fi
else
  echo "  SKIPPED - failure_context.py not found (WP-AL-1B3 not yet deployed)"
fi

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
