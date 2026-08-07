"""
WP-AL-1C5 PR #56 review remediation regression tests.

Each test corresponds to a confirmed finding from the independent review:

  R1 (HIGH-1, DEC-R3) — absolute filesystem paths in actor stdout/stderr
      must be redacted from persisted diagnostics.
  R2 (HIGH-2, DEC-R2) — final repair-adapter-result.json publication failure
      must not let run_repair return ADAPTER_SUCCESS.
  R3 (HIGH-2, DEC-R2) — atomic-write temp naming must be unpredictable
      (not derived solely from PID).
  R4 (HIGH-3, DEC-R1) — a pre-existing non-excluded untracked file must cause
      ADAPTER_DIRTY_BASELINE before actor invocation.
  R5 (MEDIUM-1, DEC-R4) — sanitization metadata must reflect actual redaction
      counts and truncation flags produced during output sanitization.
  R6 (LOW-1)           — BB-SAFETY-05 must contain a real bounded assertion.

These tests are written to FAIL against the pre-fix implementation and PASS
after the remediation is applied.
"""

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Generator, Iterator
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from repair_adapter import (
    ADAPTER_DIRTY_BASELINE,
    ADAPTER_INTERNAL_ERROR,
    ADAPTER_OUTPUT_SIZE_EXCEEDED,
    ADAPTER_SUCCESS,
    _atomic_write_json,
    _sanitize_output,
    run_repair,
    validate_adapter_result,
)

# ---------------------------------------------------------------------------
# Shared helpers (mirror the block-B fixtures without cross-file coupling)
# ---------------------------------------------------------------------------


def _make_valid_repair_request(
    *,
    run_id: str = "run-123",
    story_id: str = "story-456",
    attempt: int = 1,
    max_attempts: int = 3,
    source_revision: str = "a" * 40,
    failure_class: str = "verification_fail",
    failure_summary: str = "Test failure",
    allowed_paths: list[str] | None = None,
    forbidden_paths: list[str] | None = None,
) -> dict[str, Any]:
    if allowed_paths is None:
        allowed_paths = ["**/*"]
    if forbidden_paths is None:
        forbidden_paths = []
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "story_id": story_id,
        "attempt": attempt,
        "max_attempts": max_attempts,
        "source_revision": source_revision,
        "failure_class": failure_class,
        "failure_summary": failure_summary,
        "failure_context_ref": {
            "path": "failure-context.json",
            "schema_version": "1.0",
            "sha256": "a" * 64,
        },
        "verification_result_ref": {
            "path": "verification-result.json",
            "schema_version": "1.0",
            "sha256": "a" * 64,
        },
        "review_result_ref": None,
        "allowed_paths": allowed_paths,
        "forbidden_paths": forbidden_paths,
        "repair_guidance": [],
        "requested_action": "fix_verification",
        "generated_at": "2026-08-06T12:00:00Z",
    }


def _get_head_sha(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _create_actor_script(tmp_dir: Path, content: str, name: str = "actor.py") -> Path:
    script = tmp_dir / name
    script.write_text(f"#!/usr/bin/env python3\n{content}")
    script.chmod(0o755)
    return script


@pytest.fixture
def temp_git_repo() -> Generator[Path, None, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir) / "repo"
        repo_root.mkdir()
        subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_root, check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_root, check=True, capture_output=True,
        )
        (repo_root / "README.md").write_text("# Test\n")
        subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_root, check=True, capture_output=True)
        yield repo_root


@pytest.fixture
def run_dir(temp_git_repo: Path) -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as tmpdir:
        rd = Path(tmpdir) / "runs" / "run-123"
        rd.mkdir(parents=True)
        yield rd


