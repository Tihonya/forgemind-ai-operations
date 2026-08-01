#!/usr/bin/env python3
"""
Harness validation script for agent-loop verify-story.sh.

Tests scenarios A-E with synthetic fixtures:
A. Required test exists and passes → PASS, VERIFIED
B. Required test missing → FAIL, NOT_VERIFIED, exit!=0
C. All tests skipped → FAIL, passed=0, skipped>0
D. Real test passed → PASS, passed>0
E. Internal harness error → ERROR, error object present

Usage:
    python3 run_harness_tests.py
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from datetime import datetime


# Configuration
SCRIPT_DIR = Path(__file__).parent.parent
REPO_ROOT = SCRIPT_DIR.parent.parent
VERIFY_SCRIPT = SCRIPT_DIR / "verify-story.sh"
PYTHON_BIN = REPO_ROOT.parent / "VScode/AIAutomation/.venv/bin/python"


def create_temp_manifest(story_id: str, test_command: str = None, gate_config: dict = None):
    """Create a temporary manifest file."""
    manifest = {
        "story_id": story_id,
        "title": f"Test Story {story_id}",
        "description": "Synthetic test for harness validation",
        "branch": "test/harness-validation",
        "gates": gate_config or {
            "scope": {"required": True, "enabled": True},
            "json_syntax": {"required": True, "enabled": True},
            "targeted_tests": {"required": True, "enabled": True, "assertion_gate": True},
            "lint": {"required": True, "enabled": True, "scope_to_diff": True},
            "secrets": {"required": True, "enabled": True, "scope_to_diff": True},
            "git_diff_check": {"required": False, "enabled": True}
        },
        "test_commands": {
            "targeted_args": test_command or "",
            "related_unit_args": ""
        }
    }
    
    fd, path = tempfile.mkstemp(suffix=".json")
    with open(path, 'w') as f:
        json.dump(manifest, f, indent=2)
    return path


def create_synthetic_test_file(test_name: str, content: str):
    """Create a synthetic test file in a temporary location."""
    backend_dir = REPO_ROOT / "backend"
    test_dir = backend_dir / "tests" / "synthetic"
    test_dir.mkdir(parents=True, exist_ok=True)
    
    test_file = test_dir / test_name
    test_file.write_text(content)
    return test_file


def run_verify(manifest_path: str):
    """Run verify-story.sh and capture results."""
    env = os.environ.copy()
    env["DRY_RUN"] = "false"
    
    result = subprocess.run(
        ["bash", str(VERIFY_SCRIPT), manifest_path],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT
    )
    
    return result


def load_verify_result(run_dir: Path):
    """Load verify-result.json from run directory."""
    verify_file = run_dir / "reports" / "verify-result.json"
    if not verify_file.exists():
        return None
    
    with open(verify_file) as f:
        return json.load(f)


def load_final_report(run_dir: Path):
    """Load final-report.json from run directory."""
    report_file = run_dir / "reports" / "final-report.json"
    if not report_file.exists():
        return None
    
    with open(report_file) as f:
        return json.load(f)


def extract_run_dir(stdout: str):
    """Extract run directory from verify-story.sh output."""
    for line in stdout.split('\n'):
        if "Run directory:" in line:
            return Path(line.split("Run directory:")[-1].strip())
    return None


def test_scenario_A():
    """Scenario A: Required test exists and passes."""
    print("\n=== Scenario A: Required test exists and passes ===")
    
    # Create a passing test
    test_content = """
def test_passing():
    assert True
