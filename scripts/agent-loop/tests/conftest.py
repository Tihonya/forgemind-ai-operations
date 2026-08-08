"""Pytest configuration for agent-loop tests.

Excludes the fixtures/ directory from test collection — those files are
harness fixtures (test_harness_a.py, test_harness_fail.py, etc.) used by
run_harness_scenarios.sh, not pytest test modules. Without this, pytest
collects fixtures/test_harness_fail.py::test_failing_assertion and fails.
"""

import os
from pathlib import Path

collect_ignore: list[str] = []

# Exclude the fixtures/ subdirectory from pytest collection.
_fixtures_dir = Path(__file__).parent / "fixtures"
if _fixtures_dir.is_dir():
    for entry in os.listdir(_fixtures_dir):
        if entry.endswith(".py"):
            collect_ignore.append(str(_fixtures_dir / entry))
