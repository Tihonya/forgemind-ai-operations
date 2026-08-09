"""Chat provider abstraction with typed results.

Defines the abstract ChatProvider interface and the ChatResult data class
returned by every complete() call. The interface is intentionally minimal
so that both the OpenAI-compatible adapter and the deterministic fake
provider can implement it without coupling to a specific SDK.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ChatResult:
    """Typed result of a chat completion request.

    Attributes:
        content: The model's text response. Always a string; may be empty
            if the model returned no textual content (e.g. tool-call only),
            but never None.
        model: The model name that produced the response. Used for
            observability and audit; must match the model the provider was
            configured with.
        finish_reason: Why the model stopped generating. Common values:
            "stop", "length", "tool_calls", "content_filter". Provider-
            specific values are preserved as-is.
        usage: Token usage statistics when the provider supplies them.
            Keys typically include ``prompt_tokens``,
            ``completion_tokens`` and ``total_tokens``. Empty dict when the
            provider does not report usage (e.g. the fake provider).
        metadata: Provider-specific safe metadata. Must never contain API
            keys, authorization headers, or raw provider response objects.
    """

    content: str
    model: str
    finish_reason: str
    usage: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class ChatProvider(ABC):
    """Abstract base class for chat/reasoning providers.

    Implementations must be async and must not perform any network calls
    at construction time. Network calls happen only inside
    :meth:`complete`.
    """

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> ChatResult:
        """Generate a chat completion for the given prompt.

        Args:
            prompt: The user prompt text. Must not be empty.
            schema: Optional JSON Schema dict instructing the model to
                return a structured response. When provided, the provider
                may pass it as ``response_format`` to compatible endpoints.
                The provider does NOT validate the response against the
                schema — that is the responsibility of WP-REC-03C.
            context: Optional metadata propagated from the caller. The
                ``correlation_id`` key, if present, is used for log
                correlation. Other keys are provider-specific.

        Returns:
            A :class:`ChatResult` with the model's response.

        Raises:
            ChatProviderError: A subclass of ChatProviderError
                (TransientChatProviderError, PermanentChatProviderError,
                or ChatProviderConfigurationError) describing the failure.
        """
        ...
