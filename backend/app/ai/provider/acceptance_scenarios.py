"""Guarded acceptance-scenario providers for AT-008 / AT-013 harness (WP-REC-03H).

This module is imported **only** when the environment variable
``FORGEMIND_ACCEPTANCE_SCENARIO`` is set and the application environment
is ``development``.  The import is performed lazily inside
:func:`app.ai.provider.factory.create_chat_provider` so that production
and staging deployments never load this module.

Scenarios
---------

``AT008_INVALID_OUTPUT``
    Returns a ``ChatResult`` whose ``content`` is valid JSON but does
    **not** conform to the recommendation wire schema.  This exercises
    the ``FAILED_VALIDATION`` path through the real vertical wiring.

``AT013_OUTAGE_UNTIL_RETRY``
    Raises :class:`TransientChatProviderError` when
    ``context["dispatch_generation"]`` is ``0`` (initial dispatch),
    simulating a provider outage that exhausts the automatic retry
    wrapper.  When ``dispatch_generation >= 1`` (after an authorised
    user Retry), returns a valid recommendation ``ChatResult``.

``NORMAL_SUCCESS``
    Returns a valid recommendation ``ChatResult`` unconditionally.
    Control scenario for verifying the happy path without the fake
    provider's schema-incompatible output.

Fail-closed guarantees
----------------------

- Unknown scenario names raise
  :class:`ChatProviderConfigurationError`.
- The module is never imported in production or staging.
- No network calls are made.
- No mutable global state is used.
"""

from __future__ import annotations

import json
from typing import Any

from app.ai.provider.chat_provider import ChatProvider, ChatResult
from app.ai.provider.exceptions import (
    ChatProviderConfigurationError,
    TransientChatProviderError,
)
from app.config import Settings
from app.core.logging import get_logger

_logger = get_logger(__name__)

# Recognised scenario names.
_SCENARIO_AT008_INVALID_OUTPUT = "AT008_INVALID_OUTPUT"
_SCENARIO_AT013_OUTAGE_UNTIL_RETRY = "AT013_OUTAGE_UNTIL_RETRY"
_SCENARIO_NORMAL_SUCCESS = "NORMAL_SUCCESS"

_KNOWN_SCENARIOS: frozenset[str] = frozenset({
    _SCENARIO_AT008_INVALID_OUTPUT,
    _SCENARIO_AT013_OUTAGE_UNTIL_RETRY,
    _SCENARIO_NORMAL_SUCCESS,
})


def _build_valid_recommendation(
    run_id: str,
    plan_id: str = "PLAN-2026-W31",
) -> str:
    """Return a JSON string that passes ``validate_structured_output()``.

    The payload conforms to the recommendation wire schema v1.0 defined
    in ``app.schemas.recommendation.RecommendationData``.
    """
    body = {
        "schema_version": "1.0",
        "run_id": run_id,
        "plan_id": plan_id,
        "risks": [
            {
                "risk_id": "RISK-001",
                "summary": "Acceptance scenario risk summary",
                "business_impact": "Acceptance scenario business impact",
                "recommended_actions": [
                    {
                        "action_type": "REVIEW",
                        "title": "Review supply risk",
                        "rationale": "Acceptance test rationale",
                        "requires_approval": False,
                    }
                ],
                "sources": [],
            }
        ],
    }
    return json.dumps(body, sort_keys=True)


