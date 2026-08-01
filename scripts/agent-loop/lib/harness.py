#!/usr/bin/env python3
"""
Agent-loop harness shared Python utilities.

Provides:
  - atomic_json_write: write JSON atomically via tmp+os.replace
  - parse_junit_xml: parse pytest JUnit XML and return structured counts
  - validate_manifest: validate story manifest JSON schema
  - load_gate_config: extract gate config from manifest
"""

import json
import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


def atomic_json_write(path, data, indent=2):
    """Write JSON data atomically: tmp file in same dir + os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        suffix=".tmp",
        prefix=path.name + ".",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=indent)
            f.write("\n")
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def parse_junit_xml(report_file):
    """Parse pytest JUnit XML and return gate decision.

    Returns dict with keys:
      collected, passed, failed, error, skipped
      gate_status: 'pass' | 'fail'
      gate_reason: str
    """
    report_file = str(report_file)
    try:
        tree = ET.parse(report_file)
        root = tree.getroot()
    except Exception as e:
        return {
            "collected": 0, "passed": 0, "failed": 0,
            "error": 0, "skipped": 0,
            "gate_status": "fail",
            "gate_reason": f"PARSE_ERROR: {type(e).__name__}: {e}",
        }

    passed = 0
    failed = 0
    skipped = 0
    error = 0
    collected = 0

    testsuites = root.findall(".//testsuite")
    if not testsuites:
        testsuites = [root] if root.tag == "testsuite" else []

    for ts in testsuites:
        collected += int(ts.get("tests", 0))
        failed += int(ts.get("failures", 0))
        error += int(ts.get("errors", 0))
        skipped += int(ts.get("skipped", 0))

    passed = collected - failed - skipped - error

    if collected == 0:
        return {
            "collected": collected, "passed": passed, "failed": failed,
            "error": error, "skipped": skipped,
            "gate_status": "fail",
            "gate_reason": "zero tests collected",
        }

    if passed == 0 and skipped > 0:
        return {
            "collected": collected, "passed": passed, "failed": failed,
            "error": error, "skipped": skipped,
            "gate_status": "fail",
            "gate_reason": "all tests skipped, zero passed",
        }

    if failed > 0 or error > 0:
        return {
            "collected": collected, "passed": passed, "failed": failed,
            "error": error, "skipped": skipped,
            "gate_status": "fail",
            "gate_reason": "tests failed or errors",
        }

    return {
        "collected": collected, "passed": passed, "failed": failed,
        "error": error, "skipped": skipped,
        "gate_status": "pass",
        "gate_reason": "assertions executed",
    }


def validate_manifest(manifest_path):
    """Validate story manifest JSON.

    Returns ('OK', story_id) or ('ERROR', error_string).
    """
    try:
        with open(manifest_path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return ("ERROR", f"JSON_SYNTAX|Invalid JSON syntax: {e}")
    except Exception as e:
        return ("ERROR", f"UNEXPECTED|Unexpected error: {type(e).__name__}: {e}")

    if not isinstance(data, dict):
        return ("ERROR", "ROOT_TYPE|Root element is not a JSON object")

    if "story_id" not in data:
        return ("ERROR", "STORY_ID_MISSING|story_id field is required")

    story_id = data["story_id"]
    if not story_id or not isinstance(story_id, str) or story_id.strip() == "":
        return ("ERROR", "STORY_ID_EMPTY|story_id must be a non-empty string")

    if "gates" in data:
        gates = data["gates"]
        if not isinstance(gates, dict):
            return ("ERROR", "GATES_TYPE|gates must be a JSON object")
        for gate_name, gate_config in gates.items():
            if not isinstance(gate_config, dict):
                return ("ERROR", f"GATE_CONFIG_TYPE|Gate {gate_name} config must be a JSON object")
            if "required" in gate_config and not isinstance(gate_config["required"], bool):
                return ("ERROR", f"GATE_REQUIRED_TYPE|Gate {gate_name}.required must be boolean")
            if "enabled" in gate_config and not isinstance(gate_config["enabled"], bool):
                return ("ERROR", f"GATE_ENABLED_TYPE|Gate {gate_name}.enabled must be boolean")

    return ("OK", story_id)


def load_gate_config(manifest_path):
    """Extract gate config from manifest. Supports gates dict or gates_required list."""
    try:
        with open(manifest_path) as f:
            m = json.load(f)
    except Exception:
        return {}

    if "gates" in m:
        return m["gates"]
    elif "gates_required" in m:
        gates = {}
        for g in m["gates_required"]:
            gates[g] = {"required": True, "enabled": True}
        return gates
    return {}


def load_test_args(manifest_path):
    """Extract targeted_args from manifest as a JSON array.

    Backward compatible: if targeted_args is a string, split into list.
    Returns list of strings (argv elements, no shell interpolation).
    """
    try:
        with open(manifest_path) as f:
            m = json.load(f)
    except Exception:
        return []

    tc = m.get("test_commands", {})
    if not isinstance(tc, dict):
        return []

    args = tc.get("targeted_args", [])

    # Backward compatibility: string → split on whitespace
    if isinstance(args, str):
        if not args.strip():
            return []
        return args.split()

    if isinstance(args, list):
        return args

    return []


if __name__ == "__main__":
    # CLI entry for bash callers
    if len(sys.argv) < 2:
        print("Usage: harness.py <command> [args...]", file=sys.stderr)
        print("Commands: validate, load_gate_config, load_test_args, parse_junit", file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "validate":
        ok, val = validate_manifest(sys.argv[2])
        print(f"{ok}:{val}")
        sys.exit(0)

    elif cmd == "load_gate_config":
        config = load_gate_config(sys.argv[2])
        print(json.dumps(config))
        sys.exit(0)

    elif cmd == "load_test_args":
        args = load_test_args(sys.argv[2])
        print(json.dumps(args))
        sys.exit(0)

    elif cmd == "parse_junit":
        result = parse_junit_xml(sys.argv[2])
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["gate_status"] == "pass" else 1)

    elif cmd == "atomic_write":
        # atomic_write <output_file> <json_string>
        data = json.loads(sys.argv[3])
        atomic_json_write(sys.argv[2], data)
        sys.exit(0)

    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)
