"""Authentication Pydantic schemas for WP-2.6.

Defines request/response schemas for:
- POST /api/v1/auth/login
- GET /api/v1/auth/me
"""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Login request body.

    Attributes:
        username: User login identifier.
        password: Plain-text password (transmitted over HTTPS, never logged).
    """

    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=256)


class TokenResponse(BaseModel):
    """JWT token response.

    Attributes:
        access_token: Encoded JWT access token.
        token_type: Token type identifier (always "Bearer").
        expires_in: Token lifetime in seconds.
    """

    access_token: str
    token_type: str = "Bearer"  # noqa: S105 — RFC 6750 value, not a secret
    expires_in: int = Field(..., ge=60)


class UserResponse(BaseModel):
    """Authenticated user response.

    Attributes:
        id: User UUID.
        username: Login identifier.
        display_name: Human-readable name.
        roles: List of assigned role codes.
    """

    id: str  # UUID as string
    username: str
    display_name: str
    roles: list[str]
