#!/usr/bin/env python3
"""
Harness validation script for agent-loop verify-story.sh (WP-AL-1B2B).

Isolation design: every scenario runs inside its own disposable temporary
Git repository (tests/lib/temp_repo_fixture.py). The real infrastructure
worktree is never mutated — no stash, no registered worktrees, no synthetic
files in the real backend tree.

final-report contract: run-story.sh (the documented pipeline) invokes
report-story.sh after verify-story.sh to produce final-report.json. These
tests therefore run report-story.sh inside the isolated repo after
verify-story.sh and assert final-report.json, matching the documented
harness contract rather than asserting an artifact verify-story.sh alone
never creates.

Scenarios:
A. Required test exists and passes -> PASS, VERIFIED, exit 0
B. Required test missing           -> FAIL, VERIFICATION_FAILED, exit != 0
C. All tests skipped               -> FAIL (assertion gate), exit != 0
D. Real tests pass                 -> PASS, exit 0, passed > 0
E. Internal harness error          -> ERROR, error object present, exit 2

Usage:
    python3 run_harness_tests.py
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Configuration
SCRIPT_DIR = Path(__file__).parent.parent
REPO_ROOT = SCRIPT_DIR.parent.parent
FIXTURE_LIB = Path(__file__).parent / "lib"

sys.path.insert(0, str(FIXTURE_LIB))
import temp_repo_fixture  # noqa: E402


def _resolve_python_bin() -> str:
    """Resolve Python binary path without machine-specific hardcoded paths."""
    # Honour pre-set binary (isolated environments)
    preset = os.environ.get("PYTHON_BIN")
    if preset and os.access(preset, os.X_OK):
        return preset

    # Try to find .venv from git common dir
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        common_dir = Path(result.stdout.strip())
        if not common_dir.is_absolute():
            common_dir = REPO_ROOT / common_dir
        main_repo = common_dir.parent
        venv_python = main_repo / ".venv" / "bin" / "python"
        if venv_python.exists() and os.access(venv_python, os.X_OK):
            return str(venv_python)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Fall back to python3 in PATH
    python3_path = shutil.which("python3")
    if python3_path:
        return python3_path
    raise RuntimeError("Python not found. Ensure python3 is in PATH or .venv exists")


PYTHON_BIN = _resolve_python_bin()

# Tool binaries for isolated repos (detected once from the host environment)
PYTEST_BIN = os.environ.get("PYTEST_BIN") or shutil.which("pytest") or ""
RUFF_BIN = os.environ.get("RUFF_BIN") or shutil.which("ruff") or ""
MYPY_BIN = os.environ.get("MYPY_BIN") or shutil.which("mypy") or ""

# Shared isolated roots for config.sh requirements
_ISOLATED_AGENTLAB = Path("/tmp/agent-loop-harness-python-agentlab")
_ISOLATED_MAIN = Path("/tmp/agent-loop-harness-python-main")

_TEMP_REPOS: list[Path] = []


def _create_isolated_repo(scenario: str) -> tuple[Path, str]:
    repo = temp_repo_fixture.create_temp_repo(REPO_ROOT, scenario)
    _TEMP_REPOS.append(repo)
    base = temp_repo_fixture.base_sha(repo)
    _ISOLATED_AGENTLAB.mkdir(parents=True, exist_ok=True)
    _ISOLATED_MAIN.mkdir(parents=True, exist_ok=True)
    return repo, base


def _cleanup_temp_repos() -> None:
    for repo in _TEMP_REPOS:
        try:
            temp_repo_fixture.remove_temp_repo(repo)
        except Exception as e:  # noqa: BLE001 - visibility over silence
            print(f"CLEANUP_WARNING: {repo}: {e}")


def _isolated_env() -> dict:
    env = os.environ.copy()
    env["DRY_RUN"] = "false"
    env["PYTHON_BIN"] = PYTHON_BIN
    env["PYTEST_BIN"] = PYTEST_BIN
    env["RUFF_BIN"] = RUFF_BIN
    env["MYPY_BIN"] = MYPY_BIN
    env["AGENTLAB_ROOT"] = str(_ISOLATED_AGENTLAB)
    env["FORGEMIND_MAIN_ROOT"] = str(_ISOLATED_MAIN)
    return env


def create_isolated_manifest(
    repo: Path,
    base_sha: str,
    story_id: str,
    targeted_args: list,
) -> Path:
    """Create a canonical schema v1.0 manifest inside the isolated repo."""
    manifest = temp_repo_fixture.canonical_manifest(
        story_id=story_id,
        targeted_args=targeted_args,
        allowed_paths=["backend/**"],
        forbidden_paths=[".env"],
        base_commit=base_sha,
        expected_branch="harness-test",
        gate_overrides={
            "targeted_tests": {"assertion_gate": True},
            "lint": {"scope_to_diff": True},
            "secrets": {"scope_to_diff": True},
        },
    )
    return temp_repo_fixture.write_manifest(repo, manifest)


def run_verify(repo: Path, manifest_path: Path):
    """Run the isolated repo's own verify-story.sh."""
    result = subprocess.run(
        ["bash", str(repo / "scripts" / "agent-loop" / "verify-story.sh"),
         str(manifest_path)],
        capture_output=True,
        text=True,
        env=_isolated_env(),
        cwd=repo,
    )
    return result


