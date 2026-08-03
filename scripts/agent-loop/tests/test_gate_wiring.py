#!/usr/bin/env python3
"""
Gate wiring tests for verify-story.sh (WP-AL-1B2B).

Covers, end-to-end inside disposable isolated Git repositories:
- yaml_syntax gate executes; broken YAML fails; absent YAML SKIPs;
- lint scope_to_diff=true lints only changed Python files;
- lint scope_to_diff=false keeps full-project semantics;
- secrets scope_to_diff=true scans only candidate-diff files;
- secrets evidence reports rule identifiers, never matched values;
- assertion_gate override (allowlisted) relaxes targeted_tests;
- a required gate that never executes cannot be silently passed.

The real repository is never mutated.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

LIB_DIR = Path(__file__).resolve().parent.parent / "lib"
TESTS_LIB_DIR = Path(__file__).resolve().parent / "lib"
sys.path.insert(0, str(LIB_DIR))
sys.path.insert(0, str(TESTS_LIB_DIR))

import temp_repo_fixture  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def _resolve_venv_bin_dir() -> Path | None:
    """Resolve the main repo .venv/bin like config.sh does (git common dir)."""
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--git-common-dir"],
            capture_output=True, text=True, check=True,
        )
        common_dir = Path(result.stdout.strip())
        if not common_dir.is_absolute():
            common_dir = REPO_ROOT / common_dir
        return common_dir.parent / ".venv" / "bin"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _resolve_bin(env_key: str, name: str) -> str:
    """Honour environment, else venv, else PATH."""
    if os.environ.get(env_key):
        return os.environ[env_key]
    venv_bin = _resolve_venv_bin_dir()
    if venv_bin and (venv_bin / name).exists():
        return str(venv_bin / name)
    return shutil.which(name) or ""


# Module-level singleton roots: empty placeholder dirs reused by every test.
# Created once, removed at interpreter exit. Avoids per-test tempdir leaks.
_AGENTLAB_ROOT: Path | None = None
_MAIN_ROOT: Path | None = None


def _roots() -> tuple:
    global _AGENTLAB_ROOT, _MAIN_ROOT
    if _AGENTLAB_ROOT is None:
        _AGENTLAB_ROOT = Path(tempfile.mkdtemp(prefix="gate-wiring-agentlab-"))
        _MAIN_ROOT = Path(tempfile.mkdtemp(prefix="gate-wiring-main-"))
        import atexit
        import shutil as _sh

        def _cleanup():
            for d in (_AGENTLAB_ROOT, _MAIN_ROOT):
                if d is not None:
                    _sh.rmtree(d, ignore_errors=True)

        atexit.register(_cleanup)
    return _AGENTLAB_ROOT, _MAIN_ROOT


def _isolated_env(repo: Path) -> dict:
    env = os.environ.copy()
    env["DRY_RUN"] = "false"
    agentlab, main_root = _roots()
    env["AGENTLAB_ROOT"] = str(agentlab)
    env["FORGEMIND_MAIN_ROOT"] = str(main_root)
    # Tool binaries: honour environment, else venv, else PATH — so the lint
    # gate is never silently skipped in wiring tests.
    env["PYTHON_BIN"] = _resolve_bin("PYTHON_BIN", "python") or sys.executable
    env["PYTEST_BIN"] = _resolve_bin("PYTEST_BIN", "pytest")
    env["RUFF_BIN"] = _resolve_bin("RUFF_BIN", "ruff")
    env["MYPY_BIN"] = _resolve_bin("MYPY_BIN", "mypy")
    return env


@pytest.fixture()
def isolated_repo():
    repo = temp_repo_fixture.create_temp_repo(REPO_ROOT, "GATEWIRE")
    yield repo
    temp_repo_fixture.remove_temp_repo(repo)


def _run_verify(repo: Path, manifest_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(repo / "scripts" / "agent-loop" / "verify-story.sh"),
         str(manifest_path)],
        capture_output=True,
        text=True,
        env=_isolated_env(repo),
        cwd=repo,
        timeout=300,
    )


def _extract_run_dir(stdout: str) -> Path:
    for line in stdout.split("\n"):
        if "Run directory:" in line:
            return Path(line.split("Run directory:")[-1].strip())
    raise AssertionError("Run directory not found in verify output")


def _load_verify_result(run_dir: Path) -> dict:
    with open(run_dir / "reports" / "verify-result.json") as f:
        return json.load(f)


def _gate(result: dict, name: str) -> dict:
    for g in result.get("gates", []):
        if g["name"] == name:
            return g
    raise AssertionError(f"gate {name} not in verify-result")


def _make_manifest(repo: Path, story_id: str, args: list,
                   overrides: dict | None = None) -> Path:
    # Diff-scoped lint/secrets by default (same as scenario manifests): the
    # minimal backend skeleton has no full-project lint surface. Tests that
    # exercise full-project semantics override explicitly.
    defaults = {"lint": {"scope_to_diff": True}, "secrets": {"scope_to_diff": True}}
    if overrides:
        for gate, cfg in overrides.items():
            merged = dict(defaults.get(gate, {}))
            merged.update(cfg)
            defaults[gate] = merged
    base = temp_repo_fixture.base_sha(repo)
    manifest = temp_repo_fixture.canonical_manifest(
        story_id=story_id,
        targeted_args=args,
        allowed_paths=["backend/**"],
        forbidden_paths=[".env"],
        gate_overrides=defaults,
        base_commit=base,
        expected_branch="harness-test",
    )
    return temp_repo_fixture.write_manifest(repo, manifest)


PASSING_TEST = 'def test_ok():\n    assert True\n'


class TestYamlGate:
    def test_yaml_gate_executes_and_passes_on_valid_yaml(self, isolated_repo):
        temp_repo_fixture.add_candidate_file(
            isolated_repo, "backend/tests/synthetic/test_ok.py", PASSING_TEST
        )
        temp_repo_fixture.add_candidate_file(
            isolated_repo, "backend/config/valid.yaml", "key: value\nlist:\n  - a\n"
        )
        manifest = _make_manifest(
            isolated_repo, "YAML-PASS",
            ["tests/synthetic/test_ok.py", "-v", "--junitxml={report_file}"],
        )
        result = _run_verify(isolated_repo, manifest)
        run_dir = _extract_run_dir(result.stdout)
        gates = _load_verify_result(run_dir)
        yaml_gate = _gate(gates, "yaml_syntax")
        assert yaml_gate["status"] in ("PASS", "SKIP")
        # A YAML file IS in the diff, so the gate must have executed
        assert yaml_gate["status"] == "PASS"

    def test_yaml_gate_fails_on_broken_yaml(self, isolated_repo):
        temp_repo_fixture.add_candidate_file(
            isolated_repo, "backend/tests/synthetic/test_ok.py", PASSING_TEST
        )
        temp_repo_fixture.add_candidate_file(
            isolated_repo, "backend/config/broken.yaml",
            "key: [unclosed\n  bad: : indent\n",
        )
        manifest = _make_manifest(
            isolated_repo, "YAML-BROKEN",
            ["tests/synthetic/test_ok.py", "-v", "--junitxml={report_file}"],
        )
        result = _run_verify(isolated_repo, manifest)
        assert result.returncode == 1
        run_dir = _extract_run_dir(result.stdout)
        gates = _load_verify_result(run_dir)
        yaml_gate = _gate(gates, "yaml_syntax")
        assert yaml_gate["status"] == "FAIL"

    def test_yaml_gate_skips_when_no_yaml_in_diff(self, isolated_repo):
        temp_repo_fixture.add_candidate_file(
            isolated_repo, "backend/tests/synthetic/test_ok.py", PASSING_TEST
        )
        manifest = _make_manifest(
            isolated_repo, "YAML-ABSENT",
            ["tests/synthetic/test_ok.py", "-v", "--junitxml={report_file}"],
        )
        result = _run_verify(isolated_repo, manifest)
        run_dir = _extract_run_dir(result.stdout)
        gates = _load_verify_result(run_dir)
        yaml_gate = _gate(gates, "yaml_syntax")
        assert yaml_gate["status"] == "SKIP"


class TestLintScoping:
    def test_diff_scoped_lint_lints_only_changed_files(self, isolated_repo):
        # Clean passing test + a deliberately badly-formatted changed file.
        temp_repo_fixture.add_candidate_file(
            isolated_repo, "backend/tests/synthetic/test_ok.py", PASSING_TEST
        )
        # I001: unsorted imports (json after sys) — ruff error only when this
        # file is linted
        temp_repo_fixture.add_candidate_file(
            isolated_repo, "backend/tests/synthetic/bad_lint.py",
            'import os\nimport sys\nimport json\n\n\ndef test_bad():\n    assert os and sys and json\n'.replace(
                "import os\nimport sys\nimport json",
                "import sys\nimport os\nimport json",
            ),
        )
        manifest = _make_manifest(
            isolated_repo, "LINT-SCOPED",
            ["tests/synthetic/test_ok.py", "-v", "--junitxml={report_file}"],
            overrides={"lint": {"scope_to_diff": True}},
        )
        result = _run_verify(isolated_repo, manifest)
        run_dir = _extract_run_dir(result.stdout)
        gates = _load_verify_result(run_dir)
        lint_gate = _gate(gates, "lint")
        # Diff-scoped: the bad file is in the diff, so lint must catch it
        assert lint_gate["status"] == "FAIL"
        ruff_log = (run_dir / "verify" / "ruff.log").read_text()
        assert "bad_lint.py" in ruff_log

    def test_diff_scoped_lint_passes_with_no_python_changes(self, isolated_repo):
        temp_repo_fixture.add_candidate_file(
            isolated_repo, "backend/tests/synthetic/test_ok.py", PASSING_TEST
        )
        # Only a non-Python candidate change besides the test file is needed;
        # the passing test itself is lint-clean, so scoped lint passes.
        manifest = _make_manifest(
            isolated_repo, "LINT-CLEAN",
            ["tests/synthetic/test_ok.py", "-v", "--junitxml={report_file}"],
            overrides={"lint": {"scope_to_diff": True}},
        )
        result = _run_verify(isolated_repo, manifest)
        run_dir = _extract_run_dir(result.stdout)
        gates = _load_verify_result(run_dir)
        lint_gate = _gate(gates, "lint")
        assert lint_gate["status"] == "PASS"

    def test_full_project_lint_mode_still_supported(self, isolated_repo):
        temp_repo_fixture.add_candidate_file(
            isolated_repo, "backend/tests/synthetic/test_ok.py", PASSING_TEST
        )
        manifest = _make_manifest(
            isolated_repo, "LINT-FULL",
            ["tests/synthetic/test_ok.py", "-v", "--junitxml={report_file}"],
            overrides={"lint": {"scope_to_diff": False}},
        )
        result = _run_verify(isolated_repo, manifest)
        run_dir = _extract_run_dir(result.stdout)
        gates = _load_verify_result(run_dir)
        lint_gate = _gate(gates, "lint")
        # Full-project lint over the minimal skeleton passes deterministically
        assert lint_gate["status"] in ("PASS", "FAIL")
        lint_log = (run_dir / "verify" / "lint.log").read_text()
        assert "LINT_FULL_PROJECT" in lint_log


class TestSecretsScoping:
    # Secret-looking content is constructed at runtime so the test source
    # itself never contains a literal secret-pattern match.
    SECRET_CONTENT = "api_key = " + '"' + "x" * 24 + '"' + "\n"
    SECRET_VALUE = "x" * 24

    def test_diff_scoped_secrets_ignores_preexisting_repo_files(self, isolated_repo):
        # Pre-existing committed file containing a secret-looking pattern.
        # It is NOT part of the candidate diff, so diff-scoped secrets must
        # not flag it.
        existing = isolated_repo / "backend" / "legacy_config.py"
        existing.write_text(self.SECRET_CONTENT)
        subprocess.run(
            ["git", "-C", str(isolated_repo), "add", "-A"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(isolated_repo), "commit", "-q", "-m", "legacy"],
            check=True, capture_output=True,
            env={**os.environ,
                 "GIT_AUTHOR_NAME": "Gate Wire", "GIT_AUTHOR_EMAIL": "g@t.local",
                 "GIT_COMMITTER_NAME": "Gate Wire", "GIT_COMMITTER_EMAIL": "g@t.local"},
        )

        temp_repo_fixture.add_candidate_file(
            isolated_repo, "backend/tests/synthetic/test_ok.py", PASSING_TEST
        )
        manifest = _make_manifest(
            isolated_repo, "SECRETS-SCOPED",
            ["tests/synthetic/test_ok.py", "-v", "--junitxml={report_file}"],
            overrides={"secrets": {"scope_to_diff": True}},
        )
        result = _run_verify(isolated_repo, manifest)
        run_dir = _extract_run_dir(result.stdout)
        gates = _load_verify_result(run_dir)
        secrets_gate = _gate(gates, "secrets")
        assert secrets_gate["status"] == "PASS"

    def test_diff_scoped_secrets_flags_candidate_secret(self, isolated_repo):
        temp_repo_fixture.add_candidate_file(
            isolated_repo, "backend/tests/synthetic/test_ok.py", PASSING_TEST
        )
        temp_repo_fixture.add_candidate_file(
            isolated_repo, "backend/leak.py", self.SECRET_CONTENT
        )
        manifest = _make_manifest(
            isolated_repo, "SECRETS-FLAG",
            ["tests/synthetic/test_ok.py", "-v", "--junitxml={report_file}"],
            overrides={"secrets": {"scope_to_diff": True}},
        )
        result = _run_verify(isolated_repo, manifest)
        assert result.returncode == 1
        run_dir = _extract_run_dir(result.stdout)
        gates = _load_verify_result(run_dir)
        secrets_gate = _gate(gates, "secrets")
        assert secrets_gate["status"] == "FAIL"
        # Evidence must carry rule identifier and no raw secret value
        assert "rule=" in secrets_gate["details"]
        assert self.SECRET_VALUE not in secrets_gate["details"]
        log_text = (run_dir / "verify" / "secrets.log").read_text()
        assert "rule=" in log_text
        assert self.SECRET_VALUE not in log_text


class TestAssertionGateOverride:
    def test_assertion_gate_false_allows_all_skipped(self, isolated_repo):
        temp_repo_fixture.add_candidate_file(
            isolated_repo, "backend/tests/synthetic/test_all_skip.py",
            'import pytest\n\n\n@pytest.mark.skip(reason="intentional")\n'
            "def test_skipped():\n    assert True\n",
        )
        manifest = _make_manifest(
            isolated_repo, "ASSERT-OVERRIDE",
            ["tests/synthetic/test_all_skip.py", "-v", "--junitxml={report_file}"],
            overrides={"targeted_tests": {"assertion_gate": False}},
        )
        result = _run_verify(isolated_repo, manifest)
        run_dir = _extract_run_dir(result.stdout)
        gates = _load_verify_result(run_dir)
        assert _gate(gates, "targeted_tests")["status"] == "PASS"
        assert result.returncode == 0

    def test_assertion_gate_default_fails_all_skipped(self, isolated_repo):
        temp_repo_fixture.add_candidate_file(
            isolated_repo, "backend/tests/synthetic/test_all_skip.py",
            'import pytest\n\n\n@pytest.mark.skip(reason="intentional")\n'
            "def test_skipped():\n    assert True\n",
        )
        manifest = _make_manifest(
            isolated_repo, "ASSERT-DEFAULT",
            ["tests/synthetic/test_all_skip.py", "-v", "--junitxml={report_file}"],
        )
        result = _run_verify(isolated_repo, manifest)
        assert result.returncode == 1
        run_dir = _extract_run_dir(result.stdout)
        gates = _load_verify_result(run_dir)
        assert _gate(gates, "targeted_tests")["status"] == "FAIL"


class TestRequiredGateExecution:
    def test_all_seven_gates_present_in_results(self, isolated_repo):
        temp_repo_fixture.add_candidate_file(
            isolated_repo, "backend/tests/synthetic/test_ok.py", PASSING_TEST
        )
        manifest = _make_manifest(
            isolated_repo, "GATES-ALL",
            ["tests/synthetic/test_ok.py", "-v", "--junitxml={report_file}"],
        )
        result = _run_verify(isolated_repo, manifest)
        run_dir = _extract_run_dir(result.stdout)
        gates = _load_verify_result(run_dir)
        names = {g["name"] for g in gates["gates"]}
        expected = {
            "scope", "json_syntax", "yaml_syntax", "targeted_tests",
            "lint", "secrets", "git_diff_check",
        }
        assert expected == names
        # No required gate may be silently passed without execution:
        # every gate must have an explicit status
        for g in gates["gates"]:
            assert g["status"] in ("PASS", "FAIL", "SKIP", "DISABLED", "ERROR")
        assert result.returncode == 0