"""
    test_file = create_synthetic_test_file("test_passing.py", test_content)
    
    # Create manifest with required targeted_tests
    manifest = create_temp_manifest(
        "SCENARIO_A",
        "tests/synthetic/test_passing.py -v --junitxml={report_file}"
    )
    
    # Run verification
    result = run_verify(manifest)
    run_dir = extract_run_dir(result.stdout)
    
    if not run_dir:
        print("FAIL: Could not extract run directory")
        return False
    
    # Load results
    verify_result = load_verify_result(run_dir)
    final_report = load_final_report(run_dir)
    
    if not verify_result or not final_report:
        print("FAIL: Could not load verification or final report")
        return False
    
    # Validate
    success = True
    print(f"Exit code: {result.returncode} (expected: 0)")
    if result.returncode != 0:
        print("FAIL: Exit code should be 0")
        success = False
    
    print(f"Overall status: {verify_result['overall_status']} (expected: PASS)")
    if verify_result['overall_status'] != 'PASS':
        print("FAIL: Overall status should be PASS")
        success = False
    
    print(f"Final status: {final_report['final_status']} (expected: VERIFIED)")
    if final_report['final_status'] != 'VERIFIED':
        print("FAIL: Final status should be VERIFIED")
        success = False
    
    # Check targeted_tests gate
    targeted_gate = next((g for g in verify_result['gates'] if g['name'] == 'targeted_tests'), None)
    if targeted_gate:
        print(f"Targeted tests gate: {targeted_gate['status']} (expected: PASS)")
        if targeted_gate['status'] != 'PASS':
            print("FAIL: Targeted tests gate should be PASS")
            success = False
    
    # Cleanup
    test_file.unlink()
    Path(manifest).unlink()
    
    return success


def test_scenario_B():
    """Scenario B: Required test missing."""
    print("\n=== Scenario B: Required test missing ===")
    
    # Create manifest pointing to non-existent test
    manifest = create_temp_manifest(
        "SCENARIO_B",
        "tests/synthetic/test_nonexistent.py -v --junitxml={report_file}"
    )
    
    # Run verification
    result = run_verify(manifest)
    run_dir = extract_run_dir(result.stdout)
    
    if not run_dir:
        print("FAIL: Could not extract run directory")
        return False
    
    # Load results
    verify_result = load_verify_result(run_dir)
    final_report = load_final_report(run_dir)
    
    if not verify_result or not final_report:
        print("FAIL: Could not load verification or final report")
        return False
    
    # Validate
    success = True
    print(f"Exit code: {result.returncode} (expected: non-zero)")
    if result.returncode == 0:
        print("FAIL: Exit code should be non-zero")
        success = False
    
    print(f"Overall status: {verify_result['overall_status']} (expected: FAIL)")
    if verify_result['overall_status'] != 'FAIL':
        print("FAIL: Overall status should be FAIL")
        success = False
    
    print(f"Final status: {final_report['final_status']} (expected: VERIFICATION_FAILED or NOT_VERIFIED)")
    if final_report['final_status'] not in ['VERIFICATION_FAILED', 'NOT_VERIFIED']:
        print("FAIL: Final status should be VERIFICATION_FAILED or NOT_VERIFIED")
        success = False
    
    # Check targeted_tests gate
    targeted_gate = next((g for g in verify_result['gates'] if g['name'] == 'targeted_tests'), None)
    if targeted_gate:
        print(f"Targeted tests gate: {targeted_gate['status']} (expected: FAIL)")
        if targeted_gate['status'] != 'FAIL':
            print("FAIL: Targeted tests gate should be FAIL")
            success = False
    
    # Cleanup
    Path(manifest).unlink()
    
    return success


def test_scenario_C():
    """Scenario C: All tests skipped."""
    print("\n=== Scenario C: All tests skipped ===")
    
    # Create a test that's all skipped
    test_content = """
import pytest

@pytest.mark.skip(reason="Test skip scenario")
def test_skipped():
    assert True
"""
    test_file = create_synthetic_test_file("test_all_skipped.py", test_content)
    
    # Create manifest
    manifest = create_temp_manifest(
        "SCENARIO_C",
        "tests/synthetic/test_all_skipped.py -v --junitxml={report_file}"
    )
    
    # Run verification
    result = run_verify(manifest)
    run_dir = extract_run_dir(result.stdout)
    
    if not run_dir:
        print("FAIL: Could not extract run directory")
        return False
    
    # Load results
    verify_result = load_verify_result(run_dir)
    
    if not verify_result:
        print("FAIL: Could not load verification report")
        return False
    
    # Validate
    success = True
    print(f"Exit code: {result.returncode} (expected: non-zero)")
    if result.returncode == 0:
        print("FAIL: Exit code should be non-zero")
        success = False
    
    print(f"Overall status: {verify_result['overall_status']} (expected: FAIL)")
    if verify_result['overall_status'] != 'FAIL':
        print("FAIL: Overall status should be FAIL")
        success = False
    
    # Check pytest report for passed=0, skipped>0
    pytest_report = run_dir / "verify" / "pytest-report.xml"
    if pytest_report.exists():
        import xml.etree.ElementTree as ET
        tree = ET.parse(pytest_report)
        root = tree.getroot()
        
        passed = 0
        skipped = 0
        for ts in root.findall('.//testsuite'):
            passed += int(ts.get('tests', 0)) - int(ts.get('failures', 0)) - int(ts.get('errors', 0)) - int(ts.get('skipped', 0))
            skipped += int(ts.get('skipped', 0))
        
        print(f"Pytest passed: {passed} (expected: 0)")
        print(f"Pytest skipped: {skipped} (expected: >0)")
        
        if passed != 0:
            print("FAIL: Passed should be 0")
            success = False
        if skipped <= 0:
            print("FAIL: Skipped should be >0")
            success = False
    
    # Cleanup
    test_file.unlink()
    Path(manifest).unlink()
    
    return success


def test_scenario_D():
    """Scenario D: Real test passed."""
    print("\n=== Scenario D: Real test passed ===")
    
    # Create a real passing test with assertions
    test_content = """
