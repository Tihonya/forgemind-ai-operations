"""Authentication API router for WP-2.6.

Endpoints:
- POST /api/v1/auth/login — authenticate and receive JWT access token
- GET /api/v1/auth/me — retrieve current authenticated user info
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.logging import get_logger
from app.database import get_async_session
from app.dependencies import get_current_user
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse
from app.services.auth_service import (
    AuthenticatedUser,
    AuthenticationError,
    authenticate,
    issue_token,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
async def login(
    request: LoginRequest,
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> TokenResponse:
    """Authenticate a user and return a JWT access token.

    Accepts username/password credentials and returns a signed JWT
    if the password is valid and the user account is active.

    On failure, returns a generic 401 response that does not reveal
    whether the username exists or the password was wrong.
    """
    try:
        user, role_codes = await authenticate(session, request.username, request.password)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_credentials",
                "message": "Invalid username or password",
            },
        ) from exc
    except SQLAlchemyError as exc:
        logger.error("auth_db_error", exc=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "internal_error",
                "message": "Authentication service unavailable",
            },
        ) from exc

    token = issue_token(user, role_codes)

    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_expire_minutes * 60,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
)
async def get_me(
    current_user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
) -> UserResponse:
    """Return the currently authenticated user's profile.

    Requires a valid Bearer token in the Authorization header.
    Roles are reloaded from the database on each request.
    """
    return UserResponse(
        id=str(current_user.user_id),
        username=current_user.username,
        display_name=current_user.display_name,
        roles=sorted(current_user.roles),
    )
