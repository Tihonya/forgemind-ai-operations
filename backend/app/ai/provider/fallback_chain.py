"""Ordered chat-provider fallback chain (WP-REC-05-PROVIDER-IMP).

Implements a server-configured ordered chain of chat providers
(Groq free → OpenRouter paid). A client cannot choose or reorder
providers — the order is fixed by the factory from ``CHAT_PROVIDER_CHAIN``.

Fallback semantics (bounded, fail-closed):

- Each chain member is an independently retried provider (e.g. a
  :class:`~app.ai.workflow.outage_handler.RetryingChatProvider` wrapping a
  concrete adapter). The chain performs **no** retry of its own.
- The chain advances to the next member **only** when the current member's
  transient retry budget is exhausted — i.e. it raises
  :class:`TransientChatProviderError`.
- Permanent errors (:class:`PermanentChatProviderError`),
  configuration errors (:class:`ChatProviderConfigurationError`), and any
  other exception propagate immediately — the chain never falls back on them.
- OpenRouter HTTP 402 (budget/credit exhaustion) is classified by the adapter
  as a permanent error and therefore never retried or routed around. The
  application does **not** enforce the external budget; that is an external
  OpenRouter account/key control.
- Schema-invalid and citation-invalid responses never reach the chain: they
  are produced as successful ``ChatResult`` objects and are rejected
  downstream by the authoritative server-side validators (WP-REC-03C / §G).
- Total provider calls are bounded by
  ``provider_count × attempts_per_provider``.

Safe observability: on success the chain adds bounded, deterministic metadata
(chain position, final provider name, provider count, and a summarized
attempt history of exhausted providers). It never records prompts, response
content, API keys, or raw provider bodies.
"""

from __future__ import annotations

from typing import Any

from app.ai.provider.chat_provider import ChatProvider, ChatResult
from app.ai.provider.exceptions import (
    ChatProviderConfigurationError,
    TransientChatProviderError,
)
from app.core.logging import get_logger

_logger = get_logger(__name__)

# Chain-controlled metadata keys added to ``ChatResult.metadata`` on success.
_META_CHAIN_POSITION = "chain_position"
_META_CHAIN_PROVIDER = "chain_provider"
_META_CHAIN_PROVIDER_COUNT = "chain_provider_count"
_META_CHAIN_ATTEMPT_HISTORY = "chain_attempt_history"

# Safe fields recorded per exhausted provider in the chain attempt history.
_SAFE_CHAIN_ATTEMPT_FIELDS: frozenset[str] = frozenset({
    "chain_position",
    "provider",
    "outcome",
    "error_type",
})


class FallbackChatProvider(ChatProvider):
    """Ordered fallback chain of chat providers.

    Args:
        providers: Ordered list of ``(provider_name, provider)`` pairs. Each
            provider is expected to already own its bounded retry policy
            (e.g. wrapped in ``RetryingChatProvider``). The chain itself does
            not retry.

    Raises:
        ChatProviderConfigurationError: If the chain is empty.
    """

    def __init__(self, providers: list[tuple[str, ChatProvider]]) -> None:
        if not providers:
            raise ChatProviderConfigurationError(
                "Fallback chain must contain at least one provider"
            )
        self._providers: list[tuple[str, ChatProvider]] = list(providers)

    @property
    def provider_count(self) -> int:
        """Number of providers in the chain."""
        return len(self._providers)

    async def complete(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> ChatResult:
        """Generate a completion, advancing providers on transient exhaustion.

        Args:
            prompt: The user prompt text. Passed unchanged to each member.
            schema: Optional JSON Schema dict. Passed unchanged.
            context: Optional metadata dict. Passed unchanged.

        Returns:
            The first successful member's :class:`ChatResult`, enriched with
            chain metadata.

        Raises:
            TransientChatProviderError: After every provider's transient
                retry budget is exhausted (terminal ``FAILED_PROVIDER``).
            PermanentChatProviderError: Immediately, without falling back.
            ChatProviderConfigurationError: Immediately, without falling back.
            asyncio.CancelledError: Immediately, without falling back.
        """
        chain_attempt_history: list[dict[str, Any]] = []

        for position, (name, provider) in enumerate(self._providers):
            try:
                result = await provider.complete(
                    prompt=prompt,
                    schema=schema,
                    context=context,
                )
            except TransientChatProviderError as exc:
                # This provider's bounded retry budget is exhausted. Record a
                # safe attempt and advance to the next provider.
                chain_attempt_history.append(
                    self._safe_chain_attempt_record(
                        position=position,
                        provider=name,
                        outcome="exhausted",
                        error_type=type(exc).__name__,
                    )
                )
                self._log_advance(
                    position=position,
                    provider=name,
                    error_type=type(exc).__name__,
                )
                continue

            # Success — enrich and return. Any other exception (permanent,
            # configuration, cancellation, unknown) propagates immediately and
            # is NOT caught here, so the chain never falls back on it.
            return self._enrich_result(
                result=result,
                position=position,
                provider=name,
                chain_attempt_history=chain_attempt_history,
            )

        # Every provider exhausted its transient retry budget. Terminal.
        raise TransientChatProviderError(
            "All providers in the fallback chain exhausted their retry budgets"
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_chain_attempt_record(
        *,
        position: int,
        provider: str,
        outcome: str,
        error_type: str,
    ) -> dict[str, Any]:
        """Build a safe, bounded per-provider attempt record.

        Never contains exception messages, prompts, response content, or
        context values.
        """
        return {
            "chain_position": position,
            "provider": provider,
            "outcome": outcome,
            "error_type": error_type,
        }

    @staticmethod
    def _log_advance(
        *,
        position: int,
        provider: str,
        error_type: str,
    ) -> None:
        """Log a safe chain-advance event."""
        _logger.warning(
            "chat_provider.chain.advanced",
            chain_position=position,
            provider=provider,
            error_type=error_type,
        )

    def _enrich_result(
        self,
        *,
        result: ChatResult,
        position: int,
        provider: str,
        chain_attempt_history: list[dict[str, Any]],
    ) -> ChatResult:
        """Add chain metadata to a successful ChatResult.

        Creates a new ``ChatResult`` with the member's data plus chain
        metadata. The member's original metadata is preserved (not mutated).
        Chain-controlled keys take precedence over any same-named keys the
        member supplied.
        """
        enriched_metadata: dict[str, Any] = dict(result.metadata)
        enriched_metadata[_META_CHAIN_POSITION] = position
        enriched_metadata[_META_CHAIN_PROVIDER] = provider
        enriched_metadata[_META_CHAIN_PROVIDER_COUNT] = len(self._providers)
        enriched_metadata[_META_CHAIN_ATTEMPT_HISTORY] = chain_attempt_history

        return ChatResult(
            content=result.content,
            model=result.model,
            finish_reason=result.finish_reason,
            usage=result.usage,
            metadata=enriched_metadata,
        )