class InvalidOutputProvider(ChatProvider):
    """Return valid JSON that does NOT match the recommendation schema.

    The ``content`` is a JSON object with an ``invalid`` key — it parses
    as JSON but fails Pydantic schema validation, exercising the
    ``FAILED_VALIDATION`` transition.
    """

    def __init__(self, *, model: str = "acceptance-at008") -> None:
        self._model = model

    async def complete(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> ChatResult:
        run_id = ""
        if context is not None:
            run_id = str(context.get("run_id", ""))

        _logger.info(
            "acceptance_scenario.at008.invalid_output",
            run_id=run_id,
            scenario=_SCENARIO_AT008_INVALID_OUTPUT,
        )

        content = json.dumps(
            {"invalid": "data", "prompt_hash": "acceptance-at008"},
            sort_keys=True,
        )
        return ChatResult(
            content=content,
            model=self._model,
            finish_reason="stop",
            usage={},
            metadata={"provider": "acceptance-at008", "scenario": _SCENARIO_AT008_INVALID_OUTPUT},
        )


class OutageUntilRetryProvider(ChatProvider):
    """Fail on generation 0, succeed on generation >= 1.

    Reads ``context["dispatch_generation"]`` to determine behaviour:

    - ``0``: raise :class:`TransientChatProviderError` (simulates
      provider outage that exhausts automatic retry).
    - ``>= 1``: return a valid recommendation ``ChatResult`` (simulates
      post-Retry success through the authorised application retry path).
    """

    def __init__(self, *, model: str = "acceptance-at013") -> None:
        self._model = model

    async def complete(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> ChatResult:
        run_id = ""
        dispatch_generation = 0
        if context is not None:
            run_id = str(context.get("run_id", ""))
            dg = context.get("dispatch_generation")
            if dg is not None:
                dispatch_generation = int(dg)

        _logger.info(
            "acceptance_scenario.at013.dispatch",
            run_id=run_id,
            dispatch_generation=dispatch_generation,
            scenario=_SCENARIO_AT013_OUTAGE_UNTIL_RETRY,
        )

        if dispatch_generation == 0:
            raise TransientChatProviderError(
                "Acceptance scenario: simulated provider outage (generation 0)"
            )

        # Generation >= 1: return valid recommendation.
        plan_id = "PLAN-2026-W31"
        content = _build_valid_recommendation(run_id=run_id, plan_id=plan_id)
        return ChatResult(
            content=content,
            model=self._model,
            finish_reason="stop",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            metadata={
                "provider": "acceptance-at013",
                "scenario": _SCENARIO_AT013_OUTAGE_UNTIL_RETRY,
                "dispatch_generation": dispatch_generation,
            },
        )


class ValidOutputProvider(ChatProvider):
    """Return a valid recommendation unconditionally (control scenario)."""

    def __init__(self, *, model: str = "acceptance-normal") -> None:
        self._model = model

    async def complete(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> ChatResult:
        run_id = ""
        if context is not None:
            run_id = str(context.get("run_id", ""))

        _logger.info(
            "acceptance_scenario.normal_success",
            run_id=run_id,
            scenario=_SCENARIO_NORMAL_SUCCESS,
        )

        content = _build_valid_recommendation(run_id=run_id)
        return ChatResult(
            content=content,
            model=self._model,
            finish_reason="stop",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            metadata={
                "provider": "acceptance-normal",
                "scenario": _SCENARIO_NORMAL_SUCCESS,
            },
        )


def get_acceptance_provider(
    scenario_name: str,
    settings: Settings,
) -> ChatProvider:
    """Return the acceptance-scenario provider for *scenario_name*.

    Args:
        scenario_name: One of the recognised scenario constants.
        settings: Application settings (unused currently, reserved for
            future scenario parameterisation).

    Returns:
        A :class:`ChatProvider` implementing the requested scenario.

    Raises:
        ChatProviderConfigurationError: If *scenario_name* is not
            recognised.  This is a fail-closed guard — unknown names
            never fall through to a normal provider.
    """
    if scenario_name not in _KNOWN_SCENARIOS:
        raise ChatProviderConfigurationError(
            f"Unknown acceptance scenario: {scenario_name!r}. "
            f"Known scenarios: {sorted(_KNOWN_SCENARIOS)}"
        )

    if scenario_name == _SCENARIO_AT008_INVALID_OUTPUT:
        return InvalidOutputProvider()

    if scenario_name == _SCENARIO_AT013_OUTAGE_UNTIL_RETRY:
        return OutageUntilRetryProvider()

    # NORMAL_SUCCESS
    return ValidOutputProvider()
