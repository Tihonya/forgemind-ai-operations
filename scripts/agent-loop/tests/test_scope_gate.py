#!/usr/bin/env python3
"""
Unit tests for the manifest-driven scope gate (WP-AL-1B2B).

Covers:
- gitwildmatch semantics (anchoring, **, ?, character classes, dir patterns)
- scope_check decisions: NO_CHANGES, SCOPE_OK, SCOPE_VIOLATIONS, ERROR
- candidate diff enumeration vs manifest base_commit (incl. untracked files)
- scope failures propagate (no masking) — verified via exit codes

All tests build disposable temporary Git repositories; the real repository
is never mutated.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

LIB_DIR = Path(__file__).resolve().parent.parent / "lib"
sys.path.insert(0, str(LIB_DIR))

import harness  # noqa: E402

GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "Scope Test",
    "GIT_AUTHOR_EMAIL": "scope@test.local",
    "GIT_COMMITTER_NAME": "Scope Test",
    "GIT_COMMITTER_EMAIL": "scope@test.local",
    "GIT_AUTHOR_DATE": "2024-01-01T00:00:00+00:00",
    "GIT_COMMITTER_DATE": "2024-01-01T00:00:00+00:00",
}

_MANIFESTS: list[Path] = []


def _git(repo: Path, *args: str) -> None:
    env = os.environ.copy()
    env.update(GIT_IDENTITY)
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env=env,
    )


@pytest.fixture()
def temp_git_repo():
    """Disposable standalone Git repo with one deterministic base commit."""
    tmp = tempfile.mkdtemp(prefix="scope-gate-test-")
    repo = Path(tmp)
    _git(repo, "init", "-q", "-b", "test")
    _git(repo, "config", "user.name", "Scope Test")
    _git(repo, "config", "user.email", "scope@test.local")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "base.txt").write_text("base\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    yield repo
    import shutil

    shutil.rmtree(repo, ignore_errors=True)
    for m in _MANIFESTS:
        try:
            m.unlink()
        except OSError:
            pass
    _MANIFESTS.clear()


def _write_manifest(repo: Path, allowed, forbidden, base_sha: str) -> Path:
    """Write the manifest OUTSIDE the repo so it never joins the candidate diff."""
    manifest = {
        "schema_version": "1.0",
        "project_id": "forgemind",
        "story_id": "SCOPE-TEST",
        "title": "Scope gate unit test",
        "description": "Synthetic",
        "base_commit": base_sha,
        "expected_branch": "test",
        "path_pattern_type": "gitwildmatch",
        "allowed_paths": allowed,
        "forbidden_paths": forbidden,
        "required_gates": [
            "scope", "json_syntax", "yaml_syntax", "targeted_tests",
            "lint", "secrets", "git_diff_check",
        ],
        "test_commands": {"targeted_args": []},
        "environment_requirements": {
            "database": {"required": False, "auto_start": False},
            "redis": {"required": False, "auto_start": False},
            "external_network": {"allowed": False},
        },
        "expected_outputs": [],
        "acceptance_criteria": ["scope gate decides correctly"],
        "repair_budget": 0,
        "model_routing_hints": {
            "implementation_role": "implementer",
            "review_role": "reviewer",
            "complexity": "low",
            "local_worker_allowed": True,
        },
        "dependencies": [],
        "conflict_domains": [],
    }
    fd, path_str = tempfile.mkstemp(
        prefix="scope-gate-manifest-", suffix=".json"
    )
    os.close(fd)
    path = Path(path_str)
    path.write_text(json.dumps(manifest, indent=2))
    _MANIFESTS.append(path)
    return path


def _base_sha(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


# ============================================================================
# gitwildmatch semantics
# ============================================================================

class TestGitwildmatch:
    def test_double_star_prefix_matches_all_below(self):
        assert harness.gitwildmatch("backend/tests/x.py", "backend/**")
        assert harness.gitwildmatch("backend/a/b/c.py", "backend/**")

    def test_double_star_prefix_does_not_match_dir_name_itself(self):
        assert not harness.gitwildmatch("backend", "backend/**")

    def test_unanchored_basename_matches_any_depth(self):
        assert harness.gitwildmatch(".env", ".env")
        assert harness.gitwildmatch("backend/.env", ".env")
        assert harness.gitwildmatch("backend/keys/x.pem", "*.pem")

    def test_anchored_by_interior_slash(self):
        assert harness.gitwildmatch("backend/tests/x.py", "backend/tests/**")
        assert not harness.gitwildmatch("backend/app/x.py", "backend/tests/**")

    def test_leading_slash_anchors_to_root(self):
        assert harness.gitwildmatch("src/x.py", "/src/x.py")
        assert not harness.gitwildmatch("deep/src/x.py", "/src/x.py")

    def test_middle_double_star(self):
        assert harness.gitwildmatch("a/b/c.py", "a/**/c.py")
        assert harness.gitwildmatch("a/c.py", "a/**/c.py")
        assert harness.gitwildmatch("a/b/d/c.py", "a/**/c.py")

    def test_leading_double_star(self):
        assert harness.gitwildmatch("a/b/c.py", "**/c.py")
        assert harness.gitwildmatch("c.py", "**/c.py")
        assert not harness.gitwildmatch("x/c.py.bak", "**/c.py")

    def test_question_mark_single_char(self):
        assert harness.gitwildmatch("src/ab.py", "src/a?.py")
        assert not harness.gitwildmatch("src/abc.py", "src/a?.py")

    def test_character_class(self):
        assert harness.gitwildmatch("src/a1.py", "src/a[0-9].py")
        assert not harness.gitwildmatch("src/ax.py", "src/a[0-9].py")

    def test_negated_character_class(self):
        assert not harness.gitwildmatch("src/a1.py", "src/a[!0-9].py")
        assert harness.gitwildmatch("src/ax.py", "src/a[!0-9].py")

    def test_dir_pattern_matches_files_below(self):
        assert harness.gitwildmatch("docs/x/y.md", "docs/")
        assert not harness.gitwildmatch("docs", "docs/")

    def test_paths_with_spaces(self):
        assert harness.gitwildmatch(
            "tests/synthetic/path with spaces/test.py", "tests/**"
        )

    def test_negation_pattern_rejected(self):
        with pytest.raises(ValueError):
            harness.gitwildmatch("a", "!a")

    def test_empty_pattern_rejected(self):
        with pytest.raises(ValueError):
            harness.gitwildmatch("a", "")


# ============================================================================
# Candidate diff enumeration
# ============================================================================

class TestCandidateDiff:
    def test_clean_tree_no_changes(self, temp_git_repo):
        base = _base_sha(temp_git_repo)
        status, files = harness.list_candidate_diff_files(
            str(temp_git_repo), base
        )
        assert status == "OK"
        assert files == []

    def test_untracked_file_included(self, temp_git_repo):
        base = _base_sha(temp_git_repo)
        (temp_git_repo / "new_file.txt").write_text("new\n")
        status, files = harness.list_candidate_diff_files(
            str(temp_git_repo), base
        )
        assert status == "OK"
        assert "new_file.txt" in files

    def test_modified_file_included(self, temp_git_repo):
        base = _base_sha(temp_git_repo)
        (temp_git_repo / "base.txt").write_text("changed\n")
        status, files = harness.list_candidate_diff_files(
            str(temp_git_repo), base
        )
        assert status == "OK"
        assert "base.txt" in files

    def test_missing_base_commit(self, temp_git_repo):
        status, files = harness.list_candidate_diff_files(
            str(temp_git_repo), "f" * 40
        )
        assert status == "BASE_COMMIT_MISSING"
        assert files == []


# ============================================================================
# scope_check decisions
# ============================================================================

class TestScopeCheck:
    def test_no_changes(self, temp_git_repo):
        base = _base_sha(temp_git_repo)
        manifest = _write_manifest(
            temp_git_repo, ["**"], [".env"], base
        )
        verdict = harness.scope_check(str(manifest), str(temp_git_repo))
        assert verdict["status"] == "NO_CHANGES"

    def test_scope_ok_allowed_change(self, temp_git_repo):
        base = _base_sha(temp_git_repo)
        (temp_git_repo / "src").mkdir()
        (temp_git_repo / "src" / "new.py").write_text("x = 1\n")
        manifest = _write_manifest(
            temp_git_repo, ["src/**"], [".env"], base
        )
        verdict = harness.scope_check(str(manifest), str(temp_git_repo))
        assert verdict["status"] == "SCOPE_OK"
        assert verdict["file_count"] == 1

    def test_scope_violation_not_allowed(self, temp_git_repo):
        base = _base_sha(temp_git_repo)
        (temp_git_repo / "outside").mkdir()
        (temp_git_repo / "outside" / "new.py").write_text("x = 1\n")
        manifest = _write_manifest(
            temp_git_repo, ["src/**"], [".env"], base
        )
        verdict = harness.scope_check(str(manifest), str(temp_git_repo))
        assert verdict["status"] == "SCOPE_VIOLATIONS"
        assert verdict["violations"][0]["reason"] == "NOT_ALLOWED"
        assert verdict["violations"][0]["file"] == "outside/new.py"

    def test_forbidden_wins_over_allowed(self, temp_git_repo):
        base = _base_sha(temp_git_repo)
        (temp_git_repo / "src").mkdir()
        (temp_git_repo / "src" / ".env").write_text("SECRET\n")
        manifest = _write_manifest(
            temp_git_repo, ["src/**", "**"], [".env"], base
        )
        verdict = harness.scope_check(str(manifest), str(temp_git_repo))
        assert verdict["status"] == "SCOPE_VIOLATIONS"
        assert verdict["violations"][0]["reason"] == "FORBIDDEN"

    def test_missing_base_commit_is_error(self, temp_git_repo):
        manifest = _write_manifest(
            temp_git_repo, ["**"], [".env"], "f" * 40
        )
        verdict = harness.scope_check(str(manifest), str(temp_git_repo))
        assert verdict["status"] == "ERROR"
        assert "base_commit" in verdict["error"]

    def test_unreadable_manifest_is_error(self, temp_git_repo):
        verdict = harness.scope_check(
            str(temp_git_repo / "nonexistent.json"), str(temp_git_repo)
        )
        assert verdict["status"] == "ERROR"


# ============================================================================
# CLI exit-code propagation (no masking)
# ============================================================================

class TestScopeCheckCli:
    def _run_cli(self, manifest: Path, repo: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                str(LIB_DIR / "harness.py"),
                "scope_check",
                str(manifest),
                str(repo),
            ],
            capture_output=True,
            text=True,
        )

    def test_exit_0_on_scope_ok(self, temp_git_repo):
        base = _base_sha(temp_git_repo)
        (temp_git_repo / "src").mkdir()
        (temp_git_repo / "src" / "new.py").write_text("x = 1\n")
        manifest = _write_manifest(
            temp_git_repo, ["src/**"], [".env"], base
        )
        result = self._run_cli(manifest, temp_git_repo)
        assert result.returncode == 0
        assert json.loads(result.stdout)["status"] == "SCOPE_OK"

    def test_exit_1_on_violation(self, temp_git_repo):
        base = _base_sha(temp_git_repo)
        (temp_git_repo / "outside").mkdir()
        (temp_git_repo / "outside" / "new.py").write_text("x = 1\n")
        manifest = _write_manifest(
            temp_git_repo, ["src/**"], [".env"], base
        )
        result = self._run_cli(manifest, temp_git_repo)
        assert result.returncode == 1
        verdict = json.loads(result.stdout)
        assert verdict["status"] == "SCOPE_VIOLATIONS"
        assert verdict["violations"][0]["reason"] == "NOT_ALLOWED"

    def test_exit_2_on_missing_base_commit(self, temp_git_repo):
        manifest = _write_manifest(
            temp_git_repo, ["**"], [".env"], "f" * 40
        )
        result = self._run_cli(manifest, temp_git_repo)
        assert result.returncode == 2
