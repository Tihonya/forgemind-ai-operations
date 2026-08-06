"""
WP-AL-1C5: Deterministic mock repair actor for testing the repair adapter.

Production protocol:
  mock_repair_actor.py --repair-request <path> --repair-result <path>
                        --mode <mode> [--modify <path>]...

The adapter inject --repair-request and --repair-result automatically.
User-supplied arguments: --mode and --modify.

Behavior:
1. Parse named arguments via argparse
2. Read and parse repair-request JSON
3. Validate binding fields (run_id, story_id, attempt, source_revision)
4. Perform workspace modifications (if mode requires them)
5. Construct deterministic repair-result JSON based on --mode
6. Use generated_at from request as completed_at (no internal time call)
7. Write result atomically to --repair-result path (tmp + os.replace)
8. Exit 0 on success
9. Exit 2 on mock infrastructure failure

Determinism:
- No datetime.now() or time.time() calls
- Timestamps derived from request only
- Output reproducible given same request and mode

No network, no environment configuration, no ambient state.
No LLM calls, no shell interpolation.

Modes:
  REPAIRED: modify --modify files, declare them in changed_files, status=REPAIRED
  NO_CHANGE: no modifications, empty changed_files, status=NO_CHANGE
  ERROR: no modifications, status=ERROR
  undeclared_change: modify --modify files + one extra undeclared file,
                     declare only --modify files in changed_files
  forbidden_change: modify a file at .env (matches typical forbidden pattern),
                    declare it in changed_files
  non_zero_exit: exit 1 without writing result
  missing_result: exit 0 without writing result
  malformed_result: write invalid JSON to result path, exit 0
  sleep: sleep 60 seconds (timeout testing), exit 0
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

    fd, tmp_path = tempfile.mkstemp(dir=str(parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
            f.write("\n")
            f.flush()
            try:
                os.fsync(f.fileno())
            except (OSError, AttributeError):
                pass
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _build_repaired_result(
    request: dict[str, Any],
    changed_files: list[str],
) -> dict[str, Any]:
    """Build REPAIRED result from request."""
    return {
        "schema_version": "1.0",
        "run_id": request["run_id"],
        "story_id": request["story_id"],
        "attempt": request["attempt"],
        "source_revision": request["source_revision"],
        "status": "REPAIRED",
        "changed": True,
        "changed_files": sorted(changed_files),
        "summary": "Mock repair actor: REPAIRED",
        "diagnostics": {
            "actions_taken": [],
            "obstacles": [],
        },
        "recommended_action": "reverify",
        "sanitization": {
            "redaction_applied": False,
            "redaction_count": 0,
            "truncation_applied": False,
            "truncated_fields": [],
        },
        "completed_at": request["generated_at"],
    }


def _build_no_change_result(request: dict[str, Any]) -> dict[str, Any]:
    """Build NO_CHANGE result from request."""
    return {
        "schema_version": "1.0",
        "run_id": request["run_id"],
        "story_id": request["story_id"],
        "attempt": request["attempt"],
        "source_revision": request["source_revision"],
        "status": "NO_CHANGE",
        "changed": False,
        "changed_files": [],
        "summary": "Mock repair actor: NO_CHANGE",
        "diagnostics": {
            "actions_taken": [],
            "obstacles": [],
        },
        "recommended_action": "abort",
        "sanitization": {
            "redaction_applied": False,
            "redaction_count": 0,
            "truncation_applied": False,
            "truncated_fields": [],
        },
        "completed_at": request["generated_at"],
    }


def _build_error_result(request: dict[str, Any]) -> dict[str, Any]:
    """Build ERROR result from request."""
    return {
        "schema_version": "1.0",
        "run_id": request["run_id"],
        "story_id": request["story_id"],
        "attempt": request["attempt"],
        "source_revision": request["source_revision"],
        "status": "ERROR",
        "changed": False,
        "changed_files": [],
        "summary": "Mock repair actor: ERROR",
        "diagnostics": {
            "actions_taken": [],
            "obstacles": ["mock infrastructure error"],
        },
        "recommended_action": "abort",
        "sanitization": {
            "redaction_applied": False,
            "redaction_count": 0,
            "truncation_applied": False,
            "truncated_fields": [],
        },
        "completed_at": request["generated_at"],
    }


def _build_undeclared_change_result(
    request: dict[str, Any],
    declared_files: list[str],
) -> dict[str, Any]:
    """Build REPAIRED result that declares only some files (undeclared change)."""
    return {
        "schema_version": "1.0",
        "run_id": request["run_id"],
        "story_id": request["story_id"],
        "attempt": request["attempt"],
        "source_revision": request["source_revision"],
        "status": "REPAIRED",
        "changed": True,
        "changed_files": sorted(declared_files),
        "summary": "Mock repair actor: undeclared change test",
        "diagnostics": {
            "actions_taken": [],
            "obstacles": [],
        },
        "recommended_action": "reverify",
        "sanitization": {
            "redaction_applied": False,
            "redaction_count": 0,
            "truncation_applied": False,
            "truncated_fields": [],
        },
        "completed_at": request["generated_at"],
    }


def _build_forbidden_change_result(
    request: dict[str, Any],
    changed_files: list[str],
) -> dict[str, Any]:
    """Build REPAIRED result that modifies a forbidden file."""
    return {
        "schema_version": "1.0",
        "run_id": request["run_id"],
        "story_id": request["story_id"],
        "attempt": request["attempt"],
        "source_revision": request["source_revision"],
        "status": "REPAIRED",
        "changed": True,
        "changed_files": sorted(changed_files),
        "summary": "Mock repair actor: forbidden change test",
        "diagnostics": {
            "actions_taken": [],
            "obstacles": [],
        },
        "recommended_action": "reverify",
        "sanitization": {
            "redaction_applied": False,
            "redaction_count": 0,
            "truncation_applied": False,
            "truncated_fields": [],
        },
        "completed_at": request["generated_at"],
    }


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Mock repair actor for WP-AL-1C5"
    )
    parser.add_argument(
        "--repair-request",
        required=True,
        help="Path to repair-request.json (injected by adapter)",
    )
    parser.add_argument(
        "--repair-result",
        required=True,
        help="Path to write repair-result.json (injected by adapter)",
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=[
            "REPAIRED",
            "NO_CHANGE",
            "ERROR",
            "undeclared_change",
            "forbidden_change",
            "non_zero_exit",
            "missing_result",
            "malformed_result",
            "sleep",
        ],
        help="Actor mode",
    )
    parser.add_argument(
        "--modify",
        action="append",
        default=[],
        help="Path to modify (may be repeated)",
    )
    args = parser.parse_args()

    request_path = Path(args.repair_request)
    result_path = Path(args.repair_result)
    mode = args.mode
    modify_paths = args.modify

    # Test-only: sleep mode (timeout testing)
    if mode == "sleep":
        time.sleep(60)
        return 0

    # Test-only: non_zero_exit mode
    if mode == "non_zero_exit":
        return 1

    # Test-only: missing_result mode
    if mode == "missing_result":
        return 0

    # Read request
    try:
        with open(request_path, "r", encoding="utf-8") as f:
            request = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"Mock repair actor: cannot read request: {e}", file=sys.stderr)
        return 2

    # Validate binding fields
    required_fields = [
        "run_id",
        "story_id",
        "attempt",
        "source_revision",
        "generated_at",
    ]
    for field_name in required_fields:
        if field_name not in request:
            print(
                f"Mock repair actor: request missing field: {field_name}",
                file=sys.stderr,
            )
            return 2

    # Test-only: malformed_result mode
    if mode == "malformed_result":
        try:
            with open(result_path, "w", encoding="utf-8") as f:
                f.write("{ invalid json }")
                f.write("\n")
        except OSError as e:
            print(
                f"Mock repair actor: cannot write output: {e}",
                file=sys.stderr,
            )
            return 2
        return 0

    # Validate mode-specific requirements
    if mode in ("REPAIRED", "undeclared_change") and not modify_paths:
        print(
            f"Mock repair actor: mode {mode} requires at least one --modify path",
            file=sys.stderr,
        )
        return 2

    # Build result based on mode
    if mode == "REPAIRED":
        # Modify declared files
        for path_str in modify_paths:
            p = Path(path_str)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f"# Mock repair: modified {path_str}\n", encoding="utf-8")

        result = _build_repaired_result(request, list(modify_paths))

    elif mode == "NO_CHANGE":
        result = _build_no_change_result(request)

    elif mode == "ERROR":
        result = _build_error_result(request)

    elif mode == "undeclared_change":
        # Modify declared files
        for path_str in modify_paths:
            p = Path(path_str)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f"# Mock repair: modified {path_str}\n", encoding="utf-8")

        # Also modify an undeclared file
        undeclared = Path("undeclared_change.txt")
        undeclared.parent.mkdir(parents=True, exist_ok=True)
        undeclared.write_text(
            "# Mock repair: undeclared modification\n", encoding="utf-8"
        )

        # Declare only the --modify files, not the undeclared one
        result = _build_undeclared_change_result(request, list(modify_paths))

    elif mode == "forbidden_change":
        # Modify a file that typically matches forbidden patterns (.env)
        forbidden_path = Path(".env")
        forbidden_path.write_text(
            "# Mock repair: forbidden modification\n", encoding="utf-8"
        )

        # Declare the forbidden file in changed_files
        result = _build_forbidden_change_result(request, [".env"])

    else:
        print(f"Mock repair actor: unknown mode: {mode}", file=sys.stderr)
        return 2

    # Write result atomically
    try:
        _atomic_write_json(result_path, result)
    except OSError as e:
        print(f"Mock repair actor: cannot write output: {e}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
