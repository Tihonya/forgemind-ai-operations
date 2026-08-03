#!/usr/bin/env bash
# Identity Guard — formal phase validation before each agent-loop phase.
#
# Sourced by run-story.sh, verify-story.sh, etc.
# Do NOT set -e here — this file is sourced.
set -uo pipefail

# Resolve path safely (no symlink following for security, but canonicalize . and ..)
resolve_path_strict() {
  local path="$1"
  if [[ ! -e "$path" ]]; then
    echo ""
    return 1
  fi
  # Use readlink -f only if target exists; reject symlinks that escape workspace
  local resolved
  resolved="$(cd "$path" 2>/dev/null && pwd -P)" || resolved=""
  if [[ -z "$resolved" ]]; then
    echo ""
    return 1
  fi
  echo "$resolved"
}

# Resolve main ForgeMind worktree path (forbidden for agent-loop execution)
# Resolution order:
#   1. Explicit FORBIDDEN_MAIN_WORKTREE env var
#   2. FORGEMIND_MAIN_ROOT env var (canonical project config)
#   3. Fail-closed: INFRASTRUCTURE_ERROR if neither resolves to existing path

if [[ -n "${FORBIDDEN_MAIN_WORKTREE:-}" ]]; then
  _resolved_forbidden="$(resolve_path_strict "$FORBIDDEN_MAIN_WORKTREE")" || _resolved_forbidden=""
  if [[ -z "$_resolved_forbidden" ]]; then
    echo "INFRASTRUCTURE_ERROR: FORBIDDEN_MAIN_WORKTREE='$FORBIDDEN_MAIN_WORKTREE' does not resolve to existing path" >&2
    exit 2
  fi
elif [[ -n "${FORGEMIND_MAIN_ROOT:-}" ]]; then
  _resolved_forbidden="$(resolve_path_strict "$FORGEMIND_MAIN_ROOT")" || _resolved_forbidden=""
  if [[ -z "$_resolved_forbidden" ]]; then
    echo "INFRASTRUCTURE_ERROR: FORGEMIND_MAIN_ROOT='$FORGEMIND_MAIN_ROOT' does not resolve to existing path" >&2
    exit 2
  fi
  FORBIDDEN_MAIN_WORKTREE="$FORGEMIND_MAIN_ROOT"
else
  echo "INFRASTRUCTURE_ERROR: neither FORBIDDEN_MAIN_WORKTREE nor FORGEMIND_MAIN_ROOT is set" >&2
  exit 2
fi

