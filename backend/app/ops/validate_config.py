"""Production configuration validation (WP-P7-02, fail-closed).

Release 1 production configuration MUST be validated before any
deployment action. This module implements the repository-owned rules
recorded in docs/planning/phase_7_deployment_contract.md:

- environment must be exactly ``production``;
- the JWT SECRET_KEY must not be the development default;
- database and Redis credentials must be explicitly provided;
- the Redis limiter must be enabled with fail_closed degraded mode
  (shared limiting is a hard requirement of the Phase 7 topology);
- fake chat/embedding providers are prohibited (enforced again here);
- provider configuration must match the accepted Release 1 decisions:
  chat = OpenRouter only (no automatic fallback chain), embedding =
  OpenRouter via the OpenAI-compatible endpoint with the exact pinned
  model and 1536 dimensions;
- the deployment FQDN must be an explicitly supplied value, not a
  localhost placeholder;
- secret values must never be echoed: validation reports only
  set/not-set status.

Design principles:

- Every check is deterministic and pure — no network calls, no side
  effects, no exception messages containing secret values.
- Fail-closed: any parse failure or unknown condition is reported as an
  error, never silently passed.

This module is also exposed as a CLI:

    python -m app.ops.validate_config

which exits 0 when the configuration passes, 1 when any rule fails.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

from app.config import Settings

# ---------------------------------------------------------------------------
# Canonical Release 1 production values (Phase 7 contract, PD-3/PD-3a).
# These exact values are required; anything else fails closed.
# ---------------------------------------------------------------------------

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_EMBEDDING_MODEL = "openai/text-embedding-3-small"
OPENROUTER_EMBEDDING_DIMENSIONS = 1536
OPENROUTER_CHAT_MODEL = "qwen/qwen3.7-flash"

# ISO-3166/ENV is not a dependency; the database URL must be
# postgresql+asyncpg (the driver the app actually uses).
REQUIRED_DATABASE_PREFIX = "postgresql+asyncpg://"


def _has_placeholder(value: str) -> bool:
    """True when the value contains an obvious un-set placeholder."""
    lowered = value.lower()
    return any(
        token in lowered
        for token in (
            "changeme",
            "change_me",
            "<",
            "your-",
            "example.com",
            "localhost",
        )
    )


@dataclass
class ConfigFinding:
    """A single validation result item."""

    severity: Literal["error", "warning"]
    rule: str
    detail: str


@dataclass
class ValidationResult:
    """Aggregate result of a validation run."""

    findings: list[ConfigFinding] = field(default_factory=list)

    @property
    def errors(self) -> list[ConfigFinding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[ConfigFinding]:
        return [f for f in self.findings if f.severity == "warning"]

    @property
    def passed(self) -> bool:
        return not self.errors

    def render(self) -> str:
        """Render a human-readable report without any secret values."""
        lines: list[str] = []
        lines.append("Production configuration validation")
        lines.append(f"  findings: {len(self.findings)} "
                     f"({len(self.errors)} errors, {len(self.warnings)} warnings)")
        for severity in ("error", "warning"):
            items = self.errors if severity == "error" else self.warnings
            for item in items:
                lines.append(f"  [{severity.upper():7s}] {item.rule}: {item.detail}")
        lines.append(
            "VERDICT: PASS"
            if self.passed
            else "VERDICT: FAIL — production configuration is not safe"
        )
        return "\n".join(lines)


def _redacted(url: str) -> str:
    """Return a display-safe version of a URL (scheme/host/path only).

    Not currently referenced by any rule (secrets are never emitted at
    all), but kept as the single sanctioned place to build display-safe
    URL strings if a future warning wants one.
    """
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.hostname}{parts.path}"
    except ValueError:
        return "<invalid-url>"


def _setting_status(name: str) -> str:
    """Return 'set' / 'not set' for a raw environment variable."""
    value = os.environ.get(name, "")
    return "set" if value else "not set"


class ProductionConfigValidator:
    """Validate a Settings instance against Release 1 production rules."""

    def __init__(self, config: Settings) -> None:
        self._cfg = config

    # ------------------------------------------------------------------
    # Rule implementations
    # ------------------------------------------------------------------

    def validate(self) -> ValidationResult:
        """Run all rules and return the aggregate result."""

        result = ValidationResult()

        # 1. Environment.
        if self._cfg.environment != "production":
            result.findings.append(
                ConfigFinding(
                    "error",
                    "environment",
                    "'ENVIRONMENT' must be exactly 'production' "
                    f"(got '{self._cfg.environment}')",
                )
            )

        # 2. SECRET_KEY placeholder guard.
        if "changeme" in self._cfg.secret_key.lower() or len(self._cfg.secret_key) < 32:
            result.findings.append(
                ConfigFinding(
                    "error",
                    "secret_key",
                    "'SECRET_KEY' must be set to a strong value of at least "
                    "32 characters (placeholder or short value rejected)",
                )
            )

        # 3. Database URL must be explicitly provided.
        if (
            not self._cfg.database_url
            or _has_placeholder(self._cfg.database_url)
            or not self._cfg.database_url.startswith(REQUIRED_DATABASE_PREFIX)
        ):
            result.findings.append(
                ConfigFinding(
                    "error",
                    "database",
                    "'DATABASE_URL' must be an explicitly supplied "
                    f"{REQUIRED_DATABASE_PREFIX} URL",
                )
            )

        # 4. Redis URL must be explicitly provided.
        if not self._cfg.redis_url or _has_placeholder(self._cfg.redis_url):
            result.findings.append(
                ConfigFinding(
                    "error",
                    "redis",
                    "'REDIS_URL' must be an explicitly supplied URL",
                )
            )

        # 5. Distributed rate limiting must be enabled and fail-closed.
        if not self._cfg.distributed_rate_limit_enabled:
            result.findings.append(
                ConfigFinding(
                    "error",
                    "rate_limit",
                    "'DISTRIBUTED_RATE_LIMIT_ENABLED' must be true in production",
                )
            )
        if self._cfg.rate_limit_degraded_mode != "fail_closed":
            result.findings.append(
                ConfigFinding(
                    "error",
                    "rate_limit",
                    "'RATE_LIMIT_DEGRADED_MODE' must be 'fail_closed' in production",
                )
            )

        # 6. Fake providers are forbidden.
        if self._cfg.embedding_provider == "fake":
            result.findings.append(
                ConfigFinding(
                    "error",
                    "embedding",
                    "'EMBEDDING_PROVIDER' must not be 'fake' in production",
                )
            )
        if self._cfg.chat_provider_mode == "fake":
            result.findings.append(
                ConfigFinding(
                    "error",
                    "chat",
                    "'CHAT_PROVIDER_MODE' must not be 'fake' in production",
                )
            )

        # 7. Chat provider: OpenRouter only, exact pinned model, no chain.
        if self._cfg.chat_provider_mode != "openrouter":
            result.findings.append(
                ConfigFinding(
                    "error",
                    "chat",
                    "'CHAT_PROVIDER_MODE' must be 'openrouter' in production "
                    "(OpenRouter only, automatic fallback disabled)",
                )
            )
        if self._cfg.openrouter_chat_model != OPENROUTER_CHAT_MODEL:
            result.findings.append(
                ConfigFinding(
                    "error",
                    "chat",
                    f"'OPENROUTER_CHAT_MODEL' must be exactly '{OPENROUTER_CHAT_MODEL}'",
                )
            )
        if self._cfg.openrouter_structured_output_mode != "json_object":
            result.findings.append(
                ConfigFinding(
                    "error",
                    "chat",
                    "'OPENROUTER_STRUCTURED_OUTPUT_MODE' must be 'json_object'",
                )
            )
        if not self._cfg.openrouter_api_key:
            result.findings.append(
                ConfigFinding(
                    "error",
                    "chat",
                    "'OPENROUTER_API_KEY' must be set",
                )
            )

        # 8. Embedding provider: OpenRouter via the canonical base URL,
        # exact model, exact dimensions; the API key is the OpenRouter key.
        if self._cfg.embedding_provider != "openai":
            result.findings.append(
                ConfigFinding(
                    "error",
                    "embedding",
                    "'EMBEDDING_PROVIDER' must be 'openai' in production "
                    "(OpenRouter embedding path per PD-3a)",
                )
            )
        base = self._cfg.openai_api_base
        if base != OPENROUTER_BASE_URL:
            result.findings.append(
                ConfigFinding(
                    "error",
                    "embedding",
                    f"'OPENAI_API_BASE' must be exactly '{OPENROUTER_BASE_URL}'",
                )
            )
        if self._cfg.openai_embedding_model != OPENROUTER_EMBEDDING_MODEL:
            result.findings.append(
                ConfigFinding(
                    "error",
                    "embedding",
                    f"'OPENAI_EMBEDDING_MODEL' must be exactly "
                    f"'{OPENROUTER_EMBEDDING_MODEL}'",
                )
            )
        if self._cfg.embedding_dimensions != OPENROUTER_EMBEDDING_DIMENSIONS:
            result.findings.append(
                ConfigFinding(
                    "error",
                    "embedding",
                    f"'EMBEDDING_DIMENSIONS' must be exactly "
                    f"{OPENROUTER_EMBEDDING_DIMENSIONS}",
                )
            )
        if not self._cfg.openai_api_key:
            result.findings.append(
                ConfigFinding(
                    "error",
                    "embedding",
                    "'OPENAI_API_KEY' must be set (the OpenRouter key, per PD-3a)",
                )
            )

        # 9. Deployment FQDN must be explicitly supplied.
        fqdn = os.environ.get("CADDY_DOMAIN", "")
        if not fqdn or _has_placeholder(fqdn):
            result.findings.append(
                ConfigFinding(
                    "error",
                    "fqdn",
                    "'CADDY_DOMAIN' must be an explicitly supplied production FQDN",
                )
            )

        # 10. TLS email must be explicitly supplied.
        tls_email = os.environ.get("CADDY_EMAIL", "")
        if not tls_email or "@" not in tls_email or _has_placeholder(tls_email):
            result.findings.append(
                ConfigFinding(
                    "error",
                    "fqdn",
                    "'CADDY_EMAIL' must be a real TLS contact email address",
                )
            )

        return result


def main() -> int:
    """CLI entry point: validate and print a secret-free report."""
    from app.config import settings as app_settings

    validator = ProductionConfigValidator(app_settings)
    result = validator.validate()
    print(result.render())
    return 0 if result.passed else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry exercised by tests
    raise SystemExit(main())
