#!/usr/bin/env bash
# Scope verification: manifest-driven candidate-diff scope gate.
#
# WP-AL-1B2B: the scope gate is delegated to harness.py scope_check:
#   - allowed_paths / forbidden_paths come from the validated story manifest;
#   - gitwildmatch semantics are implemented natively in harness.py (single
#     implementation, no duplicated pattern logic in Bash);
#   - candidate diff = committed/staged/working-tree changes + untracked
#     files vs the manifest base_commit.
#
# check_scope exit codes:
#   0 = NO_CHANGES or SCOPE_OK (status is the first output line)
#   1 = SCOPE_VIOLATIONS
#   2 = infrastructure error (missing manifest, git failure, bad base commit)
#
# NOTE: no set -euo pipefail here — this file is sourced, not executed.

check_scope() {
  local manifest_file="${1:-}"

  if [[ -z "$manifest_file" || ! -f "$manifest_file" ]]; then
    echo "SCOPE_ERROR"
    echo "ERROR_DETAIL: No validated story manifest provided"
    return 2
  fi

  local verdict_json scope_exit
  verdict_json="$("$PYTHON_BIN" "$HARNESS_PY" scope_check "$manifest_file" "$REPO_ROOT" 2>/dev/null)"
  scope_exit=$?

  # Normalize unexpected crashes to infrastructure error
  if [[ $scope_exit -ne 0 && $scope_exit -ne 1 ]]; then
    scope_exit=2
  fi

  if [[ -z "$verdict_json" ]]; then
    echo "SCOPE_ERROR"
    echo "ERROR_DETAIL: scope_check produced no verdict"
    return 2
  fi

  # Render human-readable verdict (paths + reasons only, no secret values).
  local rendered
  rendered="$("$PYTHON_BIN" - "$verdict_json" <<'PYEOF'
import json
import sys

try:
    verdict = json.loads(sys.argv[1])
except Exception:
    print("SCOPE_ERROR")
    print("ERROR_DETAIL: unreadable scope verdict")
    sys.exit(2)
print(verdict.get("status", "SCOPE_ERROR"))
if verdict.get("file_count"):
    print("candidate_diff_files: {}".format(verdict["file_count"]))
for v in verdict.get("violations", []):
    suffix = " (matches {})".format(v["pattern"]) if v.get("pattern") else ""
    print("{}: {}{}".format(v["reason"], v["file"], suffix))
if verdict.get("error"):
    print("ERROR_DETAIL: {}".format(verdict["error"]))
PYEOF
)"

  if [[ -n "$rendered" ]]; then
    echo "$rendered"
  else
    echo "SCOPE_ERROR"
    echo "ERROR_DETAIL: scope verdict rendering failed"
    return 2
  fi

  return "$scope_exit"
}

check_untracked() {
  local untracked
  untracked="$(git ls-files --others --exclude-standard)"

  if [[ -z "$untracked" ]]; then
    echo "NO_UNTRACKED"
    return 0
  fi

  echo "UNTRACKED_FILES:"
  echo "$untracked"
  return 0
}

check_json_syntax() {
  local file="$1"

  if ! "$PYTHON_BIN" -m json.tool "$file" > /dev/null 2>&1; then
    echo "JSON_SYNTAX_ERROR: $file"
    return 1
  fi

  echo "JSON_OK: $file"
  return 0
}

check_yaml_syntax() {
  local file="$1"

  # Safe: pass file path via argv, not shell interpolation
  if ! "$PYTHON_BIN" -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))" "$file" 2>/dev/null; then
    echo "YAML_SYNTAX_ERROR: $file"
    return 1
  fi

  echo "YAML_OK: $file"
  return 0
}
