"""Production configuration validation (WP-P7-02, fail-closed).

Release 1 production configuration MUST be validated before any
deployment action. This module implements the repository-owned rules
recorded in docs/planning/phase_7_deployment_contract.md:

- environment must be exactly ``production``;
- the JWT SECRET_KEY must not be a development default or a template
  placeholder;
- database and Redis credentials must be explicitly provided and must
  use the documented URL-safe credential alphabet;
- the Redis limiter must be enabled with fail_closed degraded mode
  (shared limiting is a hard requirement of the Phase 7 topology);
- fake chat/embedding providers are prohibited (enforced again here);
- provider configuration must match the accepted Release 1 decisions:
  chat = OpenRouter only (no automatic fallback chain), embedding =
  OpenRouter via the OpenAI-compatible endpoint with the exact pinned
  model and 1536 dimensions;
- both provider keys must be explicitly supplied (no implicit reuse);
- the deployment FQDN and TLS contact email must be explicitly
  supplied values, not template placeholders;
- secret values must never be echoed: validation reports only
  set/not-set status and rule names.

Placeholder policy (WP-P7-02 remediation F-2): one coherent
case-insensitive vocabulary shared by every rule. Any value matching
the repository's own template conventions —
``REPLACE_WITH_*`` / ``replace-with-*`` / ``REPLACE_*`` prefixes,
``changeme`` / ``change_me``, ``your-`` attribution tokens,
``example.com``-class FQDNs, or ``localhost`` — is rejected by every
production-critical rule that checks it.

The repository template (infra/prod.env.example) uses the SAME
vocabulary; tests load the template's literal values, so the validator
and the template cannot drift silently.

Design principles:

- Every check is deterministic and pure — no network calls, no side
  effects, no exception messages containing secret values.
- Fail-closed: any parse failure or unknown condition is reported as an
  error, never silently passed.
- Findings carry rule names and human orientation text only; rejected
  values are never interpolated into findings or reports.

This module is also exposed as a CLI:

    python -m app.ops.validate_config

which exits 0 when the configuration passes, 1 when any rule fails.
"""

from __future__ import annotations

import re
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

# ---------------------------------------------------------------------------
# Template-placeholder policy (remediation F-2).
#
# Single source of truth for "this value looks like an un-set template
# placeholder". Kept in line with the literal placeholder vocabulary of
# infra/prod.env.example and schema-adjacent templates; the unit tests
# feed the template's own literal values through these matchers so
# validator/template drift fails the suite.
# ---------------------------------------------------------------------------

# Matches the repository's REPLACE-family convention at a value
# boundary: REPLACE_WITH_x, replace-with-x, replace_x, replace/… —
# case-insensitive (remediation F-2 requires covering the repository's
# own convention including case variants). ``:``/``@`` in the boundary
# class covers credential positions inside URLs
# (``…:REPLACE_WITH_…``, ``…@REPLACE…``).
_REPLACE_PLACEHOLDER_RE = re.compile(
    r"(?:^|[._\-\s/=:@])replace(?:[-_][a-z0-9_]|_with|$)",
    re.IGNORECASE,
)

# Example-domain placeholders (example.com / .net / .org / .test /
# .invalid) — a real production FQDN naming something like
# "demo.example-ops.net" is NOT matched (no literal "example." domain).
_EXAMPLE_DOMAIN_RE = re.compile(r"example\.(?:com|net|org|test|invalid)", re.IGNORECASE)

# Older placeholder tokens retained as defense-in-depth.
_LEGACY_PLACEHOLDER_TOKENS = (
    "changeme",
    "change_me",
    "your-",
    "localhost",
    "<",
)

# Restricted credential alphabet for values embedded inside URLs
# (remediation F-8, Option B): unreserved URL characters only. The
# template documents this alphabet; the validator enforces it; Compose
# interpolates credentials verbatim — all three agree. Percent-encoded
# credentials are NOT supported for Release 1 (kept simple and
# deterministic).
URL_SAFE_CREDENTIAL_RE = re.compile(r"^[A-Za-z0-9._~-]+$")


def _has_placeholder(value: str) -> bool:
    """True when the value is missing or looks like an un-set placeholder."""
    if not value:
        return True
    if _REPLACE_PLACEHOLDER_RE.search(value):
        return True
    if _EXAMPLE_DOMAIN_RE.search(value):
        return True
    lowered = value.lower()
    return any(token in lowered for token in _LEGACY_PLACEHOLDER_TOKENS)


