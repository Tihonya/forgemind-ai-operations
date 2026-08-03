#!/usr/bin/env bash
# Test execution and assertion counting
#
# WP-AL-1B2B: lint scoping
#   - scope_to_diff=true  → ruff/mypy run only on the changed Python files of
#     the candidate diff (no full-project `ruff check .`);
#   - scope_to_diff=false → full-project lint (backend/ tree) semantics.
#
# NOTE: no set -euo pipefail here -- this file is sourced, not executed.

run_targeted_tests() {
  local manifest_file="${1:-}"
  local assertion_gate="${2:-true}"

  # Load test args as JSON array from manifest (no shell word splitting)
  local test_args_json
  test_args_json="$("$PYTHON_BIN" "$HARNESS_PY" load_test_args "$manifest_file" 2>/dev/null || echo "[]")"

  if [[ "$test_args_json" == "[]" || -z "$test_args_json" ]]; then
    # Fallback: run all integration tests
    echo "FALLBACK: running all integration tests"
    local report_tmpdir
    report_tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/agent-loop-report-XXXXXX")"
    local report_file="$report_tmpdir/pytest-report.xml"
    run_pytest_with_junit_array "$report_file" "$report_tmpdir" "$assertion_gate" "tests/integration/" "-v" "--junitxml=$report_file"
    return $?
  fi

  # Convert JSON array to bash array safely via Python
  local report_tmpdir
  report_tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/agent-loop-report-XXXXXX")"
  local report_file="$report_tmpdir/pytest-report.xml"

  # Parse JSON array and replace {report_file} placeholder with safe tmp path
  local -a test_array=()
  while IFS= read -r arg; do
    # Replace placeholder
    arg="${arg//\{report_file\}/$report_file}"
    test_array+=("$arg")
  done < <("$PYTHON_BIN" -c "import json,sys; [print(a) for a in json.loads(sys.argv[1])]" "$test_args_json")

  if [[ ${#test_array[@]} -eq 0 ]]; then
    echo "NO_TEST_ARGS"
    return 1
  fi

  echo "Running pytest in backend/ with ${#test_array[@]} args"
  run_pytest_with_junit_array "$report_file" "$report_tmpdir" "$assertion_gate" "${test_array[@]}"
  return $?
}

run_pytest_with_junit_array() {
  local report_file="$1"
  local report_tmpdir="$2"
  local assertion_gate="$3"
  shift 3
  local -a pytest_array=("$@")
  local backend_dir="$REPO_ROOT/backend"

  # Run pytest with JUnit XML report (built-in, no extra deps)
  (cd "$backend_dir" && "$PYTEST_BIN" "${pytest_array[@]}") > "$RUN_DIR/verify/pytest-stdout.log" 2>&1
  local exit_code=$?

  # Copy report from tmpdir to RUN_DIR if it exists
  if [[ -f "$report_file" ]]; then
    cp "$report_file" "$RUN_DIR/verify/pytest-report.xml" 2>/dev/null || true
  fi

  # Cleanup tmp dir
  rm -rf "$report_tmpdir" 2>/dev/null || true

  local final_report="$RUN_DIR/verify/pytest-report.xml"
  if [[ -f "$final_report" ]]; then
    analyze_pytest_junit "$final_report" "$assertion_gate"
    local analyze_exit=$?
    return $analyze_exit
  else
    echo "PYTEST_NO_REPORT (pytest exit code: $exit_code)"
    return 1
  fi
}

analyze_pytest_junit() {
  local report_file="$1"
  local assertion_gate="${2:-true}"

  "$PYTHON_BIN" "$HARNESS_PY" parse_junit "$report_file" "$assertion_gate"
  return $?
}

# run_lint [file...]
#   With arguments: lint only those Python files (diff-scoped mode).
#   Without arguments: full-project lint over the backend tree.
run_lint() {
  local backend_dir="$REPO_ROOT/backend"
  local ruff_exit=0
  local mypy_exit=0
  local -a target_files=("$@")

  if [[ ${#target_files[@]} -gt 0 ]]; then
    echo "LINT_SCOPED_TO_DIFF: ${#target_files[@]} file(s)"
  else
    echo "LINT_FULL_PROJECT"
  fi

  if [[ -n "${RUFF_BIN:-}" ]]; then
    if [[ ${#target_files[@]} -gt 0 ]]; then
      if ! (cd "$backend_dir" && "$RUFF_BIN" check "${target_files[@]}" > "$RUN_DIR/verify/ruff.log" 2>&1); then
        ruff_exit=1
        echo "RUFF_FAIL"
      else
        echo "RUFF_OK"
      fi
    else
      if ! (cd "$backend_dir" && "$RUFF_BIN" check . > "$RUN_DIR/verify/ruff.log" 2>&1); then
        ruff_exit=1
        echo "RUFF_FAIL"
      else
        echo "RUFF_OK"
      fi
    fi
  else
    echo "RUFF_SKIP (ruff not found)"
  fi

  if [[ -n "${MYPY_BIN:-}" ]]; then
    if [[ ${#target_files[@]} -gt 0 ]]; then
      if ! (cd "$backend_dir" && "$MYPY_BIN" "${target_files[@]}" > "$RUN_DIR/verify/mypy.log" 2>&1); then
        mypy_exit=1
        echo "MYPY_FAIL"
      else
        echo "MYPY_OK"
      fi
    else
      if ! (cd "$backend_dir" && "$MYPY_BIN" app/ > "$RUN_DIR/verify/mypy.log" 2>&1); then
        mypy_exit=1
        echo "MYPY_FAIL"
      else
        echo "MYPY_OK"
      fi
    fi
  else
    echo "MYPY_SKIP (mypy not found)"
  fi

  return $((ruff_exit + mypy_exit))
}
