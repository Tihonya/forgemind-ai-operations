"""Chat provider exception hierarchy.

Mirrors the embedding provider exception pattern with four exception types:
- ChatProviderError: base exception for all chat provider errors
- TransientChatProviderError: transient error that may succeed on retry
- PermanentChatProviderError: permanent error that will not succeed on retry
- ChatProviderConfigurationError: configuration error at construction time

All exceptions preserve the original exception as __cause__ (raise from).
Error messages must never contain API keys, authorization headers, or raw
provider responses.
"""

from __future__ import annotations


class ChatProviderError(Exception):
    """Base exception for all chat provider errors."""


class TransientChatProviderError(ChatProviderError):
    """Transient error — the operation may succeed on retry.

    Raised for network timeouts, rate limits, 5xx server errors, and
    other recoverable conditions. Workflow-level retry logic (03D) may
    retry this error type.
    """


class PermanentChatProviderError(ChatProviderError):
    """Permanent error — retrying the same request will not help.

    Raised for authentication failures, invalid requests, malformed
    responses, and other non-recoverable conditions. Should not be
    retried.
    """


class ChatProviderConfigurationError(ChatProviderError):
    """Configuration error — provider was misconfigured at construction.

    Raised when required settings are missing or invalid (e.g., empty
    API key for official OpenAI endpoint, invalid timeout value). The
    application should fail fast at startup rather than at first call.
    """
