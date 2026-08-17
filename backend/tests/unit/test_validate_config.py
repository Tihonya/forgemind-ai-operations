"""Unit tests for the production configuration validator (WP-P7-02).

The validator must fail closed on every Release 1 production rule and
pass only on the exact accepted configuration. No secret value ever
appears in a rendered report.

Remediation F-2 coverage (template-literal regression): the committed
template placeholder vocabulary (infra/prod.env.example) is loaded
verbatim, composed into Settings exactly the way docker-compose.prod.yml
composes it, and MUST fail validation with non-zero exit semantics.

Remediation F-6A coverage: CADDY_DOMAIN / CADDY_EMAIL are read from
the typed settings channel (Settings.caddy_domain / caddy_email).

Remediation F-8 coverage: URL-special characters in DB/Redis
credentials are rejected; URL-safe credential alphabets pass.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.config import Settings
from app.ops.validate_config import (
    OPENROUTER_BASE_URL,
    OPENROUTER_CHAT_MODEL,
    OPENROUTER_EMBEDDING_DIMENSIONS,
    OPENROUTER_EMBEDDING_MODEL,
    ProductionConfigValidator,
    main,
)

_FAKE_SECRET = "x7b3c9d1e5f0a2b4c6d8e0f2a4b6c8d0e2f4a6b8c0d2e4f6a8b0c2d4e"

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATE_PATH = _REPO_ROOT / "infra" / "prod.env.example"


def _load_template() -> dict[str, str]:
    """Parse infra/prod.env.example into a dict (skip comments/blanks)."""
    values: dict[str, str] = {}
    for raw_line in _TEMPLATE_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def _production_settings(**overrides: object) -> Settings:
    """A fully-valid Release 1 production configuration."""
    base: dict[str, object] = {
        "environment": "production",
        "secret_key": _FAKE_SECRET,
        "database_url": "postgresql+asyncpg://forgemind:dbpass@postgres:5432/forgemind",
        "redis_url": "redis://:redpass@redis:6379/0",
        "distributed_rate_limit_enabled": True,
        "rate_limit_degraded_mode": "fail_closed",
        "embedding_provider": "openai",
        "chat_provider_mode": "openrouter",
        "openrouter_chat_model": OPENROUTER_CHAT_MODEL,
        "openrouter_structured_output_mode": "json_object",
        "openrouter_api_key": "sr-or-test-key",
        "openai_api_key": "sr-or-test-key",
        "openai_api_base": OPENROUTER_BASE_URL,
        "openai_embedding_model": OPENROUTER_EMBEDDING_MODEL,
        "embedding_dimensions": OPENROUTER_EMBEDDING_DIMENSIONS,
        "caddy_domain": "demo.example-ops.net",
        "caddy_email": "ops@example-ops.net",
        "cors_origins": "https://demo.example-ops.net",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_fully_valid_production_configuration_passes() -> None:
    result = ProductionConfigValidator(_production_settings()).validate()
    assert result.passed, result.render()
    assert result.findings == []


# ---------------------------------------------------------------------------
# Fail-closed rules
# ---------------------------------------------------------------------------


class TestEnvironmentRule:
    def test_development_rejected(self) -> None:
        result = ProductionConfigValidator(
            _production_settings(environment="development")
        ).validate()
        assert not result.passed
        assert any(f.rule == "environment" for f in result.errors)


class TestSecretKeyRule:
    def test_insecure_secret_rejected(self) -> None:
        result = ProductionConfigValidator(
            _production_settings(
                secret_key="changeme_generate_32_random_bytes"
            )
        ).validate()
        assert not result.passed
        assert any(f.rule == "secret_key" for f in result.errors)

    def test_short_secret_key_rejected_by_settings_schema(self) -> None:
        """Length floor is enforced by the pydantic schema itself."""
        with pytest.raises(Exception, match="at least 32 characters"):
            _production_settings(secret_key="short")


class TestProviderRules:
    def test_chain_mode_rejected_in_production(self) -> None:
        result = ProductionConfigValidator(
            _production_settings(chat_provider_mode="chain")
        ).validate()
        assert not result.passed
        assert any(f.rule == "chat" for f in result.errors)

    def test_wrong_chat_model_rejected(self) -> None:
        result = ProductionConfigValidator(
            _production_settings(openrouter_chat_model="other/model")
        ).validate()
        assert not result.passed
        assert any(
            "OPENROUTER_CHAT_MODEL" in f.detail for f in result.errors
        )

    def test_wrong_embedding_model_rejected(self) -> None:
        result = ProductionConfigValidator(
            _production_settings(openai_embedding_model="text-embedding-ada-002")
        ).validate()
        assert not result.passed
        assert any(
            "OPENAI_EMBEDDING_MODEL" in f.detail for f in result.errors
        )

    def test_wrong_dimensions_rejected(self) -> None:
        result = ProductionConfigValidator(
            _production_settings(embedding_dimensions=768)
        ).validate()
        assert not result.passed
        assert any("EMBEDDING_DIMENSIONS" in f.detail for f in result.errors)

    def test_missing_embedding_key_rejected(self) -> None:
        result = ProductionConfigValidator(
            _production_settings(openai_api_key="")
        ).validate()
        assert not result.passed
        assert any("OPENAI_API_KEY" in f.detail for f in result.errors)

    def test_wrong_embedding_base_url_rejected(self) -> None:
        result = ProductionConfigValidator(
            _production_settings(openai_api_base="https://api.openai.com/v1")
        ).validate()
        assert not result.passed
        assert any("OPENAI_API_BASE" in f.detail for f in result.errors)

    def test_fake_chat_provider_rejected(self) -> None:
        result = ProductionConfigValidator(
            _production_settings(chat_provider_mode="fake")
        ).validate()
        assert not result.passed
        assert any("CHAT_PROVIDER_MODE" in f.detail for f in result.errors)

    def test_fake_embedding_provider_rejected(self) -> None:
        result = ProductionConfigValidator(
            _production_settings(embedding_provider="fake")
        ).validate()
        assert not result.passed
        assert any("EMBEDDING_PROVIDER" in f.detail for f in result.errors)


class TestRateLimitRules:
    def test_disabled_shared_limiter_rejected(self) -> None:
        result = ProductionConfigValidator(
            _production_settings(distributed_rate_limit_enabled=False)
        ).validate()
        assert not result.passed
        assert any("DISTRIBUTED_RATE_LIMIT_ENABLED" in f.detail for f in result.errors)

    def test_fail_open_limiter_rejected(self) -> None:
        result = ProductionConfigValidator(
            _production_settings(rate_limit_degraded_mode="fail_open")
        ).validate()
        assert not result.passed
        assert any("RATE_LIMIT_DEGRADED_MODE" in f.detail for f in result.errors)


class TestNetworkRules:
    def test_placeholder_database_url_rejected(self) -> None:
        result = ProductionConfigValidator(
            _production_settings(
                database_url=(
                    "postgresql+asyncpg://forgemind:changeme_in_production"
                    "@postgres:5432/forgemind"
                )
            )
        ).validate()
        assert not result.passed
        assert any(f.rule == "database" for f in result.errors)

    def test_placeholder_redis_url_rejected(self) -> None:
        result = ProductionConfigValidator(
            _production_settings(
                redis_url="redis://:changeme_in_production@redis:6379/0"
            )
        ).validate()
        assert not result.passed
        assert any(f.rule == "redis" for f in result.errors)


class TestFqdnRules:
    def test_missing_caddy_domain_rejected(self) -> None:
        result = ProductionConfigValidator(
            _production_settings(caddy_domain="")
        ).validate()
        assert not result.passed
        assert any("CADDY_DOMAIN" in f.detail for f in result.errors)

    def test_localhost_domain_rejected(self) -> None:
        result = ProductionConfigValidator(
            _production_settings(caddy_domain="localhost")
        ).validate()
        assert not result.passed
        assert any("CADDY_DOMAIN" in f.detail for f in result.errors)

    def test_missing_email_rejected(self) -> None:
        result = ProductionConfigValidator(
            _production_settings(caddy_email="")
        ).validate()
        assert not result.passed
        assert any("CADDY_EMAIL" in f.detail for f in result.errors)


# ---------------------------------------------------------------------------
# Remediation F-2: template-literal placeholder rejection
# ---------------------------------------------------------------------------


class TestTemplateLiteralRejection:
    """The validator rejects the repository template's own placeholders."""

    def test_template_secret_key_rejected(self) -> None:
        result = ProductionConfigValidator(
            _production_settings(secret_key="REPLACE_WITH_RANDOM_32_PLUS_CHARS")
        ).validate()
        assert not result.passed
        assert any(f.rule == "secret_key" for f in result.errors)

    def test_template_provider_keys_rejected(self) -> None:
        result = ProductionConfigValidator(
            _production_settings(
                openai_api_key="REPLACE_WITH_OPENROUTER_KEY",
                openrouter_api_key="REPLACE_WITH_OPENROUTER_KEY",
            )
        ).validate()
        assert not result.passed
        assert any(f.rule == "chat" for f in result.errors)
        assert any(f.rule == "embedding" for f in result.errors)

    def test_template_db_redis_passwords_rejected(self) -> None:
        result = ProductionConfigValidator(
            _production_settings(
                database_url=(
                    "postgresql+asyncpg://forgemind:"
                    "REPLACE_WITH_STRONG_DB_PASSWORD@postgres:5432/forgemind"
                ),
                redis_url=(
                    "redis://:REPLACE_WITH_STRONG_REDIS_PASSWORD@redis:6379/0"
                ),
            )
        ).validate()
        assert not result.passed
        assert any(f.rule == "database" for f in result.errors)
        assert any(f.rule == "redis" for f in result.errors)

    def test_template_fqdn_email_rejected(self) -> None:
        result = ProductionConfigValidator(
            _production_settings(
                caddy_domain="replace-with-production-fqdn.example",
                caddy_email="replace-with-tls-contact@example.com",
            )
        ).validate()
        assert not result.passed
        assert any("CADDY_DOMAIN" in f.detail for f in result.errors)
        assert any("CADDY_EMAIL" in f.detail for f in result.errors)

    def test_template_fqdn_via_typed_channel_rejected_even_when_env_set(
        self, monkeypatch: Any
    ) -> None:
        """F-6A: the typed channel rejects template env values both ways."""
        monkeypatch.setenv("CADDY_DOMAIN", "replace-with-production-fqdn.example")
        result = ProductionConfigValidator(
            _production_settings(caddy_domain="")
        ).validate()
        assert not result.passed

    def test_whole_template_env_fails_closed(self, monkeypatch: Any) -> None:
        """A configuration populated from the committed template placeholders
        (composed exactly as docker-compose.prod.yml composes them) must
        yield findings, a FAIL verdict, and a non-zero CLI exit."""
        template = _load_template()
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("SECRET_KEY", template["SECRET_KEY"])
        monkeypatch.setenv("POSTGRES_DB", template["POSTGRES_DB"])
        monkeypatch.setenv("POSTGRES_USER", template["POSTGRES_USER"])
        monkeypatch.setenv("POSTGRES_PASSWORD", template["POSTGRES_PASSWORD"])
        monkeypatch.setenv("REDIS_PASSWORD", template["REDIS_PASSWORD"])
        monkeypatch.setenv("OPENAI_API_KEY", template["OPENAI_API_KEY"])
        monkeypatch.setenv("OPENROUTER_API_KEY", template["OPENROUTER_API_KEY"])
        monkeypatch.setenv("CADDY_DOMAIN", template["CADDY_DOMAIN"])
        monkeypatch.setenv("CADDY_EMAIL", template["CADDY_EMAIL"])
        monkeypatch.setenv("DISTRIBUTED_RATE_LIMIT_ENABLED", "true")
        monkeypatch.setenv("RATE_LIMIT_DEGRADED_MODE", "fail_closed")
        # Compose-style composition (same interpolation as the compose file):
        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql+asyncpg://"
            f"{template['POSTGRES_USER']}:{template['POSTGRES_PASSWORD']}"
            f"@postgres:5432/{template['POSTGRES_DB']}",
        )
        monkeypatch.setenv(
            "REDIS_URL",
            f"redis://:{template['REDIS_PASSWORD']}@redis:6379/0",
        )

        config = Settings()
        result = ProductionConfigValidator(config).validate()
        rendered = result.render()
        assert result.findings, "template placeholders must yield findings"
        assert "VERDICT: FAIL" in rendered
        assert not result.passed

        # Non-zero CLI exit for the strict gate.
        import app.config as config_module

        monkeypatch.setattr(config_module, "settings", config)
        assert main() == 1

    def test_cli_exit_zero_on_valid_config(self, monkeypatch: Any) -> None:
        """A real-looking safe configuration exits 0."""
        import app.config as config_module

        monkeypatch.setattr(config_module, "settings", _production_settings())
        assert main() == 0

    def test_case_insensitive_placeholder_variants_rejected(self) -> None:
        result = ProductionConfigValidator(
            _production_settings(secret_key="replace_with_some_secret_key_123456")
        ).validate()
        assert not result.passed
        assert any(f.rule == "secret_key" for f in result.errors)


