"""Deterministic bounded exponential backoff retry policy (WP-REC-03D).

This module provides :class:`RetryPolicy`, a pure configuration and
calculation dataclass that computes backoff delays for transient
provider failures. It performs no I/O and has no side effects.

Design contract (WP-REC-03D):

- **Pure calculation**: no sleeping, no logging, no network, no
  database access. The :class:`RetryingChatProvider` in
  ``outage_handler.py`` owns the execution loop and calls this policy
  for delay computation.
- **Deterministic**: no jitter. Tests require deterministic timing.
  The per-instance rate limiter in ``OpenAIChatProvider`` provides
  natural desynchronisation in production.
- **Bounded**: maximum delay caps exponential growth.
- **Injectable sleeper**: the policy accepts a ``sleeper`` callable so
  that :class:`RetryingChatProvider` can sleep without real waiting in
  tests. The policy itself does not sleep.
- **No new dependency**: uses only standard-library math.

``llm_max_retries`` semantics:

``llm_max_retries`` is the number of retries **after** the initial
attempt.  Total provider calls = ``1 + max_retries``.

| max_retries | Initial attempt | Retries | Total calls | Possible delays |
|------------:|----------------:|--------:|------------:|-----------------|
| 0           | 1               | 0       | 1           | none            |
| 1           | 1               | 1       | 2           | 1 second        |
| 3 (default) | 1               | 3       | 4           | 1, 2, 4 seconds |

For failed 1-based attempt *n*, before the next attempt:

    delay = min(base_delay * 2 ** (n - 1), max_delay)

Examples:

- failure of attempt 1 → 1 second (2 ** 0 = 1);
- failure of attempt 2 → 2 seconds (2 ** 1 = 2);
- failure of attempt 3 → 4 seconds (2 ** 2 = 4).

Never sleep after the final allowed attempt.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

# Default base delay in seconds for the first retry.
DEFAULT_BASE_DELAY_SECONDS: float = 1.0

# Maximum delay cap in seconds.  Aligns with ``llm_timeout_seconds``
# default (30 s) to prevent a single retry's backoff from exceeding the
# provider call's own timeout.
DEFAULT_MAX_DELAY_SECONDS: float = 30.0

# Type alias for an async sleeper callable.  The default is
# ``asyncio.sleep``, injected by ``RetryingChatProvider``.
AsyncSleeper = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class RetryPolicy:
    """Pure configuration for bounded exponential backoff retry.

    This dataclass holds retry parameters and computes delays.  It does
    not perform any I/O.  The :class:`RetryingChatProvider` owns the
    execution loop.

    Args:
        max_retries: Number of retries after the initial attempt.
            ``0`` means a single attempt with no retry.  Total
            provider calls = ``1 + max_retries``.
        base_delay_seconds: Base delay for the first retry.  The
            delay for the *n*-th retry (1-based) is
            ``base_delay * 2 ** (n - 1)``, capped at
            ``max_delay_seconds``.
        max_delay_seconds: Maximum delay cap.  Prevents unbounded
            exponential growth.
    """

    max_retries: int
    base_delay_seconds: float = DEFAULT_BASE_DELAY_SECONDS
    max_delay_seconds: float = DEFAULT_MAX_DELAY_SECONDS

    def __post_init__(self) -> None:
        """Validate configuration at construction time.

        Raises:
            ValueError: If any parameter is invalid.
        """
        if self.max_retries < 0:
            raise ValueError(
                f"max_retries must be non-negative, got {self.max_retries}"
            )
        if self.base_delay_seconds <= 0:
            raise ValueError(
                f"base_delay_seconds must be positive, "
                f"got {self.base_delay_seconds}"
            )
        if self.max_delay_seconds <= 0:
            raise ValueError(
                f"max_delay_seconds must be positive, "
                f"got {self.max_delay_seconds}"
            )
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError(
                f"max_delay_seconds ({self.max_delay_seconds}) must be "
                f">= base_delay_seconds ({self.base_delay_seconds})"
            )

    @property
    def total_allowed_attempts(self) -> int:
        """Total provider calls including the initial attempt.

        Returns ``1 + max_retries``.
        """
        return 1 + self.max_retries

    def compute_delay(self, failed_attempt_number: int) -> float:
        """Compute the backoff delay after a failed attempt.

        For the 1-based ``failed_attempt_number`` (e.g. ``1`` for the
        first failed attempt), the delay before the next retry is::

            min(base_delay * 2 ** (failed_attempt_number - 1), max_delay)

        This method must only be called when a retry will actually be
        performed — i.e. when ``failed_attempt_number < total_allowed_attempts``.
        Call :meth:`should_retry` first to determine whether a retry
        is allowed.

        Args:
            failed_attempt_number: 1-based number of the attempt that
                just failed.  Must be >= 1.

        Returns:
            The delay in seconds.

        Raises:
            ValueError: If ``failed_attempt_number`` is < 1.
        """
        if failed_attempt_number < 1:
            raise ValueError(
                f"failed_attempt_number must be >= 1, "
                f"got {failed_attempt_number}"
            )
        raw: float = self.base_delay_seconds * (2 ** (failed_attempt_number - 1))
        return float(min(raw, self.max_delay_seconds))

    def should_retry(
        self,
        failed_attempt_number: int,
    ) -> bool:
        """Determine whether a retry should be attempted.

        A retry is allowed only if the number of attempts so far
        (``failed_attempt_number``) has not yet reached
        ``total_allowed_attempts``.

        Args:
            failed_attempt_number: 1-based number of the attempt that
                just failed.  Must be >= 1.

        Returns:
            ``True`` if a retry should be performed, ``False`` if the
            retry budget is exhausted.

        Raises:
            ValueError: If ``failed_attempt_number`` is < 1.
        """
        if failed_attempt_number < 1:
            raise ValueError(
                f"failed_attempt_number must be >= 1, "
                f"got {failed_attempt_number}"
            )
        return failed_attempt_number < self.total_allowed_attempts