@pytest.fixture
def actor_dir() -> Generator[Path, None, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


# ===========================================================================
# R1 — absolute path leakage (HIGH-1, DEC-R3)
# ===========================================================================


class TestR1AbsolutePathLeakage:
    """R1: absolute filesystem paths must be redacted from actor diagnostics."""

    def test_posix_absolute_path_absent_from_result(
        self, temp_git_repo: Path, run_dir: Path, actor_dir: Path,
    ) -> None:
        """Actor emits a known POSIX absolute path; it must not survive into
        the persisted adapter-result diagnostics or the in-memory result."""
        source_revision = _get_head_sha(temp_git_repo)
        leaked_path = "/tmp/leaked/actor/internal/path"
        actor_script = _create_actor_script(
            actor_dir,
            f"""
import json, sys
print("{leaked_path}")
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "NO_CHANGE", "changed": False, "changed_files": [],
    "summary": "No changes",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "abort",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
        )

        repair_request = _make_valid_repair_request(source_revision=source_revision)
        result = run_repair(
            repo_root=temp_git_repo,
            run_dir=run_dir,
            repair_request=repair_request,
            actor_executable=str(actor_script),
            actor_arguments=[],
            timeout_seconds=30,
            max_output_bytes=4096,
            baseline_exclusions=[],
            completed_at="2026-08-06T12:00:00Z",
        )

        # In-memory result must not carry the literal absolute path.
        stdout_tail = result.diagnostics.get("actor_stdout_tail", "")
        assert leaked_path not in stdout_tail

        # Persisted artifact must not carry the literal absolute path either.
        adapter_result_path = run_dir / "repair" / "repair-adapter-result.json"
        assert adapter_result_path.exists()
        persisted = json.loads(adapter_result_path.read_text())
        persisted_stdout = persisted.get("diagnostics", {}).get("actor_stdout_tail", "")
        assert leaked_path not in persisted_stdout


# ===========================================================================
# R2 — final artifact publication failure (HIGH-2, DEC-R2)
# ===========================================================================


class TestR2FinalPublicationFailure:
    """R2: a final adapter-result write failure must not yield ADAPTER_SUCCESS."""

    def test_publication_failure_is_internal_error(
        self, temp_git_repo: Path, run_dir: Path, actor_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Force _atomic_write_json to fail on the final adapter-result write
        and verify run_repair does not return ADAPTER_SUCCESS."""
        source_revision = _get_head_sha(temp_git_repo)
        actor_script = _create_actor_script(
            actor_dir,
            f"""
import json, sys
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "NO_CHANGE", "changed": False, "changed_files": [],
    "summary": "No changes",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "abort",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
        )
        repair_request = _make_valid_repair_request(source_revision=source_revision)

        original_write = _atomic_write_json
        call_count = {"n": 0}

        def failing_write(path: Path, data: Any) -> None:
            call_count["n"] += 1
            target = str(path)
            # Only the final adapter-result publication should fail.
            if target.endswith("repair-adapter-result.json"):
                raise OSError("simulated publication failure")
            return original_write(path, data)

        # Patch the module-level name used inside run_repair.
        import repair_adapter as ra

        monkeypatch.setattr(ra, "_atomic_write_json", failing_write)

        result = run_repair(
            repo_root=temp_git_repo,
            run_dir=run_dir,
            repair_request=repair_request,
            actor_executable=str(actor_script),
            actor_arguments=[],
            timeout_seconds=30,
            max_output_bytes=4096,
            baseline_exclusions=[],
            completed_at="2026-08-06T12:00:00Z",
        )

        # No false success: the adapter must not claim ADAPTER_SUCCESS when
        # the final artifact could not be published.
        assert result.adapter_status != ADAPTER_SUCCESS
        assert result.adapter_status == ADAPTER_INTERNAL_ERROR


# ===========================================================================
# R3 — predictable temp collision (HIGH-2, DEC-R2)
# ===========================================================================


class TestR3UnpredictableTempName:
    """R3: the atomic-write temp name must be unpredictable."""

    def test_temp_name_not_pid_only(self, tmp_path: Path) -> None:
        """The temp file path produced during an atomic write must not be
        derivable from only the PID (`.name-tmp-{pid}`)."""
        target = tmp_path / "artifact.json"
        seen_tmp_names: list[str] = []

        original_replace = os.replace

        def capture_replace(src: str, dst: str) -> None:
            seen_tmp_names.append(Path(src).name)
            return original_replace(src, dst)

        # _atomic_write_json uses os.replace at module scope.
        try:
            os.replace = capture_replace  # type: ignore[assignment]
            _atomic_write_json(target, {"key": "value"})
        finally:
            os.replace = original_replace

        assert seen_tmp_names, "os.replace was not invoked — temp name not captured"
        tmp_name = seen_tmp_names[0]
        # The old scheme produced f".{path.name}-tmp-{pid}" which is fully
        # predictable. Assert the name is NOT of that predictable form.
        pid = os.getpid()
        predictable = f".{target.name}-tmp-{pid}"
        assert tmp_name != predictable, (
            f"temp name {tmp_name!r} is predictable from PID ({predictable!r})"
        )


# ===========================================================================
# R4 — pre-existing untracked deletion escape (HIGH-3, DEC-R1)
# ===========================================================================


class TestR4PreExistingUntrackedBaseline:
    """R4: a non-excluded pre-existing untracked file must cause
    ADAPTER_DIRTY_BASELINE before actor invocation."""

    def test_non_excluded_untracked_rejected(
        self, temp_git_repo: Path, run_dir: Path, actor_dir: Path,
    ) -> None:
        """A pre-existing untracked file not in baseline_exclusions must cause
        ADAPTER_DIRTY_BASELINE and the actor must not be invoked."""
        source_revision = _get_head_sha(temp_git_repo)

        # Create a pre-existing untracked file BEFORE actor invocation.
        (temp_git_repo / "pre_existing_untracked.txt").write_text("data\n")

        actor_invoked_marker = actor_dir / "actor_ran.marker"

        actor_script = _create_actor_script(
            actor_dir,
            f"""
import json, sys
# Mark that the actor was invoked — this test asserts it is NOT.
with open({str(actor_invoked_marker)!r}, "w") as f:
    f.write("ran")
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "NO_CHANGE", "changed": False, "changed_files": [],
    "summary": "No changes",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "abort",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
        )
        repair_request = _make_valid_repair_request(source_revision=source_revision)

        result = run_repair(
            repo_root=temp_git_repo,
            run_dir=run_dir,
            repair_request=repair_request,
            actor_executable=str(actor_script),
            actor_arguments=[],
            timeout_seconds=30,
            max_output_bytes=4096,
            baseline_exclusions=[],
            completed_at="2026-08-06T12:00:00Z",
        )

        assert result.adapter_status == ADAPTER_DIRTY_BASELINE
        # Actor must not have been invoked.
        assert not actor_invoked_marker.exists()

    def test_excluded_untracked_allowed(
        self, temp_git_repo: Path, run_dir: Path, actor_dir: Path,
    ) -> None:
        """An excluded pre-existing untracked file must be allowed."""
        source_revision = _get_head_sha(temp_git_repo)
        (temp_git_repo / "approved_artifact.txt").write_text("data\n")

        actor_script = _create_actor_script(
            actor_dir,
            f"""
import json, sys
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "NO_CHANGE", "changed": False, "changed_files": [],
    "summary": "No changes",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "abort",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
        )
        repair_request = _make_valid_repair_request(source_revision=source_revision)

        result = run_repair(
            repo_root=temp_git_repo,
            run_dir=run_dir,
            repair_request=repair_request,
            actor_executable=str(actor_script),
            actor_arguments=[],
            timeout_seconds=30,
            max_output_bytes=4096,
            baseline_exclusions=["approved_artifact.txt"],
            completed_at="2026-08-06T12:00:00Z",
        )

        assert result.adapter_status == ADAPTER_SUCCESS


# ===========================================================================
# R5 — sanitization metadata discarded (MEDIUM-1, DEC-R4)
# ===========================================================================


class TestR5SanitizationMetadata:
    """R5: redaction counts and truncation flags must be carried from
    _sanitize_output through ActorInvocationResult into RepairAdapterResult
    sanitization metadata."""

    def test_unit_redaction_count_returned(self, tmp_path: Path) -> None:
        """_sanitize_output itself returns a non-zero redaction_count for
        secret-bearing payloads. This is the precondition the integration
        must preserve."""
        payload = b"token=ghp_" + b"A" * 36 + b" more text"
        _sanitized, redaction_count, _truncated = _sanitize_output(payload, 4096)
        assert redaction_count > 0

    def test_unit_truncation_flag_returned(self) -> None:
        """_sanitize_output itself sets truncated=True at the byte boundary."""
        payload = b"x" * 100
        _sanitized, _count, truncated = _sanitize_output(payload, 10)
        assert truncated is True

    def test_integration_redaction_count_in_result(
        self, temp_git_repo: Path, run_dir: Path, actor_dir: Path,
    ) -> None:
        """Actor stdout contains a redactable secret; the adapter result's
        sanitization.redaction_count must reflect the redaction (>0)."""
        source_revision = _get_head_sha(temp_git_repo)
        actor_script = _create_actor_script(
            actor_dir,
            f"""
import json, sys
print("token=ghp_{'A' * 36}")
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "NO_CHANGE", "changed": False, "changed_files": [],
    "summary": "No changes",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "abort",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
        )
        repair_request = _make_valid_repair_request(source_revision=source_revision)
        result = run_repair(
            repo_root=temp_git_repo,
            run_dir=run_dir,
            repair_request=repair_request,
            actor_executable=str(actor_script),
            actor_arguments=[],
            timeout_seconds=30,
            max_output_bytes=4096,
            baseline_exclusions=[],
            completed_at="2026-08-06T12:00:00Z",
        )
        assert result.adapter_status == ADAPTER_SUCCESS
        san = result.sanitization
        assert san.get("redaction_count", 0) > 0, (
            f"redaction_count not reflected: {san}"
        )
        assert san.get("redaction_applied") is True

    def test_integration_truncation_in_result(
        self, temp_git_repo: Path, run_dir: Path, actor_dir: Path,
    ) -> None:
        """Actor stdout exceeds max_output_bytes; the adapter result's
        sanitization.truncation_applied must be True and the field listed."""
        source_revision = _get_head_sha(temp_git_repo)
        # Emit enough data to exceed a tiny max_output_bytes=8.
        actor_script = _create_actor_script(
            actor_dir,
            f"""
import json, sys
print("x" * 200)
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "NO_CHANGE", "changed": False, "changed_files": [],
    "summary": "No changes",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "abort",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
        )
        repair_request = _make_valid_repair_request(source_revision=source_revision)
        result = run_repair(
            repo_root=temp_git_repo,
            run_dir=run_dir,
            repair_request=repair_request,
            actor_executable=str(actor_script),
            actor_arguments=[],
            timeout_seconds=30,
            max_output_bytes=8,
            baseline_exclusions=[],
            completed_at="2026-08-06T12:00:00Z",
        )
        # Output overflow → ADAPTER_OUTPUT_SIZE_EXCEEDED; but sanitization
        # metadata must still reflect truncation truthfully.
        san = result.sanitization
        assert san.get("truncation_applied") is True, (
            f"truncation_applied not reflected: {san}"
        )
        assert "actor_stdout_tail" in san.get("truncated_fields", [])


# ===========================================================================
# R6 — empty safety test (LOW-1)
# ===========================================================================


class TestR6SafetyTestHasAssertion:
    """R6: test_BB_SAFETY_05_no_git_commands must contain an executable
    assertion. This meta-test asserts the safety test body is non-empty and
    contains at least one assert statement."""

    def test_safety_test_has_assertion(self) -> None:
        # Import the block-B module by file path to inspect the function body.
        block_b_path = Path(__file__).parent / "test_repair_adapter_block_b.py"
        source = block_b_path.read_text()
        # Locate the function body.
        marker = "def test_BB_SAFETY_05_no_git_commands"
        idx = source.index(marker)
        # Slice until the next top-level def or end-of-file.
        rest = source[idx:]
        lines = rest.splitlines()
        body_lines: list[str] = []
        for line in lines[1:]:
            if line.startswith(("def ", "class ")):
                break
            body_lines.append(line)
        body = "\n".join(body_lines)
        # The body must contain at least one real executable assertion.
        assert "assert" in body, (
            "test_BB_SAFETY_05_no_git_commands has no executable assertion"
        )


# ===========================================================================
# Additional DEC-R3 sanitization coverage (Step 3)
# ===========================================================================


class TestSanitizationAbsolutePathsExtended:
    """Extended coverage for absolute-path redaction (DEC-R3)."""

    def test_posix_absolute_path_redacted(self) -> None:
        """A POSIX absolute path is replaced with the stable token."""
        from repair_adapter import _redact_absolute_paths
        text = "failed at /tmp/actor/internal/path please check"
        result, count = _redact_absolute_paths(text, [])
        assert "/tmp/actor/internal/path" not in result
        assert "[REDACTED:absolute_path]" in result
        assert count >= 1

    def test_windows_drive_path_redacted(self) -> None:
        """A Windows drive-letter absolute path is replaced (cross-platform)."""
        from repair_adapter import _redact_absolute_paths
        text = "loaded C:\\Users\\actor\\secret.txt here"
        result, count = _redact_absolute_paths(text, [])
        assert "C:\\Users\\actor\\secret.txt" not in result
        assert "[REDACTED:absolute_path]" in result
        assert count >= 1

    def test_multiple_paths_redacted(self) -> None:
        """Multiple absolute paths in one stream are all redacted."""
        from repair_adapter import _redact_absolute_paths
        text = "/etc/passwd and /var/log/syslog and /home/user/.ssh/id_rsa"
        result, count = _redact_absolute_paths(text, [])
        assert "/etc/passwd" not in result
        assert "/var/log/syslog" not in result
        assert "/home/user/.ssh/id_rsa" not in result
        assert count >= 3

    def test_relative_path_preserved(self) -> None:
        """Ordinary relative repository paths are preserved (contractually useful)."""
        from repair_adapter import _redact_absolute_paths
        text = "modified scripts/agent-loop/lib/file.py and backend/test.py"
        result, _count = _redact_absolute_paths(text, [])
        assert "scripts/agent-loop/lib/file.py" in result
        assert "backend/test.py" in result

    def test_path_adjacent_to_punctuation(self) -> None:
        """A path adjacent to punctuation is redacted without corrupting the
        surrounding syntax."""
        from repair_adapter import _redact_absolute_paths
        text = 'error in "/tmp/actor/internal/path", aborting'
        result, count = _redact_absolute_paths(text, [])
        assert "/tmp/actor/internal/path" not in result
        assert "[REDACTED:absolute_path]" in result
        # The comma and quote structure must survive.
        assert '",' in result or '", [REDACTED:absolute_path]' in result or result.endswith('aborting')
        assert count >= 1

    def test_no_false_redaction_of_ordinary_text(self) -> None:
        """Ordinary text (no absolute paths) is not falsely redacted."""
        from repair_adapter import _redact_absolute_paths
        text = "ADAPTER_SUCCESS NO_CHANGE reverify backend/test.py"
        result, count = _redact_absolute_paths(text, [])
        assert result == text
        assert count == 0

    def test_persisted_artifact_has_no_literal_absolute_path(
        self, temp_git_repo: Path, run_dir: Path, actor_dir: Path,
    ) -> None:
        """The persisted repair-adapter-result.json must contain no literal
        absolute host path in any actor-derived diagnostic field."""
        source_revision = _get_head_sha(temp_git_repo)
        leaked_path = str(run_dir / "repair" / "internal" / "leaked")
        actor_script = _create_actor_script(
            actor_dir,
            f"""
import json, sys
print("{leaked_path}")
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "NO_CHANGE", "changed": False, "changed_files": [],
    "summary": "No changes",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "abort",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
        )
        repair_request = _make_valid_repair_request(source_revision=source_revision)
        result = run_repair(
            repo_root=temp_git_repo,
            run_dir=run_dir,
            repair_request=repair_request,
            actor_executable=str(actor_script),
            actor_arguments=[],
            timeout_seconds=30,
            max_output_bytes=4096,
            baseline_exclusions=[],
            completed_at="2026-08-06T12:00:00Z",
        )
        assert result.adapter_status == ADAPTER_SUCCESS
        adapter_result_path = run_dir / "repair" / "repair-adapter-result.json"
        assert adapter_result_path.exists()
        persisted = json.loads(adapter_result_path.read_text())
        diag = persisted.get("diagnostics", {})
        stdout_tail = diag.get("actor_stdout_tail", "")
        assert leaked_path not in stdout_tail


# ===========================================================================
# Additional DEC-R1 baseline coverage (Step 5)
# ===========================================================================


class TestUntrackedBaselineExtended:
    """Extended coverage for fail-closed untracked baseline (DEC-R1)."""

    def test_no_untracked_baseline_allowed(
        self, temp_git_repo: Path, run_dir: Path, actor_dir: Path,
    ) -> None:
        """A clean repo with no untracked files allows actor invocation."""
        source_revision = _get_head_sha(temp_git_repo)
        actor_script = _create_actor_script(
            actor_dir,
            f"""
import json, sys
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "NO_CHANGE", "changed": False, "changed_files": [],
    "summary": "No changes",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "abort",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
        )
        repair_request = _make_valid_repair_request(source_revision=source_revision)
        result = run_repair(
            repo_root=temp_git_repo,
            run_dir=run_dir,
            repair_request=repair_request,
            actor_executable=str(actor_script),
            actor_arguments=[],
            timeout_seconds=30,
            max_output_bytes=4096,
            baseline_exclusions=[],
            completed_at="2026-08-06T12:00:00Z",
        )
        assert result.adapter_status == ADAPTER_SUCCESS

    def test_multiple_untracked_paths_sorted_in_error(
        self, temp_git_repo: Path, run_dir: Path, actor_dir: Path,
    ) -> None:
        """Multiple non-excluded untracked paths cause ADAPTER_DIRTY_BASELINE
        and are reported in sorted order."""
        source_revision = _get_head_sha(temp_git_repo)
        # Create multiple untracked files (unsorted creation order).
        (temp_git_repo / "zeta.txt").write_text("z\n")
        (temp_git_repo / "alpha.txt").write_text("a\n")
        (temp_git_repo / "mid.txt").write_text("m\n")

        actor_script = _create_actor_script(actor_dir, "# noop")
        repair_request = _make_valid_repair_request(source_revision=source_revision)
        result = run_repair(
            repo_root=temp_git_repo,
            run_dir=run_dir,
            repair_request=repair_request,
            actor_executable=str(actor_script),
            actor_arguments=[],
            timeout_seconds=30,
            max_output_bytes=4096,
            baseline_exclusions=[],
            completed_at="2026-08-06T12:00:00Z",
        )
        assert result.adapter_status == ADAPTER_DIRTY_BASELINE
        # Error message must list paths in sorted order.
        msg = result.diagnostics.get("adapter_error_message", "")
        # alpha before mid before zeta in the message.
        assert msg.index("alpha.txt") < msg.index("mid.txt") < msg.index("zeta.txt")

    def test_ignored_path_outside_inspection(
        self, temp_git_repo: Path, run_dir: Path, actor_dir: Path,
    ) -> None:
        """A git-ignored untracked file does not cause baseline failure."""
        source_revision = _get_head_sha(temp_git_repo)
        # Create a .gitignore and an ignored file.
        (temp_git_repo / ".gitignore").write_text("*.log\n")
        (temp_git_repo / "debug.log").write_text("ignored\n")
        # .gitignore itself is untracked but must be excluded.
        actor_script = _create_actor_script(
            actor_dir,
            f"""
import json, sys
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "NO_CHANGE", "changed": False, "changed_files": [],
    "summary": "No changes",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "abort",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
        )
        repair_request = _make_valid_repair_request(source_revision=source_revision)
        result = run_repair(
            repo_root=temp_git_repo,
            run_dir=run_dir,
            repair_request=repair_request,
            actor_executable=str(actor_script),
            actor_arguments=[],
            timeout_seconds=30,
            max_output_bytes=4096,
            baseline_exclusions=[".gitignore"],
            completed_at="2026-08-06T12:00:00Z",
        )
        # The ignored debug.log is outside integrity scope; .gitignore is
        # excluded. The baseline must pass.
        assert result.adapter_status == ADAPTER_SUCCESS

    def test_actor_not_invoked_on_dirty_baseline(
        self, temp_git_repo: Path, run_dir: Path, actor_dir: Path,
    ) -> None:
        """When baseline is dirty (untracked non-excluded), the actor must
        never be invoked."""
        source_revision = _get_head_sha(temp_git_repo)
        (temp_git_repo / "pre_existing.txt").write_text("data\n")
        actor_invoked_marker = actor_dir / "ran.marker"
        actor_script = _create_actor_script(
            actor_dir,
            f"""
with open({str(actor_invoked_marker)!r}, "w") as f:
    f.write("ran")
""",
        )
        repair_request = _make_valid_repair_request(source_revision=source_revision)
        result = run_repair(
            repo_root=temp_git_repo,
            run_dir=run_dir,
            repair_request=repair_request,
            actor_executable=str(actor_script),
            actor_arguments=[],
            timeout_seconds=30,
            max_output_bytes=4096,
            baseline_exclusions=[],
            completed_at="2026-08-06T12:00:00Z",
        )
        assert result.adapter_status == ADAPTER_DIRTY_BASELINE
        assert not actor_invoked_marker.exists()

    def test_deletion_escape_regression(
        self, temp_git_repo: Path, run_dir: Path, actor_dir: Path,
    ) -> None:
        """Regression: an actor that deletes a pre-existing untracked file
        cannot evade detection. Under DEC-R1, the pre-existing untracked file
        causes ADAPTER_DIRTY_BASELINE before the actor even runs."""
        source_revision = _get_head_sha(temp_git_repo)
        # Pre-existing untracked file the actor would delete.
        (temp_git_repo / "pre_existing_untracked.txt").write_text("data\n")
        actor_script = _create_actor_script(
            actor_dir,
            "import os; os.remove('pre_existing_untracked.txt')\n"
            "import json, sys\n"
            'args = sys.argv[1:]\n'
            'result_path = args[args.index("--repair-result") + 1]\n'
            'result = {\n'
            '    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",\n'
            '    "attempt": 1, "source_revision": "' + source_revision + '",\n'
            '    "status": "NO_CHANGE", "changed": False, "changed_files": [],\n'
            '    "summary": "No changes",\n'
            '    "diagnostics": {"actions_taken": [], "obstacles": []},\n'
            '    "recommended_action": "abort",\n'
            '    "sanitization": {"redaction_applied": False, "redaction_count": 0,\n'
            '        "truncation_applied": False, "truncated_fields": []},\n'
            '    "completed_at": "2026-08-06T12:00:00Z"\n'
            '}\n'
            'with open(result_path, "w") as f:\n'
            '    json.dump(result, f)\n',
        )
        repair_request = _make_valid_repair_request(source_revision=source_revision)
        result = run_repair(
            repo_root=temp_git_repo,
            run_dir=run_dir,
            repair_request=repair_request,
            actor_executable=str(actor_script),
            actor_arguments=[],
            timeout_seconds=30,
            max_output_bytes=4096,
            baseline_exclusions=[],
            completed_at="2026-08-06T12:00:00Z",
        )
        # The actor never runs because the baseline is dirty.
        assert result.adapter_status == ADAPTER_DIRTY_BASELINE
        # The pre-existing file must still exist (actor did not run).
        assert (temp_git_repo / "pre_existing_untracked.txt").exists()


# ===========================================================================
# Additional DEC-R4 metadata coverage (Step 6)
# ===========================================================================


class TestSanitizationMetadataExtended:
    """Extended coverage for sanitization metadata accuracy (DEC-R4)."""

    def test_zero_operation_metadata(
        self, temp_git_repo: Path, run_dir: Path, actor_dir: Path,
    ) -> None:
        """Actor output with no redactions or truncation yields zero metadata."""
        source_revision = _get_head_sha(temp_git_repo)
        actor_script = _create_actor_script(
            actor_dir,
            f"""
import json, sys
print("clean output no secrets no paths")
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "NO_CHANGE", "changed": False, "changed_files": [],
    "summary": "No changes",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "abort",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
        )
        repair_request = _make_valid_repair_request(source_revision=source_revision)
        result = run_repair(
            repo_root=temp_git_repo,
            run_dir=run_dir,
            repair_request=repair_request,
            actor_executable=str(actor_script),
            actor_arguments=[],
            timeout_seconds=30,
            max_output_bytes=4096,
            baseline_exclusions=[],
            completed_at="2026-08-06T12:00:00Z",
        )
        assert result.adapter_status == ADAPTER_SUCCESS
        san = result.sanitization
        assert san["redaction_count"] == 0
        assert san["redaction_applied"] is False
        assert san["truncation_applied"] is False
        assert san["truncated_fields"] == []

    def test_invalid_utf8_does_not_corrupt_metadata(
        self, temp_git_repo: Path, run_dir: Path, actor_dir: Path,
    ) -> None:
        """Invalid UTF-8 bytes in actor output do not corrupt sanitization
        metadata or the adapter result."""
        source_revision = _get_head_sha(temp_git_repo)
        actor_script = _create_actor_script(
            actor_dir,
            f"""
import json, sys
sys.stdout.buffer.write(b"\\xff\\xfe bad bytes /tmp/leaked")
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "NO_CHANGE", "changed": False, "changed_files": [],
    "summary": "No changes",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "abort",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
        )
        repair_request = _make_valid_repair_request(source_revision=source_revision)
        result = run_repair(
            repo_root=temp_git_repo,
            run_dir=run_dir,
            repair_request=repair_request,
            actor_executable=str(actor_script),
            actor_arguments=[],
            timeout_seconds=30,
            max_output_bytes=4096,
            baseline_exclusions=[],
            completed_at="2026-08-06T12:00:00Z",
        )
        # The adapter must not crash; metadata must be valid.
        assert result.adapter_status == ADAPTER_SUCCESS
        san = result.sanitization
        assert isinstance(san["redaction_count"], int)
        # The absolute path in the output must be redacted.
        assert "/tmp/leaked" not in result.diagnostics.get("actor_stdout_tail", "")

    def test_output_size_exceeded_causal_status_unchanged(
        self, temp_git_repo: Path, run_dir: Path, actor_dir: Path,
    ) -> None:
        """Output overflow maps to ADAPTER_OUTPUT_SIZE_EXCEEDED (causal status
        unchanged by the metadata fix)."""
        source_revision = _get_head_sha(temp_git_repo)
        actor_script = _create_actor_script(
            actor_dir,
            "import sys; sys.stdout.write('x' * 100000)",
        )
        repair_request = _make_valid_repair_request(source_revision=source_revision)
        result = run_repair(
            repo_root=temp_git_repo,
            run_dir=run_dir,
            repair_request=repair_request,
            actor_executable=str(actor_script),
            actor_arguments=[],
            timeout_seconds=30,
            max_output_bytes=8,
            baseline_exclusions=[],
            completed_at="2026-08-06T12:00:00Z",
        )
        assert result.adapter_status == "ADAPTER_OUTPUT_SIZE_EXCEEDED"


# ===========================================================================
# Additional DEC-R2 atomic publication coverage (Step 4)
# ===========================================================================


class TestAtomicPublicationExtended:
    """Extended coverage for secure atomic publication (DEC-R2)."""

    def test_temp_file_mode_0600(self, tmp_path: Path) -> None:
        """The sibling temp file must have mode 0o600."""
        target = tmp_path / "artifact.json"
        captured_modes: list[int] = []

        def capture_mode(src: str, dst: str) -> None:
            try:
                captured_modes.append(os.stat(src).st_mode & 0o777)
            except OSError:
                pass
            return original(src, dst)

        original = os.replace
        try:
            os.replace = capture_mode  # type: ignore[assignment]
            _atomic_write_json(target, {"key": "value"})
        finally:
            os.replace = original

        assert captured_modes, "temp mode not captured"
        assert captured_modes[0] == 0o600

    def test_temp_in_same_directory_as_destination(self, tmp_path: Path) -> None:
        """The temp file must be a sibling of the destination (same dir)."""
        target = tmp_path / "subdir" / "artifact.json"
        captured_tmp_parents: list[str] = []

        def capture_parent(src: str, dst: str) -> None:
            captured_tmp_parents.append(str(Path(src).parent))
            return original(src, dst)

        original = os.replace
        try:
            os.replace = capture_parent  # type: ignore[assignment]
            _atomic_write_json(target, {"key": "value"})
        finally:
            os.replace = original

        assert captured_tmp_parents
        assert captured_tmp_parents[0] == str(target.parent)

    def test_unrelated_pre_existing_files_not_removed(self, tmp_path: Path) -> None:
        """On failure, the adapter-owned temp file is removed but unrelated
        pre-existing files are never touched."""
        unrelated = tmp_path / "unrelated.txt"
        unrelated.write_text("keep me")
        blocker = tmp_path / "artifact.json"
        blocker.write_text("blocker")

        with pytest.raises(OSError):
            _atomic_write_json(blocker / "sub" / "x.json", {"k": "v"})

        assert unrelated.exists()
        assert unrelated.read_text() == "keep me"

    def test_deterministic_final_json_bytes(self, tmp_path: Path) -> None:
        """The final JSON bytes are deterministic (sorted keys)."""
        p1 = tmp_path / "a.json"
        p2 = tmp_path / "b.json"
        data = {"z": 1, "a": 2, "m": 3}
        _atomic_write_json(p1, data)
        _atomic_write_json(p2, data)
        assert p1.read_bytes() == p2.read_bytes()


# ===========================================================================
# SECOND REVIEW REMEDIATION — F1: relative actor path over-redaction
# ===========================================================================


class TestF1RelativeActorPath:
    """F1: relative actor_executable must not be redacted from diagnostics;
    only absolute actor paths are sensitive."""

    def test_relative_actor_executable_preserved_in_stdout(
        self, temp_git_repo: Path, run_dir: Path, actor_dir: Path,
    ) -> None:
        """Actor prints a relative path to stdout; when actor_executable
        is itself relative, it must NOT appear in sensitive_paths and
        must survive sanitization in the persisted diagnostics."""
        source_revision = _get_head_sha(temp_git_repo)
        relative_actor = "scripts/agent-loop/lib/mock_repair_actor.py"
        # Create the actor inside the repo at the relative path so
        # subprocess.Popen(cwd=repo_root, ...) can find it.
        actor_in_repo = temp_git_repo / relative_actor
        actor_in_repo.parent.mkdir(parents=True, exist_ok=True)
        actor_in_repo.write_text(
            "#!/usr/bin/env python3\n"
            "import json, sys\n"
            f"print('{relative_actor}')\n"
            'args = sys.argv[1:]\n'
            'result_path = args[args.index("--repair-result") + 1]\n'
            "result = {\n"
            '    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",\n'
            f'    "attempt": 1, "source_revision": "{source_revision}",\n'
            '    "status": "NO_CHANGE", "changed": False, "changed_files": [],\n'
            '    "summary": "No changes",\n'
            '    "diagnostics": {"actions_taken": [], "obstacles": []},\n'
            '    "recommended_action": "abort",\n'
            '    "sanitization": {"redaction_applied": False, "redaction_count": 0,\n'
            '        "truncation_applied": False, "truncated_fields": []},\n'
            '    "completed_at": "2026-08-06T12:00:00Z"\n'
            "}\n"
            'with open(result_path, "w") as f:\n'
            "    json.dump(result, f)\n"
        )
        actor_in_repo.chmod(0o755)
        repair_request = _make_valid_repair_request(source_revision=source_revision)
        result = run_repair(
            repo_root=temp_git_repo,
            run_dir=run_dir,
            repair_request=repair_request,
            actor_executable=relative_actor,
            actor_arguments=[],
            timeout_seconds=30,
            max_output_bytes=4096,
            baseline_exclusions=["scripts/agent-loop/lib/mock_repair_actor.py"],
            completed_at="2026-08-06T12:00:00Z",
        )
        assert result.adapter_status == ADAPTER_SUCCESS
        stdout_tail = result.diagnostics.get("actor_stdout_tail", "")
        assert relative_actor in stdout_tail, (
            f"relative actor path was over-redacted: {stdout_tail!r}"
        )

    def test_absolute_actor_executable_redacted_from_stdout(
        self, temp_git_repo: Path, run_dir: Path, actor_dir: Path,
    ) -> None:
        """Actor prints its own absolute path to stdout; it must be redacted."""
        source_revision = _get_head_sha(temp_git_repo)
        actor_script = _create_actor_script(
            actor_dir,
            f"""
import json, sys, os
print(os.path.abspath(sys.argv[0]))
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "NO_CHANGE", "changed": False, "changed_files": [],
    "summary": "No changes",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "abort",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
        )
        abs_actor = str(actor_script)
        repair_request = _make_valid_repair_request(source_revision=source_revision)
        result = run_repair(
            repo_root=temp_git_repo,
            run_dir=run_dir,
            repair_request=repair_request,
            actor_executable=abs_actor,
            actor_arguments=[],
            timeout_seconds=30,
            max_output_bytes=4096,
            baseline_exclusions=[],
            completed_at="2026-08-06T12:00:00Z",
        )
        assert result.adapter_status == ADAPTER_SUCCESS
        stdout_tail = result.diagnostics.get("actor_stdout_tail", "")
        assert abs_actor not in stdout_tail, (
            f"absolute actor path was not redacted: {stdout_tail!r}"
        )

    def test_relative_actor_argument_preserved(
        self, temp_git_repo: Path, run_dir: Path, actor_dir: Path,
    ) -> None:
        """A relative actor argument printed to stdout survives sanitization."""
        source_revision = _get_head_sha(temp_git_repo)
        relative_arg = "backend/test_utils/fixture.py"
        actor_script = _create_actor_script(
            actor_dir,
            f"""
import json, sys
print(sys.argv[1])
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "NO_CHANGE", "changed": False, "changed_files": [],
    "summary": "No changes",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "abort",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
        )
        repair_request = _make_valid_repair_request(source_revision=source_revision)
        result = run_repair(
            repo_root=temp_git_repo,
            run_dir=run_dir,
            repair_request=repair_request,
            actor_executable=str(actor_script),
            actor_arguments=[relative_arg],
            timeout_seconds=30,
            max_output_bytes=4096,
            baseline_exclusions=[],
            completed_at="2026-08-06T12:00:00Z",
        )
        assert result.adapter_status == ADAPTER_SUCCESS
        stdout_tail = result.diagnostics.get("actor_stdout_tail", "")
        assert relative_arg in stdout_tail, (
            f"relative actor argument was over-redacted: {stdout_tail!r}"
        )

    def test_absolute_actor_argument_redacted(
        self, temp_git_repo: Path, run_dir: Path, actor_dir: Path,
    ) -> None:
        """An absolute actor argument printed to stdout is redacted."""
        source_revision = _get_head_sha(temp_git_repo)
        abs_arg = str(actor_dir / "config.json")
        actor_script = _create_actor_script(
            actor_dir,
            f"""
import json, sys
print(sys.argv[1])
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "NO_CHANGE", "changed": False, "changed_files": [],
    "summary": "No changes",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "abort",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
        )
        repair_request = _make_valid_repair_request(source_revision=source_revision)
        result = run_repair(
            repo_root=temp_git_repo,
            run_dir=run_dir,
            repair_request=repair_request,
            actor_executable=str(actor_script),
            actor_arguments=[abs_arg],
            timeout_seconds=30,
            max_output_bytes=4096,
            baseline_exclusions=[],
            completed_at="2026-08-06T12:00:00Z",
        )
        assert result.adapter_status == ADAPTER_SUCCESS
        stdout_tail = result.diagnostics.get("actor_stdout_tail", "")
        assert abs_arg not in stdout_tail, (
            f"absolute actor argument was not redacted: {stdout_tail!r}"
        )


# ===========================================================================
# SECOND REVIEW REMEDIATION — F2: per-stream truncation metadata
# ===========================================================================


class TestF2PerStreamTruncation:
    """F2: stdout_truncated and stderr_truncated must be independent.
    The global output_size_exceeded flag may set the causal status, but
    truncated_fields must only include fields actually truncated."""

    def test_stdout_only_overflow_marks_stdout_not_stderr(
        self, temp_git_repo: Path, run_dir: Path, actor_dir: Path,
    ) -> None:
        """Large stdout, minimal stderr: only actor_stdout_tail in
        truncated_fields, not actor_stderr_tail."""
        source_revision = _get_head_sha(temp_git_repo)
        actor_script = _create_actor_script(
            actor_dir,
            f"""
import json, sys
sys.stdout.write("x" * 10000)
sys.stderr.write("small")
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "NO_CHANGE", "changed": False, "changed_files": [],
    "summary": "No changes",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "abort",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
        )
        repair_request = _make_valid_repair_request(source_revision=source_revision)
        result = run_repair(
            repo_root=temp_git_repo,
            run_dir=run_dir,
            repair_request=repair_request,
            actor_executable=str(actor_script),
            actor_arguments=[],
            timeout_seconds=30,
            max_output_bytes=8,
            baseline_exclusions=[],
            completed_at="2026-08-06T12:00:00Z",
        )
        assert result.adapter_status == ADAPTER_OUTPUT_SIZE_EXCEEDED
        tf = result.sanitization.get("truncated_fields", [])
        assert "actor_stdout_tail" in tf
        assert "actor_stderr_tail" not in tf, (
            f"stderr incorrectly marked truncated: {tf}"
        )

    def test_stderr_only_overflow_marks_stderr_not_stdout(
        self, temp_git_repo: Path, run_dir: Path, actor_dir: Path,
    ) -> None:
        """Small stdout, large stderr: only actor_stderr_tail in
        truncated_fields, not actor_stdout_tail."""
        source_revision = _get_head_sha(temp_git_repo)
        actor_script = _create_actor_script(
            actor_dir,
            f"""
import json, sys
sys.stdout.write("ok")
sys.stderr.write("y" * 10000)
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "NO_CHANGE", "changed": False, "changed_files": [],
    "summary": "No changes",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "abort",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
        )
        repair_request = _make_valid_repair_request(source_revision=source_revision)
        result = run_repair(
            repo_root=temp_git_repo,
            run_dir=run_dir,
            repair_request=repair_request,
            actor_executable=str(actor_script),
            actor_arguments=[],
            timeout_seconds=30,
            max_output_bytes=8,
            baseline_exclusions=[],
            completed_at="2026-08-06T12:00:00Z",
        )
        assert result.adapter_status == ADAPTER_OUTPUT_SIZE_EXCEEDED
        tf = result.sanitization.get("truncated_fields", [])
        assert "actor_stderr_tail" in tf
        assert "actor_stdout_tail" not in tf, (
            f"stdout incorrectly marked truncated: {tf}"
        )

    def test_both_streams_overflow_marks_both(
        self, temp_git_repo: Path, run_dir: Path, actor_dir: Path,
    ) -> None:
        """Both stdout and stderr overflow: both fields in truncated_fields."""
        source_revision = _get_head_sha(temp_git_repo)
        actor_script = _create_actor_script(
            actor_dir,
            f"""
import json, sys
sys.stdout.write("x" * 10000)
sys.stderr.write("y" * 10000)
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "NO_CHANGE", "changed": False, "changed_files": [],
    "summary": "No changes",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "abort",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
        )
        repair_request = _make_valid_repair_request(source_revision=source_revision)
        result = run_repair(
            repo_root=temp_git_repo,
            run_dir=run_dir,
            repair_request=repair_request,
            actor_executable=str(actor_script),
            actor_arguments=[],
            timeout_seconds=30,
            max_output_bytes=8,
            baseline_exclusions=[],
            completed_at="2026-08-06T12:00:00Z",
        )
        assert result.adapter_status == ADAPTER_OUTPUT_SIZE_EXCEEDED
        tf = result.sanitization.get("truncated_fields", [])
        assert "actor_stdout_tail" in tf
        assert "actor_stderr_tail" in tf
        # Must be sorted lexicographically.
        assert tf == sorted(tf)

    def test_neither_stream_overflow_no_truncation(
        self, temp_git_repo: Path, run_dir: Path, actor_dir: Path,
    ) -> None:
        """Neither stream overflows: truncated_fields is empty."""
        source_revision = _get_head_sha(temp_git_repo)
        actor_script = _create_actor_script(
            actor_dir,
            f"""
import json, sys
sys.stdout.write("small stdout")
sys.stderr.write("small stderr")
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "NO_CHANGE", "changed": False, "changed_files": [],
    "summary": "No changes",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "abort",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
        )
        repair_request = _make_valid_repair_request(source_revision=source_revision)
        result = run_repair(
            repo_root=temp_git_repo,
            run_dir=run_dir,
            repair_request=repair_request,
            actor_executable=str(actor_script),
            actor_arguments=[],
            timeout_seconds=30,
            max_output_bytes=4096,
            baseline_exclusions=[],
            completed_at="2026-08-06T12:00:00Z",
        )
        assert result.adapter_status == ADAPTER_SUCCESS
        tf = result.sanitization.get("truncated_fields", [])
        assert tf == []


# ===========================================================================
# SECOND REVIEW REMEDIATION — F3: status-presence contract after
# publication failure
# ===========================================================================


class TestF3PublicationFailureStatusPresence:
    """F3: when publication fails after a would-be success, the returned
    in-memory result must conform exactly to ADAPTER_INTERNAL_ERROR
    status-presence rules (no success-only conditional fields)."""

    def test_publication_failure_validates_against_schema(
        self, temp_git_repo: Path, run_dir: Path, actor_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Force publication failure and validate the complete returned
        object against the authoritative result validator."""
        source_revision = _get_head_sha(temp_git_repo)
        actor_script = _create_actor_script(
            actor_dir,
            f"""
import json, sys
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "NO_CHANGE", "changed": False, "changed_files": [],
    "summary": "No changes",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "abort",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
        )
        repair_request = _make_valid_repair_request(source_revision=source_revision)

        original_write = _atomic_write_json

        def failing_write(path: Path, data: Any) -> None:
            target = str(path)
            if target.endswith("repair-adapter-result.json"):
                raise OSError("simulated publication failure")
            return original_write(path, data)

        import repair_adapter as ra

        monkeypatch.setattr(ra, "_atomic_write_json", failing_write)

        result = run_repair(
            repo_root=temp_git_repo,
            run_dir=run_dir,
            repair_request=repair_request,
            actor_executable=str(actor_script),
            actor_arguments=[],
            timeout_seconds=30,
            max_output_bytes=4096,
            baseline_exclusions=[],
            completed_at="2026-08-06T12:00:00Z",
        )

        assert result.adapter_status == ADAPTER_INTERNAL_ERROR

        # Build the dict form for the authoritative validator.
        result_dict = {
            "schema_version": result.schema_version,
            "run_id": result.run_id,
            "story_id": result.story_id,
            "attempt": result.attempt,
            "adapter_status": result.adapter_status,
            "completed_at": result.completed_at,
            "diagnostics": result.diagnostics,
            "sanitization": result.sanitization,
            "integrity_scope": result.integrity_scope,
        }
        if result.repair_result_summary is not None:
            result_dict["repair_result_summary"] = result.repair_result_summary
        if result.workspace_changes is not None:
            result_dict["workspace_changes"] = result.workspace_changes
        if result.reconciliation is not None:
            result_dict["reconciliation"] = result.reconciliation
        if result.permission_enforcement is not None:
            result_dict["permission_enforcement"] = result.permission_enforcement

        # The authoritative validator must accept this result.
        validate_adapter_result(result_dict)

        # All success-only conditional fields must be absent or None.
        assert result.repair_result_summary is None
        assert result.workspace_changes is None
        assert result.reconciliation is None
        assert result.permission_enforcement is None

        # No raw exception message or absolute path in the error text.
        error_msg = result.diagnostics.get("adapter_error_message", "")
        assert "simulated publication failure" not in error_msg
        assert "/" not in error_msg or "[REDACTED" in error_msg

    def test_publication_failure_no_artifact_claim(
        self, temp_git_repo: Path, run_dir: Path, actor_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """After publication failure, no adapter-result artifact should
        exist on disk and the result must not claim it was published."""
        source_revision = _get_head_sha(temp_git_repo)
        actor_script = _create_actor_script(
            actor_dir,
            f"""
import json, sys
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "NO_CHANGE", "changed": False, "changed_files": [],
    "summary": "No changes",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "abort",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
        )
        repair_request = _make_valid_repair_request(source_revision=source_revision)

        original_write = _atomic_write_json

        def failing_write(path: Path, data: Any) -> None:
            target = str(path)
            if target.endswith("repair-adapter-result.json"):
                raise OSError("simulated publication failure")
            return original_write(path, data)

        import repair_adapter as ra

        monkeypatch.setattr(ra, "_atomic_write_json", failing_write)

        result = run_repair(
            repo_root=temp_git_repo,
            run_dir=run_dir,
            repair_request=repair_request,
            actor_executable=str(actor_script),
            actor_arguments=[],
            timeout_seconds=30,
            max_output_bytes=4096,
            baseline_exclusions=[],
            completed_at="2026-08-06T12:00:00Z",
        )

        assert result.adapter_status == ADAPTER_INTERNAL_ERROR
        adapter_result_path = run_dir / "repair" / "repair-adapter-result.json"
        assert not adapter_result_path.exists(), (
            "adapter-result artifact should not exist after publication failure"
        )


# ===========================================================================
# SECOND REVIEW REMEDIATION — F4: source-of-truth contradiction
# ===========================================================================


class TestF4SourceOfTruthConsistency:
    """F4: verify that the production code and planning documents accurately
    reflect the DEC-R1 fail-closed baseline behavior, not stale wording."""

    def test_production_docstring_reflects_fail_closed(self) -> None:
        """The docstring at _verify_clean_tracked_baseline must not say
        that non-excluded untracked files are 'allowed at baseline time'."""
        adapter_path = (
            Path(__file__).parent.parent / "lib" / "repair_adapter.py"
        )
        source = adapter_path.read_text()
        # The stale wording claimed untracked files NOT in baseline_exclusions
        # are "allowed at baseline time". This must be corrected.
        assert "allowed at baseline time" not in source, (
            "stale wording 'allowed at baseline time' remains in repair_adapter.py"
        )

    def test_planning_doc_reflects_fail_closed(self) -> None:
        """The planning document §15.2 must not say non-excluded untracked
        files 'will trigger ADAPTER_UNDECLARED_CHANGE' — that contradicts
        DEC-R1 fail-closed behavior which triggers ADAPTER_DIRTY_BASELINE."""
        planning_path = (
            Path(__file__).parents[3]
            / "docs" / "planning" / "wp_al_1c5_repair_adapter.md"
        )
        source = planning_path.read_text()
        # Stale wording said non-excluded untracked files are "treated as
        # potential actor changes (will trigger ADAPTER_UNDECLARED_CHANGE)".
        # Under DEC-R1, they trigger ADAPTER_DIRTY_BASELINE before invocation.
        assert "will trigger `ADAPTER_UNDECLARED_CHANGE`" not in source, (
            "stale wording in planning doc contradicts DEC-R1 fail-closed"
        )
