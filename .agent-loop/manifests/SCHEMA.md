# Canonical Story Manifest Schema v1.0

## Required Fields

All fields below are mandatory. Any missing field results in validation failure.

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | string | Must be exactly `"1.0"` |
| `project_id` | string | Must be exactly `"forgemind"` |
| `story_id` | string | Non-empty identifier for the story |
| `title` | string | Non-empty story title |
| `description` | string | Non-empty story description |
| `base_commit` | string | Concrete 40-char hex SHA (no symbolic refs) |
| `expected_branch` | string | Non-empty branch name |
| `path_pattern_type` | string | Must be exactly `"gitwildmatch"` |
| `allowed_paths` | array of strings | Repo-relative paths, no traversal |
| `forbidden_paths` | array of strings | Repo-relative paths, no traversal |
| `required_gates` | array of strings | All 7 canonical gates: `scope`, `json_syntax`, `yaml_syntax`, `targeted_tests`, `lint`, `secrets`, `git_diff_check` |
| `test_commands` | object | Must contain `targeted_args` array |
| `environment_requirements` | object | Database/redis/network configuration |
| `expected_outputs` | array of strings | Repo-relative output paths |
| `acceptance_criteria` | array of strings | Non-empty acceptance criteria |
| `repair_budget` | integer | 0 ≤ value ≤ 3 |
| `model_routing_hints` | object | Abstract roles only (see routing section) |
| `dependencies` | array of strings | No duplicates, no empty strings |
| `conflict_domains` | array of strings | No duplicates, no empty strings |

## Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `gate_overrides` | object | Allowlisted gate property overrides only |
| `repair_guidance` | array of strings | Repair hints for failed gates |

## Rejected Fields

### Runtime Fields (cannot appear in static manifests)
- `run_id`, `slot_id`, `workspace_root`, `artifact_root`, `phase`, `role`

### Legacy Fields (no longer supported)
- `gates` (dict) — replaced by `required_gates` array
- `branch` — replaced by `expected_branch`

## Path Validation

All path arrays (`allowed_paths`, `forbidden_paths`, `expected_outputs`) must:
- Be repo-relative (no leading `/`)
- No Windows drive letters (`C:`) or UNC paths (`\\`)
- No path traversal (`..`)
- No empty strings
- No NUL characters

## Gate Overrides

Only allowlisted fields can be overridden:
- `targeted_tests.assertion_gate` (boolean) — when `false`, zero-collected and
  all-skipped test runs pass the targeted_tests gate (execution completed);
  actual failures/errors still fail. Default `true`.
- `lint.scope_to_diff` (boolean) — when `true`, lint runs only on the changed
  Python files of the candidate diff (never `ruff check .`); when `false`,
  full-project lint semantics apply.
- `secrets.scope_to_diff` (boolean) — when `true`, only candidate-diff files
  are scanned; when `false`, all tracked files plus candidate-diff files.

Cannot override:
- `required` (global policy)
- `enabled` (global policy)

## Candidate Diff Semantics

The candidate diff is the change set under audit, computed against the
manifest `base_commit`:

- committed, staged and working-tree changes since `base_commit`;
- plus untracked files (they have no base version but belong to the change).

All diff-aware gates (scope, json_syntax, yaml_syntax, lint, secrets) operate
on this candidate diff. The scope gate matches changed paths against the
manifest `allowed_paths` / `forbidden_paths` using gitwildmatch semantics
(forbidden wins); its failure propagates and is never masked.

## Model Routing Hints

Must use abstract roles, not concrete tool names:
- `implementation_role`: must be `"implementer"`
- `review_role`: must be `"reviewer"`
- `complexity`: must be `"low"`, `"standard"`, or `"high"`
- `local_worker_allowed`: boolean

## Base Commit Validation

Must be concrete 40-character hex SHA:
- ✗ `"HEAD"`, `"main"`, `"origin/main"` (symbolic refs)
- ✓ `"a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"` (concrete SHA)

## Exit Codes

| Scenario | CLI Exit | Runtime Wrapper Exit |
|----------|----------|---------------------|
| Valid manifest | 0 | 0 |
| Schema validation error | 1 | 2 (INFRASTRUCTURE_ERROR) |
| JSON syntax error | 1 | 2 (INFRASTRUCTURE_ERROR) |
| Unknown gate ID | 1 | 2 (INFRASTRUCTURE_ERROR) |
| Test/gate failure | N/A | 1 |
| Environment check failure | N/A | Out of scope |

## Example

```json
{
  "schema_version": "1.0",
  "project_id": "forgemind",
  "story_id": "HARNESS-A",
  "title": "Harness Validation Scenario",
  "description": "Synthetic test",
  "base_commit": "0000000000000000000000000000000000000000",
  "expected_branch": "chore/agent-loop-infrastructure",
  "path_pattern_type": "gitwildmatch",
  "allowed_paths": ["tests/.*"],
  "forbidden_paths": [".env"],
  "required_gates": ["scope", "json_syntax", "yaml_syntax", "targeted_tests", "lint", "secrets", "git_diff_check"],
  "test_commands": {
    "targeted_args": ["tests/synthetic/test.py", "-v"]
  },
  "environment_requirements": {
    "database": {"required": false, "auto_start": false},
    "redis": {"required": false, "auto_start": false},
    "external_network": {"allowed": false}
  },
  "expected_outputs": ["test-report.json"],
  "acceptance_criteria": ["All required gates pass"],
  "repair_budget": 3,
  "model_routing_hints": {
    "implementation_role": "implementer",
    "review_role": "reviewer",
    "complexity": "standard",
    "local_worker_allowed": true
  },
  "dependencies": [],
  "conflict_domains": []
}
```

## Architecture

### manifest_loader.py
Single source of truth for schema validation. All validation logic lives here.

### harness.py
Thin adapter that delegates to manifest_loader. Does not duplicate schema rules.

### No Legacy Fallback
All manifests must use canonical schema v1.0. No silent fallback to legacy format.

### Test Isolation (WP-AL-1B2B)
Harness scenarios run in disposable temporary Git repositories built by
`scripts/agent-loop/tests/lib/temp_repo_fixture.py`: one deterministic base
commit per scenario, scenario-local candidate changes left uncommitted. The
real infrastructure worktree is never mutated (no stash, no registered
worktrees, no synthetic files in the real backend tree). Tool binaries may be
pre-set via PYTHON_BIN / PYTEST_BIN / RUFF_BIN / MYPY_BIN; config.sh honors
pre-set values.
