#!/usr/bin/env python3
"""
Cycle Passport — formal identity and workspace validation for agent loops.

Mandatory for all phases. No silent legacy mode.
"""

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class CyclePassport:
    """Formal cycle identity and workspace context."""

    # Identity fields (no defaults)
    schema_version: str
    project_id: str
    run_id: str
    slot_id: str
    story_id: str
    role: str
    phase: str

    # Workspace fields (no defaults)
    workspace_type: str  # "source", "validation", "control-plane"
    workspace_root: str
    expected_branch: str
    base_commit: str
    manifest_path: str
    artifact_root: str

    # Optional fields (with defaults)
    candidate_commit: Optional[str] = None  # or candidate_tree

    def to_json(self) -> str:
        """Serialize to JSON string."""
        data = asdict(self)
        # Remove None values
        data = {k: v for k, v in data.items() if v is not None}
        return json.dumps(data, indent=2)

    def save(self, path: Path) -> None:
        """Save passport to file atomically."""
        from harness import atomic_json_write
        atomic_json_write(str(path), asdict(self))

    @classmethod
    def load(cls, path: Path) -> 'CyclePassport':
        """Load passport from file."""
        with open(path) as f:
            data = json.load(f)
        return cls(**data)

    def validate_workspace(self) -> tuple[bool, str]:
        """Validate current workspace matches passport."""
        try:
            # Check pwd matches workspace_root
            pwd = Path.cwd().resolve()
            ws_root = Path(self.workspace_root).resolve()

            if pwd != ws_root:
                return False, f"PWD {pwd} does not match workspace_root {ws_root}"

            # Check git toplevel matches workspace_root
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                cwd=str(pwd)
            )
            if result.returncode != 0:
                return False, f"Git toplevel check failed: {result.stderr}"

            git_root = Path(result.stdout.strip()).resolve()
            if git_root != ws_root:
                return False, f"Git toplevel {git_root} does not match workspace_root {ws_root}"

            # Check branch matches expected_branch
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                cwd=str(pwd)
            )
            if result.returncode != 0:
                return False, f"Branch check failed: {result.stderr}"

            current_branch = result.stdout.strip()
            if current_branch != self.expected_branch:
                return False, f"Branch {current_branch} does not match expected_branch {self.expected_branch}"

            # Check base_commit exists
            result = subprocess.run(
                ["git", "cat-file", "-t", self.base_commit],
                capture_output=True,
                text=True,
                cwd=str(pwd)
            )
            if result.returncode != 0:
                return False, f"Base commit {self.base_commit} does not exist"

            # Check HEAD descends from base_commit (or is equal)
            result = subprocess.run(
                ["git", "merge-base", "--is-ancestor", self.base_commit, "HEAD"],
                capture_output=True,
                text=True,
                cwd=str(pwd)
            )
            if result.returncode != 0:
                return False, f"HEAD does not descend from base_commit {self.base_commit}"

            return True, "Workspace validation passed"

        except Exception as e:
            return False, f"Workspace validation error: {e}"

    def validate_identity(self, run_id: str, slot_id: str, story_id: str, role: str) -> tuple[bool, str]:
        """Validate identity fields match."""
        if self.run_id != run_id:
            return False, f"run_id mismatch: passport={self.run_id}, actual={run_id}"
        if self.slot_id != slot_id:
            return False, f"slot_id mismatch: passport={self.slot_id}, actual={slot_id}"
        if self.story_id != story_id:
            return False, f"story_id mismatch: passport={self.story_id}, actual={story_id}"
        if self.role != role:
            return False, f"role mismatch: passport={self.role}, actual={role}"
        return True, "Identity validation passed"

    def validate_manifest_ownership(self, manifest_path: Path) -> tuple[bool, str]:
        """Validate manifest belongs to this passport."""
        try:
            with open(manifest_path) as f:
                manifest_data = json.load(f)

            # Check required fields in manifest
            for field in ["project_id", "run_id", "slot_id", "story_id"]:
                if field not in manifest_data:
                    return False, f"Manifest missing required field: {field}"

                passport_value = getattr(self, field)
                manifest_value = manifest_data[field]

                if passport_value != manifest_value:
                    return False, f"Manifest {field} mismatch: passport={passport_value}, manifest={manifest_value}"

            return True, "Manifest ownership validation passed"

        except FileNotFoundError:
            return False, f"Manifest not found: {manifest_path}"
        except json.JSONDecodeError as e:
            return False, f"Manifest JSON error: {e}"
        except Exception as e:
            return False, f"Manifest validation error: {e}"

    def validate_artifact_root(self) -> tuple[bool, str]:
        """Validate artifact_root belongs to current run/slot."""
        try:
            artifact_path = Path(self.artifact_root).resolve()

            # Check artifact_root exists
            if not artifact_path.exists():
                return False, f"Artifact root does not exist: {artifact_path}"

            # Check artifact_root contains run_id or slot_id in path
            if self.run_id not in str(artifact_path) and self.slot_id not in str(artifact_path):
                return False, f"Artifact root {artifact_path} does not contain run_id {self.run_id} or slot_id {self.slot_id}"

            # Check artifact_root is under workspace_root
            ws_root = Path(self.workspace_root).resolve()
            if ws_root not in artifact_path.parents:
                return False, f"Artifact root {artifact_path} is not under workspace_root {ws_root}"

            return True, "Artifact root validation passed"

        except Exception as e:
            return False, f"Artifact root validation error: {e}"

    def validate_workspace_type(self, expected_type: str) -> tuple[bool, str]:
        """Validate workspace_type matches phase requirements."""
        if self.workspace_type != expected_type:
            return False, f"Workspace type mismatch: passport={self.workspace_type}, expected={expected_type}"
        return True, "Workspace type validation passed"

    def validate_source_vs_validation(self, main_worktree: str) -> tuple[bool, str]:
        """Validate source workspace != validation workspace and != main worktree."""
        try:
            ws_root = Path(self.workspace_root).resolve()
            main_wt = Path(main_worktree).resolve()

            # Check workspace_root != main worktree
            if ws_root == main_wt:
                return False, f"Workspace root {ws_root} equals main worktree {main_wt}"

            # For validation workspace, check it's different from source
            # (This is a simplified check; full implementation would track source workspace)
            if self.workspace_type == "validation":
                # Validation workspace should be under a "validation" directory
                if "validation" not in str(ws_root):
                    return False, f"Validation workspace {ws_root} does not contain 'validation' in path"

            return True, "Source vs validation validation passed"

        except Exception as e:
            return False, f"Source vs validation validation error: {e}"

    def validate_phase_role(self, phase: str, role: str) -> tuple[bool, str]:
        """Validate role is allowed for phase."""
        phase_role_map = {
            "implement": ["implementer"],
            "verify": ["implementer", "verifier"],
            "review": ["reviewer"],
            "repair": ["repair"],
            "report": ["manager", "reporter"]
        }

        if phase not in phase_role_map:
            return False, f"Unknown phase: {phase}"

        allowed_roles = phase_role_map[phase]
        if role not in allowed_roles:
            return False, f"Role {role} not allowed for phase {phase}. Allowed: {allowed_roles}"

        return True, "Phase role validation passed"