def run_report(repo: Path, run_dir: Path):
    """Run the isolated repo's own report-story.sh (final-report contract)."""
    result = subprocess.run(
        ["bash", str(repo / "scripts" / "agent-loop" / "report-story.sh"),
         str(run_dir)],
        capture_output=True,
        text=True,
        env=_isolated_env(),
        cwd=repo,
    )
    return result


def extract_run_dir(stdout: str):
    """Extract run directory from verify-story.sh output."""
    for line in stdout.split("\n"):
        if "Run directory:" in line:
            return Path(line.split("Run directory:")[-1].strip())
    return None


def load_verify_result(run_dir: Path):
    verify_file = run_dir / "reports" / "verify-result.json"
    if not verify_file.exists():
        return None
    with open(verify_file) as f:
        return json.load(f)


def load_final_report(run_dir: Path):
    report_file = run_dir / "reports" / "final-report.json"
    if not report_file.exists():
        return None
    with open(report_file) as f:
        return json.load(f)


def _add_synthetic_test(repo: Path, rel_path: str, content: str) -> None:
    temp_repo_fixture.add_candidate_file(repo, rel_path, content)


def test_scenario_A():
    """Scenario A: Required test exists and passes."""
    print("\n=== Scenario A: Required test exists and passes ===")

    repo, base = _create_isolated_repo("PYA")
    _add_synthetic_test(
        repo,
        "backend/tests/synthetic/test_passing.py",
        "\ndef test_passing():\n    assert True\n",
    )
    manifest = create_isolated_manifest(
        repo, base, "SCENARIO_A",
        ["tests/synthetic/test_passing.py", "-v", "--junitxml={report_file}"],
    )

    result = run_verify(repo, manifest)
    run_dir = extract_run_dir(result.stdout)
    if not run_dir:
        print("FAIL: Could not extract run directory")
        return False

    verify_result = load_verify_result(run_dir)
    if not verify_result:
        print("FAIL: Could not load verification report")
        return False

    # final-report contract: run report-story.sh like run-story.sh does
    report_result = run_report(repo, run_dir)
    final_report = load_final_report(run_dir)
    if report_result.returncode != 0 or not final_report:
        print("FAIL: report-story.sh did not produce final-report.json")
        return False

    success = True
    print(f"Exit code: {result.returncode} (expected: 0)")
    if result.returncode != 0:
        print("FAIL: Exit code should be 0")
        success = False

    print(f"Overall status: {verify_result['overall_status']} (expected: PASS)")
    if verify_result["overall_status"] != "PASS":
        print("FAIL: Overall status should be PASS")
        success = False

    print(f"Final status: {final_report['final_status']} (expected: VERIFIED)")
    if final_report["final_status"] != "VERIFIED":
        print("FAIL: Final status should be VERIFIED")
        success = False

    targeted_gate = next(
        (g for g in verify_result["gates"] if g["name"] == "targeted_tests"), None
    )
    if targeted_gate:
        print(f"Targeted tests gate: {targeted_gate['status']} (expected: PASS)")
        if targeted_gate["status"] != "PASS":
            print("FAIL: Targeted tests gate should be PASS")
            success = False

    return success


