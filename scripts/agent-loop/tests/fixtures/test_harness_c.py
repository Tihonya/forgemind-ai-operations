"""Harness Scenario C: all tests skipped."""

import pytest


@pytest.mark.skip(reason="Harness scenario C: intentional skip")
def test_skipped_one():
    """This test is skipped."""
    assert True


@pytest.mark.skip(reason="Harness scenario C: intentional skip")
def test_skipped_two():
    """This test is also skipped."""
    assert True
