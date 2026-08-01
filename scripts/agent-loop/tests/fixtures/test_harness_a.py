"""Harness Scenario A: required test exists and passes."""


def test_passing_assertion():
    """This test exists and passes."""
    assert 2 + 2 == 4


def test_another_passing():
    """Second passing test."""
    data = {"key": "value"}
    assert "key" in data
    assert data["key"] == "value"