def test_real_passing():
    result = 2 + 2
    assert result == 4, f"Expected 4, got {result}"
    
def test_another_passing():
    data = {"key": "value"}
    assert "key" in data
    assert data["key"] == "value"
"""
    test_file = create_synthetic_test_file("test_real_passing.py", test_content)
    
    # Create manifest
    manifest = create_temp_manifest(
        "SCENARIO_D",
        "tests/synthetic/test_real_passing.py -v --junitxml={report_file}"
    )
    
    # Run verification
    result = run_verify(manifest)
    run_dir = extract_run_dir(result.stdout)
    
    if not run_dir:
        print("FAIL: Could not extract run directory")
        return False
    
    # Load results
    verify_result = load_verify_result(run_dir)
    
    if not verify_result:
        print("FAIL: Could not load verification report")
        return False
    
    # Validate
    success = True
    print(f"Exit code: {result.returncode} (expected: 0)")
    if result.returncode != 0:
        print("FAIL: Exit code should be 0")
        success = False
    
    print(f"Overall status: {verify_result['overall_status']} (expected: PASS)")
    if verify_result['overall_status'] != 'PASS':
        print("FAIL: Overall status should be PASS")
        success = False
    
    # Check pytest report for passed>0
    pytest_report = run_dir / "verify" / "pytest-report.xml"
    if pytest_report.exists():
        import xml.etree.ElementTree as ET
        tree = ET.parse(pytest_report)
        root = tree.getroot()
        
        passed = 0
        for ts in root.findall('.//testsuite'):
            passed += int(ts.get('tests', 0)) - int(ts.get('failures', 0)) - int(ts.get('errors', 0)) - int(ts.get('skipped', 0))
        
        print(f"Pytest passed: {passed} (expected: >0)")
        
        if passed <= 0:
            print("FAIL: Passed should be >0")
            success = False
    
    # Cleanup
    test_file.unlink()
    Path(manifest).unlink()
    
    return success


def test_scenario_E():
    """Scenario E: Internal harness error."""
    print("\n=== Scenario E: Internal harness error ===")
    
    # Create a manifest with invalid JSON to trigger parse error
    fd, manifest = tempfile.mkstemp(suffix=".json")
    with open(manifest, 'w') as f:
        f.write("{invalid json")
    
    # Run verification
    result = run_verify(manifest)
    run_dir = extract_run_dir(result.stdout)
    
    if not run_dir:
        print("FAIL: Could not extract run directory")
        return False
    
    # Load results
    verify_result = load_verify_result(run_dir)
    
    if not verify_result:
        print("FAIL: Could not load verification report")
        return False
    
    # Validate
    success = True
    print(f"Exit code: {result.returncode} (expected: 2 for ERROR)")
    if result.returncode != 2:
        print(f"FAIL: Exit code should be 2, got {result.returncode}")
        success = False
    
    print(f"Overall status: {verify_result['overall_status']} (expected: ERROR)")
    if verify_result['overall_status'] != 'ERROR':
        print("FAIL: Overall status should be ERROR")
        success = False
    
    # Check for error object
    if 'error' not in verify_result:
        print("FAIL: Error object should be present")
        success = False
    else:
        print(f"Error object present: {verify_result['error']}")
    
    # Cleanup
    Path(manifest).unlink()
    
    return success


def main():
    """Run all harness validation scenarios."""
    print("=" * 70)
    print("HARNESS VALIDATION - Agent Loop Phase 1")
    print("=" * 70)
    
    scenarios = [
        ("A", test_scenario_A, "Required test exists and passes"),
        ("B", test_scenario_B, "Required test missing"),
        ("C", test_scenario_C, "All tests skipped"),
        ("D", test_scenario_D, "Real test passed"),
        ("E", test_scenario_E, "Internal harness error"),
    ]
    
    results = []
    
    for scenario_id, test_func, description in scenarios:
        print(f"\n{'='*70}")
        print(f"Scenario {scenario_id}: {description}")
        print(f"{'='*70}")
        
        try:
            success = test_func()
            results.append((scenario_id, description, success))
        except Exception as e:
            print(f"EXCEPTION: {e}")
            results.append((scenario_id, description, False))
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    for scenario_id, description, success in results:
        status = "PASS" if success else "FAIL"
        print(f"Scenario {scenario_id}: {status} - {description}")
    
    passed = sum(1 for _, _, success in results if success)
    total = len(results)
    
    print(f"\nTotal: {passed}/{total} scenarios passed")
    
    if passed == total:
        print("\nALL SCENARIOS PASSED")
        return 0
    else:
        print("\nSOME SCENARIOS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