def test_scenario_B():
    """Scenario B: Required test missing."""
    print("\n=== Scenario B: Required test missing ===")

    repo, base = _create_isolated_repo("PYB")
    manifest = create_isolated_manifest(
        repo, base, "SCENARIO_B",
        ["tests/synthetic/test_nonexistent.py", "-v", "--junitxml={report_file}"],
    )

    result = run_verify(repo, manifest)
    run_dir = extract_run_dir(result.stdout)
    if not run_dir:
        print("FAIL: Could not extract run directory")
        return False

    verify_result = load_verify_result(run_dir)
    if not verify_result:
        print("FAIL: Could not load verification report")
        return False

    run_report(repo, run_dir)
    final_report = load_final_report(run_dir)
    if not final_report:
        print("FAIL: Could not load final report")
        return False

    success = True
    print(f"Exit code: {result.returncode} (expected: non-zero)")
    if result.returncode == 0:
        print("FAIL: Exit code should be non-zero")
        success = False

    print(f"Overall status: {verify_result['overall_status']} (expected: FAIL)")
    if verify_result["overall_status"] != "FAIL":
        print("FAIL: Overall status should be FAIL")
        success = False

    print(
        f"Final status: {final_report['final_status']} "
        "(expected: VERIFICATION_FAILED or NOT_VERIFIED)"
    )
    if final_report["final_status"] not in ["VERIFICATION_FAILED", "NOT_VERIFIED"]:
        print("FAIL: Final status should be VERIFICATION_FAILED or NOT_VERIFIED")
        success = False

    targeted_gate = next(
        (g for g in verify_result["gates"] if g["name"] == "targeted_tests"), None
    )
    if targeted_gate:
        print(f"Targeted tests gate: {targeted_gate['status']} (expected: FAIL)")
        if targeted_gate["status"] != "FAIL":
            print("FAIL: Targeted tests gate should be FAIL")
            success = False

    return success


def test_scenario_C():
    """Scenario C: All tests skipped (assertion gate must FAIL)."""
    print("\n=== Scenario C: All tests skipped ===")

    repo, base = _create_isolated_repo("PYC")
    _add_synthetic_test(
        repo,
        "backend/tests/synthetic/test_all_skipped.py",
        "\nimport pytest\n\n\n"
        '@pytest.mark.skip(reason="Test skip scenario")\n'
        "def test_skipped():\n    assert True\n",
    )
    manifest = create_isolated_manifest(
        repo, base, "SCENARIO_C",
        ["tests/synthetic/test_all_skipped.py", "-v", "--junitxml={report_file}"],
    )

    result = run_verify(repo, manifest)
    run_dir = extract_run_dir(result.stdout)
    if not run_dir:
        print("FAIL: Could not extract run directory")
        return False

    verify_result = load_verify_result(run_dir)
    if not verify_result:
        print("FAIL: Could not load verification report")
        return False

    success = True
    print(f"Exit code: {result.returncode} (expected: non-zero)")
    if result.returncode == 0:
        print("FAIL: Exit code should be non-zero")
        success = False

    print(f"Overall status: {verify_result['overall_status']} (expected: FAIL)")
    if verify_result["overall_status"] != "FAIL":
        print("FAIL: Overall status should be FAIL")
        success = False

    pytest_report = run_dir / "verify" / "pytest-report.xml"
    if pytest_report.exists():
        import xml.etree.ElementTree as ET

        tree = ET.parse(pytest_report)
        root = tree.getroot()

        passed = 0
        skipped = 0
        for ts in root.findall(".//testsuite"):
            passed += (
                int(ts.get("tests", 0))
                - int(ts.get("failures", 0))
                - int(ts.get("errors", 0))
                - int(ts.get("skipped", 0))
            )
            skipped += int(ts.get("skipped", 0))

        print(f"Pytest passed: {passed} (expected: 0)")
        print(f"Pytest skipped: {skipped} (expected: >0)")

        if passed != 0:
            print("FAIL: Passed should be 0")
            success = False
        if skipped <= 0:
            print("FAIL: Skipped should be >0")
            success = False

    return success