def create_passport(
    project_id: str,
    run_id: str,
    slot_id: str,
    story_id: str,
    role: str,
    phase: str,
    workspace_type: str,
    workspace_root: str,
    expected_branch: str,
    base_commit: str,
    manifest_path: str,
    artifact_root: str,
    candidate_commit: Optional[str] = None
) -> CyclePassport:
    """Create a new cycle passport."""
    return CyclePassport(
        schema_version="1.0",
        project_id=project_id,
        run_id=run_id,
        slot_id=slot_id,
        story_id=story_id,
        role=role,
        phase=phase,
        workspace_type=workspace_type,
        workspace_root=workspace_root,
        expected_branch=expected_branch,
        base_commit=base_commit,
        candidate_commit=candidate_commit,
        manifest_path=manifest_path,
        artifact_root=artifact_root
    )


def write_error_artifact(
    output_path: Path,
    status: str,
    error_code: str,
    phase: str,
    failed_check: str,
    expected: str,
    actual: str,
    project_id: str = "unknown",
    run_id: str = "unknown",
    slot_id: str = "unknown",
    story_id: str = "unknown"
) -> None:
    """Write deterministic error artifact (no secrets)."""
    error_data = {
        "schema_version": "1.0",
        "status": status,
        "error_code": error_code,
        "phase": phase,
        "failed_check": failed_check,
        "expected": expected,
        "actual": actual,
        "project_id": project_id,
        "run_id": run_id,
        "slot_id": slot_id,
        "story_id": story_id,
        "timestamp": datetime.now().isoformat()
    }

    from harness import atomic_json_write
    atomic_json_write(str(output_path), error_data)


