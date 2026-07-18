"""Unit tests for WP-2.6 security configuration.

Tests config validators: JWT algorithm allowlist, secret_key enforcement,
bcrypt cost factor defaults, and token expiry bounds.
"""

from __future__ import annotations

import pytest
from pydantic_core import ValidationError

from app.config import Settings


class TestJWTAlgorithmConfig:
    def test_default_jwt_algorithm_is_hs256(self) -> None:
        s = Settings()
        assert s.jwt_algorithm == "HS256"

    def test_jwt_algorithm_rejects_non_hs256(self) -> None:
        with pytest.raises(ValidationError):
            Settings(jwt_algorithm="RS256")


class TestJWTExpireMinutesConfig:
    def test_default_jwt_expire_minutes_is_30(self) -> None:
        s = Settings()
        assert s.jwt_expire_minutes == 30

    def test_jwt_expire_minutes_rejects_zero(self) -> None:
        with pytest.raises(ValidationError):
            Settings(jwt_expire_minutes=0)

    def test_jwt_expire_minutes_rejects_too_large(self) -> None:
        with pytest.raises(ValidationError):
            Settings(jwt_expire_minutes=2000)


class TestBcryptCostFactorConfig:
    def test_default_bcrypt_cost_factor_is_12(self) -> None:
        s = Settings()
        assert s.bcrypt_cost_factor == 12

    def test_bcrypt_cost_factor_rejects_too_low(self) -> None:
        with pytest.raises(ValidationError):
            Settings(bcrypt_cost_factor=3)


class TestSecretKeyValidation:
    def test_development_accepts_default_secret(self, monkeypatch) -> None:
        monkeypatch.setenv("ENVIRONMENT", "development")
        s = Settings()
        assert len(s.secret_key) >= 32

    def test_production_rejects_default_secret(self, monkeypatch) -> None:
        monkeypatch.setenv("ENVIRONMENT", "production")
        insecure = "dev-secret-key-change-in-production-must-be-32-chars-min"
        with pytest.raises(ValidationError):
            Settings(secret_key=insecure)

    def test_staging_rejects_default_secret(self, monkeypatch) -> None:
        monkeypatch.setenv("ENVIRONMENT", "staging")
        insecure = "dev-secret-key-change-in-production-must-be-32-chars-min"
        with pytest.raises(ValidationError):
            Settings(secret_key=insecure)

    def test_production_accepts_real_secret(self, monkeypatch) -> None:
        monkeypatch.setenv("ENVIRONMENT", "production")
        s = Settings(secret_key="real-production-secret-at-least-32-characters-min")
        assert len(s.secret_key) >= 32
