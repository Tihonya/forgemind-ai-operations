"""
WP-AL-1C2: Deterministic mock reviewer for testing the reviewer adapter.

Production protocol:
  mock_reviewer.py --request <path> --output <path> --mode PASS|FAIL|ERROR

Behavior:
1. Parse named arguments via argparse
2. Read and parse request_path as JSON
3. Validate binding fields (run_id, story_id, review_iteration, repair_iteration, reviewer_id)
4. Construct deterministic review-result.json based on --mode
5. Use generated_at from request as status_generated_at (no internal time call)
6. Write result atomically to output_path (tmp + os.replace)
7. Exit 0 on success
8. Exit 2 on mock infrastructure failure

Determinism:
- No datetime.now() or time.time() calls
- Timestamps derived from request only
- Finding IDs are deterministic
- Output reproducible given same request and mode

No network, no environment configuration, no ambient state.

Test-only modes (hidden, not part of production protocol):
- invalid_json: Write malformed JSON to output, exit 0
- contract_violation: Write result missing required field, exit 0
- non_zero_exit: Exit 1 without writing output
- sleep: Sleep for 60 seconds (timeout testing), exit 0
- missing_output: Exit 0 without writing output
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """Atomically write JSON to path via tmp + os.replace."""
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)

    # Create temp file in same directory for atomic replace
    fd, tmp_path = tempfile.mkstemp(dir=str(parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
            f.write("\n")
            f.flush()
            try:
                os.fsync(f.fileno())
            except (OSError, AttributeError):
                pass  # fsync not always supported
        os.replace(tmp_path, path)
    except Exception:
        # Clean up temp file on error
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _build_pass_result(request: dict[str, Any]) -> dict[str, Any]:
    """Build PASS result from request."""
    return {
        "schema_version": "1.0",
        "run_id": request["run_id"],
        "story_id": request["story_id"],
        "review_iteration": request["review_iteration"],
        "repair_iteration": request["repair_iteration"],
        "status": "PASS",
        "status_generated_at": request["generated_at"],
        "reviewer_id": request["reviewer_id"],
        "findings": [],
        "decision_rationale": "Mock reviewer: PASS",
        "recommended_action": "none",
        "sanitization": {
            "redaction_applied": False,
            "redaction_count": 0,
            "truncation_applied": False,
            "truncated_fields": [],
        },
    }


def _build_fail_result(request: dict[str, Any]) -> dict[str, Any]:
    """Build FAIL result with one BLOCKER finding."""
    return {
        "schema_version": "1.0",
        "run_id": request["run_id"],
        "story_id": request["story_id"],
        "review_iteration": request["review_iteration"],
        "repair_iteration": request["repair_iteration"],
        "status": "FAIL",
        "status_generated_at": request["generated_at"],
        "reviewer_id": request["reviewer_id"],
        "findings": [
            {
                "finding_id": "mock-finding-001",
                "severity": "BLOCKER",
                "category": "implementation",
                "summary": "Mock reviewer: implementation defect",
                "evidence_refs": [],
                "recommended_fix": "Fix implementation defect",
            }
        ],
        "decision_rationale": "Mock reviewer: FAIL",
        "recommended_action": "repair",
        "sanitization": {
            "redaction_applied": False,
            "redaction_count": 0,
            "truncation_applied": False,
            "truncated_fields": [],
        },
    }


def _build_error_result(request: dict[str, Any]) -> dict[str, Any]:
    """Build ERROR result with one MAJOR finding (infrastructure category)."""
    return {
        "schema_version": "1.0",
        "run_id": request["run_id"],
        "story_id": request["story_id"],
        "review_iteration": request["review_iteration"],
        "repair_iteration": request["repair_iteration"],
        "status": "ERROR",
        "status_generated_at": request["generated_at"],
        "reviewer_id": request["reviewer_id"],
        "findings": [
            {
                "finding_id": "mock-finding-001",
                "severity": "MAJOR",
                "category": "infrastructure",
                "summary": "Mock reviewer: infrastructure error",
                "evidence_refs": [],
                "recommended_fix": "Human review required",
            }
        ],
        "decision_rationale": "Mock reviewer: ERROR",
        "recommended_action": "human_review",
        "sanitization": {
            "redaction_applied": False,
            "redaction_count": 0,
            "truncation_applied": False,
            "truncated_fields": [],
        },
    }


def _build_invalid_json() -> str:
    """Build malformed JSON for test-only invalid_json mode."""
    return "{ invalid json }"


def _build_contract_violation_result(request: dict[str, Any]) -> dict[str, Any]:
    """Build result missing required field for test-only contract_violation mode."""
    # Missing 'status' field
    return {
        "schema_version": "1.0",
        "run_id": request["run_id"],
        "story_id": request["story_id"],
        "review_iteration": request["review_iteration"],
        "repair_iteration": request["repair_iteration"],
        # status field intentionally omitted
        "status_generated_at": request["generated_at"],
        "reviewer_id": request["reviewer_id"],
        "findings": [],
        "decision_rationale": "Contract violation test",
        "recommended_action": "none",
        "sanitization": {
            "redaction_applied": False,
            "redaction_count": 0,
            "truncation_applied": False,
            "truncated_fields": [],
        },
    }


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Mock reviewer for WP-AL-1C2")
    parser.add_argument("--request", required=True, help="Path to review-request.json")
    parser.add_argument("--output", required=True, help="Path to write review-result.json")
    parser.add_argument(
        "--mode",
        required=True,
        choices=["PASS", "FAIL", "ERROR", "invalid_json", "contract_violation", "non_zero_exit", "sleep", "missing_output"],
        help="Reviewer mode",
    )
    args = parser.parse_args()

    request_path = Path(args.request)
    output_path = Path(args.output)
    mode = args.mode

    # Test-only: sleep mode (timeout testing)
    if mode == "sleep":
        time.sleep(60)
        return 0

    # Test-only: non_zero_exit mode
    if mode == "non_zero_exit":
        return 1

    # Test-only: missing_output mode
    if mode == "missing_output":
        return 0

    # Read request
    try:
        with open(request_path, "r", encoding="utf-8") as f:
            request = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"Mock reviewer: cannot read request: {e}", file=sys.stderr)
        return 2

    # Validate binding fields
    required_fields = ["run_id", "story_id", "review_iteration", "repair_iteration", "reviewer_id", "generated_at"]
    for field in required_fields:
        if field not in request:
            print(f"Mock reviewer: request missing field: {field}", file=sys.stderr)
            return 2

    # Build result based on mode
    if mode == "PASS":
        result = _build_pass_result(request)
    elif mode == "FAIL":
        result = _build_fail_result(request)
    elif mode == "ERROR":
        result = _build_error_result(request)
    elif mode == "invalid_json":
        # Write malformed JSON
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(_build_invalid_json())
                f.write("\n")
        except OSError as e:
            print(f"Mock reviewer: cannot write output: {e}", file=sys.stderr)
            return 2
        return 0
    elif mode == "contract_violation":
        result = _build_contract_violation_result(request)
    else:
        print(f"Mock reviewer: unknown mode: {mode}", file=sys.stderr)
        return 2

    # Write result atomically
    try:
        _atomic_write_json(output_path, result)
    except OSError as e:
        print(f"Mock reviewer: cannot write output: {e}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
