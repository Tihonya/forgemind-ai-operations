"""Unit tests for RetryPolicy (WP-REC-03D).

Tests cover:

- retry/total-attempt semantics for max_retries 0, 1 and 3;
- exponential delay computation;
- delay cap enforcement;
- invalid configuration rejection;
- no delay computation after exhaustion (should_retry returns False);
- 1-based attempt numbering;
- edge cases (attempt 1 delay, large attempt cap).
"""

from __future__ import annotations

import pytest

from app.ai.workflow.retry_policy import (
    DEFAULT_BASE_DELAY_SECONDS,
    DEFAULT_MAX_DELAY_SECONDS,
    RetryPolicy,
)


class TestRetrySemantics:
    """Retry count and total-attempt semantics."""

    def test_max_retries_zero_means_single_attempt(self) -> None:
        policy = RetryPolicy(max_retries=0)
        assert policy.total_allowed_attempts == 1

    def test_max_retries_one_means_two_attempts(self) -> None:
        policy = RetryPolicy(max_retries=1)
        assert policy.total_allowed_attempts == 2

    def test_max_retries_three_means_four_attempts(self) -> None:
        policy = RetryPolicy(max_retries=3)
        assert policy.total_allowed_attempts == 4

    def test_should_retry_returns_false_when_exhausted(self) -> None:
        """When attempt_number equals total_allowed_attempts, no retry."""
        policy = RetryPolicy(max_retries=3)
        assert policy.total_allowed_attempts == 4
        # Attempt 4 is the last allowed attempt — no retry after it.
        assert policy.should_retry(4) is False

    def test_should_retry_returns_true_when_retries_remain(self) -> None:
        policy = RetryPolicy(max_retries=3)
        assert policy.should_retry(1) is True
        assert policy.should_retry(2) is True
        assert policy.should_retry(3) is True

    def test_should_retry_false_for_zero_retries(self) -> None:
        """max_retries=0: no retry after the single attempt."""
        policy = RetryPolicy(max_retries=0)
        assert policy.should_retry(1) is False


class TestExponentialDelays:
    """Exponential backoff delay computation."""

    def test_attempt_1_delay_is_base(self) -> None:
        policy = RetryPolicy(max_retries=3)
        assert policy.compute_delay(1) == pytest.approx(1.0)

    def test_attempt_2_delay_is_double(self) -> None:
        policy = RetryPolicy(max_retries=3)
        assert policy.compute_delay(2) == pytest.approx(2.0)

    def test_attempt_3_delay_is_quadruple(self) -> None:
        policy = RetryPolicy(max_retries=3)
        assert policy.compute_delay(3) == pytest.approx(4.0)

    def test_custom_base_delay(self) -> None:
        policy = RetryPolicy(max_retries=3, base_delay_seconds=0.5)
        assert policy.compute_delay(1) == pytest.approx(0.5)
        assert policy.compute_delay(2) == pytest.approx(1.0)
        assert policy.compute_delay(3) == pytest.approx(2.0)


class TestDelayCap:
    """Maximum delay cap enforcement."""

    def test_delay_capped_at_max(self) -> None:
        policy = RetryPolicy(
            max_retries=10,
            base_delay_seconds=1.0,
            max_delay_seconds=4.0,
        )
        # Attempt 1: 1, 2: 2, 3: 4, 4: 8 -> capped at 4
        assert policy.compute_delay(1) == pytest.approx(1.0)
        assert policy.compute_delay(2) == pytest.approx(2.0)
        assert policy.compute_delay(3) == pytest.approx(4.0)
        assert policy.compute_delay(4) == pytest.approx(4.0)
        assert policy.compute_delay(10) == pytest.approx(4.0)

    def test_default_max_delay_is_30(self) -> None:
        policy = RetryPolicy(max_retries=10)
        # 2^5 = 32, which exceeds 30 — should be capped.
        assert policy.compute_delay(6) == pytest.approx(30.0)

    def test_max_delay_equal_to_base(self) -> None:
        """max_delay == base_delay: all delays are base."""
        policy = RetryPolicy(
            max_retries=3,
            base_delay_seconds=5.0,
            max_delay_seconds=5.0,
        )
        assert policy.compute_delay(1) == pytest.approx(5.0)
        assert policy.compute_delay(2) == pytest.approx(5.0)
        assert policy.compute_delay(3) == pytest.approx(5.0)


class TestInvalidConfiguration:
    """Invalid configuration is rejected at construction."""

    def test_negative_max_retries_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_retries must be non-negative"):
            RetryPolicy(max_retries=-1)

    def test_zero_base_delay_rejected(self) -> None:
        with pytest.raises(ValueError, match="base_delay_seconds must be positive"):
            RetryPolicy(max_retries=3, base_delay_seconds=0.0)

    def test_negative_base_delay_rejected(self) -> None:
        with pytest.raises(ValueError, match="base_delay_seconds must be positive"):
            RetryPolicy(max_retries=3, base_delay_seconds=-1.0)

    def test_zero_max_delay_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_delay_seconds must be positive"):
            RetryPolicy(max_retries=3, max_delay_seconds=0.0)

    def test_max_delay_less_than_base_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_delay_seconds .* must be >= base_delay_seconds"):
            RetryPolicy(
                max_retries=3,
                base_delay_seconds=10.0,
                max_delay_seconds=5.0,
            )


class TestNoDelayAfterExhaustion:
    """No delay should be computed when retries are exhausted.

    The policy itself does not prevent compute_delay from being called
    with a large attempt number, but should_retry correctly returns
    False when the budget is exhausted.  The caller (RetryingChatProvider)
    must check should_retry before calling compute_delay.
    """

    def test_should_retry_false_means_no_more_attempts(self) -> None:
        policy = RetryPolicy(max_retries=1)
        # After attempt 2 (the last), no retry.
        assert policy.should_retry(2) is False
        # compute_delay would still work, but the caller must not call it.

    def test_exhausted_policy_does_not_retry(self) -> None:
        """Simulate the exhaustion path: should_retry returns False."""
        policy = RetryPolicy(max_retries=0)
        # max_retries=0: after attempt 1, no retry.
        assert policy.should_retry(1) is False


class TestEdgeCases:
    """Edge cases for attempt numbering and validation."""

    def test_compute_delay_rejects_zero(self) -> None:
        policy = RetryPolicy(max_retries=3)
        with pytest.raises(ValueError, match="failed_attempt_number must be >= 1"):
            policy.compute_delay(0)

    def test_compute_delay_rejects_negative(self) -> None:
        policy = RetryPolicy(max_retries=3)
        with pytest.raises(ValueError, match="failed_attempt_number must be >= 1"):
            policy.compute_delay(-1)

    def test_should_retry_rejects_zero(self) -> None:
        policy = RetryPolicy(max_retries=3)
        with pytest.raises(ValueError, match="failed_attempt_number must be >= 1"):
            policy.should_retry(0)

    def test_should_retry_rejects_negative(self) -> None:
        policy = RetryPolicy(max_retries=3)
        with pytest.raises(ValueError, match="failed_attempt_number must be >= 1"):
            policy.should_retry(-1)

    def test_defaults(self) -> None:
        """Verify default constant values."""
        assert DEFAULT_BASE_DELAY_SECONDS == 1.0
        assert DEFAULT_MAX_DELAY_SECONDS == 30.0

    def test_frozen_dataclass(self) -> None:
        """RetryPolicy is frozen — cannot be mutated."""
        policy = RetryPolicy(max_retries=3)
        with pytest.raises(AttributeError):
            policy.max_retries = 5  # type: ignore[misc]
