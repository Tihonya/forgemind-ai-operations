#!/usr/bin/env python3
"""
Temporary isolated Git repository fixture for agent-loop harness scenarios.

WP-AL-1B2B test isolation design
---------------------------------
Each scenario builds a disposable standalone Git repository under
$TMPDIR/agent-loop-scenario-<NAME>-XXXXXX containing ONLY the files the
harness needs (agent-loop scripts, .agent-loop config, minimal backend
skeleton). One deterministic base commit is created; scenario-local candidate
changes are applied afterwards and stay UNCOMMITTED, so verify-story.sh's
gates operate on an isolated candidate diff instead of the real infrastructure
worktree.

Guarantees:
  - never touches the real repository (no stash, no worktree registration,
    no reset/clean, no synthetic files written into the real backend tree);
  - local Git identity only (never reads or writes global/user config);
  - cleanup removes ONLY the uniquely-created temp directory;
  - deterministic: identical inputs produce identical gate decisions.

CLI subcommands:
  create    [--source-root PATH] [--scenario NAME]      -> prints repo path
  add-file  --repo PATH --rel REL (--src FILE | --content STR | --stdin)
  manifest  --repo PATH --base SHA --story-id ID --output PATH
            [--arg ARG ...] [--allowed PAT ...] [--forbidden PAT ...]
            [--overrides-json JSON]
  base-sha  --repo PATH                                   -> prints HEAD sha
  remove    REPO_PATH
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent          # .../agent-loop/tests/lib
AGENT_LOOP_SRC = THIS_DIR.parent.parent             # .../agent-loop

DETERMINISTIC_DATE = "2024-01-01T00:00:00+00:00"
GIT_IDENTITY_NAME = "Agent Loop Harness"
GIT_IDENTITY_EMAIL = "harness@agent-loop.local"

# .gitignore for the temp repo: ignore harness artifacts and caches so they
# never become part of the candidate diff.
TEMP_REPO_GITIGNORE = """\
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
.ralph-tui/
.env
.venv/
"""

# Minimal backend config: pytest discovery + a small lint ruleset so the
# diff-scoped lint gate has deterministic, meaningful behaviour.
BACKEND_PYPROJECT = """\
[tool.pytest.ini_options]
minversion = "8.0"
testpaths = ["tests"]
addopts = "-v --tb=short"

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I"]