def test_scenario_D():
    """Scenario D: Real tests pass with meaningful assertions."""
    print("\n=== Scenario D: Real test passed ===")

    repo, base = _create_isolated_repo("PYD")
    _add_synthetic_test(
        repo,
        "backend/tests/synthetic/test_real_passing.py",
        "\ndef test_real_passing():\n"
        "    result = 2 + 2\n"
        '    assert result == 4, f"Expected 4, got {result}"\n'
        "\n\n"
        "def test_another_passing():\n"
        '    data = {"key": "value"}\n'
        '    assert "key" in data\n'
        '    assert data["key"] == "value"\n',
    )
    manifest = create_isolated_manifest(
        repo, base, "SCENARIO_D",
        ["tests/synthetic/test_real_passing.py", "-v", "--junitxml={report_file}"],
    )

    result = run_verify(repo, manifest)
    run_dir = extract_run_dir(result.stdout)
    if not run_dir:
        print("FAIL: Could not extract run directory")
        return False

    verify_result = load_verify_result(run_dir)
    if not verify_result:
        print("FAIL: Could not load verification report")
        return False

    success = True
    print(f"Exit code: {result.returncode} (expected: 0)")
    if result.returncode != 0:
        print("FAIL: Exit code should be 0")
        success = False

    print(f"Overall status: {verify_result['overall_status']} (expected: PASS)")
    if verify_result["overall_status"] != "PASS":
        print("FAIL: Overall status should be PASS")
        success = False

    pytest_report = run_dir / "verify" / "pytest-report.xml"
    if pytest_report.exists():
        import xml.etree.ElementTree as ET

        tree = ET.parse(pytest_report)
        root = tree.getroot()

        passed = 0
        for ts in root.findall(".//testsuite"):
            passed += (
                int(ts.get("tests", 0))
                - int(ts.get("failures", 0))
                - int(ts.get("errors", 0))
                - int(ts.get("skipped", 0))
            )

        print(f"Pytest passed: {passed} (expected: >0)")
        if passed <= 0:
            print("FAIL: Passed should be >0")
            success = False

    return success


def test_scenario_E():
    """Scenario E: Internal harness error (broken manifest JSON)."""
    print("\n=== Scenario E: Internal harness error ===")

    repo, _base = _create_isolated_repo("PYE")
    broken_manifest = repo / "broken-manifest.json"
    broken_manifest.write_text("{invalid json")

    result = run_verify(repo, broken_manifest)
    run_dir = extract_run_dir(result.stdout)
    if not run_dir:
        print("FAIL: Could not extract run directory")
        return False

    verify_result = load_verify_result(run_dir)
    if not verify_result:
        print("FAIL: Could not load verification report")
        return False

    success = True
    print(f"Exit code: {result.returncode} (expected: 2 for ERROR)")
    if result.returncode != 2:
        print(f"FAIL: Exit code should be 2, got {result.returncode}")
        success = False

    print(f"Overall status: {verify_result['overall_status']} (expected: ERROR)")
    if verify_result["overall_status"] != "ERROR":
        print("FAIL: Overall status should be ERROR")
        success = False

    if "error" not in verify_result:
        print("FAIL: Error object should be present")
        success = False
    else:
        print(f"Error object present: {verify_result['error']}")

    return success


def main() -> int:
    print("=" * 70)
    print("HARNESS VALIDATION - Agent Loop Phase 1 (isolated repos)")
    print("=" * 70)

    scenarios = [
        ("A", test_scenario_A, "Required test exists and passes"),
        ("B", test_scenario_B, "Required test missing"),
        ("C", test_scenario_C, "All tests skipped"),
        ("D", test_scenario_D, "Real test passed"),
        ("E", test_scenario_E, "Internal harness error"),
    ]

    results = {}
    try:
        for name, fn, description in scenarios:
            print(f"\n--- Running scenario {name}: {description} ---")
            try:
                results[name] = fn()
            except Exception as e:  # noqa: BLE001 - capture, do not abort suite
                print(f"FAIL: Scenario {name} raised: {type(e).__name__}: {e}")
                results[name] = False
    finally:
        _cleanup_temp_repos()

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    all_pass = True
    for name, fn, description in scenarios:
        status = "PASS" if results.get(name) else "FAIL"
        print(f"Scenario {name} ({description}): {status}")
        if not results.get(name):
            all_pass = False

    if all_pass:
        print("\nALL PYTHON HARNESS TESTS PASSED")
        return 0
    print("\nSOME PYTHON HARNESS TESTS FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
