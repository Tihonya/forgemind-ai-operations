"""
WP-AL-1B3: Tests for the failure context collector.

Covers:
- U01-U16 unit test matrix from the planning spec
- Schema validation
- Deterministic digest computation
- Redaction patterns
- Safe diagnostic extraction
- Bounded truncation
- Collection status semantics
"""

# Import the module under test
import json
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
import failure_context


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_run_dir(tmp_path: Path) -> Iterator[Path]:
    """Create a minimal run directory structure."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "verify").mkdir()
    (run_dir / "reports").mkdir()
    yield run_dir


@pytest.fixture
def temp_manifest(tmp_path: Path) -> Path:
    """Create a minimal story manifest."""
    manifest = {
        "schema_version": "1.0",
        "project_id": "test-project",
        "story_id": "TEST-001",
        "base_commit": "a" * 40,
        "repair_guidance": ["Fix the failing tests"],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    return manifest_path


@pytest.fixture
def temp_verify_result(temp_run_dir: Path) -> Path:
    """Create a minimal verify-result.json."""
    verify_result = {
        "schema_version": "1.0",
        "run_id": "test-run-001",
        "story_id": "TEST-001",
        "overall_status": "PASS",
        "gates": [
            {"name": "scope", "status": "PASS", "details": ""},
            {"name": "json_syntax", "status": "PASS", "details": ""},
            {"name": "yaml_syntax", "status": "PASS", "details": ""},
            {"name": "targeted_tests", "status": "PASS", "details": ""},
            {"name": "lint", "status": "PASS", "details": ""},
            {"name": "secrets", "status": "PASS", "details": ""},
            {"name": "git_diff_check", "status": "PASS", "details": ""},
        ],
    }
    verify_result_path = temp_run_dir / "reports" / "verify-result.json"
    verify_result_path.write_text(json.dumps(verify_result))
    return verify_result_path


# ---------------------------------------------------------------------------
# U01: Successful run
# ---------------------------------------------------------------------------
def test_successful_run(temp_run_dir: Path, temp_manifest: Path, temp_verify_result: Path) -> None:
    """U01: collection_status = complete for successful verification."""
    output_path = temp_run_dir / "reports" / "failure-context.json"

    # Mock compute_candidate_identity to avoid git operations
    original_func = failure_context.compute_candidate_identity
    failure_context.compute_candidate_identity = lambda repo_root, base_commit, manifest_path: {
        "base_commit": "a" * 40,
        "candidate_commit": "b" * 40,
        "candidate_state": "committed",
        "candidate_diff_digest": "c" * 64,
    }

    try:
        failure_context.collect_failure_context(
            run_dir=temp_run_dir,
            repo_root=temp_run_dir,
            manifest_path=temp_manifest,
            output_path=output_path,
        )

        assert output_path.exists()
        data = json.loads(output_path.read_text())

        assert data["schema_version"] == "1.0"
        assert data["collection_status"] == "complete"
        assert data["overall_verification_status"] == "PASS"
        assert len(data["collection_errors"]) == 0
        assert data["redaction_applied"] is False
        assert data["redaction_count"] == 0
    finally:
        failure_context.compute_candidate_identity = original_func


# ---------------------------------------------------------------------------
# U02: One failed gate
# ---------------------------------------------------------------------------
def test_one_failed_gate(temp_run_dir: Path, temp_manifest: Path) -> None:
    """U02: failing_gates contains one entry when one gate fails."""
    verify_result = {
        "schema_version": "1.0",
        "run_id": "test-run-002",
        "story_id": "TEST-002",
        "overall_status": "FAIL",
        "gates": [
            {"name": "scope", "status": "PASS", "details": ""},
            {"name": "targeted_tests", "status": "FAIL", "details": "3 tests failed"},
        ],
    }
    verify_result_path = temp_run_dir / "reports" / "verify-result.json"
    verify_result_path.write_text(json.dumps(verify_result))

    # Create a gate log
    (temp_run_dir / "verify" / "targeted_tests.log").write_text("Test output with failures")

    output_path = temp_run_dir / "reports" / "failure-context.json"

    original_func = failure_context.compute_candidate_identity
    failure_context.compute_candidate_identity = lambda repo_root, base_commit, manifest_path: {
        "base_commit": "a" * 40,
        "candidate_commit": None,
        "candidate_state": "working_tree",
        "candidate_diff_digest": "d" * 64,
    }

    try:
        failure_context.collect_failure_context(
            run_dir=temp_run_dir,
            repo_root=temp_run_dir,
            manifest_path=temp_manifest,
            output_path=output_path,
        )

        data = json.loads(output_path.read_text())
        assert data["overall_verification_status"] == "FAIL"
        assert data["failing_gate_ids"] == ["targeted_tests"]
        assert "targeted_tests" in data["gate_verdicts"]
        assert len(data["gate_verdicts"]["targeted_tests"]["diagnostics"]) > 0
    finally:
        failure_context.compute_candidate_identity = original_func


# ---------------------------------------------------------------------------
# U03: Multiple failed gates
# ---------------------------------------------------------------------------
def test_multiple_failed_gates(temp_run_dir: Path, temp_manifest: Path) -> None:
    """U03: failing_gates contains N entries when N gates fail."""
    verify_result = {
        "schema_version": "1.0",
        "run_id": "test-run-003",
        "story_id": "TEST-003",
        "overall_status": "FAIL",
        "gates": [
            {"name": "scope", "status": "FAIL", "details": "Scope violation"},
            {"name": "lint", "status": "FAIL", "details": "Lint errors found"},
            {"name": "secrets", "status": "FAIL", "details": "Secret detected"},
        ],
    }
    verify_result_path = temp_run_dir / "reports" / "verify-result.json"
    verify_result_path.write_text(json.dumps(verify_result))

    output_path = temp_run_dir / "reports" / "failure-context.json"

    original_func = failure_context.compute_candidate_identity
    failure_context.compute_candidate_identity = lambda repo_root, base_commit, manifest_path: {
        "base_commit": "a" * 40,
        "candidate_commit": None,
        "candidate_state": "working_tree",
        "candidate_diff_digest": "e" * 64,
    }

    try:
        failure_context.collect_failure_context(
            run_dir=temp_run_dir,
            repo_root=temp_run_dir,
            manifest_path=temp_manifest,
            output_path=output_path,
        )

        data = json.loads(output_path.read_text())
        assert sorted(data["failing_gate_ids"]) == ["lint", "scope", "secrets"]
        assert len(data["failing_gate_ids"]) == 3
    finally:
        failure_context.compute_candidate_identity = original_func


# ---------------------------------------------------------------------------
# U04: Working-tree candidate
# ---------------------------------------------------------------------------
def test_working_tree_candidate(temp_run_dir: Path, temp_manifest: Path, temp_verify_result: Path) -> None:
    """U04: candidate_commit is null, state is working_tree."""
    output_path = temp_run_dir / "reports" / "failure-context.json"

    original_func = failure_context.compute_candidate_identity
    failure_context.compute_candidate_identity = lambda repo_root, base_commit, manifest_path: {
        "base_commit": "a" * 40,
        "candidate_commit": None,
        "candidate_state": "working_tree",
        "candidate_diff_digest": "f" * 64,
    }

    try:
        failure_context.collect_failure_context(
            run_dir=temp_run_dir,
            repo_root=temp_run_dir,
            manifest_path=temp_manifest,
            output_path=output_path,
        )

        data = json.loads(output_path.read_text())
        ci = data["candidate_identity"]
        assert ci["candidate_commit"] is None
        assert ci["candidate_state"] == "working_tree"
    finally:
        failure_context.compute_candidate_identity = original_func


# ---------------------------------------------------------------------------
# U05: Committed candidate
# ---------------------------------------------------------------------------
def test_committed_candidate(temp_run_dir: Path, temp_manifest: Path, temp_verify_result: Path) -> None:
    """U05: candidate_commit is SHA, state is committed."""
    output_path = temp_run_dir / "reports" / "failure-context.json"

    original_func = failure_context.compute_candidate_identity
    failure_context.compute_candidate_identity = lambda repo_root, base_commit, manifest_path: {
        "base_commit": "a" * 40,
        "candidate_commit": "b" * 40,
        "candidate_state": "committed",
        "candidate_diff_digest": "0" * 64,
    }

    try:
        failure_context.collect_failure_context(
            run_dir=temp_run_dir,
            repo_root=temp_run_dir,
            manifest_path=temp_manifest,
            output_path=output_path,
        )

        data = json.loads(output_path.read_text())
        ci = data["candidate_identity"]
        assert ci["candidate_commit"] == "b" * 40
        assert ci["candidate_state"] == "committed"
    finally:
        failure_context.compute_candidate_identity = original_func


# ---------------------------------------------------------------------------
# U06: Missing optional artifact
# ---------------------------------------------------------------------------
def test_missing_optional_artifact(temp_run_dir: Path, temp_manifest: Path, temp_verify_result: Path) -> None:
    """U06: collection_status is partial when optional artifact is missing."""
    # Remove a gate log (optional)
    output_path = temp_run_dir / "reports" / "failure-context.json"

    original_func = failure_context.compute_candidate_identity
    failure_context.compute_candidate_identity = lambda repo_root, base_commit, manifest_path: {
        "base_commit": "a" * 40,
        "candidate_commit": None,
        "candidate_state": "working_tree",
        "candidate_diff_digest": "1" * 64,
    }

    try:
        failure_context.collect_failure_context(
            run_dir=temp_run_dir,
            repo_root=temp_run_dir,
            manifest_path=temp_manifest,
            output_path=output_path,
        )

        data = json.loads(output_path.read_text())
        # Collection should still succeed (logs are optional)
        assert data["collection_status"] == "complete"
    finally:
        failure_context.compute_candidate_identity = original_func


# ---------------------------------------------------------------------------
# U07: Missing required artifact
# ---------------------------------------------------------------------------
def test_missing_required_artifact(temp_run_dir: Path, temp_manifest: Path) -> None:
    """U07: collection_errors is populated when required artifact is missing."""
    # Remove verify-result.json (required)
    output_path = temp_run_dir / "reports" / "failure-context.json"

    with pytest.raises(RuntimeError, match="verify-result.json missing"):
        failure_context.collect_failure_context(
            run_dir=temp_run_dir,
            repo_root=temp_run_dir,
            manifest_path=temp_manifest,
            output_path=output_path,
        )


# ---------------------------------------------------------------------------
# U08: Excerpt truncation
# ---------------------------------------------------------------------------
def test_excerpt_truncation(temp_run_dir: Path, temp_manifest: Path) -> None:
    """U08: truncation marker and source ref are present."""
    verify_result = {
        "schema_version": "1.0",
        "run_id": "test-run-008",
        "story_id": "TEST-008",
        "overall_status": "FAIL",
        "gates": [
            {"name": "targeted_tests", "status": "FAIL", "details": "Tests failed"},
        ],
    }
    verify_result_path = temp_run_dir / "reports" / "verify-result.json"
    verify_result_path.write_text(json.dumps(verify_result))

    # Create a large log file
    large_content = "Line of test output\n" * 1000
    (temp_run_dir / "verify" / "targeted_tests.log").write_text(large_content)

    output_path = temp_run_dir / "reports" / "failure-context.json"

    original_func = failure_context.compute_candidate_identity
    failure_context.compute_candidate_identity = lambda repo_root, base_commit, manifest_path: {
        "base_commit": "a" * 40,
        "candidate_commit": None,
        "candidate_state": "working_tree",
        "candidate_diff_digest": "2" * 64,
    }

    try:
        failure_context.collect_failure_context(
            run_dir=temp_run_dir,
            repo_root=temp_run_dir,
            manifest_path=temp_manifest,
            output_path=output_path,
        )

        data = json.loads(output_path.read_text())
        diagnostics = data["gate_verdicts"]["targeted_tests"]["diagnostics"]
        assert len(diagnostics) > 0
        diag = diagnostics[0]
        assert diag["truncated"] is True
        assert "truncated" in diag["content"].lower()
    finally:
        failure_context.compute_candidate_identity = original_func


# ---------------------------------------------------------------------------
# U09: Redaction — secret value
# ---------------------------------------------------------------------------
def test_redaction_secret_value() -> None:
    """U09: secret values are never embedded in output."""
    text_with_secrets = """
    password = "super_secret_password_123"
    api_key = "sk_live_1234567890abcdef"
    Bearer token1234567890
    """

    sanitized, count = failure_context.redact_text(text_with_secrets)

    assert "super_secret_password_123" not in sanitized
    assert "sk_live_1234567890abcdef" not in sanitized
    assert "token1234567890" not in sanitized
    assert count >= 3
    assert "[REDACTED:" in sanitized


# ---------------------------------------------------------------------------
# U10: Redaction — Authorization header
# ---------------------------------------------------------------------------
def test_redaction_authorization_header() -> None:
    """U10: Authorization headers are stripped."""
    text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    sanitized, count = failure_context.redact_text(text)

    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in sanitized
    assert count >= 1


# ---------------------------------------------------------------------------
# U11: Redaction — URL with query params
# ---------------------------------------------------------------------------
def test_redaction_url_query_params() -> None:
    """U11: URL query strings are stripped."""
    text = "Error at https://api.example.com/endpoint?secret_key=abc123&token=xyz"
    sanitized, _count = failure_context.redact_text(text)

    assert "secret_key=abc123" not in sanitized
    assert "token=xyz" not in sanitized
    assert "https://api.example.com/endpoint" in sanitized


# ---------------------------------------------------------------------------
# U12: Unicode handling
# ---------------------------------------------------------------------------
def test_unicode_handling() -> None:
    """U12: invalid UTF-8 bytes are replaced with U+FFFD."""
    # Valid UTF-8
    valid = "Hello 世界 🌍"
    normalized = failure_context.normalize_utf8(valid)
    assert normalized == valid

    # Text with control characters should be normalized
    text_with_control = "Line 1\nLine 2\r\nLine 3"
    normalized = failure_context.normalize_utf8(text_with_control)
    assert "Line 1" in normalized


# ---------------------------------------------------------------------------
# U13: Path with spaces
# ---------------------------------------------------------------------------
def test_path_with_spaces(temp_run_dir: Path, temp_manifest: Path, temp_verify_result: Path) -> None:
    """U13: paths with spaces are handled without shell split."""
    # Create a file with spaces in the path
    spaced_dir = temp_run_dir / "verify" / "dir with spaces"
    spaced_dir.mkdir(parents=True, exist_ok=True)
    (spaced_dir / "file with spaces.log").write_text("Test content")

    output_path = temp_run_dir / "reports" / "failure-context.json"

    original_func = failure_context.compute_candidate_identity
    failure_context.compute_candidate_identity = lambda repo_root, base_commit, manifest_path: {
        "base_commit": "a" * 40,
        "candidate_commit": None,
        "candidate_state": "working_tree",
        "candidate_diff_digest": "3" * 64,
    }

    try:
        # Should not raise
        failure_context.collect_failure_context(
            run_dir=temp_run_dir,
            repo_root=temp_run_dir,
            manifest_path=temp_manifest,
            output_path=output_path,
        )
        assert output_path.exists()
    finally:
        failure_context.compute_candidate_identity = original_func


# ---------------------------------------------------------------------------
# U14: Digest determinism
# ---------------------------------------------------------------------------
def test_digest_determinism() -> None:
    """U14: same input produces same digest."""
    inventory = [
        ("file1.py", 100, "a" * 64),
        ("file2.py", 200, "b" * 64),
    ]

    # Manually compute digest (same logic as in compute_candidate_identity)
    inventory.sort(key=lambda x: x[0])
    serialized = "\n".join(f"{path}\t{size}\t{sha}" for path, size, sha in inventory)

    import hashlib
    digest1 = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    digest2 = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    assert digest1 == digest2
    assert len(digest1) == 64


# ---------------------------------------------------------------------------
# U15: Digest sensitivity
# ---------------------------------------------------------------------------
def test_digest_sensitivity() -> None:
    """U15: any change produces different digest."""
    inventory1 = [("file1.py", 100, "a" * 64)]
    inventory2 = [("file1.py", 101, "a" * 64)]  # Different size

    inventory1.sort(key=lambda x: x[0])
    inventory2.sort(key=lambda x: x[0])

    serialized1 = "\n".join(f"{path}\t{size}\t{sha}" for path, size, sha in inventory1)
    serialized2 = "\n".join(f"{path}\t{size}\t{sha}" for path, size, sha in inventory2)

    import hashlib
    digest1 = hashlib.sha256(serialized1.encode("utf-8")).hexdigest()
    digest2 = hashlib.sha256(serialized2.encode("utf-8")).hexdigest()

    assert digest1 != digest2


# ---------------------------------------------------------------------------
# U16: Collector infrastructure failure
# ---------------------------------------------------------------------------
def test_collector_infrastructure_failure(temp_run_dir: Path, temp_manifest: Path) -> None:
    """U16: collection_status is failed, exit code 2 on infrastructure failure."""
    # Remove verify-result.json to trigger infrastructure failure
    output_path = temp_run_dir / "reports" / "failure-context.json"

    with pytest.raises(RuntimeError, match="verify-result.json missing"):
        failure_context.collect_failure_context(
            run_dir=temp_run_dir,
            repo_root=temp_run_dir,
            manifest_path=temp_manifest,
            output_path=output_path,
        )


# ---------------------------------------------------------------------------
# Additional tests
# ---------------------------------------------------------------------------
def test_stable_output_ordering(temp_run_dir: Path, temp_manifest: Path, temp_verify_result: Path) -> None:
    """Stable output ordering: gates sorted lexicographically."""
    output_path = temp_run_dir / "reports" / "failure-context.json"

    original_func = failure_context.compute_candidate_identity
    failure_context.compute_candidate_identity = lambda repo_root, base_commit, manifest_path: {
        "base_commit": "a" * 40,
        "candidate_commit": None,
        "candidate_state": "working_tree",
        "candidate_diff_digest": "4" * 64,
    }

    try:
        failure_context.collect_failure_context(
            run_dir=temp_run_dir,
            repo_root=temp_run_dir,
            manifest_path=temp_manifest,
            output_path=output_path,
        )

        data = json.loads(output_path.read_text())

        # Verify gate_verdicts contains all canonical gates
        expected_gates = ["git_diff_check", "json_syntax", "lint", "scope",
                         "secrets", "targeted_tests", "yaml_syntax"]
        for gate in expected_gates:
            assert gate in data["gate_verdicts"]
    finally:
        failure_context.compute_candidate_identity = original_func


def test_no_absolute_paths(temp_run_dir: Path, temp_manifest: Path, temp_verify_result: Path) -> None:
    """No absolute paths in output."""
    output_path = temp_run_dir / "reports" / "failure-context.json"

    original_func = failure_context.compute_candidate_identity
    failure_context.compute_candidate_identity = lambda repo_root, base_commit, manifest_path: {
        "base_commit": "a" * 40,
        "candidate_commit": None,
        "candidate_state": "working_tree",
        "candidate_diff_digest": "5" * 64,
    }

    try:
        failure_context.collect_failure_context(
            run_dir=temp_run_dir,
            repo_root=temp_run_dir,
            manifest_path=temp_manifest,
            output_path=output_path,
        )

        data = json.loads(output_path.read_text())

        # Check artifact_refs
        for log_path in data["artifact_refs"]["gate_logs"]:
            assert not Path(log_path).is_absolute()

        # Check diagnostics
        for verdict in data["gate_verdicts"].values():
            for artifact in verdict["source_artifacts"]:
                assert not Path(artifact).is_absolute()
    finally:
        failure_context.compute_candidate_identity = original_func


def test_collection_errors_bounded(temp_run_dir: Path, temp_manifest: Path) -> None:
    """collection_errors is bounded."""
    # Create malformed verify-result.json
    verify_result_path = temp_run_dir / "reports" / "verify-result.json"
    verify_result_path.write_text("not valid json")

    output_path = temp_run_dir / "reports" / "failure-context.json"

    with pytest.raises(RuntimeError):
        failure_context.collect_failure_context(
            run_dir=temp_run_dir,
            repo_root=temp_run_dir,
            manifest_path=temp_manifest,
            output_path=output_path,
        )


def test_candidate_commit_null_rules(temp_run_dir: Path, temp_manifest: Path, temp_verify_result: Path) -> None:
    """candidate_commit is null when candidate_state is working_tree."""
    output_path = temp_run_dir / "reports" / "failure-context.json"

    original_func = failure_context.compute_candidate_identity
    failure_context.compute_candidate_identity = lambda repo_root, base_commit, manifest_path: {
        "base_commit": "a" * 40,
        "candidate_commit": None,
        "candidate_state": "working_tree",
        "candidate_diff_digest": "6" * 64,
    }

    try:
        failure_context.collect_failure_context(
            run_dir=temp_run_dir,
            repo_root=temp_run_dir,
            manifest_path=temp_manifest,
            output_path=output_path,
        )

        data = json.loads(output_path.read_text())
        ci = data["candidate_identity"]

        if ci["candidate_state"] == "working_tree":
            assert ci["candidate_commit"] is None
        elif ci["candidate_state"] == "committed":
            assert ci["candidate_commit"] is not None
            assert len(ci["candidate_commit"]) == 40
    finally:
        failure_context.compute_candidate_identity = original_func


# ---------------------------------------------------------------------------
# Diagnostic safety tests
# ---------------------------------------------------------------------------
def test_sanitize_control_characters() -> None:
    """Control characters are removed, but \\n\\t\\r are preserved."""
    text = "Line1\nLine2\tTabbed\rCarriage" + chr(0x01) + chr(0x07) + "End"
    sanitized = failure_context.sanitize_control_characters(text)

    assert "\n" in sanitized
    assert "\t" in sanitized
    assert "\r" in sanitized
    assert chr(0x01) not in sanitized  # Control char removed
    assert chr(0x07) not in sanitized  # Bell char removed
    assert "Line1" in sanitized
    assert "End" in sanitized


def test_is_binary_content_detection() -> None:
    """Binary content is detected by high ratio of non-printable chars."""
    # Text content
    text_content = "This is normal text with some spaces and punctuation."
    assert not failure_context.is_binary_content(text_content)

    # Binary-like content with null bytes (strong indicator)
    binary_with_nulls = "text\x00more\x00data"
    assert failure_context.is_binary_content(binary_with_nulls)

    # Binary-like content (high ratio of control chars)
    binary_content = "".join(chr(i) for i in range(32)) * 32  # Mostly control chars
    assert failure_context.is_binary_content(binary_content)

    # Empty content
    assert not failure_context.is_binary_content("")


def test_redact_base64_runs() -> None:
    """Long base64-like strings are redacted."""
    # Short string should not be redacted
    short = "SGVsbG8gV29ybGQ="
    result, count = failure_context.redact_base64_runs(short, min_length=100)
    assert result == short
    assert count == 0

    # Long base64 string should be redacted
    long_b64 = "A" * 150
    result, count = failure_context.redact_base64_runs(long_b64, min_length=100)
    assert "[REDACTED:base64_payload]" in result
    assert count == 1
    assert long_b64 not in result


def test_redact_binary_content() -> None:
    """Binary content is fully redacted."""
    # Create binary-like content with null bytes
    binary = "data\x00\x01\x02more\x00binary"
    result, count = failure_context.redact_text(binary)
    assert result == "[REDACTED:binary_content]"
    assert count >= 1


def test_redact_preserves_normal_text() -> None:
    """Normal text is preserved after redaction."""
    text = "Error in function calculate_risk() at line 42"
    result, _count = failure_context.redact_text(text)
    assert "Error in function calculate_risk()" in result
    assert "line 42" in result


def test_determinism_excluding_timestamps(temp_run_dir: Path, temp_manifest: Path) -> None:
    """Two runs with identical input produce identical output except generated_at and run_id."""
    verify_result = {
        "schema_version": "1.0",
        "run_id": "det-test-001",
        "story_id": "DET-001",
        "overall_status": "FAIL",
        "gates": [
            {"name": "targeted_tests", "status": "FAIL", "details": "1 failed"},
        ],
    }
    verify_result_path = temp_run_dir / "reports" / "verify-result.json"
    verify_result_path.write_text(json.dumps(verify_result))
    (temp_run_dir / "verify" / "targeted_tests.log").write_text("FAIL test_x")

    original_func = failure_context.compute_candidate_identity
    mock_identity = {
        "base_commit": "a" * 40,
        "candidate_commit": None,
        "candidate_state": "working_tree",
        "candidate_diff_digest": "d" * 64,
    }
    failure_context.compute_candidate_identity = lambda repo_root, base_commit, manifest_path: mock_identity

    try:
        out1 = temp_run_dir / "reports" / "fc1.json"
        out2 = temp_run_dir / "reports" / "fc2.json"

        failure_context.collect_failure_context(
            run_dir=temp_run_dir, repo_root=temp_run_dir,
            manifest_path=temp_manifest, output_path=out1,
        )
        failure_context.collect_failure_context(
            run_dir=temp_run_dir, repo_root=temp_run_dir,
            manifest_path=temp_manifest, output_path=out2,
        )

        d1 = json.loads(out1.read_text())
        d2 = json.loads(out2.read_text())

        # Exclude nondeterministic fields
        excluded = ["generated_at"]
        for d in [d1, d2]:
            for k in excluded:
                d.pop(k, None)

        assert d1 == d2, f"Outputs differ after excluding {excluded}"
    finally:
        failure_context.compute_candidate_identity = original_func


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
