"""Test-only repair actor for harness scenarios AC/AM/AN.

Writes a passing test function to the --modify path so reverify can PASS.
This is a test fixture, not a production component — it provides the
narrowest deterministic behavior needed for the full repair cycle success
scenario where the mock_repair_actor's comment-only output would leave the
targeted test file with zero collected tests (assertion gate FAIL).

Usage: passed via REPAIR_ACTOR_SCRIPT env var to run-story.sh, which
forwards it as --actor-arg to the repair adapter. The adapter injects
--repair-request and --repair-result.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test-only repair actor for AC/AM/AN scenarios"
    )
    parser.add_argument("--repair-request", required=True)
    parser.add_argument("--repair-result", required=True)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--modify", action="append", default=[])
    args = parser.parse_args()

    with open(args.repair_request, "r", encoding="utf-8") as f:
        request = json.load(f)

    if args.mode == "REPAIRED" and args.modify:
        for path_str in args.modify:
            p = Path(path_str)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(
                ('"""Repaired test file."""\n\n'
                 '\ndef test_repaired():\n    assert True\n'),
                encoding="utf-8",
            )

        result = {
            "schema_version": "1.0",
            "run_id": request["run_id"],
            "story_id": request["story_id"],
            "attempt": request["attempt"],
            "source_revision": request["source_revision"],
            "status": "REPAIRED",
            "changed": True,
            "changed_files": sorted(args.modify),
            "summary": "Test repair actor: REPAIRED",
            "diagnostics": {"actions_taken": [], "obstacles": []},
            "recommended_action": "reverify",
            "sanitization": {
                "redaction_applied": False,
                "redaction_count": 0,
                "truncation_applied": False,
                "truncated_fields": [],
            },
            "completed_at": request["generated_at"],
        }
    elif args.mode == "NO_CHANGE":
        result = {
            "schema_version": "1.0",
            "run_id": request["run_id"],
            "story_id": request["story_id"],
            "attempt": request["attempt"],
            "source_revision": request["source_revision"],
            "status": "NO_CHANGE",
            "changed": False,
            "changed_files": [],
            "summary": "Test repair actor: NO_CHANGE",
            "diagnostics": {"actions_taken": [], "obstacles": []},
            "recommended_action": "abort",
            "sanitization": {
                "redaction_applied": False,
                "redaction_count": 0,
                "truncation_applied": False,
                "truncated_fields": [],
            },
            "completed_at": request["generated_at"],
        }
    elif args.mode == "ERROR":
        result = {
            "schema_version": "1.0",
            "run_id": request["run_id"],
            "story_id": request["story_id"],
            "attempt": request["attempt"],
            "source_revision": request["source_revision"],
            "status": "ERROR",
            "changed": False,
            "changed_files": [],
            "summary": "Test repair actor: ERROR",
            "diagnostics": {"actions_taken": [], "obstacles": ["mock error"]},
            "recommended_action": "abort",
            "sanitization": {
                "redaction_applied": False,
                "redaction_count": 0,
                "truncation_applied": False,
                "truncated_fields": [],
            },
            "completed_at": request["generated_at"],
        }
    elif args.mode == "undeclared_change" and args.modify:
        for path_str in args.modify:
            p = Path(path_str)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(
                ('"""Repaired test file."""\n\n'
                 '\ndef test_repaired():\n    assert True\n'),
                encoding="utf-8",
            )
        undeclared = Path("undeclared_change.txt")
        undeclared.parent.mkdir(parents=True, exist_ok=True)
        undeclared.write_text("# undeclared\n", encoding="utf-8")
        result = {
            "schema_version": "1.0",
            "run_id": request["run_id"],
            "story_id": request["story_id"],
            "attempt": request["attempt"],
            "source_revision": request["source_revision"],
            "status": "REPAIRED",
            "changed": True,
            "changed_files": sorted(args.modify),
            "summary": "Test repair actor: undeclared change",
            "diagnostics": {"actions_taken": [], "obstacles": []},
            "recommended_action": "reverify",
            "sanitization": {
                "redaction_applied": False,
                "redaction_count": 0,
                "truncation_applied": False,
                "truncated_fields": [],
            },
            "completed_at": request["generated_at"],
        }
    else:
        print(f"Unknown mode or missing --modify: {args.mode}", file=sys.stderr)
        return 2

    _atomic_write_json(Path(args.repair_result), result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
