"""Authorization and authentication dependencies.

FastAPI dependency injection functions for WP-2.6:
- get_current_user: extracts and validates JWT, reloads roles from DB
- require_role: authorization gate for role-based access control
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.database import get_async_session
from app.services.auth_service import (
    AuthenticatedUser,
    AuthenticationError,
    TokenError,
    resolve_token,
)

logger = get_logger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> AuthenticatedUser:
    """Extract and validate the current user from the Bearer token.

    Reloads roles from PostgreSQL on every request (not from token claims)
    to enforce real-time role changes.

    Args:
        credentials: HTTP Bearer credentials from request header.
        session: Async database session.

    Returns:
        Authenticated user with current roles from DB.

    Raises:
        HTTPException(401): Missing token, malformed token, expired token,
                           invalid signature, or inactive user.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "missing_authentication",
                "message": "Bearer token required",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user = await resolve_token(session, credentials.credentials)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "message": str(exc)},
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "user_unauthorized",
                "message": "Invalid username or password",
            },
        ) from e

    return user


def require_role(allowed_roles: set[str]) -> Callable[..., Awaitable[AuthenticatedUser]]:
    """Create a dependency that enforces role-based access control.

    Args:
        allowed_roles: Set of role codes permitted to access the endpoint.

    Returns:
        FastAPI dependency that checks user has at least one of the required roles.

    Raises:
        HTTPException(403): User does not have any of the required roles.
    """

    async def role_checker(
        current_user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    ) -> AuthenticatedUser:  # pragma: no cover (FastAPI dependency)
        user_roles = current_user.roles
        if not user_roles & allowed_roles:
            logger.info(
                "auth_role_denied",
                username=current_user.username,
                user_roles=sorted(user_roles),
                required_roles=sorted(allowed_roles),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "insufficient_permissions",
                    "message": "User does not have the required role for this action",
                },
            )
        return current_user

    return role_checker
