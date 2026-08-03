#!/usr/bin/env python3
"""
Agent-loop harness shared Python utilities.

Provides:
  - atomic_json_write: write JSON atomically via tmp+os.replace
  - parse_junit_xml: parse pytest JUnit XML and return structured counts
  - validate_manifest: validate story manifest JSON schema
  - load_gate_config: extract gate config from manifest
  - gitwildmatch: native gitignore-style pattern matching (path_pattern_type)
  - list_candidate_diff_files: enumerate candidate diff vs manifest base_commit
  - scope_check: manifest-driven scope gate decision (JSON verdict on stdout)
"""

import json
import os
import re
import subprocess
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


def parse_junit_xml(report_file, assertion_gate=True):
    """Parse pytest JUnit XML and return gate decision.

    assertion_gate=True (default): zero-collected and all-skipped runs FAIL.
    assertion_gate=False: relaxes the assertion requirement — zero-collected
    and all-skipped runs PASS (execution completed); actual failures and
    errors still FAIL. This is the only allowlisted relaxation of
    targeted_tests behaviour (manifest gate_overrides).

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

    # Real failures/errors fail regardless of assertion_gate.
    if failed > 0 or error > 0:
        return {
            "collected": collected, "passed": passed, "failed": failed,
            "error": error, "skipped": skipped,
            "gate_status": "fail",
            "gate_reason": "tests failed or errors",
        }

    if collected == 0:
        if assertion_gate:
            return {
                "collected": collected, "passed": passed, "failed": failed,
                "error": error, "skipped": skipped,
                "gate_status": "fail",
                "gate_reason": "zero tests collected",
            }
        return {
            "collected": collected, "passed": passed, "failed": failed,
            "error": error, "skipped": skipped,
            "gate_status": "pass",
            "gate_reason": "assertion_gate disabled: zero tests collected",
        }

    if passed == 0 and skipped > 0:
        if assertion_gate:
            return {
                "collected": collected, "passed": passed, "failed": failed,
                "error": error, "skipped": skipped,
                "gate_status": "fail",
                "gate_reason": "all tests skipped, zero passed",
            }
        return {
            "collected": collected, "passed": passed, "failed": failed,
            "error": error, "skipped": skipped,
            "gate_status": "pass",
            "gate_reason": "assertion_gate disabled: all tests skipped",
        }

    return {
        "collected": collected, "passed": passed, "failed": failed,
        "error": error, "skipped": skipped,
        "gate_status": "pass",
        "gate_reason": "assertions executed",
    }


def validate_manifest(manifest_path):
    """Validate story manifest JSON.

    Delegates to manifest_loader.py (canonical schema v1.0).
    Returns ('OK', story_id) or ('ERROR', error_string).
    """
    import manifest_loader
    return manifest_loader.validate_manifest(manifest_path)


def load_gate_config(manifest_path):
    """Extract gate config from canonical schema v1.0 manifest.

    Adapter function: assumes manifest has passed validation.
    Translates required_gates + gate_overrides into verify-story.sh format.
    """
    try:
        with open(manifest_path) as f:
            m = json.load(f)
    except Exception:
        return {}

    gates = {}
    for g in m.get("required_gates", []):
        gates[g] = {"required": True, "enabled": True}

    # Apply allowlisted overrides only
    overrides = m.get("gate_overrides", {})
    for gate_id, override_config in overrides.items():
        if gate_id in gates:
            # Allowlisted overrides per SCHEMA.md
            if "scope_to_diff" in override_config and gate_id in ("lint", "secrets"):
                gates[gate_id]["scope_to_diff"] = override_config["scope_to_diff"]
            if "assertion_gate" in override_config and gate_id == "targeted_tests":
                gates[gate_id]["assertion_gate"] = override_config["assertion_gate"]
    return gates


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


# ============================================================================
# gitwildmatch — native gitignore-style pattern matching
# ============================================================================

def _translate_wildcard_segment(seg: str) -> str:
    """Translate one pattern segment (no '/') into a regex fragment.

    Handles '*', '?' and '[...]' character classes; everything else literal.
    """
    out = []
    i = 0
    n = len(seg)
    while i < n:
        c = seg[i]
        if c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        elif c == "[":
            # Find matching close bracket (a ']' right after '[' or '[!' is literal)
            j = i + 1
            if j < n and seg[j] in "!^":
                j += 1
            if j < n and seg[j] == "]":
                j += 1
            while j < n and seg[j] != "]":
                j += 1
            if j >= n:
                # Unterminated class: treat '[' as literal
                out.append(re.escape(c))
                i += 1
            else:
                cls = seg[i + 1:j]
                if cls.startswith("!"):
                    cls = "^" + cls[1:]
                # Escape backslashes inside class, keep ranges intact
                out.append("[" + cls + "]")
                i = j + 1
        else:
            out.append(re.escape(c))
            i += 1
    return "".join(out)


def _translate_pattern(pattern: str):
    """Translate one gitwildmatch pattern into a compiled regex.

    Returns (compiled_regex, dir_only_flag) or raises ValueError on negation
    patterns, which are not supported by the scope gate.

    Semantics implemented (gitignore rules, applied to repo-relative FILE
    paths as produced by the candidate-diff enumeration):

      - a pattern containing '/' (other than trailing) is anchored to root;
      - otherwise it may match the basename at any directory depth;
      - leading '/' anchors to the root;
      - trailing '/' marks a directory pattern: it matches file paths located
        below that directory (never the bare directory name itself, which
        cannot appear in a file diff anyway);
      - '*' matches anything except '/', '?' one char, '[...]' a class;
      - trailing 'a/**' matches everything below 'a';
      - 'a/**/b' matches 'a/b' plus any intermediate directories;
      - leading '**/x' matches 'x' at any depth.
    """
    if not isinstance(pattern, str) or pattern == "":
        raise ValueError("empty pattern")
    if pattern.startswith("!"):
        raise ValueError(f"negation patterns are not supported: {pattern}")

    p = pattern
    dir_only = p.endswith("/")
    if dir_only:
        p = p[:-1]
    if not p:
        raise ValueError(f"pattern reduces to empty: {pattern}")

    anchored = p.startswith("/")
    if anchored:
        p = p.lstrip("/")
        if not p:
            raise ValueError(f"pattern reduces to empty: {pattern}")
    elif "/" in p:
        # Contains an interior slash → anchored to the root
        anchored = True

    segments = p.split("/")
    if any(seg == "" for seg in segments):
        raise ValueError(f"empty segment in pattern: {pattern}")

    n = len(segments)
    body = ""
    i = 0
    while i < n:
        seg = segments[i]
        if seg == "**":
            if n == 1:
                # Bare '**' matches everything
                body += ".*"
            elif i == n - 1:
                # Trailing '**': everything below the previous segment
                body += "/.+"
            elif i == 0:
                # Leading '**/': zero or more directories before the rest
                body += "(?:[^/]+/)*"
                i += 1
                continue
            else:
                # Middle '**/': slash plus zero or more directories
                body += "/(?:[^/]+/)*"
                i += 1
                continue
        else:
            body += _translate_wildcard_segment(seg)

        # Separator between ordinary segments (not before a '**', which
        # carries its own separator handling).
        if i < n - 1 and segments[i + 1] != "**":
            body += "/"
        i += 1

    prefix = "" if anchored else "(?:[^/]+/)*"

    if dir_only:
        # Directory pattern: matches file paths below the directory.
        full = prefix + body + "/.*"
    else:
        full = prefix + body

    return re.compile("^" + full + "$"), dir_only


def gitwildmatch(path: str, pattern: str) -> bool:
    """Return True if repo-relative path matches the gitwildmatch pattern."""
    compiled, _ = _translate_pattern(pattern)
    return compiled.match(path) is not None


def match_any_pattern(path: str, patterns) -> str:
    """Return the first pattern from the list that matches path, or ''."""
    for pat in patterns:
        try:
            if gitwildmatch(path, pat):
                return pat
        except ValueError:
            # Invalid pattern cannot match; validation of pattern syntax is
            # the manifest loader's concern. Skip defensively.
            continue
    return ""


# ============================================================================
# Candidate diff enumeration
# ============================================================================

def _git(repo_root, args, timeout=30):
    """Run git with -C repo_root, return (exit_code, stdout_bytes)."""
    proc = subprocess.run(
        ["git", "-C", repo_root] + args,
        capture_output=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout


def base_commit_exists(repo_root: str, base_commit: str) -> bool:
    rc, _ = _git(repo_root, ["cat-file", "-t", base_commit])
    return rc == 0


def list_candidate_diff_files(repo_root: str, base_commit: str):
    """Enumerate the candidate change set against the manifest base_commit.

    Candidate diff = committed-or-staged-or-working-tree changes since
    base_commit, plus untracked files (they are part of the candidate change
    set even though they have no base version).

    Returns (status, files):
      ("OK", list_of_repo_relative_paths)
      ("BASE_COMMIT_MISSING", [])
      ("ERROR:<detail>", [])
    """
    if not base_commit_exists(repo_root, base_commit):
        return ("BASE_COMMIT_MISSING", [])

    # name-only with -z: NUL-separated, safe for any path (incl. spaces).
    rc, out = _git(
        repo_root,
        ["diff", "--name-only", "-z", base_commit, "--", "."],
    )
    if rc != 0:
        return ("ERROR:git diff failed", [])
    files = [p for p in out.decode("utf-8", "replace").split("\0") if p]

    rc, out = _git(repo_root, ["ls-files", "--others", "--exclude-standard", "-z", "--", "."])
    if rc != 0:
        return ("ERROR:git ls-files failed", [])
    untracked = [p for p in out.decode("utf-8", "replace").split("\0") if p]

    seen = set()
    result = []
    for p in files + untracked:
        if p not in seen:
            seen.add(p)
            result.append(p)
    return ("OK", result)


# ============================================================================
# Scope gate
# ============================================================================

def scope_check(manifest_path: str, repo_root: str = "."):
    """Manifest-driven scope gate decision.

    Reads allowed_paths / forbidden_paths / base_commit from a validated
    canonical manifest, enumerates the candidate diff, and classifies every
    changed path:

      - FORBIDDEN  — matches any forbidden_paths pattern (forbidden wins);
      - NOT_ALLOWED — matches no allowed_paths pattern.

    Returns dict:
      status: NO_CHANGES | SCOPE_OK | SCOPE_VIOLATIONS | ERROR
      violations: [{"file": ..., "reason": "FORBIDDEN|NOT_ALLOWED",
                    "pattern": <matched pattern or "">}]
      file_count: int
      error: str (only when status == ERROR)
    """
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return {"status": "ERROR", "violations": [], "file_count": 0,
                "error": f"manifest unreadable: {type(e).__name__}"}

    if not isinstance(manifest, dict):
        return {"status": "ERROR", "violations": [], "file_count": 0,
                "error": "manifest root is not an object"}

    allowed = manifest.get("allowed_paths", [])
    forbidden = manifest.get("forbidden_paths", [])
    base_commit = manifest.get("base_commit", "")
    if not isinstance(allowed, list) or not isinstance(forbidden, list):
        return {"status": "ERROR", "violations": [], "file_count": 0,
                "error": "allowed_paths/forbidden_paths must be arrays"}
    if not isinstance(base_commit, str) or not base_commit:
        return {"status": "ERROR", "violations": [], "file_count": 0,
                "error": "base_commit missing"}

    status, files = list_candidate_diff_files(repo_root, base_commit)
    if status == "BASE_COMMIT_MISSING":
        return {"status": "ERROR", "violations": [], "file_count": 0,
                "error": f"base_commit not found in repository: {base_commit}"}
    if status != "OK":
        return {"status": "ERROR", "violations": [], "file_count": 0,
                "error": status}

    if not files:
        return {"status": "NO_CHANGES", "violations": [], "file_count": 0}

    violations = []
    for path in files:
        forbidden_hit = match_any_pattern(path, forbidden)
        if forbidden_hit:
            violations.append({"file": path, "reason": "FORBIDDEN",
                               "pattern": forbidden_hit})
            continue
        allowed_hit = match_any_pattern(path, allowed)
        if not allowed_hit:
            violations.append({"file": path, "reason": "NOT_ALLOWED",
                               "pattern": ""})

    if violations:
        return {"status": "SCOPE_VIOLATIONS", "violations": violations,
                "file_count": len(files)}
    return {"status": "SCOPE_OK", "violations": [], "file_count": len(files)}


if __name__ == "__main__":
    # CLI entry for bash callers
    if len(sys.argv) < 2:
        print("Usage: harness.py <command> [args...]", file=sys.stderr)
        print("Commands: validate, load_gate_config, load_test_args, "
              "parse_junit, scope_check, list_diff_files", file=sys.stderr)
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
        # parse_junit <report_file> [assertion_gate: true|false]
        assertion_gate = True
        if len(sys.argv) > 3:
            assertion_gate = sys.argv[3].strip().lower() != "false"
        result = parse_junit_xml(sys.argv[2], assertion_gate=assertion_gate)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["gate_status"] == "pass" else 1)

    elif cmd == "atomic_write":
        # atomic_write <output_file> <json_string>
        data = json.loads(sys.argv[3])
        atomic_json_write(sys.argv[2], data)
        sys.exit(0)

    elif cmd == "scope_check":
        # scope_check <manifest_path> [repo_root]
        # stdout: JSON verdict. exit 0 = NO_CHANGES|SCOPE_OK,
        # 1 = SCOPE_VIOLATIONS, 2 = ERROR (infrastructure)
        manifest_arg = sys.argv[2]
        repo_root_arg = sys.argv[3] if len(sys.argv) > 3 else "."
        verdict = scope_check(manifest_arg, repo_root_arg)
        print(json.dumps(verdict))
        if verdict["status"] in ("NO_CHANGES", "SCOPE_OK"):
            sys.exit(0)
        elif verdict["status"] == "SCOPE_VIOLATIONS":
            sys.exit(1)
        else:
            sys.exit(2)

    elif cmd == "list_diff_files":
        # list_diff_files <repo_root> <base_commit>
        status, files = list_candidate_diff_files(sys.argv[2], sys.argv[3])
        print(json.dumps({"status": status, "files": files}))
        sys.exit(0 if status == "OK" else 1)

    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)
