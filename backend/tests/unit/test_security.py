"""Unit tests for WP-2.6 security utilities."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import bcrypt
import jwt
import pytest

from app.config import settings
from app.core.security import (
    ALLOWED_ALGORITHMS,
    JWT_ISSUER,
    create_access_token,
    decode_access_token,
    verify_password,
)


class TestBCryptVerification:
    def test_verify_valid_password(self) -> None:
        password = "TestPassword123!"
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
        assert verify_password(password, hashed) is True

    def test_verify_wrong_password(self) -> None:
        password = "TestPassword123!"
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
        assert verify_password("WrongPassword", hashed) is False

    def test_verify_unicode_password(self) -> None:
        password = "密码测试"
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
        assert verify_password(password, hashed) is True

    def test_no_hash_generation_in_service(self) -> None:
        import app.core.security as sec

        assert not hasattr(sec, "hash_password")
        assert hasattr(sec, "verify_password")


class TestJWTCreate:
    def test_create_access_token_basic(self) -> None:
        user_id = uuid4()
        token = create_access_token(subject=user_id, roles=["ADMIN"])

        assert isinstance(token, str)
        decoded = jwt.decode(token, options={"verify_signature": False})

        assert decoded["sub"] == str(user_id)
        assert decoded["roles"] == ["ADMIN"]
        assert decoded["iss"] == JWT_ISSUER
        assert "exp" in decoded
        assert "iat" in decoded

    def test_access_token_expiration(self) -> None:
        user_id = uuid4()
        token = create_access_token(subject=user_id, roles=["ADMIN"])
        decoded = jwt.decode(token, options={"verify_signature": False})

        duration = decoded["exp"] - decoded["iat"]
        expected = settings.jwt_expire_minutes * 60
        assert abs(duration - expected) <= 10

    def test_custom_expiration_delta(self) -> None:
        custom_delta = timedelta(hours=2)
        token = create_access_token(subject=uuid4(), roles=["ADMIN"], expires_delta=custom_delta)
        decoded = jwt.decode(token, options={"verify_signature": False})

        duration = decoded["exp"] - decoded["iat"]
        expected = int(custom_delta.total_seconds())
        assert abs(duration - expected) <= 10

    def test_token_algorithm_hs256(self) -> None:
        token = create_access_token(subject=uuid4(), roles=["ADMIN"])
        header = jwt.get_unverified_header(token)
        assert header["alg"] == "HS256"


class TestJWTVerification:
    def test_decode_valid_token(self) -> None:
        user_id = uuid4()
        token = create_access_token(subject=user_id, roles=["ADMIN"])
        decoded = decode_access_token(token)

        assert decoded["sub"] == str(user_id)
        assert decoded["roles"] == ["ADMIN"]
        assert decoded["iss"] == JWT_ISSUER

    def test_decode_expired_token(self) -> None:
        token = create_access_token(
            subject=uuid4(), roles=["ADMIN"], expires_delta=timedelta(hours=-1)
        )
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_access_token(token)

    def test_decode_wrong_secret(self) -> None:
        user_id = uuid4()
        now = datetime.now(UTC)
        payload = {
            "sub": str(user_id),
            "roles": ["ADMIN"],
            "exp": (now + timedelta(minutes=30)).timestamp(),
            "iat": now.timestamp(),
            "iss": JWT_ISSUER,
        }
        wrong_token = jwt.encode(payload, "different-secret-key-32chars-or-more", algorithm="HS256")
        with pytest.raises(jwt.InvalidSignatureError):
            decode_access_token(wrong_token)

    def test_decode_malformed_token(self) -> None:
        with pytest.raises(jwt.DecodeError):
            decode_access_token("header.payload")

    def test_decode_wrong_algorithm(self) -> None:
        user_id = uuid4()
        now = datetime.now(UTC)
        payload = {
            "sub": str(user_id),
            "roles": ["ADMIN"],
            "exp": (now + timedelta(minutes=30)).timestamp(),
            "iat": now.timestamp(),
            "iss": JWT_ISSUER,
        }
        wrong_alg_token = jwt.encode(payload, settings.secret_key, algorithm="HS384")
        with pytest.raises(jwt.InvalidAlgorithmError):
            decode_access_token(wrong_alg_token)

    def test_decode_wrong_issuer(self) -> None:
        user_id = uuid4()
        now = datetime.now(UTC)
        payload = {
            "sub": str(user_id),
            "roles": ["ADMIN"],
            "exp": (now + timedelta(minutes=30)).timestamp(),
            "iat": now.timestamp(),
            "iss": "wrong-issuer",
        }
        wrong_iss_token = jwt.encode(payload, settings.secret_key, algorithm="HS256")
        with pytest.raises(jwt.InvalidIssuerError):
            decode_access_token(wrong_iss_token)


class TestAlgorithmAllowlist:
    def test_hs256_in_allowlist(self) -> None:
        assert "HS256" in ALLOWED_ALGORITHMS

    def test_only_hs256_in_allowlist(self) -> None:
        assert {"HS256"} == ALLOWED_ALGORITHMS