# Check for path traversal or symlink escape
check_path_safety() {
  local path="$1"
  local workspace_root="$2"

  # Resolve both paths
  local resolved_path resolved_ws
  resolved_path="$(resolve_path_strict "$path")" || {
    echo "PATH_NOT_RESOLVABLE|$path"
    return 1
  }
  resolved_ws="$(resolve_path_strict "$workspace_root")" || {
    echo "WORKSPACE_NOT_RESOLVABLE|$workspace_root"
    return 1
  }

  # Check that resolved path starts with resolved workspace
  if [[ "$resolved_path" != "$resolved_ws" && "$resolved_path" != "$resolved_ws"/* ]]; then
    echo "PATH_TRAVERSAL|$path escapes $workspace_root"
    return 1
  fi

  # Check for symlink component that escapes workspace
  local original_resolved
  original_resolved="$(cd "$path" 2>/dev/null && pwd -L)" || original_resolved=""
  if [[ -n "$original_resolved" && "$original_resolved" != "$resolved_path" ]]; then
    # There's a symlink; check if it stays within workspace
    local symlink_target
    symlink_target="$(readlink -f "$path" 2>/dev/null)" || symlink_target=""
    if [[ -n "$symlink_target" && "$symlink_target" != "$resolved_ws" && "$symlink_target" != "$resolved_ws"/* ]]; then
      echo "SYMLINK_ESCAPE|$path symlink target $symlink_target escapes workspace"
      return 1
    fi
  fi

  echo "OK"
  return 0
}

# Write infrastructure error artifact (no secrets)
write_infra_error() {
  local output_file="$1"
  local error_code="$2"
  local phase="$3"
  local failed_check="$4"
  local expected="$5"
  local actual="$6"
  local project_id="${7:-unknown}"
  local run_id="${8:-unknown}"
  local slot_id="${9:-unknown}"
  local story_id="${10:-unknown}"

  "$PYTHON_BIN" "$HARNESS_PY" atomic_write "$output_file" "$(cat <<EOF
{
  "schema_version": "1.0",
  "status": "INFRASTRUCTURE_ERROR",
  "error_code": "$error_code",
  "phase": "$phase",
  "failed_check": "$failed_check",
  "expected": "$expected",
  "actual": "$actual",
  "project_id": "$project_id",
  "run_id": "$run_id",
  "slot_id": "$slot_id",
  "story_id": "$story_id",
  "timestamp": "$(date -Iseconds)"
}
EOF
)"
}

# Bootstrap guard — runs before passport creation
# Validates: worktree path, branch, git root, forbidden main worktree
bootstrap_guard() {
  local workspace_root="$1"
  local expected_branch="$2"
  local phase="${3:-allocate}"
  local error_dir="${4:-.}"

  local project_id="${PROJECT_ID:-forgemind}"
  local run_id="${RUN_ID:-unknown}"
  local slot_id="${SLOT_ID:-unknown}"
  local story_id="${STORY_ID:-unknown}"

  # Resolve workspace root
  local resolved_ws
  resolved_ws="$(resolve_path_strict "$workspace_root")" || {
    write_infra_error "$error_dir/guard-error.json" \
      "BOOTSTRAP_WORKSPACE_UNRESOLVABLE" \
      "$phase" \
      "workspace_root_resolvable" \
      "resolvable absolute path" \
      "workspace_root not found or not accessible: $workspace_root" \
      "$project_id" "$run_id" "$slot_id" "$story_id"
    return 1
  }

  # Check: workspace_root != main ForgeMind worktree
  local resolved_main
  resolved_main="$(resolve_path_strict "$FORBIDDEN_MAIN_WORKTREE")" || resolved_main=""
  if [[ -n "$resolved_main" && "$resolved_ws" == "$resolved_main" ]]; then
    write_infra_error "$error_dir/guard-error.json" \
      "BOOTSTRAP_MAIN_WORKTREE_FORBIDDEN" \
      "$phase" \
      "workspace_not_main_worktree" \
      "workspace_root != $FORBIDDEN_MAIN_WORKTREE" \
      "workspace_root equals main ForgeMind worktree" \
      "$project_id" "$run_id" "$slot_id" "$story_id"
    return 1
  fi

  # Check: current pwd is under workspace_root
  local resolved_pwd
  resolved_pwd="$(resolve_path_strict "$(pwd)")" || {
    write_infra_error "$error_dir/guard-error.json" \
      "BOOTSTRAP_PWD_UNRESOLVABLE" \
      "$phase" \
      "pwd_resolvable" \
      "resolvable absolute path" \
      "current directory not accessible" \
      "$project_id" "$run_id" "$slot_id" "$story_id"
    return 1
  }

  if [[ "$resolved_pwd" != "$resolved_ws" && "$resolved_pwd" != "$resolved_ws"/* ]]; then
    write_infra_error "$error_dir/guard-error.json" \
      "BOOTSTRAP_PWD_OUTSIDE_WORKSPACE" \
      "$phase" \
      "pwd_under_workspace_root" \
      "pwd under $resolved_ws" \
      "pwd=$resolved_pwd" \
      "$project_id" "$run_id" "$slot_id" "$story_id"
    return 1
  fi

  # Check: git toplevel matches workspace_root
  local git_toplevel
  git_toplevel="$(git rev-parse --show-toplevel 2>/dev/null)" || {
    write_infra_error "$error_dir/guard-error.json" \
      "BOOTSTRAP_NOT_GIT_REPO" \
      "$phase" \
      "git_repository" \
      "inside a git repository" \
      "git rev-parse --show-toplevel failed" \
      "$project_id" "$run_id" "$slot_id" "$story_id"
    return 1
  }

  local resolved_git
  resolved_git="$(resolve_path_strict "$git_toplevel")" || resolved_git=""
  if [[ "$resolved_git" != "$resolved_ws" ]]; then
    write_infra_error "$error_dir/guard-error.json" \
      "BOOTSTRAP_GIT_ROOT_MISMATCH" \
      "$phase" \
      "git_toplevel_matches_workspace_root" \
      "$resolved_ws" \
      "$resolved_git" \
      "$project_id" "$run_id" "$slot_id" "$story_id"
    return 1
  fi

  # Check: branch matches expected
  local current_branch
  current_branch="$(git branch --show-current 2>/dev/null)" || {
    write_infra_error "$error_dir/guard-error.json" \
      "BOOTSTRAP_BRANCH_UNRESOLVABLE" \
      "$phase" \
      "branch_resolvable" \
      "resolvable branch name" \
      "git branch --show-current failed" \
      "$project_id" "$run_id" "$slot_id" "$story_id"
    return 1
  }

  if [[ "$current_branch" != "$expected_branch" ]]; then
    write_infra_error "$error_dir/guard-error.json" \
      "BOOTSTRAP_BRANCH_MISMATCH" \
      "$phase" \
      "branch_matches_expected" \
      "$expected_branch" \
      "$current_branch" \
      "$project_id" "$run_id" "$slot_id" "$story_id"
    return 1
  fi

  return 0
}

# Phase guard — runs before each phase (implement, verify, review, repair, report)
# Requires passport file to exist
phase_guard() {
  local passport_file="$1"
  local phase="$2"
  local expected_workspace_type="$3"
  local expected_role="$4"
  local error_dir="${5:-.}"

  local project_id="${PROJECT_ID:-forgemind}"
  local run_id="${RUN_ID:-unknown}"
  local slot_id="${SLOT_ID:-unknown}"
  local story_id="${STORY_ID:-unknown}"

  # Check passport file exists
  if [[ ! -f "$passport_file" ]]; then
    write_infra_error "$error_dir/guard-error.json" \
      "PASSPORT_MISSING" \
      "$phase" \
      "passport_file_exists" \
      "passport file at $passport_file" \
      "file not found" \
      "$project_id" "$run_id" "$slot_id" "$story_id"
    return 1
  fi

  # Validate passport JSON is well-formed and has required fields
  local passport_valid
  passport_valid="$("$PYTHON_BIN" -c "
import json, sys
try:
    with open(sys.argv[1]) as f:
        data = json.load(f)
    required = ['schema_version', 'project_id', 'run_id', 'slot_id', 'story_id',
                 'role', 'phase', 'workspace_type', 'workspace_root',
                 'expected_branch', 'base_commit', 'manifest_path', 'artifact_root']
    missing = [k for k in required if k not in data]
    if missing:
        print(f'MISSING_FIELDS:{\"|\".join(missing)}')
        sys.exit(1)
    print('OK')
except json.JSONDecodeError as e:
    print(f'MALFORMED_JSON:{e}')
    sys.exit(1)
except FileNotFoundError:
    print('FILE_NOT_FOUND')
    sys.exit(1)
except Exception as e:
    print(f'ERROR:{e}')
    sys.exit(1)
" "$passport_file" 2>&1)" || passport_valid="EXCEPTION:$?"

  if [[ "$passport_valid" != "OK" ]]; then
    local error_code="PASSPORT_INVALID"
    local failed_check="passport_json_valid"
    local expected="valid JSON with required fields"
    local actual="$passport_valid"

    # Try to extract IDs from passport for error artifact
    local p_pid p_rid p_sid p_stid
    p_pid="$("$PYTHON_BIN" -c "import json; print(json.load(open('$passport_file')).get('project_id','unknown'))" 2>/dev/null || echo "unknown")"
    p_rid="$("$PYTHON_BIN" -c "import json; print(json.load(open('$passport_file')).get('run_id','unknown'))" 2>/dev/null || echo "unknown")"
    p_sid="$("$PYTHON_BIN" -c "import json; print(json.load(open('$passport_file')).get('slot_id','unknown'))" 2>/dev/null || echo "unknown")"
    p_stid="$("$PYTHON_BIN" -c "import json; print(json.load(open('$passport_file')).get('story_id','unknown'))" 2>/dev/null || echo "unknown")"

    write_infra_error "$error_dir/guard-error.json" \
      "$error_code" "$phase" "$failed_check" "$expected" "$actual" \
      "$p_pid" "$p_rid" "$p_sid" "$p_stid"
    return 1
  fi

  # Load passport fields from JSON
  eval "$("$PYTHON_BIN" -c "
import json, sys, shlex
with open(sys.argv[1]) as f:
    data = json.load(f)
for key in ['project_id', 'run_id', 'slot_id', 'story_id', 'role', 'phase',
            'workspace_type', 'workspace_root', 'expected_branch', 'base_commit',
            'manifest_path', 'artifact_root', 'candidate_commit']:
    val = data.get(key, '')
    if val is None:
        val = ''
    print(f'P_{key}={shlex.quote(str(val))}')
" "$passport_file")"

  # Check 1: resolved absolute pwd matches workspace_root
  local resolved_pwd resolved_ws
  resolved_pwd="$(resolve_path_strict "$(pwd)")" || {
    write_infra_error "$error_dir/guard-error.json" \
      "GUARD_PWD_UNRESOLVABLE" "$phase" "pwd_resolvable" \
      "resolvable absolute path" "pwd not accessible" \
      "$P_project_id" "$P_run_id" "$P_slot_id" "$P_story_id"
    return 1
  }

  resolved_ws="$(resolve_path_strict "$P_workspace_root")" || {
    write_infra_error "$error_dir/guard-error.json" \
      "GUARD_WORKSPACE_UNRESOLVABLE" "$phase" "workspace_root_resolvable" \
      "resolvable absolute path" "workspace_root not accessible: $P_workspace_root" \
      "$P_project_id" "$P_run_id" "$P_slot_id" "$P_story_id"
    return 1
  }

  if [[ "$resolved_pwd" != "$resolved_ws" && "$resolved_pwd" != "$resolved_ws"/* ]]; then
    write_infra_error "$error_dir/guard-error.json" \
      "GUARD_PWD_MISMATCH" "$phase" "pwd_matches_workspace_root" \
      "$resolved_ws" "$resolved_pwd" \
      "$P_project_id" "$P_run_id" "$P_slot_id" "$P_story_id"
    return 1
  fi

  # Check 2: git toplevel matches workspace_root
  local git_toplevel resolved_git
  git_toplevel="$(git rev-parse --show-toplevel 2>/dev/null)" || {
    write_infra_error "$error_dir/guard-error.json" \
      "GUARD_NOT_GIT_REPO" "$phase" "git_repository" \
      "inside a git repository" "git rev-parse --show-toplevel failed" \
      "$P_project_id" "$P_run_id" "$P_slot_id" "$P_story_id"
    return 1
  }

  resolved_git="$(resolve_path_strict "$git_toplevel")" || resolved_git=""
  if [[ "$resolved_git" != "$resolved_ws" ]]; then
    write_infra_error "$error_dir/guard-error.json" \
      "GUARD_GIT_ROOT_MISMATCH" "$phase" "git_toplevel_matches_workspace_root" \
      "$resolved_ws" "$resolved_git" \
      "$P_project_id" "$P_run_id" "$P_slot_id" "$P_story_id"
    return 1
  fi

  # Check 3: branch matches expected_branch
  local current_branch
  current_branch="$(git branch --show-current 2>/dev/null)" || {
    write_infra_error "$error_dir/guard-error.json" \
      "GUARD_BRANCH_UNRESOLVABLE" "$phase" "branch_resolvable" \
      "resolvable branch name" "git branch --show-current failed" \
      "$P_project_id" "$P_run_id" "$P_slot_id" "$P_story_id"
    return 1
  }

  if [[ "$current_branch" != "$P_expected_branch" ]]; then
    write_infra_error "$error_dir/guard-error.json" \
      "GUARD_BRANCH_MISMATCH" "$phase" "branch_matches_expected" \
      "$P_expected_branch" "$current_branch" \
      "$P_project_id" "$P_run_id" "$P_slot_id" "$P_story_id"
    return 1
  fi

  # Check 4: base_commit exists
  if ! git cat-file -t "$P_base_commit" >/dev/null 2>&1; then
    write_infra_error "$error_dir/guard-error.json" \
      "GUARD_BASE_COMMIT_MISSING" "$phase" "base_commit_exists" \
      "valid git commit" "commit not found: $P_base_commit" \
      "$P_project_id" "$P_run_id" "$P_slot_id" "$P_story_id"
    return 1
  fi

  # Check 5: HEAD descends from base_commit
  if ! git merge-base --is-ancestor "$P_base_commit" HEAD 2>/dev/null; then
    # Also allow HEAD == base_commit (already checked above with cat-file)
    local head_commit
    head_commit="$(git rev-parse HEAD 2>/dev/null)" || head_commit=""
    if [[ "$head_commit" != "$P_base_commit" ]]; then
      write_infra_error "$error_dir/guard-error.json" \
        "GUARD_HEAD_NOT_DESCENDANT" "$phase" "HEAD_descends_from_base_commit" \
        "HEAD is descendant of $P_base_commit" \
        "HEAD does not descend from base_commit" \
        "$P_project_id" "$P_run_id" "$P_slot_id" "$P_story_id"
      return 1
    fi
  fi

  # Check 6: project_id/run_id/slot_id/story_id match environment
  if [[ "$P_project_id" != "${PROJECT_ID:-$P_project_id}" ]]; then
    write_infra_error "$error_dir/guard-error.json" \
      "GUARD_PROJECT_ID_MISMATCH" "$phase" "project_id_matches_environment" \
      "${PROJECT_ID}" "$P_project_id" \
      "$P_project_id" "$P_run_id" "$P_slot_id" "$P_story_id"
    return 1
  fi

  if [[ -n "${RUN_ID:-}" && "$P_run_id" != "$RUN_ID" ]]; then
    write_infra_error "$error_dir/guard-error.json" \
      "GUARD_RUN_ID_MISMATCH" "$phase" "run_id_matches_environment" \
      "$RUN_ID" "$P_run_id" \
      "$P_project_id" "$P_run_id" "$P_slot_id" "$P_story_id"
    return 1
  fi

  if [[ -n "${SLOT_ID:-}" && "$P_slot_id" != "$SLOT_ID" ]]; then
    write_infra_error "$error_dir/guard-error.json" \
      "GUARD_SLOT_ID_MISMATCH" "$phase" "slot_id_matches_environment" \
      "$SLOT_ID" "$P_slot_id" \
      "$P_project_id" "$P_run_id" "$P_slot_id" "$P_story_id"
    return 1
  fi

  if [[ -n "${STORY_ID:-}" && "$P_story_id" != "$STORY_ID" ]]; then
    write_infra_error "$error_dir/guard-error.json" \
      "GUARD_STORY_ID_MISMATCH" "$phase" "story_id_matches_environment" \
      "$STORY_ID" "$P_story_id" \
      "$P_project_id" "$P_run_id" "$P_slot_id" "$P_story_id"
    return 1
  fi

  # Check 7: role is allowed for phase
  local role_ok
  role_ok="$("$PYTHON_BIN" -c "
import sys
phase = sys.argv[1]
role = sys.argv[2]
phase_role_map = {
    'allocate': ['manager'],
    'implement': ['implementer'],
    'verify': ['implementer', 'verifier'],
    'review': ['reviewer'],
    'repair': ['repair'],
    'report': ['manager', 'reporter']
}
allowed = phase_role_map.get(phase, [])
if role in allowed or not allowed:
    print('OK')
else:
    print(f'FAIL:{role} not allowed for {phase}, allowed={allowed}')
" "$phase" "$P_role" 2>/dev/null)" || role_ok="EXCEPTION"

  if [[ "$role_ok" != "OK" ]]; then
    write_infra_error "$error_dir/guard-error.json" \
      "GUARD_ROLE_NOT_ALLOWED" "$phase" "role_allowed_for_phase" \
      "allowed role for $phase" "$role_ok" \
      "$P_project_id" "$P_run_id" "$P_slot_id" "$P_story_id"
    return 1
  fi

  # Check 8: workspace_type matches phase
  if [[ "$P_workspace_type" != "$expected_workspace_type" ]]; then
    write_infra_error "$error_dir/guard-error.json" \
      "GUARD_WORKSPACE_TYPE_MISMATCH" "$phase" "workspace_type_matches_phase" \
      "$expected_workspace_type" "$P_workspace_type" \
      "$P_project_id" "$P_run_id" "$P_slot_id" "$P_story_id"
    return 1
  fi

  # Check 9: workspace_root != main ForgeMind root
  local resolved_main
  resolved_main="$(resolve_path_strict "$FORBIDDEN_MAIN_WORKTREE")" || resolved_main=""
  if [[ -n "$resolved_main" && "$resolved_ws" == "$resolved_main" ]]; then
    write_infra_error "$error_dir/guard-error.json" \
      "GUARD_MAIN_WORKTREE_FORBIDDEN" "$phase" "workspace_not_main_worktree" \
      "workspace_root != $FORBIDDEN_MAIN_WORKTREE" \
      "workspace_root equals main ForgeMind worktree" \
      "$P_project_id" "$P_run_id" "$P_slot_id" "$P_story_id"
    return 1
  fi

  # Check 10: artifact_root belongs to current run/slot
  local resolved_artifact
  resolved_artifact="$(resolve_path_strict "$P_artifact_root")" || {
    write_infra_error "$error_dir/guard-error.json" \
      "GUARD_ARTIFACT_ROOT_UNRESOLVABLE" "$phase" "artifact_root_resolvable" \
      "resolvable absolute path" "artifact_root not accessible: $P_artifact_root" \
      "$P_project_id" "$P_run_id" "$P_slot_id" "$P_story_id"
    return 1
  }

  if [[ "$resolved_artifact" != *"$P_run_id"* && "$resolved_artifact" != *"$P_slot_id"* ]]; then
    write_infra_error "$error_dir/guard-error.json" \
      "GUARD_ARTIFACT_ROOT_MISMATCH" "$phase" "artifact_root_belongs_to_run_slot" \
      "artifact_root contains run_id or slot_id" \
      "artifact_root=$resolved_artifact does not contain run_id=$P_run_id or slot_id=$P_slot_id" \
      "$P_project_id" "$P_run_id" "$P_slot_id" "$P_story_id"
    return 1
  fi

  # Check 11: manifest belongs to same project/run/slot/story
  if [[ -f "$P_manifest_path" ]]; then
    local manifest_ok
    manifest_ok="$("$PYTHON_BIN" -c "
import json, sys
try:
    with open(sys.argv[1]) as f:
        m = json.load(f)
    errors = []
    if m.get('project_id', '$P_project_id') != '$P_project_id':
        errors.append('project_id')
    if m.get('run_id', '$P_run_id') != '$P_run_id':
        errors.append('run_id')
    if m.get('slot_id', '$P_slot_id') != '$P_slot_id':
        errors.append('slot_id')
    if m.get('story_id', '$P_story_id') != '$P_story_id':
        errors.append('story_id')
    if errors:
        print(f'MISMATCH:{\"|\".join(errors)}')
        sys.exit(1)
    print('OK')
except Exception as e:
    print(f'ERROR:{e}')
    sys.exit(1)
" "$P_manifest_path" 2>&1)" || manifest_ok="EXCEPTION"

    if [[ "$manifest_ok" != "OK" ]]; then
      write_infra_error "$error_dir/guard-error.json" \
        "GUARD_MANIFEST_MISMATCH" "$phase" "manifest_ids_match_passport" \
        "manifest contains matching project/run/slot/story IDs" \
        "$manifest_ok" \
        "$P_project_id" "$P_run_id" "$P_slot_id" "$P_story_id"
      return 1
    fi
  fi

  # Check 12: path safety (no symlink escape)
  local safety_check
  safety_check="$(check_path_safety "$(pwd)" "$P_workspace_root")" || {
    write_infra_error "$error_dir/guard-error.json" \
      "GUARD_PATH_SAFETY_VIOLATION" "$phase" "path_safety" \
      "no path traversal or symlink escape" \
      "$safety_check" \
      "$P_project_id" "$P_run_id" "$P_slot_id" "$P_story_id"
    return 1
  }

  if [[ "$safety_check" != "OK" ]]; then
    write_infra_error "$error_dir/guard-error.json" \
      "GUARD_PATH_SAFETY_VIOLATION" "$phase" "path_safety" \
      "no path traversal or symlink escape" \
      "$safety_check" \
      "$P_project_id" "$P_run_id" "$P_slot_id" "$P_story_id"
    return 1
  fi

  return 0
}
