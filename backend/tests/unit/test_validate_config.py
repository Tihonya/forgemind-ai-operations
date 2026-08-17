"""Unit tests for the production configuration validator (WP-P7-02).

The validator must fail closed on every Release 1 production rule and
pass only on the exact accepted configuration. No secret value ever
appears in a rendered report.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from app.config import Settings
from app.ops.validate_config import (
    OPENROUTER_BASE_URL,
    OPENROUTER_CHAT_MODEL,
    OPENROUTER_EMBEDDING_DIMENSIONS,
    OPENROUTER_EMBEDDING_MODEL,
    ProductionConfigValidator,
)

_FAKE_SECRET = "x7b3c9d1e5f0a2b4c6d8e0f2a4b6c8d0e2f4a6b8c0d2e4f6a8b0c2d4e"


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
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _validator_with_env(config: Settings, **env: str) -> ProductionConfigValidator:
    """Build a validator with CADDY_DOMAIN/CADDY_EMAIL in the raw env."""
    for key, value in env.items():
        os.environ[key] = value
    return ProductionConfigValidator(config)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_fully_valid_production_configuration_passes(monkeypatch: Any) -> None:
    monkeypatch.setenv("CADDY_DOMAIN", "demo.example-ops.net")
    monkeypatch.setenv("CADDY_EMAIL", "ops@example-ops.net")
    result = ProductionConfigValidator(_production_settings()).validate()
    assert result.passed, result.render()
    assert result.findings == []


# ---------------------------------------------------------------------------
# Fail-closed rules
# ---------------------------------------------------------------------------


class TestEnvironmentRule:
    def test_development_rejected(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("CADDY_DOMAIN", "demo.example-ops.net")
        monkeypatch.setenv("CADDY_EMAIL", "ops@example-ops.net")
        result = ProductionConfigValidator(
            _production_settings(environment="development")
        ).validate()
        assert not result.passed
        assert any(f.rule == "environment" for f in result.errors)


class TestSecretKeyRule:
    def test_insecure_secret_rejected(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("CADDY_DOMAIN", "demo.example-ops.net")
        monkeypatch.setenv("CADDY_EMAIL", "ops@example-ops.net")
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
    def test_chain_mode_rejected_in_production(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("CADDY_DOMAIN", "demo.example-ops.net")
        monkeypatch.setenv("CADDY_EMAIL", "ops@example-ops.net")
        result = ProductionConfigValidator(
            _production_settings(chat_provider_mode="chain")
        ).validate()
        assert not result.passed
        assert any(f.rule == "chat" for f in result.errors)

    def test_wrong_chat_model_rejected(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("CADDY_DOMAIN", "demo.example-ops.net")
        monkeypatch.setenv("CADDY_EMAIL", "ops@example-ops.net")
        result = ProductionConfigValidator(
            _production_settings(openrouter_chat_model="other/model")
        ).validate()
        assert not result.passed
        assert any(
            "OPENROUTER_CHAT_MODEL" in f.detail for f in result.errors
        )

    def test_wrong_embedding_model_rejected(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("CADDY_DOMAIN", "demo.example-ops.net")
        monkeypatch.setenv("CADDY_EMAIL", "ops@example-ops.net")
        result = ProductionConfigValidator(
            _production_settings(openai_embedding_model="text-embedding-ada-002")
        ).validate()
        assert not result.passed
        assert any(
            "OPENAI_EMBEDDING_MODEL" in f.detail for f in result.errors
        )

    def test_wrong_dimensions_rejected(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("CADDY_DOMAIN", "demo.example-ops.net")
        monkeypatch.setenv("CADDY_EMAIL", "ops@example-ops.net")
        result = ProductionConfigValidator(
            _production_settings(embedding_dimensions=768)
        ).validate()
        assert not result.passed
        assert any("EMBEDDING_DIMENSIONS" in f.detail for f in result.errors)

    def test_missing_embedding_key_rejected(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("CADDY_DOMAIN", "demo.example-ops.net")
        monkeypatch.setenv("CADDY_EMAIL", "ops@example-ops.net")
        result = ProductionConfigValidator(
            _production_settings(openai_api_key="")
        ).validate()
        assert not result.passed
        assert any("OPENAI_API_KEY" in f.detail for f in result.errors)

    def test_wrong_embedding_base_url_rejected(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("CADDY_DOMAIN", "demo.example-ops.net")
        monkeypatch.setenv("CADDY_EMAIL", "ops@example-ops.net")
        result = ProductionConfigValidator(
            _production_settings(openai_api_base="https://api.openai.com/v1")
        ).validate()
        assert not result.passed
        assert any("OPENAI_API_BASE" in f.detail for f in result.errors)

    def test_fake_chat_provider_rejected(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("CADDY_DOMAIN", "demo.example-ops.net")
        monkeypatch.setenv("CADDY_EMAIL", "ops@example-ops.net")
        result = ProductionConfigValidator(
            _production_settings(chat_provider_mode="fake")
        ).validate()
        assert not result.passed
        assert any("CHAT_PROVIDER_MODE" in f.detail for f in result.errors)

    def test_fake_embedding_provider_rejected(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("CADDY_DOMAIN", "demo.example-ops.net")
        monkeypatch.setenv("CADDY_EMAIL", "ops@example-ops.net")
        result = ProductionConfigValidator(
            _production_settings(embedding_provider="fake")
        ).validate()
        assert not result.passed
        assert any("EMBEDDING_PROVIDER" in f.detail for f in result.errors)


class TestRateLimitRules:
    def test_disabled_shared_limiter_rejected(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("CADDY_DOMAIN", "demo.example-ops.net")
        monkeypatch.setenv("CADDY_EMAIL", "ops@example-ops.net")
        result = ProductionConfigValidator(
            _production_settings(distributed_rate_limit_enabled=False)
        ).validate()
        assert not result.passed
        assert any("DISTRIBUTED_RATE_LIMIT_ENABLED" in f.detail for f in result.errors)

    def test_fail_open_limiter_rejected(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("CADDY_DOMAIN", "demo.example-ops.net")
        monkeypatch.setenv("CADDY_EMAIL", "ops@example-ops.net")
        result = ProductionConfigValidator(
            _production_settings(rate_limit_degraded_mode="fail_open")
        ).validate()
        assert not result.passed
        assert any("RATE_LIMIT_DEGRADED_MODE" in f.detail for f in result.errors)


class TestNetworkRules:
    def test_placeholder_database_url_rejected(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("CADDY_DOMAIN", "demo.example-ops.net")
        monkeypatch.setenv("CADDY_EMAIL", "ops@example-ops.net")
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

    def test_placeholder_redis_url_rejected(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("CADDY_DOMAIN", "demo.example-ops.net")
        monkeypatch.setenv("CADDY_EMAIL", "ops@example-ops.net")
        result = ProductionConfigValidator(
            _production_settings(
                redis_url="redis://:changeme_in_production@redis:6379/0"
            )
        ).validate()
        assert not result.passed
        assert any(f.rule == "redis" for f in result.errors)


class TestFqdnRules:
    def test_missing_caddy_domain_rejected(self, monkeypatch: Any) -> None:
        monkeypatch.delenv("CADDY_DOMAIN", raising=False)
        monkeypatch.setenv("CADDY_EMAIL", "ops@example-ops.net")
        result = ProductionConfigValidator(_production_settings()).validate()
        assert not result.passed
        assert any("CADDY_DOMAIN" in f.detail for f in result.errors)

    def test_localhost_domain_rejected(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("CADDY_DOMAIN", "localhost")
        monkeypatch.setenv("CADDY_EMAIL", "ops@example-ops.net")
        result = ProductionConfigValidator(_production_settings()).validate()
        assert not result.passed
        assert any("CADDY_DOMAIN" in f.detail for f in result.errors)

    def test_missing_email_rejected(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("CADDY_DOMAIN", "demo.example-ops.net")
        monkeypatch.delenv("CADDY_EMAIL", raising=False)
        result = ProductionConfigValidator(_production_settings()).validate()
        assert not result.passed
        assert any("CADDY_EMAIL" in f.detail for f in result.errors)


# ---------------------------------------------------------------------------
# Report safety: no secrets in rendered output
# ---------------------------------------------------------------------------


class TestReportSafety:
    def test_no_secret_values_in_report(self, monkeypatch: Any) -> None:
        """Even a failing report never contains any configured secret."""
        monkeypatch.setenv("CADDY_DOMAIN", "demo.example-ops.net")
        monkeypatch.setenv("CADDY_EMAIL", "ops@example-ops.net")
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

    def test_cannot_fail_open_on_null_config(self, monkeypatch: Any) -> None:
        """A straight-defaulted Settings instance cannot pass production rules."""
        monkeypatch.setenv("CADDY_DOMAIN", "demo.example-ops.net")
        monkeypatch.setenv("CADDY_EMAIL", "ops@example-ops.net")
        result = ProductionConfigValidator(Settings()).validate()
        assert not result.passed