def _credential_alphabet_finding(url: str, rule: str) -> ConfigFinding | None:
    """Return a finding when the URL's userinfo password uses unsafe chars.

    Release 1 credential policy (F-8, Option B): passwords embedded in
    DATABASE_URL / REDIS_URL must consist solely of unreserved URL
    characters (``A-Z a-z 0-9 . _ ~ -``). Values containing
    ``@``, ``:``, ``/``, ``#``, ``%``, spaces, or any other reserved
    character would silently corrupt the URL when Compose interpolates
    them, so they are rejected here with a finding that never echoes
    the offending value.

    The password is parsed from the RAW address: everything after the
    scheme up to the LAST ``@`` (the host delimiter), then the portion
    after the first ``:`` inside that userinfo. Using the last ``@``
    (not the first) makes passwords that themselves contain ``@``,
    ``/``, ``#``, or ``%`` visible to the check instead of silently
    truncating the parse — exactly the corruption case the policy is
    meant to reject.
    """
    raw = url.split("://", 1)[1] if "://" in url else url
    last_at = raw.rfind("@")
    if last_at == -1:
        return None
    userinfo = raw[:last_at]
    if ":" not in userinfo:
        return None
    password = userinfo.split(":", 1)[1]
    if not password:
        return None
    if URL_SAFE_CREDENTIAL_RE.match(password):
        return None
    return _finding(
        "error",
        rule,
        "'%s' password contains characters outside the URL-safe set; "
        "use only A-Z a-z 0-9 . _ ~ - (see docs/infra-production.md "
        "password policy)" % ("<DATABASE_URL>" if rule == "database" else "<REDIS_URL>"),
    )


