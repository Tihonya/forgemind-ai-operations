"""Harness test fixture that fails (for scenarios requiring verify FAIL)."""


def test_failing_assertion() -> None:
    """This test intentionally fails."""
    assert False, "Intentional failure for test scenarios"
