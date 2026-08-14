"""Unit tests for capability-aware structured output modes (WP-REC-05 §6, §9.C).

Verifies the exact request payload for each mode, that unsupported modes fail
safely, that a provider 400 never silently downgrades the mode, and that
server-side Pydantic validation remains authoritative regardless of mode.

All tests use a mock OpenAI client — no network, no credentials.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ai.provider.exceptions import (
    ChatProviderConfigurationError,
    PermanentChatProviderError,
)
from app.ai.provider.openai_chat_provider import OpenAIChatProvider
from app.ai.workflow.schema_validator import validate_structured_output
from app.schemas.recommendation import RecommendationData


def _mock_response() -> Any:
    mock_message = MagicMock()
    mock_message.content = "{}"
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_choice.finish_reason = "stop"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.id = "resp-1"
    mock_response.usage = None
    return mock_response


def _schema() -> dict[str, Any]:
    return {"type": "object", "properties": {"x": {"type": "string"}}}


def _response_format_of(mock_client: AsyncMock) -> Any:
    """Return the ``response_format`` kwarg from the last mocked API call."""
    create = mock_client.chat.completions.create
    return create.call_args.kwargs.get("response_format")


class TestJsonSchemaMode:
    @pytest.mark.asyncio
    async def test_json_schema_request_payload(self) -> None:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_mock_response()
        )
        provider = OpenAIChatProvider(
            api_key="test-key",
            client=mock_client,
            structured_output_mode="json_schema",
        )
        schema = _schema()
        await provider.complete("p", schema=schema)

        assert _response_format_of(mock_client) == {
            "type": "json_schema",
            "json_schema": {
                "name": "structured_output",
                "schema": schema,
                "strict": True,
            },
        }

    @pytest.mark.asyncio
    async def test_json_schema_without_schema_omits_response_format(self) -> None:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_mock_response()
        )
        provider = OpenAIChatProvider(
            api_key="test-key",
            client=mock_client,
            structured_output_mode="json_schema",
        )
        await provider.complete("p", schema=None)
        assert _response_format_of(mock_client) is None


class TestJsonObjectMode:
    @pytest.mark.asyncio
    async def test_json_object_request_payload(self) -> None:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_mock_response()
        )
        provider = OpenAIChatProvider(
            api_key="test-key",
            client=mock_client,
            structured_output_mode="json_object",
        )
        await provider.complete("p", schema=_schema())
        assert _response_format_of(mock_client) == {"type": "json_object"}


class TestPromptJsonMode:
    @pytest.mark.asyncio
    async def test_prompt_json_sends_no_response_format(self) -> None:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_mock_response()
        )
        provider = OpenAIChatProvider(
            api_key="test-key",
            client=mock_client,
            structured_output_mode="prompt_json",
        )
        await provider.complete("p", schema=_schema())
        assert _response_format_of(mock_client) is None

    @pytest.mark.asyncio
    async def test_prompt_json_is_explicit_not_hidden(self) -> None:
        """prompt_json is an explicit mode, not a downgrade from another mode."""
        provider = OpenAIChatProvider(
            api_key="test-key",
            client=AsyncMock(),
            structured_output_mode="prompt_json",
        )
        assert provider._structured_output_mode == "prompt_json"


class TestUnsupportedMode:
    def test_unsupported_mode_fails_safely(self) -> None:
        with pytest.raises(
            ChatProviderConfigurationError, match="Unsupported structured output"
        ):
            OpenAIChatProvider(
                api_key="test-key",
                structured_output_mode="bogus",
            )


class TestNoAutomaticDowngrade:
    @pytest.mark.asyncio
    async def test_400_does_not_downgrade_mode(self) -> None:
        """A provider 400 (BadRequestError) must not silently change the mode."""
        from openai import BadRequestError

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.headers = {}
        mock_response.request = MagicMock()
        original = BadRequestError(
            message="bad request", response=mock_response, body=None
        )
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=original)
        provider = OpenAIChatProvider(
            api_key="test-key",
            client=mock_client,
            structured_output_mode="json_schema",
        )
        with pytest.raises(PermanentChatProviderError):
            await provider.complete("p", schema=_schema())
        # Mode unchanged after the provider error.
        assert provider._structured_output_mode == "json_schema"


class TestServerValidationRemainsAuthoritative:
    def test_pydantic_validation_independent_of_mode(self) -> None:
        """Server-side Pydantic validation is unaffected by the request mode."""
        from uuid import uuid4

        valid_content = (
            '{"schema_version": "1.0", "run_id": "'
            + str(uuid4())
            + '", "plan_id": "PLAN-1", "risks": [{"risk_id": "RISK-001", '
            '"summary": "s", "business_impact": "b", '
            '"recommended_actions": [], "sources": []}]}'
        )
        # Validation is a pure function of the content — mode-agnostic.
        recommendation = validate_structured_output(valid_content)
        assert isinstance(recommendation, RecommendationData)
        assert recommendation.schema_version == "1.0"


class TestModeObservability:
    @pytest.mark.asyncio
    async def test_mode_and_provider_in_metadata(self) -> None:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_mock_response()
        )
        provider = OpenAIChatProvider(
            api_key="test-key",
            client=mock_client,
            provider_name="groq",
            structured_output_mode="json_object",
        )
        result = await provider.complete("p", schema=_schema())
        assert result.metadata["provider"] == "groq"
        assert result.metadata["structured_output_mode"] == "json_object"