def bootstrap_guard(
    workspace_root: str,
    expected_branch: str,
    main_worktree: str
) -> tuple[bool, str]:
    """Pre-passport bootstrap validation."""
    try:
        ws_root = Path(workspace_root).resolve()
        main_wt = Path(main_worktree).resolve()

        # Check workspace_root != main worktree
        if ws_root == main_wt:
            return False, f"Bootstrap failed: workspace_root {ws_root} equals main worktree {main_wt}"

        # Check we're in a git repository
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            cwd=str(ws_root)
        )
        if result.returncode != 0:
            return False, f"Bootstrap failed: not a git repository at {ws_root}"

        git_root = Path(result.stdout.strip()).resolve()
        if git_root != ws_root:
            return False, f"Bootstrap failed: git root {git_root} does not match workspace_root {ws_root}"

        # Check branch
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            cwd=str(ws_root)
        )
        if result.returncode != 0:
            return False, f"Bootstrap failed: branch check failed"

        current_branch = result.stdout.strip()
        if current_branch != expected_branch:
            return False, f"Bootstrap failed: branch {current_branch} does not match expected {expected_branch}"

        return True, "Bootstrap validation passed"

    except Exception as e:
        return False, f"Bootstrap validation error: {e}"


if __name__ == "__main__":
    # CLI interface for shell scripts
    if len(sys.argv) < 2:
        print("Usage: passport.py <command> [args...]", file=sys.stderr)
        sys.exit(2)

    command = sys.argv[1]

    if command == "validate":
        # Validate passport from file
        if len(sys.argv) < 3:
            print("Usage: passport.py validate <passport.json>", file=sys.stderr)
            sys.exit(2)

        passport_path = Path(sys.argv[2])
        try:
            passport = CyclePassport.load(passport_path)
            valid, msg = passport.validate_workspace()
            if not valid:
                print(f"INVALID: {msg}", file=sys.stderr)
                sys.exit(1)
            print(f"VALID: {msg}")
            sys.exit(0)
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(2)

    elif command == "bootstrap":
        # Bootstrap guard
        if len(sys.argv) < 5:
            print("Usage: passport.py bootstrap <workspace_root> <expected_branch> <main_worktree>", file=sys.stderr)
            sys.exit(2)

        workspace_root = sys.argv[2]
        expected_branch = sys.argv[3]
        main_worktree = sys.argv[4]

        valid, msg = bootstrap_guard(workspace_root, expected_branch, main_worktree)
        if not valid:
            print(f"INVALID: {msg}", file=sys.stderr)
            sys.exit(1)
        print(f"VALID: {msg}")
        sys.exit(0)

    elif command == "create":
        # Create passport from arguments
        if len(sys.argv) < 15:
            print("Usage: passport.py create <project_id> <run_id> <slot_id> <story_id> <role> <phase> <workspace_type> <workspace_root> <expected_branch> <base_commit> <manifest_path> <artifact_root> [<candidate_commit>]", file=sys.stderr)
            sys.exit(2)

        candidate_commit = sys.argv[14] if len(sys.argv) > 14 else None

        passport = create_passport(
            project_id=sys.argv[2],
            run_id=sys.argv[3],
            slot_id=sys.argv[4],
            story_id=sys.argv[5],
            role=sys.argv[6],
            phase=sys.argv[7],
            workspace_type=sys.argv[8],
            workspace_root=sys.argv[9],
            expected_branch=sys.argv[10],
            base_commit=sys.argv[11],
            manifest_path=sys.argv[12],
            artifact_root=sys.argv[13],
            candidate_commit=candidate_commit
        )

        print(passport.to_json())
        sys.exit(0)

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(2)
