#!/usr/bin/env python3
"""
Manifest loader for canonical story manifests (schema v1.0).

Validates story manifests against strict schema rules.
Single Source of Truth for manifest validation.

Schema v1.0 required fields:
- schema_version, project_id, story_id, title, description
- base_commit, expected_branch, path_pattern_type
- allowed_paths, forbidden_paths, required_gates
- test_commands, environment_requirements, expected_outputs
- acceptance_criteria, repair_budget, model_routing_hints
- dependencies, conflict_domains

Optional fields:
- gate_overrides, repair_guidance

Exit codes:
- 0: validation passed
- 1: validation failed (schema defect)
- 2: infrastructure error (reserved for runtime wrapper)
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Tuple

# Canonical gate IDs from .agent-loop/gates.json
CANONICAL_GATE_IDS = {
    "scope",
    "json_syntax",
    "yaml_syntax",
    "targeted_tests",
    "lint",
    "secrets",
    "git_diff_check"
}

# Allowlisted gate override fields
ALLOWED_OVERRIDE_FIELDS = {
    "targeted_tests": {"assertion_gate"},
    "lint": {"scope_to_diff"},
    "secrets": {"scope_to_diff"}
}

# Forbidden override fields (global policy)
FORBIDDEN_OVERRIDE_FIELDS = {"required", "enabled"}

# Allowlisted model routing hint keys
ALLOWED_ROUTING_KEYS = {
    "implementation_role",
    "review_role",
    "complexity",
    "local_worker_allowed"
}

# Valid routing role values
VALID_ROLES = {"implementer", "reviewer"}

# Valid complexity values
VALID_COMPLEXITY = {"low", "standard", "high"}

# Strict top-level field allowlist for schema v1.0
ALLOWED_TOP_LEVEL_FIELDS = {
    "schema_version",
    "project_id",
    "story_id",
    "title",
    "description",
    "base_commit",
    "expected_branch",
    "path_pattern_type",
    "allowed_paths",
    "forbidden_paths",
    "required_gates",
    "gate_overrides",  # optional
    "test_commands",
    "environment_requirements",
    "expected_outputs",
    "acceptance_criteria",
    "repair_budget",
    "repair_guidance",  # optional
    "model_routing_hints",
    "dependencies",
    "conflict_domains"
}

# Runtime fields that must be rejected
RUNTIME_FIELDS = {
    "run_id",
    "slot_id",
    "workspace_root",
    "artifact_root",
    "phase",
    "role"
}

# Legacy fields that must be rejected
LEGACY_FIELDS = {
    "gates",  # legacy dict shape
    "branch"  # legacy field, use expected_branch
}

# Global max repair iterations from project.json
GLOBAL_MAX_REPAIR_ITERATIONS = 3

# SHA pattern (40 hex characters)
SHA_PATTERN = re.compile(r'^[0-9a-f]{40}$')


def validate_path(path_str: str) -> Tuple[bool, str]:
    """
    Validate a single path string.

    Returns:
        (is_valid, error_code)
        error_code is empty string if valid

    Validation rules:
        - Must be non-empty
        - Must not contain NUL
        - Must not be absolute (no leading / or drive letters)
        - Must not contain path traversal (..)
        - Must be repo-relative
    """
    if not path_str:
        return False, "PATH_EMPTY"

    if '\x00' in path_str:
        return False, "PATH_NUL"

    # Check for absolute paths
    if path_str.startswith('/'):
        return False, "PATH_ABSOLUTE"

    # Check for Windows drive letters (C:, D:, etc.)
    if len(path_str) >= 2 and path_str[1] == ':':
        return False, "PATH_ABSOLUTE"

    # Check for UNC paths
    if path_str.startswith('\\\\'):
        return False, "PATH_ABSOLUTE"

    # Check for path traversal
    # Split by / and check for '..' segments
    segments = path_str.split('/')
    if '..' in segments:
        return False, "PATH_TRAVERSAL"

    return True, ""


def validate_paths(paths: list, field_name: str) -> Tuple[bool, str, str]:
    """
    Validate a list of path strings.

    Returns:
        (is_valid, error_code, error_detail)
    """
    if not isinstance(paths, list):
        return False, f"{field_name.upper()}_NOT_ARRAY", f"{field_name} must be an array"

    for path_str in paths:
        if not isinstance(path_str, str):
            return False, f"{field_name.upper()}_INVALID_TYPE", f"{field_name} items must be strings"

        is_valid, error_code = validate_path(path_str)
        if not is_valid:
            return False, error_code, f"Invalid path in {field_name}: {path_str}"

    return True, "", ""


def validate_base_commit(commit: str) -> Tuple[bool, str, str]:
    """
    Validate base_commit field.

    Must be:
        - Non-empty string
        - 40 hex characters (full SHA)
        - Not a symbolic ref (HEAD, main, branch names, etc.)

    Returns:
        (is_valid, error_code, error_detail)
    """
    if not isinstance(commit, str) or not commit:
        return False, "BASE_COMMIT_MISSING", "base_commit must be a non-empty string"

    # Check for symbolic refs
    symbolic_refs = {"HEAD", "main", "master", "develop", "dev"}
    if commit in symbolic_refs or commit.startswith("refs/") or commit.startswith("origin/"):
        return False, "BASE_COMMIT_SYMBOLIC", f"base_commit must be concrete SHA, not symbolic ref: {commit}"

    # Check SHA format
    if not SHA_PATTERN.match(commit):
        return False, "BASE_COMMIT_INVALID", f"base_commit must be 40 hex characters: {commit}"

    return True, "", ""


def validate_gate_overrides(overrides: dict, required_gates: list) -> Tuple[bool, str, str]:
    """
    Validate gate_overrides field.

    Rules:
        - Must be object if present
        - Keys must be gate IDs from required_gates
        - Values must be objects with only allowlisted fields
        - Cannot override 'required' or 'enabled' (global policy)

    Returns:
        (is_valid, error_code, error_detail)
    """
    if not isinstance(overrides, dict):
        return False, "GATE_OVERRIDES_NOT_OBJECT", "gate_overrides must be an object"

    for gate_id, override_config in overrides.items():
        # Check gate exists in required_gates
        if gate_id not in required_gates:
            return False, "OVERRIDE_UNKNOWN_GATE", f"Cannot override unknown gate: {gate_id}"

        if not isinstance(override_config, dict):
            return False, "OVERRIDE_NOT_OBJECT", f"Override for {gate_id} must be an object"

        # Check each override field
        for field_name, field_value in override_config.items():
            # Check forbidden fields
            if field_name in FORBIDDEN_OVERRIDE_FIELDS:
                return False, "OVERRIDE_FORBIDDEN_FIELD", f"Cannot override '{field_name}' for gate {gate_id}"

            # Check if field is allowlisted for this gate
            allowed_fields = ALLOWED_OVERRIDE_FIELDS.get(gate_id, set())
            if field_name not in allowed_fields:
                return False, "OVERRIDE_UNKNOWN_FIELD", f"Unknown override field '{field_name}' for gate {gate_id}"

    return True, "", ""


def validate_model_routing_hints(hints: dict) -> Tuple[bool, str, str]:
    """
    Validate model_routing_hints field.

    Rules:
        - Must be object
        - Keys must be from allowlist
        - Values must match expected types
        - No concrete tool names (tool-independent)

    Returns:
        (is_valid, error_code, error_detail)
    """
    if not isinstance(hints, dict):
        return False, "MODEL_ROUTING_HINTS_NOT_OBJECT", "model_routing_hints must be an object"

    for key, value in hints.items():
        # Check key is allowlisted
        if key not in ALLOWED_ROUTING_KEYS:
            return False, "ROUTING_UNKNOWN_KEY", f"Unknown routing hint key: {key}"

        # Validate role fields
        if key in {"implementation_role", "review_role"}:
            if not isinstance(value, str):
                return False, "ROUTING_INVALID_ROLE", f"{key} must be a string"
            if value not in VALID_ROLES:
                return False, "ROUTING_INVALID_ROLE", f"{key} must be one of {VALID_ROLES}, got: {value}"

        # Validate complexity
        elif key == "complexity":
            if not isinstance(value, str):
                return False, "ROUTING_INVALID_COMPLEXITY", f"complexity must be a string"
            if value not in VALID_COMPLEXITY:
                return False, "ROUTING_INVALID_COMPLEXITY", f"complexity must be one of {VALID_COMPLEXITY}, got: {value}"

        # Validate local_worker_allowed
        elif key == "local_worker_allowed":
            if not isinstance(value, bool):
                return False, "ROUTING_INVALID_LOCAL_WORKER", f"local_worker_allowed must be boolean"

    return True, "", ""


def validate_manifest(manifest_path: str) -> Tuple[str, str]:
    """
    Validate a manifest file against schema v1.0.

    Args:
        manifest_path: Path to manifest JSON file

    Returns:
        Tuple of (status, value)
        - ("OK", story_id) if valid
        - ("ERROR", error_code|error_message) if invalid
    """
    # Load JSON
    try:
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
    except json.JSONDecodeError as e:
        return ("ERROR", f"JSON_SYNTAX|Invalid JSON: {e}")
    except FileNotFoundError:
        return ("ERROR", f"FILE_NOT_FOUND|Manifest not found: {manifest_path}")
    except Exception as e:
        return ("ERROR", f"UNEXPECTED|Failed to load manifest: {e}")

    if not isinstance(manifest, dict):
        return ("ERROR", "ROOT_NOT_OBJECT|Manifest root must be a JSON object")

    # Check for runtime fields
    for field in RUNTIME_FIELDS:
        if field in manifest:
            return ("ERROR", f"RUNTIME_FIELD_REJECTED|Field '{field}' is runtime-only, not allowed in static manifest")

    # Check for legacy fields
    for field in LEGACY_FIELDS:
        if field in manifest:
            return ("ERROR", f"LEGACY_{field.upper()}_REJECTED|Legacy field '{field}' is not allowed in schema v1.0")

    # Check for unknown top-level fields
    for field in manifest.keys():
        if field not in ALLOWED_TOP_LEVEL_FIELDS:
            return ("ERROR", f"UNKNOWN_TOP_LEVEL_FIELD|Unknown field: {field}")

    # Validate required fields

    # schema_version
    if "schema_version" not in manifest:
        return ("ERROR", "SCHEMA_VERSION_MISSING|Required field missing: schema_version")
    if manifest["schema_version"] != "1.0":
        return ("ERROR", f"SCHEMA_VERSION_MISMATCH|Expected 1.0, got {manifest['schema_version']}")

    # project_id
    if "project_id" not in manifest:
        return ("ERROR", "PROJECT_ID_MISSING|Required field missing: project_id")
    if manifest["project_id"] != "forgemind":
        return ("ERROR", f"PROJECT_ID_MISMATCH|Expected 'forgemind', got {manifest['project_id']}")

    # story_id
    if "story_id" not in manifest:
        return ("ERROR", "STORY_ID_MISSING|Required field missing: story_id")
    story_id = manifest["story_id"]
    if not isinstance(story_id, str) or not story_id or not story_id.strip():
        return ("ERROR", "STORY_ID_EMPTY|story_id must be non-empty string")

    # title
    if "title" not in manifest:
        return ("ERROR", "TITLE_MISSING|Required field missing: title")

    # description
    if "description" not in manifest:
        return ("ERROR", "DESCRIPTION_MISSING|Required field missing: description")

    # base_commit
    if "base_commit" not in manifest:
        return ("ERROR", "BASE_COMMIT_MISSING|Required field missing: base_commit")
    is_valid, error_code, error_detail = validate_base_commit(manifest["base_commit"])
    if not is_valid:
        return ("ERROR", f"{error_code}|{error_detail}")

    # expected_branch
    if "expected_branch" not in manifest:
        return ("ERROR", "EXPECTED_BRANCH_MISSING|Required field missing: expected_branch")

    # path_pattern_type
    if "path_pattern_type" not in manifest:
        return ("ERROR", "PATH_PATTERN_TYPE_MISSING|Required field missing: path_pattern_type")
    if manifest["path_pattern_type"] != "gitwildmatch":
        return ("ERROR", f"PATH_PATTERN_TYPE_UNSUPPORTED|Only 'gitwildmatch' supported, got {manifest['path_pattern_type']}")

    # allowed_paths
    if "allowed_paths" not in manifest:
        return ("ERROR", "ALLOWED_PATHS_MISSING|Required field missing: allowed_paths")
    is_valid, error_code, error_detail = validate_paths(manifest["allowed_paths"], "allowed_paths")
    if not is_valid:
        return ("ERROR", f"{error_code}|{error_detail}")

    # forbidden_paths
    if "forbidden_paths" not in manifest:
        return ("ERROR", "FORBIDDEN_PATHS_MISSING|Required field missing: forbidden_paths")
    is_valid, error_code, error_detail = validate_paths(manifest["forbidden_paths"], "forbidden_paths")
    if not is_valid:
        return ("ERROR", f"{error_code}|{error_detail}")

    # required_gates
    if "required_gates" not in manifest:
        return ("ERROR", "REQUIRED_GATES_MISSING|Required field missing: required_gates")
    required_gates = manifest["required_gates"]
    if not isinstance(required_gates, list):
        return ("ERROR", "REQUIRED_GATES_NOT_ARRAY|required_gates must be an array")

    # Check for duplicates
    if len(required_gates) != len(set(required_gates)):
        return ("ERROR", "GATE_DUPLICATE|required_gates contains duplicate entries")

    # Check all gates are canonical
    for gate_id in required_gates:
        if gate_id not in CANONICAL_GATE_IDS:
            return ("ERROR", f"GATE_UNKNOWN|Unknown gate ID: {gate_id}")

    # Check all canonical gates are present
    missing_gates = CANONICAL_GATE_IDS - set(required_gates)
    if missing_gates:
        return ("ERROR", f"GATE_MISSING_GLOBAL|Missing canonical gates: {', '.join(sorted(missing_gates))}")

    # gate_overrides (optional)
    if "gate_overrides" in manifest:
        is_valid, error_code, error_detail = validate_gate_overrides(manifest["gate_overrides"], required_gates)
        if not is_valid:
            return ("ERROR", f"{error_code}|{error_detail}")

    # test_commands
    if "test_commands" not in manifest:
        return ("ERROR", "TEST_COMMANDS_MISSING|Required field missing: test_commands")
    test_commands = manifest["test_commands"]
    if not isinstance(test_commands, dict):
        return ("ERROR", "TEST_COMMANDS_NOT_OBJECT|test_commands must be an object")

    if "targeted_args" not in test_commands:
        return ("ERROR", "TARGETED_ARGS_MISSING|test_commands.targeted_args is required")
    if not isinstance(test_commands["targeted_args"], list):
        return ("ERROR", "TARGETED_ARGS_NOT_ARRAY|targeted_args must be an array")

    # environment_requirements
    if "environment_requirements" not in manifest:
        return ("ERROR", "ENVIRONMENT_REQUIREMENTS_MISSING|Required field missing: environment_requirements")
    env_reqs = manifest["environment_requirements"]
    if not isinstance(env_reqs, dict):
        return ("ERROR", "ENVIRONMENT_REQUIREMENTS_NOT_OBJECT|environment_requirements must be an object")

    # expected_outputs
    if "expected_outputs" not in manifest:
        return ("ERROR", "EXPECTED_OUTPUTS_MISSING|Required field missing: expected_outputs")
    is_valid, error_code, error_detail = validate_paths(manifest["expected_outputs"], "expected_outputs")
    if not is_valid:
        return ("ERROR", f"{error_code}|{error_detail}")

    # acceptance_criteria
    if "acceptance_criteria" not in manifest:
        return ("ERROR", "ACCEPTANCE_CRITERIA_MISSING|Required field missing: acceptance_criteria")
    acceptance_criteria = manifest["acceptance_criteria"]
    if not isinstance(acceptance_criteria, list):
        return ("ERROR", "ACCEPTANCE_CRITERIA_NOT_ARRAY|acceptance_criteria must be an array")
    if len(acceptance_criteria) == 0:
        return ("ERROR", "ACCEPTANCE_CRITERIA_EMPTY|acceptance_criteria must be non-empty array")

    # repair_budget
    if "repair_budget" not in manifest:
        return ("ERROR", "REPAIR_BUDGET_MISSING|Required field missing: repair_budget")
    repair_budget = manifest["repair_budget"]
    if not isinstance(repair_budget, int) or isinstance(repair_budget, bool):
        return ("ERROR", "REPAIR_BUDGET_NOT_INT|repair_budget must be an integer")
    if repair_budget < 0:
        return ("ERROR", "REPAIR_BUDGET_NEGATIVE|repair_budget must be non-negative")
    if repair_budget > GLOBAL_MAX_REPAIR_ITERATIONS:
        return ("ERROR", f"REPAIR_BUDGET_EXCEEDS_GLOBAL|repair_budget ({repair_budget}) exceeds global max ({GLOBAL_MAX_REPAIR_ITERATIONS})")

    # repair_guidance (optional)
    if "repair_guidance" in manifest:
        repair_guidance = manifest["repair_guidance"]
        if not isinstance(repair_guidance, list):
            return ("ERROR", "REPAIR_GUIDANCE_NOT_ARRAY|repair_guidance must be an array")

    # model_routing_hints
    if "model_routing_hints" not in manifest:
        return ("ERROR", "MODEL_ROUTING_HINTS_MISSING|Required field missing: model_routing_hints")
    is_valid, error_code, error_detail = validate_model_routing_hints(manifest["model_routing_hints"])
    if not is_valid:
        return ("ERROR", f"{error_code}|{error_detail}")

    # dependencies
    if "dependencies" not in manifest:
        return ("ERROR", "DEPENDENCIES_MISSING|Required field missing: dependencies")
    dependencies = manifest["dependencies"]
    if not isinstance(dependencies, list):
        return ("ERROR", "DEPENDENCIES_NOT_ARRAY|dependencies must be an array")

    # Check for empty items
    if any(not dep for dep in dependencies):
        return ("ERROR", "DEPENDENCIES_EMPTY_ITEM|dependencies contains empty items")

    # Check for duplicates
    if len(dependencies) != len(set(dependencies)):
        return ("ERROR", "DEPENDENCIES_DUPLICATE|dependencies contains duplicate entries")

    # conflict_domains
    if "conflict_domains" not in manifest:
        return ("ERROR", "CONFLICT_DOMAINS_MISSING|Required field missing: conflict_domains")
    conflict_domains = manifest["conflict_domains"]
    if not isinstance(conflict_domains, list):
        return ("ERROR", "CONFLICT_DOMAINS_NOT_ARRAY|conflict_domains must be an array")

    # Check for empty items
    if any(not domain for domain in conflict_domains):
        return ("ERROR", "CONFLICT_DOMAINS_EMPTY_ITEM|conflict_domains contains empty items")

    # Check for duplicates
    if len(conflict_domains) != len(set(conflict_domains)):
        return ("ERROR", "CONFLICT_DOMAINS_DUPLICATE|conflict_domains contains duplicate entries")

    # All validation passed
    return ("OK", story_id)


def load_manifest(manifest_path: str) -> dict:
    """
    Load and validate a manifest file.

    Args:
        manifest_path: Path to manifest JSON file

    Returns:
        Validated manifest dict

    Raises:
        ValueError: If validation fails
        FileNotFoundError: If file not found
    """
    status, value = validate_manifest(manifest_path)

    if status == "ERROR":
        error_code, error_message = value.split("|", 1)
        raise ValueError(f"Manifest validation failed: {error_code} - {error_message}")

    # Load and return the manifest
    with open(manifest_path, 'r') as f:
        return json.load(f)


if __name__ == "__main__":
    # CLI entry point
    if len(sys.argv) < 2:
        print("Usage: manifest_loader.py validate <manifest_path>", file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]

    if command == "validate":
        if len(sys.argv) < 3:
            print("Usage: manifest_loader.py validate <manifest_path>", file=sys.stderr)
            sys.exit(1)

        manifest_path = sys.argv[2]
        status, value = validate_manifest(manifest_path)

        if status == "OK":
            print(f"{status}:{value}")
            sys.exit(0)
        else:
            print(f"{status}:{value}")
            sys.exit(1)

    elif command == "load":
        if len(sys.argv) < 3:
            print("Usage: manifest_loader.py load <manifest_path>", file=sys.stderr)
            sys.exit(1)

        manifest_path = sys.argv[2]

        try:
            manifest = load_manifest(manifest_path)
            print(json.dumps(manifest, indent=2))
            sys.exit(0)
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)