[tool.mypy]
python_version = "3.12"
ignore_missing_imports = true
"""


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.update({
        "GIT_AUTHOR_NAME": GIT_IDENTITY_NAME,
        "GIT_AUTHOR_EMAIL": GIT_IDENTITY_EMAIL,
        "GIT_COMMITTER_NAME": GIT_IDENTITY_NAME,
        "GIT_COMMITTER_EMAIL": GIT_IDENTITY_EMAIL,
        "GIT_AUTHOR_DATE": DETERMINISTIC_DATE,
        "GIT_COMMITTER_DATE": DETERMINISTIC_DATE,
    })
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=env,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed in {repo}: {proc.stderr.strip()}"
        )
    return proc


def _copy_agent_loop_infrastructure(repo: Path, source_root: Path) -> None:
    """Copy only the harness runtime files into the temp repo."""
    src_agent_loop = source_root / "scripts" / "agent-loop"
    dst_agent_loop = repo / "scripts" / "agent-loop"

    def _ignore(_directory: str, entries: list) -> list:
        ignored = []
        for entry in entries:
            if entry in ("__pycache__", ".pytest_cache"):
                ignored.append(entry)
            elif entry.endswith(".pyc"):
                ignored.append(entry)
        return ignored

    shutil.copytree(src_agent_loop, dst_agent_loop, ignore=_ignore)

    # .agent-loop configuration (gates.json, project.json, manifests/)
    src_config = source_root / ".agent-loop"
    dst_config = repo / ".agent-loop"
    shutil.copytree(src_config, dst_config, ignore=_ignore)


def _create_backend_skeleton(repo: Path) -> None:
    backend = repo / "backend"
    (backend / "tests").mkdir(parents=True, exist_ok=True)
    (backend / "pyproject.toml").write_text(BACKEND_PYPROJECT)
    (backend / "tests" / "__init__.py").write_text("")


def create_temp_repo(source_root: Path, scenario_name: str) -> Path:
    """Create the isolated temp repo with its deterministic base commit."""
    tmp_root = tempfile.mkdtemp(prefix=f"agent-loop-scenario-{scenario_name}-")
    repo = Path(tmp_root)

    _git(repo, "init", "-q", "-b", "harness-test")
    _git(repo, "config", "user.name", GIT_IDENTITY_NAME)
    _git(repo, "config", "user.email", GIT_IDENTITY_EMAIL)
    _git(repo, "config", "commit.gpgsign", "false")

    _copy_agent_loop_infrastructure(repo, source_root)
    _create_backend_skeleton(repo)
    (repo / ".gitignore").write_text(TEMP_REPO_GITIGNORE)

    # Deterministic base commit
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"base: scenario {scenario_name}")

    return repo


def add_candidate_file(repo: Path, rel_path: str, content: str) -> None:
    """Add a scenario-local candidate change (uncommitted)."""
    target = repo / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)


def base_sha(repo: Path) -> str:
    proc = _git(repo, "rev-parse", "HEAD")
    return proc.stdout.strip()


def write_manifest(repo: Path, manifest: dict, name: str = "manifest.json") -> Path:
    """Write the manifest OUTSIDE the repo (sibling file) so it never becomes
    part of the candidate diff. Removed together with the repo by
    remove_temp_repo."""
    path = repo.parent / f"{repo.name}--{name}"
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    return path


def remove_temp_repo(repo: Path) -> None:
    """Remove ONLY this uniquely-created temp directory and its sibling
    manifest files."""
    root = Path(str(repo))
    if not root.name.startswith("agent-loop-scenario-"):
        raise RuntimeError(f"refusing to remove non-fixture directory: {root}")
    tmp_root = tempfile.gettempdir()
    if str(root) != tmp_root and not str(root).startswith(tmp_root + os.sep):
        raise RuntimeError(f"refusing to remove directory outside tmp: {root}")
    shutil.rmtree(root, ignore_errors=False)
    # Sibling manifests written by write_manifest()
    for sibling in root.parent.glob(f"{root.name}--*"):
        if sibling.is_file():
            sibling.unlink()


def canonical_manifest(
    story_id: str,
    targeted_args: list,
    allowed_paths: list,
    forbidden_paths: list,
    gate_overrides: dict | None = None,
    base_commit: str = "0" * 40,
    expected_branch: str = "harness-test",
) -> dict:
    """Build a canonical schema v1.0 manifest (all seven required gates)."""
    manifest = {
        "schema_version": "1.0",
        "project_id": "forgemind",
        "story_id": story_id,
        "title": f"Harness Validation Scenario {story_id}",
        "description": "Synthetic isolated-repo harness scenario",
        "base_commit": base_commit,
        "expected_branch": expected_branch,
        "path_pattern_type": "gitwildmatch",
        "allowed_paths": allowed_paths,
        "forbidden_paths": forbidden_paths,
        "required_gates": [
            "scope", "json_syntax", "yaml_syntax", "targeted_tests",
            "lint", "secrets", "git_diff_check",
        ],
        "test_commands": {"targeted_args": targeted_args},
        "environment_requirements": {
            "database": {"required": False, "auto_start": False},
            "redis": {"required": False, "auto_start": False},
            "external_network": {"allowed": False},
        },
        "expected_outputs": ["test-report.json"],
        "acceptance_criteria": [
            "All required gates execute and aggregate correctly",
        ],
        "repair_budget": 3,
        "model_routing_hints": {
            "implementation_role": "implementer",
            "review_role": "reviewer",
            "complexity": "standard",
            "local_worker_allowed": True,
        },
        "dependencies": [],
        "conflict_domains": [],
    }
    if gate_overrides:
        manifest["gate_overrides"] = gate_overrides
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent-loop temp repo fixture")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="create isolated temp repo")
    create.add_argument(
        "--source-root",
        # scripts/agent-loop -> scripts -> repo root
        default=str(AGENT_LOOP_SRC.parent.parent),
        help="real repo root to copy harness files from",
    )
    create.add_argument("--scenario", default="GENERIC")

    addfile = sub.add_parser("add-file", help="add an uncommitted candidate file")
    addfile.add_argument("--repo", required=True)
    addfile.add_argument("--rel", required=True)
    src_group = addfile.add_mutually_exclusive_group(required=True)
    src_group.add_argument("--src", help="copy contents of this file")
    src_group.add_argument("--content", help="inline content string")
    src_group.add_argument("--stdin", action="store_true",
                           help="read content from stdin")

    manifest = sub.add_parser("manifest", help="write a canonical manifest")
    manifest.add_argument("--repo", required=True)
    manifest.add_argument("--base", required=True)
    manifest.add_argument("--story-id", required=True)
    manifest.add_argument("--output", required=True)
    manifest.add_argument("--arg", action="append", default=[],
                          help="targeted_args element (repeatable)")
    manifest.add_argument("--allowed", action="append", default=[],
                          help="allowed_paths pattern (repeatable)")
    manifest.add_argument("--forbidden", action="append", default=[],
                          help="forbidden_paths pattern (repeatable)")
    manifest.add_argument("--overrides-json", default="",
                          help="gate_overrides as a JSON object")

    basesha = sub.add_parser("base-sha", help="print HEAD sha of the temp repo")
    basesha.add_argument("--repo", required=True)

    remove = sub.add_parser("remove", help="remove a fixture temp repo")
    remove.add_argument("repo_root")

    args = parser.parse_args()

    if args.command == "create":
        source_root = Path(args.source_root)
        if not (source_root / "scripts" / "agent-loop" / "verify-story.sh").exists():
            print(f"ERROR: source root lacks agent-loop scripts: {source_root}",
                  file=sys.stderr)
            return 2
        try:
            repo = create_temp_repo(source_root, args.scenario)
        except Exception as e:  # noqa: BLE001 - report and fail deterministically
            print(f"ERROR: temp repo creation failed: {e}", file=sys.stderr)
            return 2
        print(repo)
        return 0

    if args.command == "add-file":
        repo = Path(args.repo)
        if args.src:
            content = Path(args.src).read_text()
        elif args.stdin:
            content = sys.stdin.read()
        else:
            content = args.content
        try:
            add_candidate_file(repo, args.rel, content)
        except Exception as e:  # noqa: BLE001
            print(f"ERROR: add-file failed: {e}", file=sys.stderr)
            return 2
        return 0

    if args.command == "manifest":
        overrides = None
        if args.overrides_json:
            try:
                overrides = json.loads(args.overrides_json)
            except json.JSONDecodeError as e:
                print(f"ERROR: bad --overrides-json: {e}", file=sys.stderr)
                return 2
        allowed = args.allowed or ["backend/**"]
        forbidden = args.forbidden or [".env"]
        m = canonical_manifest(
            story_id=args.story_id,
            targeted_args=args.arg,
            allowed_paths=allowed,
            forbidden_paths=forbidden,
            gate_overrides=overrides,
            base_commit=args.base,
        )
        out = Path(args.output)
        out.write_text(json.dumps(m, indent=2) + "\n")
        return 0

    if args.command == "base-sha":
        try:
            print(base_sha(Path(args.repo)))
        except Exception as e:  # noqa: BLE001
            print(f"ERROR: base-sha failed: {e}", file=sys.stderr)
            return 2
        return 0

    if args.command == "remove":
        try:
            remove_temp_repo(Path(args.repo_root))
        except Exception as e:  # noqa: BLE001
            print(f"ERROR: cleanup failed for {args.repo_root}: {e}",
                  file=sys.stderr)
            return 1
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