# ---------------------------------------------------------------------------
# Remediation F-8: URL-safe credential alphabet
# ---------------------------------------------------------------------------


class TestCredentialAlphabet:
    @pytest.mark.parametrize(
        "signature",
        ["@", ":", "/", "#", "%", " ", "é"],
    )
    def test_url_special_characters_rejected_in_db_password(
        self, signature: str
    ) -> None:
        database_url = (
            f"postgresql+asyncpg://forgemind:pass{signature}word@postgres:5432/forgemind"
        )
        result = ProductionConfigValidator(
            _production_settings(database_url=database_url)
        ).validate()
        assert not result.passed
        assert any(f.rule == "database" for f in result.errors)

    @pytest.mark.parametrize(
        "signature",
        ["@", ":", "/", "#", "%", " ", "é"],
    )
    def test_url_special_characters_rejected_in_redis_password(
        self, signature: str
    ) -> None:
        redis_url = f"redis://:pass{signature}word@redis:6379/0"
        result = ProductionConfigValidator(
            _production_settings(redis_url=redis_url)
        ).validate()
        assert not result.passed
        assert any(f.rule == "redis" for f in result.errors)

    @pytest.mark.parametrize(
        "password",
        ["correcthorse", "Kx9_2f~4n8.q", "A1b2C3d4", "p-w.1_9v"],
    )
    def test_url_safe_passwords_pass(self, password: str) -> None:
        result = ProductionConfigValidator(
            _production_settings(
                database_url=(
                    f"postgresql+asyncpg://forgemind:{password}@postgres:5432/forgemind"
                ),
                redis_url=f"redis://:{password}@redis:6379/0",
            )
        ).validate()
        assert result.passed, result.render()


# ---------------------------------------------------------------------------
# Report safety: no secrets in rendered output
# ---------------------------------------------------------------------------


class TestReportSafety:
    def test_no_secret_values_in_report(self) -> None:
        """Even a failing report never contains any configured secret."""
        config = _production_settings(
            openrouter_api_key="sr-or-very-secret",
            openai_api_key="sr-or-very-secret",
        )
        result = ProductionConfigValidator(config).validate()
        rendered = result.render()
        assert "sr-or-very-secret" not in rendered
        assert "dbpass" not in rendered
        assert "redpass" not in rendered
        assert _FAKE_SECRET not in rendered

    def test_rejected_placeholder_values_not_echoed(self) -> None:
        """Rejected REPLACE_* values never appear in the rendered report."""
        config = _production_settings(secret_key="REPLACE_WITH_RANDOM_32_PLUS_CHARS")
        result = ProductionConfigValidator(config).validate()
        rendered = result.render()
        assert "REPLACE_WITH_RANDOM_32_PLUS_CHARS" not in rendered

    def test_cannot_fail_open_on_null_config(self) -> None:
        """A straight-defaulted Settings instance cannot pass production rules."""
        result = ProductionConfigValidator(Settings()).validate()
        assert not result.passed
