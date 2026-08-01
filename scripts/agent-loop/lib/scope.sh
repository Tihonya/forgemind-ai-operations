#!/usr/bin/env bash
# Scope verification: diff, forbidden files, allowed paths

# NOTE: no set -euo pipefail here — this file is sourced, not executed directly

check_scope() {
  local manifest_file="${1:-}"

  # Load allowed/forbidden from manifest if provided
  if [[ -n "$manifest_file" && -f "$manifest_file" ]]; then
    # TODO: parse JSON manifest for story-specific allowed/forbidden
    echo "Using story manifest: $manifest_file"
  fi

  # Get diff since last commit
  local diff_files
  diff_files="$(git diff --name-only HEAD 2>/dev/null || echo "")"

  if [[ -z "$diff_files" ]]; then
    echo "NO_CHANGES (clean working tree)"
    return 0
  fi

  local violations=()

  while IFS= read -r file; do
    # Check forbidden patterns
    for pattern in "${FORBIDDEN_PATHS[@]}"; do
      if [[ "$file" =~ $pattern ]]; then
        violations+=("FORBIDDEN: $file (matches $pattern)")
      fi
    done

    # Check if file is in allowed paths
    local allowed=false
    for pattern in "${ALLOWED_PATHS[@]}"; do
      if [[ "$file" =~ $pattern ]]; then
        allowed=true
        break
      fi
    done

    if [[ "$allowed" == "false" ]]; then
      violations+=("NOT_ALLOWED: $file (not in ALLOWED_PATHS)")
    fi
  done <<< "$diff_files"

  if [[ ${#violations[@]} -gt 0 ]]; then
    echo "SCOPE_VIOLATIONS:"
    printf '%s\n' "${violations[@]}"
    return 1
  fi

  echo "SCOPE_OK"
  echo "$diff_files"
  return 0
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
