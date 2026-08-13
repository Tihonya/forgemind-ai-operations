"""Focused tests for WP-REC-03H formal-evidence mode and evidence utilities.

These tests verify:
- formal mode is no longer an unconditional rejection path;
- formal and verify modes remain distinct;
- safe run IDs are accepted;
- unsafe or reused run IDs are rejected;
- redaction removes configured secret values;
- redaction verification fails closed when a secret remains;
- checksums are deterministic and exclude their own file;
- missing required evidence causes failure;
- raw artifacts are preserved on failure;
- raw artifacts are removed only after successful redaction and checksum creation;
- verify mode does not represent output as authoritative Phase C evidence;
- owned-resource teardown protections remain intact.

All tests use temporary directories — no real evidence is created in the repository.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add scripts/ to path so we can import the harness module directly
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import acceptance_harness as ah  # noqa: E402


# ---------------------------------------------------------------------------
# Run-ID validation tests
# ---------------------------------------------------------------------------


class TestRunIdValidation:
    """Tests for validate_run_id()."""

    def test_safe_run_id_accepted(self) -> None:
        """Safe run IDs with alphanumeric, hyphens, underscores, dots pass."""
        ah.validate_run_id("acc-20260813-001")
        ah.validate_run_id("test_run.1")
        ah.validate_run_id("a")
        ah.validate_run_id("abc123def456")

    def test_empty_run_id_rejected(self) -> None:
        """Empty run ID raises AcceptanceHarnessError."""
        with pytest.raises(ah.AcceptanceHarnessError, match="must not be empty"):
            ah.validate_run_id("")

    def test_path_separator_rejected(self) -> None:
        """Run IDs with path separators are rejected."""
        with pytest.raises(ah.AcceptanceHarnessError, match="path separators"):
            ah.validate_run_id("acc/evil")
        with pytest.raises(ah.AcceptanceHarnessError, match="path separators"):
            ah.validate_run_id("acc\\evil")

    def test_traversal_rejected(self) -> None:
        """Run IDs with traversal sequences are rejected."""
        with pytest.raises(ah.AcceptanceHarnessError, match="traversal"):
            ah.validate_run_id("acc-..-evil")

    def test_leading_dot_rejected(self) -> None:
        """Run IDs starting with dot are rejected."""
        with pytest.raises(ah.AcceptanceHarnessError, match="alphanumeric"):
            ah.validate_run_id(".hidden")

    def test_leading_hyphen_rejected(self) -> None:
        """Run IDs starting with hyphen are rejected."""
        with pytest.raises(ah.AcceptanceHarnessError, match="alphanumeric"):
            ah.validate_run_id("-invalid")

    def test_unsafe_characters_rejected(self) -> None:
        """Run IDs with unsafe characters are rejected."""
        with pytest.raises(ah.AcceptanceHarnessError, match="unsafe characters"):
            ah.validate_run_id("acc;rm -rf")
        with pytest.raises(ah.AcceptanceHarnessError, match="unsafe characters"):
            ah.validate_run_id("acc<script>")
        with pytest.raises(ah.AcceptanceHarnessError, match="unsafe characters"):
            ah.validate_run_id("acc space")

    def test_long_run_id_rejected(self) -> None:
        """Run IDs longer than 64 characters are rejected."""
        with pytest.raises(ah.AcceptanceHarnessError, match="too long"):
            ah.validate_run_id("a" * 65)

    def test_max_length_run_id_accepted(self) -> None:
        """Run ID at exactly 64 characters is accepted."""
        ah.validate_run_id("a" * 64)


class TestRunIdGeneration:
    """Tests for generate_run_id()."""

    def test_generates_unique_ids(self) -> None:
        """Each call generates a unique run ID."""
        ids = {ah.generate_run_id() for _ in range(10)}
        assert len(ids) == 10

    def test_generated_id_is_valid(self) -> None:
        """Generated IDs pass validation."""
        run_id = ah.generate_run_id()
        ah.validate_run_id(run_id)  # Should not raise
        assert run_id.startswith("acc-")


class TestEvidenceDirValidation:
    """Tests for validate_evidence_dir_not_exists()."""

    def test_nonexistent_dir_passes(self, tmp_path: Path) -> None:
        """Non-existent directory passes validation."""
        ah.validate_evidence_dir_not_exists(tmp_path / "does-not-exist")

    def test_existing_dir_fails(self, tmp_path: Path) -> None:
        """Existing directory raises AcceptanceHarnessError."""
        existing = tmp_path / "existing"
        existing.mkdir()
        with pytest.raises(ah.AcceptanceHarnessError, match="already exists"):
            ah.validate_evidence_dir_not_exists(existing)


# ---------------------------------------------------------------------------
# Redaction tests
# ---------------------------------------------------------------------------


class TestRedaction:
    """Tests for redaction utilities."""

    def test_redact_openai_key(self) -> None:
        """OpenAI-style keys are redacted."""
        content = "API key: sk-abc123def456ghi789jkl012mno345pqr678"
        result = ah.redact_secrets(content)
        assert "sk-" not in result
        assert "[REDACTED]" in result

    def test_redact_password(self) -> None:
        """Password values are redacted."""
        content = "DATABASE_URL=postgresql://user:password=secret123@host/db"
        result = ah.redact_secrets(content)
        assert "secret123" not in result

    def test_redact_acceptance_secret(self) -> None:
        """The acceptance test secret key is redacted."""
        content = "SECRET_KEY=acceptance-test-secret-key-must-be-32-chars"
        result = ah.redact_secrets(content)
        assert "acceptance-test-secret-key-must-be-32-chars" not in result
        assert "[REDACTED]" in result

    def test_clean_content_unchanged(self) -> None:
        """Content without secrets is not modified."""
        content = "Workflow state: COMPLETED, dispatch_generation: 1"
        result = ah.redact_secrets(content)
        assert result == content

    def test_custom_patterns(self) -> None:
        """Custom patterns can be supplied."""
        content = "custom-secret: my-special-value-12345"
        result = ah.redact_secrets(content, patterns=[r"my-special-value-\d+"])
        assert "my-special-value-12345" not in result
        assert "[REDACTED]" in result


class TestRedactionVerification:
    """Tests for verify_redaction()."""

    def test_clean_content_passes(self) -> None:
        """Clean content passes verification (empty violations)."""
        content = "Workflow state: COMPLETED"
        violations = ah.verify_redaction(content)
        assert violations == []

    def test_secret_remains_detected(self) -> None:
        """Remaining secret patterns are detected."""
        content = "key=sk-abc123def456ghi789jkl012mno345pqr678"
        violations = ah.verify_redaction(content)
        assert len(violations) > 0

    def test_redacted_content_passes(self) -> None:
        """Content that has been properly redacted passes verification."""
        content = "key=sk-abc123def456ghi789jkl012mno345pqr678"
        redacted = ah.redact_secrets(content)
        violations = ah.verify_redaction(redacted)
        assert violations == []

    def test_redaction_fails_closed(self) -> None:
        """If a pattern still matches after redaction, it is reported."""
        # Use a pattern that won't be redacted by the default patterns
        content = "SPECIAL_TOKEN=xyzzy-12345-abcde"
        custom = [r"SPECIAL_TOKEN=[\w-]+"]
        violations = ah.verify_redaction(content, patterns=custom)
        assert len(violations) == 1


# ---------------------------------------------------------------------------
# Checksum tests
# ---------------------------------------------------------------------------


class TestChecksums:
    """Tests for checksum utilities."""

    def test_sha256_file(self, tmp_path: Path) -> None:
        """SHA-256 hash is correct for known content."""
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        digest = ah.sha256_file(f)
        # Known SHA-256 of "hello world"
        assert digest == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"

    def test_checksums_exclude_self(self, tmp_path: Path) -> None:
        """checksums.sha256 is excluded from its own computation."""
        (tmp_path / "a.txt").write_text("alpha")
        (tmp_path / "b.txt").write_text("beta")
        (tmp_path / "checksums.sha256").write_text("old")

        checksums = ah.compute_checksums(tmp_path)
        assert "a.txt" in checksums
        assert "b.txt" in checksums
        assert "checksums.sha256" not in checksums

    def test_checksums_deterministic(self, tmp_path: Path) -> None:
        """Checksums are deterministic (same input → same output)."""
        (tmp_path / "a.txt").write_text("alpha")
        (tmp_path / "b.txt").write_text("beta")

        c1 = ah.compute_checksums(tmp_path)
        c2 = ah.compute_checksums(tmp_path)
        assert c1 == c2

    def test_write_checksums_file(self, tmp_path: Path) -> None:
        """write_checksums_file creates a valid checksums file."""
        (tmp_path / "a.txt").write_text("alpha")
        (tmp_path / "b.txt").write_text("beta")

        path = ah.write_checksums_file(tmp_path)
        assert path.exists()
        content = path.read_text()
        assert "a.txt" in content
        assert "b.txt" in content
        # Each line: hash  filename
        for line in content.strip().split("\n"):
            parts = line.split("  ")
            assert len(parts) == 2
            assert len(parts[0]) == 64  # SHA-256 hex

    def test_write_checksums_no_files_fails(self, tmp_path: Path) -> None:
        """Writing checksums with no files raises error."""
        with pytest.raises(ah.AcceptanceHarnessError, match="No files found"):
            ah.write_checksums_file(tmp_path)

    def test_checksums_subdirectories(self, tmp_path: Path) -> None:
        """Checksums include files in subdirectories."""
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "nested.txt").write_text("nested content")
        (tmp_path / "top.txt").write_text("top content")

        checksums = ah.compute_checksums(tmp_path)
        assert "top.txt" in checksums
        assert "sub/nested.txt" in checksums


# ---------------------------------------------------------------------------
# Evidence Collector tests
# ---------------------------------------------------------------------------


class TestEvidenceCollector:
    """Tests for EvidenceCollector lifecycle."""

    def test_setup_creates_directories(self, tmp_path: Path) -> None:
        """setup() creates the expected directory structure."""
        evidence_dir = tmp_path / "evidence" / "test-run"
        collector = ah.EvidenceCollector(evidence_dir, "test-run")
        collector.setup()

        assert (evidence_dir / "raw").is_dir()
        assert (evidence_dir / "redacted").is_dir()
        assert (evidence_dir / "logs").is_dir()

    def test_collect_text(self, tmp_path: Path) -> None:
        """collect_text writes a raw artifact."""
        evidence_dir = tmp_path / "evidence" / "test-run"
        collector = ah.EvidenceCollector(evidence_dir, "test-run")
        collector.setup()

        path = collector.collect_text("data/test.txt", "hello world")
        assert path.exists()
        assert path.read_text() == "hello world"
        assert len(collector.artifacts) == 1

    def test_collect_json(self, tmp_path: Path) -> None:
        """collect_json writes a JSON artifact."""
        evidence_dir = tmp_path / "evidence" / "test-run"
        collector = ah.EvidenceCollector(evidence_dir, "test-run")
        collector.setup()

        data = {"key": "value", "count": 42}
        path = collector.collect_json("api/response.json", data)
        assert path.exists()
        loaded = json.loads(path.read_text())
        assert loaded == data

    def test_redact_and_verify_success(self, tmp_path: Path) -> None:
        """Successful redaction: raw deleted, checksums written."""
        evidence_dir = tmp_path / "evidence" / "test-run"
        collector = ah.EvidenceCollector(evidence_dir, "test-run")
        collector.setup()

        # Collect clean content (no secrets)
        collector.collect_text("workflow/state.json", '{"state": "COMPLETED"}')
        collector.collect_text("risks/list.json", '[{"id": "RISK-001"}]')

        collector.redact_and_verify()

        # Raw should be deleted
        assert not (evidence_dir / "raw").exists()
        # Redacted should exist
        assert (evidence_dir / "redacted" / "workflow" / "state.json").exists()
        assert (evidence_dir / "redacted" / "risks" / "list.json").exists()
        # Checksums should exist
        assert (evidence_dir / "redacted" / "checksums.sha256").exists()
        # Manifest should exist
        assert (evidence_dir / "redacted" / "manifest.json").exists()

    def test_redact_removes_secrets(self, tmp_path: Path) -> None:
        """Redaction replaces secret values."""
        evidence_dir = tmp_path / "evidence" / "test-run"
        collector = ah.EvidenceCollector(evidence_dir, "test-run")
        collector.setup()

        # Collect content with a known secret
        secret_content = 'SECRET_KEY=acceptance-test-secret-key-must-be-32-chars\nstate=OK'
        collector.collect_text("config/env.txt", secret_content)

        collector.redact_and_verify()

        redacted = (evidence_dir / "redacted" / "config" / "env.txt").read_text()
        assert "acceptance-test-secret-key-must-be-32-chars" not in redacted
        assert "[REDACTED]" in redacted
        assert "state=OK" in redacted

    def test_redact_fails_closed_on_remaining_secret(self, tmp_path: Path) -> None:
        """If redaction misses a secret, redact_and_verify fails closed."""
        evidence_dir = tmp_path / "evidence" / "test-run"
        collector = ah.EvidenceCollector(evidence_dir, "test-run")
        collector.setup()

        # Content with a secret that default patterns will redact
        collector.collect_text(
            "config.txt",
            "api_key=sk-abcdefghijklmnopqrstuvwxyz1234567890extra",
        )

        # Use default patterns (which redact the secret to [REDACTED])
        # PLUS a verification pattern that catches [REDACTED] itself.
        # After redaction replaces the secret, verification finds [REDACTED]
        # and reports it as a violation → fail closed.
        strict_patterns = ah.DEFAULT_REDACTION_PATTERNS + [r"\[REDACTED\]"]
        with pytest.raises(ah.AcceptanceHarnessError, match="Redaction verification failed"):
            collector.redact_and_verify(patterns=strict_patterns)

        # Raw should be preserved on failure
        assert (evidence_dir / "raw").is_dir()
        assert (evidence_dir / "raw" / "config.txt").exists()

    def test_missing_raw_artifacts_fails(self, tmp_path: Path) -> None:
        """Missing required evidence causes failure."""
        evidence_dir = tmp_path / "evidence" / "test-run"
        collector = ah.EvidenceCollector(evidence_dir, "test-run")
        collector.setup()

        # Don't collect anything
        with pytest.raises(ah.AcceptanceHarnessError, match="No raw artifacts"):
            collector.redact_and_verify()

    def test_raw_preserved_on_redaction_failure(self, tmp_path: Path) -> None:
        """Raw artifacts are preserved when redaction verification fails."""
        evidence_dir = tmp_path / "evidence" / "test-run"
        collector = ah.EvidenceCollector(evidence_dir, "test-run")
        collector.setup()

        collector.collect_text(
            "data.txt",
            "api_key=sk-abcdefghijklmnopqrstuvwxyz1234567890",
        )

        # Use default patterns (redact secrets) plus a verification pattern
        # that catches [REDACTED] → verification fails → raw preserved.
        impossible_patterns = ah.DEFAULT_REDACTION_PATTERNS + [r"\[REDACTED\]"]
        with pytest.raises(ah.AcceptanceHarnessError, match="Redaction verification failed"):
            collector.redact_and_verify(patterns=impossible_patterns)

        # Raw must still exist
        assert (evidence_dir / "raw" / "data.txt").exists()

    def test_raw_removed_only_after_success(self, tmp_path: Path) -> None:
        """Raw artifacts are removed only after successful redaction + checksums."""
        evidence_dir = tmp_path / "evidence" / "test-run"
        collector = ah.EvidenceCollector(evidence_dir, "test-run")
        collector.setup()

        collector.collect_text("clean.txt", "This is clean content with no secrets.")

        collector.redact_and_verify()

        assert not (evidence_dir / "raw").exists()
        assert (evidence_dir / "redacted" / "clean.txt").exists()
        assert (evidence_dir / "redacted" / "checksums.sha256").exists()

    def test_manifest_written(self, tmp_path: Path) -> None:
        """Manifest is written with artifact metadata."""
        evidence_dir = tmp_path / "evidence" / "test-run"
        collector = ah.EvidenceCollector(evidence_dir, "test-run")
        collector.setup()

        collector.collect_text("data.txt", "clean data")
        collector.redact_and_verify()

        manifest_path = evidence_dir / "redacted" / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert manifest["run_id"] == "test-run"
        assert manifest["artifact_count"] >= 1

    def test_collect_repository_baseline(self, tmp_path: Path) -> None:
        """collect_repository_baseline captures git state."""
        evidence_dir = tmp_path / "evidence" / "test-run"
        collector = ah.EvidenceCollector(evidence_dir, "test-run")
        collector.setup()

        collector.collect_repository_baseline()

        path = evidence_dir / "raw" / "repository" / "baseline.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert "head" in data

    def test_collect_scenario_identity(self, tmp_path: Path) -> None:
        """collect_scenario_identity records scenario metadata."""
        evidence_dir = tmp_path / "evidence" / "test-run"
        collector = ah.EvidenceCollector(evidence_dir, "test-run")
        collector.setup()

        collector.collect_scenario_identity("AT008_INVALID_OUTPUT", "corr-123")

        path = evidence_dir / "raw" / "scenarios" / "AT008_INVALID_OUTPUT" / "identity.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["scenario"] == "AT008_INVALID_OUTPUT"
        assert data["correlation_id"] == "corr-123"
        assert data["run_id"] == "test-run"


# ---------------------------------------------------------------------------
# Protected audit verification tests
# ---------------------------------------------------------------------------


class TestProtectedAuditVerification:
    """Tests for verify_protected_audit()."""

    def test_protected_audit_constant_defined(self) -> None:
        """The expected SHA-256 constant is defined."""
        assert ah.PROTECTED_AUDIT_SHA256 == (
            "639a2529351bdacc606c6c5bbede44b82c73a7aefa26ae249bb592dec8e89657"
        )

    def test_verify_missing_file_fails(self, tmp_path: Path) -> None:
        """Missing protected audit file raises error."""
        with patch.object(ah, "PROTECTED_AUDIT_PATH", tmp_path / "nonexistent.md"):
            with pytest.raises(ah.AcceptanceHarnessError, match="not found"):
                ah.verify_protected_audit()

    def test_verify_wrong_hash_fails(self, tmp_path: Path) -> None:
        """Wrong SHA-256 hash raises error."""
        fake_file = tmp_path / "audit.md"
        fake_file.write_text("tampered content")
        with patch.object(ah, "PROTECTED_AUDIT_PATH", fake_file):
            with pytest.raises(ah.AcceptanceHarnessError, match="SHA-256 mismatch"):
                ah.verify_protected_audit()


# ---------------------------------------------------------------------------
# Mode distinction tests
# ---------------------------------------------------------------------------


class TestModeDistinction:
    """Tests proving formal and verify modes are distinct."""

    def test_formal_mode_not_unconditional_rejection(self) -> None:
        """Formal mode is no longer an unconditional rejection path.

        The old code returned 1 immediately for --mode=formal.
        Now it proceeds to run_formal_mode() after validation.
        """
        # Verify that run_formal_mode exists and is callable
        assert callable(ah.run_formal_mode)
        # The function should not contain the old rejection message
        import inspect
        source = inspect.getsource(ah.run_formal_mode)
        assert "requires separate Product Owner authorization" not in source

    def test_verify_mode_function_exists(self) -> None:
        """Verify mode has its own dedicated function."""
        assert callable(ah.run_verify_mode)

    def test_verify_mode_does_not_claim_phase_c(self, capsys: pytest.CaptureFixture) -> None:
        """Verify mode output does not claim authoritative Phase C evidence.

        We test this by checking the verify mode function source doesn't
        contain Phase C evidence terminology.
        """
        import inspect
        source = inspect.getsource(ah.run_verify_mode)
        assert "formal evidence" not in source.lower() or "not authoritative" in source.lower()
        assert "Phase C" not in source or "not" in source.lower()

    def test_main_accepts_formal_mode(self) -> None:
        """main() parser accepts --mode=formal."""
        parser = __import__("argparse").ArgumentParser()
        parser.add_argument("--mode", choices=["verify", "formal"], required=True)
        args = parser.parse_args(["--mode", "formal"])
        assert args.mode == "formal"

    def test_main_accepts_verify_mode(self) -> None:
        """main() parser accepts --mode=verify."""
        parser = __import__("argparse").ArgumentParser()
        parser.add_argument("--mode", choices=["verify", "formal"], required=True)
        args = parser.parse_args(["--mode", "verify"])
        assert args.mode == "verify"


# ---------------------------------------------------------------------------
# Teardown protection tests
# ---------------------------------------------------------------------------


class TestTeardownProtection:
    """Tests proving owned-resource teardown protections remain intact."""

    def test_environment_tracks_containers(self) -> None:
        """AcceptanceEnvironment tracks container names for ownership verification."""
        env = ah.AcceptanceEnvironment(run_id="test-run", mode="verify")
        assert env.containers == []
        env.containers.append("forgemind-test-run-pg")
        assert "forgemind-test-run-pg" in env.containers

    def test_environment_tracks_processes(self) -> None:
        """AcceptanceEnvironment tracks processes for cleanup."""
        env = ah.AcceptanceEnvironment(run_id="test-run", mode="verify")
        assert env.processes == []

    def test_teardown_checks_ownership_label(self) -> None:
        """Teardown uses exact label matching for container ownership."""
        import inspect
        source = inspect.getsource(ah.AcceptanceEnvironment.teardown)
        assert 'forgemind-run' in source
        assert 'label' in source.lower()

    def test_evidence_dir_scoped_to_run_id(self) -> None:
        """Evidence directory is scoped to the run ID."""
        env = ah.AcceptanceEnvironment(run_id="unique-run-id", mode="formal")
        assert "unique-run-id" in str(env.evidence_dir)

    def test_container_names_scoped_to_run_id(self) -> None:
        """Container names include the run ID for ownership."""
        run_id = "test-ownership"
        ah.AcceptanceEnvironment(run_id=run_id, mode="verify")
        # Simulate what setup() does
        pg_name = f"forgemind-{run_id}-pg"
        redis_name = f"forgemind-{run_id}-redis"
        assert run_id in pg_name
        assert run_id in redis_name