def _finding(
    severity: Literal["error", "warning"], rule: str, detail: str
) -> ConfigFinding:
    return ConfigFinding(severity, rule, detail)


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
                _finding(
                    "error",
                    "environment",
                    "'ENVIRONMENT' must be exactly 'production' "
                    f"(got '{self._cfg.environment}')",
                )
            )

        # 2. SECRET_KEY guard: not a template placeholder, not the
        # development default, and at least 32 characters.
        if (
            _has_placeholder(self._cfg.secret_key)
            or "change" in self._cfg.secret_key.lower()
            or len(self._cfg.secret_key) < 32
        ):
            result.findings.append(
                _finding(
                    "error",
                    "secret_key",
                    "'SECRET_KEY' must be set to a strong value of at least "
                    "32 characters (placeholder or short value rejected)",
                )
            )

        # 3. Database URL must be explicitly provided with the required
        # driver prefix, no template placeholders, and credentials that
        # respect the URL-safe alphabet.
        if (
            not self._cfg.database_url
            or _has_placeholder(self._cfg.database_url)
            or not self._cfg.database_url.startswith(REQUIRED_DATABASE_PREFIX)
        ):
            result.findings.append(
                _finding(
                    "error",
                    "database",
                    "'DATABASE_URL' must be an explicitly supplied "
                    f"{REQUIRED_DATABASE_PREFIX} URL (template placeholders rejected)",
                )
            )
        else:
            cred_finding = _credential_alphabet_finding(
                self._cfg.database_url, "database"
            )
            if cred_finding is not None:
                result.findings.append(cred_finding)

        # 4. Redis URL must be explicitly provided with credentials
        # that respect the URL-safe alphabet.
        if not self._cfg.redis_url or _has_placeholder(self._cfg.redis_url):
            result.findings.append(
                _finding(
                    "error",
                    "redis",
                    "'REDIS_URL' must be an explicitly supplied URL "
                    "(template placeholders rejected)",
                )
            )
        else:
            cred_finding = _credential_alphabet_finding(self._cfg.redis_url, "redis")
            if cred_finding is not None:
                result.findings.append(cred_finding)

        # 5. Distributed rate limiting must be enabled and fail-closed.
        if not self._cfg.distributed_rate_limit_enabled:
            result.findings.append(
                _finding(
                    "error",
                    "rate_limit",
                    "'DISTRIBUTED_RATE_LIMIT_ENABLED' must be true in production",
                )
            )
        if self._cfg.rate_limit_degraded_mode != "fail_closed":
            result.findings.append(
                _finding(
                    "error",
                    "rate_limit",
                    "'RATE_LIMIT_DEGRADED_MODE' must be 'fail_closed' in production",
                )
            )

        # 6. Fake providers are forbidden.
        if self._cfg.embedding_provider == "fake":
            result.findings.append(
                _finding(
                    "error",
                    "embedding",
                    "'EMBEDDING_PROVIDER' must not be 'fake' in production",
                )
            )
        if self._cfg.chat_provider_mode == "fake":
            result.findings.append(
                _finding(
                    "error",
                    "chat",
                    "'CHAT_PROVIDER_MODE' must not be 'fake' in production",
                )
            )

        # 7. Chat provider: OpenRouter only, exact pinned model, no chain.
        if self._cfg.chat_provider_mode != "openrouter":
            result.findings.append(
                _finding(
                    "error",
                    "chat",
                    "'CHAT_PROVIDER_MODE' must be 'openrouter' in production "
                    "(OpenRouter only, automatic fallback disabled)",
                )
            )
        if self._cfg.openrouter_chat_model != OPENROUTER_CHAT_MODEL:
            result.findings.append(
                _finding(
                    "error",
                    "chat",
                    f"'OPENROUTER_CHAT_MODEL' must be exactly '{OPENROUTER_CHAT_MODEL}'",
                )
            )
        if self._cfg.openrouter_structured_output_mode != "json_object":
            result.findings.append(
                _finding(
                    "error",
                    "chat",
                    "'OPENROUTER_STRUCTURED_OUTPUT_MODE' must be 'json_object'",
                )
            )
        # No implicit key reuse (F-6B): the key must be explicitly
        # supplied and must not be a template placeholder.
        if not self._cfg.openrouter_api_key:
            result.findings.append(
                _finding(
                    "error",
                    "chat",
                    "'OPENROUTER_API_KEY' must be set",
                )
            )
        elif _has_placeholder(self._cfg.openrouter_api_key):
            result.findings.append(
                _finding(
                    "error",
                    "chat",
                    "'OPENROUTER_API_KEY' must be a real key "
                    "(template placeholders rejected)",
                )
            )

        # 8. Embedding provider: OpenRouter via the canonical base URL,
        # exact model, exact dimensions; the API key is the OpenRouter key.
        if self._cfg.embedding_provider != "openai":
            result.findings.append(
                _finding(
                    "error",
                    "embedding",
                    "'EMBEDDING_PROVIDER' must be 'openai' in production "
                    "(OpenRouter embedding path per PD-3a)",
                )
            )
        base = self._cfg.openai_api_base
        if base != OPENROUTER_BASE_URL:
            result.findings.append(
                _finding(
                    "error",
                    "embedding",
                    f"'OPENAI_API_BASE' must be exactly '{OPENROUTER_BASE_URL}'",
                )
            )
        if self._cfg.openai_embedding_model != OPENROUTER_EMBEDDING_MODEL:
            result.findings.append(
                _finding(
                    "error",
                    "embedding",
                    f"'OPENAI_EMBEDDING_MODEL' must be exactly "
                    f"'{OPENROUTER_EMBEDDING_MODEL}'",
                )
            )
        if self._cfg.embedding_dimensions != OPENROUTER_EMBEDDING_DIMENSIONS:
            result.findings.append(
                _finding(
                    "error",
                    "embedding",
                    f"'EMBEDDING_DIMENSIONS' must be exactly "
                    f"{OPENROUTER_EMBEDDING_DIMENSIONS}",
                )
            )
        if not self._cfg.openai_api_key:
            result.findings.append(
                _finding(
                    "error",
                    "embedding",
                    "'OPENAI_API_KEY' must be set (the OpenRouter key, per PD-3a)",
                )
            )
        elif _has_placeholder(self._cfg.openai_api_key):
            result.findings.append(
                _finding(
                    "error",
                    "embedding",
                    "'OPENAI_API_KEY' must be a real key "
                    "(template placeholders rejected)",
                )
            )

        # 9. Deployment FQDN must be explicitly supplied through the
        # typed settings channel (CADDY_DOMAIN — same channel the
        # Compose backend environment provides).
        fqdn = self._cfg.caddy_domain
        if not fqdn or _has_placeholder(fqdn):
            result.findings.append(
                _finding(
                    "error",
                    "fqdn",
                    "'CADDY_DOMAIN' must be an explicitly supplied production "
                    "FQDN (template placeholders rejected)",
                )
            )

        # 10. TLS email must be explicitly supplied through the typed
        # settings channel (CADDY_EMAIL), a real address shape.
        tls_email = self._cfg.caddy_email
        if not tls_email or "@" not in tls_email or _has_placeholder(tls_email):
            result.findings.append(
                _finding(
                    "error",
                    "fqdn",
                    "'CADDY_EMAIL' must be a real TLS contact email address "
                    "(template placeholders rejected)",
                )
            )

        # 11. CORS origin list must not carry template placeholders
        # (the template ships a REPLACE_WITH_* origin).
        for origin in self._cfg.cors_origins:
            if _has_placeholder(origin):
                result.findings.append(
                    _finding(
                        "error",
                        "cors",
                        "'CORS_ORIGINS' must not contain template placeholders",
                    )
                )
                break

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
