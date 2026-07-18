"""Authentication service for WP-2.6.

Central authentication logic:
- Credential verification against bcrypt hashes in PostgreSQL
- JWT access-token issuance
- User/role lookup for dependency injection

All database reads go through this service. No other module should
directly query users/roles for authentication purposes.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.core.security import create_access_token, decode_access_token, verify_password
from app.models.user import User, UserRole

logger = get_logger(__name__)


class AuthenticationError(Exception):
    """Raised when authentication fails.

    Callers map this to HTTP 401 with a generic message
    (no leakage of whether user exists, password wrong, or account locked).
    """


class TokenError(Exception):
    """Raised when token validation fails."""


@dataclass(frozen=True)
class AuthenticatedUser:
    """Value object representing a successfully authenticated user.

    Attributes:
        user_id: User UUID.
        username: Login identifier.
        display_name: Human-readable name.
        roles: Set of role codes assigned to the user.
    """

    user_id: UUID
    username: str
    display_name: str
    roles: frozenset[str]

    def has_role(self, role_code: str) -> bool:
        """Check if user has a specific role."""
        return role_code in self.roles


async def _load_user_with_roles(session: AsyncSession, username: str) -> User | None:
    """Load user with eager role loading from database.

    Args:
        session: Async database session.
        username: Login identifier to look up.

    Returns:
        User object with user_roles and role relationships loaded, or None.
    """
    stmt = (
        select(User)
        .where(User.username == username)
        .options(selectinload(User.user_roles).selectinload(UserRole.role))
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def authenticate(
    session: AsyncSession, username: str, password: str
) -> tuple[User, list[str]]:
    """Authenticate a user by username and password.

    Performs:
    1. User lookup by username
    2. Active-status check (inactive users rejected)
    3. Hashed-password existence check
    4. bcrypt verification

    All failures raise AuthenticationError with a generic message
    to prevent user enumeration or credential-attack feedback.

    Args:
        session: Async database session.
        username: Login identifier.
        password: Plain-text password to verify.

    Returns:
        Tuple of (User, list[str] of role codes).

    Raises:
        AuthenticationError: If credentials are invalid or user is inactive.
        SQLAlchemyError: Re-raised for database failures (caller -> 500).
    """
    user = await _load_user_with_roles(session, username)

    if user is None:
        logger.info("auth_login_failed", reason="user_not_found", username=username)
        raise AuthenticationError("Invalid credentials")

    if not user.is_active:
        logger.info("auth_login_failed", reason="inactive_user", username=username)
        raise AuthenticationError("Invalid credentials")

    if user.hashed_password is None:
        logger.info(
            "auth_login_failed",
            reason="no_password_hash",
            username=username,
        )
        raise AuthenticationError("Invalid credentials")

    if not verify_password(password, user.hashed_password):
        logger.info("auth_login_failed", reason="bad_password", username=username)
        raise AuthenticationError("Invalid credentials")

    # Extract role codes
    role_codes = [ur.role.code for ur in user.user_roles if ur.role is not None]

    logger.info(
        "auth_login_success",
        username=username,
        user_id=str(user.id),
        role_count=len(role_codes),
    )

    return user, role_codes


def issue_token(user: User, role_codes: list[str]) -> str:
    """Issue a JWT access token for an authenticated user.

    Args:
        user: Authenticated user model.
        role_codes: List of role codes assigned to the user.

    Returns:
        Encoded JWT access token string.
    """
    return create_access_token(subject=user.id, roles=role_codes)


async def resolve_token(session: AsyncSession, token: str) -> AuthenticatedUser:
    """Resolve a JWT token to an authenticated user with fresh DB roles.

    Flow:
    1. Decode and validate JWT signature/expiry/claims
    2. Extract user_id from subject claim
    3. Reload user and roles from PostgreSQL (not from token claims)
    4. Verify user is still active

    Args:
        session: Async database session.
        token: JWT access token string.

    Returns:
        AuthenticatedUser with freshly-loaded roles from DB.

    Raises:
        TokenError: If token is malformed, expired, or has invalid claims.
        AuthenticationError: If user no longer exists or is inactive.
    """
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError(f"Invalid token: {exc}") from exc

    subject = payload.get("sub")
    if not subject:
        raise TokenError("Token missing subject claim")

    try:
        user_id = UUID(subject)
    except (ValueError, AttributeError) as exc:
        raise TokenError(f"Invalid subject claim: {exc}") from exc

    # Reload user with roles from DB (authoritative source)
    stmt = (
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.user_roles).selectinload(UserRole.role))
    )
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        raise AuthenticationError("User no longer exists")

    if not user.is_active:
        raise AuthenticationError("User is inactive")

    role_codes = frozenset(ur.role.code for ur in user.user_roles if ur.role is not None)

    return AuthenticatedUser(
        user_id=user.id,
        username=user.username,
        display_name=user.display_name,
        roles=role_codes,
    )
