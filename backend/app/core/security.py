"""Security utilities for password verification and JWT token management.

WP-2.6 authentication infrastructure.
- bcrypt password verification (no generation — uses precomputed hashes).
- JWT HS256 issue and validation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import bcrypt
import jwt

from app.config import settings

ALLOWED_ALGORITHMS = {"HS256"}

# JWT issuer claim
JWT_ISSUER = "forgemind-api"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a bcrypt hash.

    Args:
        plain_password: Plain-text password to verify.
        hashed_password: bcrypt hash to verify against.

    Returns:
        True if the password matches, False otherwise.
    """
    password_bytes = plain_password.encode("utf-8")
    hash_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hash_bytes)


def create_access_token(
    subject: UUID,
    roles: list[str],
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token.

    Args:
        subject: User ID (UUID).
        roles: List of role codes.
        expires_delta: Optional custom expiration delta.

    Returns:
        Encoded JWT token string.

    Raises:
        ValueError: If the configured algorithm is not in the HS256 allowlist.
    """
    if settings.jwt_algorithm not in ALLOWED_ALGORITHMS:
        raise ValueError(
            f"JWT algorithm '{settings.jwt_algorithm}' is not in allowlist {ALLOWED_ALGORITHMS}"
        )

    now = datetime.now(UTC)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.jwt_expire_minutes)

    to_encode = {
        "sub": str(subject),
        "roles": roles,
        "exp": expire,
        "iat": now,
        "iss": JWT_ISSUER,
    }

    return jwt.encode(
        to_encode,
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token.

    Args:
        token: JWT token string.

    Returns:
        Decoded token payload dict.

    Raises:
        jwt.ExpiredSignatureError: Token has expired.
        jwt.InvalidTokenError: Token is invalid (bad signature, malformed, etc.).
    """
    return jwt.decode(
        token,
        settings.secret_key,
        algorithms=list(ALLOWED_ALGORITHMS),
        issuer=JWT_ISSUER,
    )
