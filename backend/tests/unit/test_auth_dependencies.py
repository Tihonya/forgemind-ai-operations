"""Unit tests for WP-2.6 dependencies.

Tests the FastAPI dependency-injection layer:
- get_current_user: missing/invalid/expired token, inactive user
- require_role: role match, role mismatch, empty user roles
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.dependencies import get_current_user, require_role
from app.services.auth_service import (
    AuthenticatedUser,
    AuthenticationError,
    TokenError,
)


def _make_user(username: str, roles: set[str]) -> AuthenticatedUser:
    """Helper to build a test AuthenticatedUser."""
    return AuthenticatedUser(
        user_id=uuid4(),
        username=username,
        display_name=username.title(),
        roles=frozenset(roles),
    )


# ─────────────────────────────────────────────────────────────────────────────
# get_current_user
# ─────────────────────────────────────────────────────────────────────────────


class TestGetCurrentUser:
    """Tests for the get_current_user FastAPI dependency."""

    @pytest.mark.asyncio
    async def test_missing_credentials_raises_401(self) -> None:
        """No Authorization header => 401 missing_authentication."""
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=None, session=AsyncMock())

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["error"] == "missing_authentication"

    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self) -> None:
        """A valid Bearer token returns the resolved AuthenticatedUser."""
        user = _make_user("alice", {"admin"})
        credentials = MagicMock()
        credentials.credentials = "valid.jwt.token"
        session = AsyncMock()

        with patch(
            "app.dependencies.resolve_token",
            new_callable=AsyncMock,
            return_value=user,
        ):
            result = await get_current_user(credentials=credentials, session=session)

        assert result == user
        assert result.username == "alice"

    @pytest.mark.asyncio
    async def test_expired_token_raises_401_invalid_token(self) -> None:
        """Expired JWT => 401 invalid_token (same bucket as malformed)."""
        credentials = MagicMock()
        credentials.credentials = "expired.jwt.token"
        session = AsyncMock()

        with (
            patch(
                "app.dependencies.resolve_token",
                new_callable=AsyncMock,
                side_effect=TokenError("Token expired"),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await get_current_user(credentials=credentials, session=session)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["error"] == "invalid_token"
        assert "expired" in exc_info.value.detail["message"].lower()

    @pytest.mark.asyncio
    async def test_malformed_token_raises_401_invalid_token(self) -> None:
        """Malformed JWT => 401 invalid_token."""
        credentials = MagicMock()
        credentials.credentials = "not.a.valid.jwt"
        session = AsyncMock()

        with (
            patch(
                "app.dependencies.resolve_token",
                new_callable=AsyncMock,
                side_effect=TokenError("Invalid token: ..."),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await get_current_user(credentials=credentials, session=session)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["error"] == "invalid_token"

    @pytest.mark.asyncio
    async def test_wrong_signature_raises_401_invalid_token(self) -> None:
        """Bad signature => 401 invalid_token."""
        credentials = MagicMock()
        credentials.credentials = "wrong.jwt.signature"
        session = AsyncMock()

        with (
            patch(
                "app.dependencies.resolve_token",
                new_callable=AsyncMock,
                side_effect=TokenError("Invalid token: Signature verification failed"),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await get_current_user(credentials=credentials, session=session)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["error"] == "invalid_token"

    @pytest.mark.asyncio
    async def test_deleted_user_raises_401_user_unauthorized(self) -> None:
        """User deleted from DB between token issue and request => 401."""
        credentials = MagicMock()
        credentials.credentials = "valid.jwt.token"
        session = AsyncMock()

        with (
            patch(
                "app.dependencies.resolve_token",
                new_callable=AsyncMock,
                side_effect=AuthenticationError("User no longer exists"),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await get_current_user(credentials=credentials, session=session)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["error"] == "user_unauthorized"

    @pytest.mark.asyncio
    async def test_inactive_user_raises_401_user_unauthorized(self) -> None:
        """Deactivated user => 401 user_unauthorized (generic, no reason leak)."""
        credentials = MagicMock()
        credentials.credentials = "valid.jwt.token"
        session = AsyncMock()

        with (
            patch(
                "app.dependencies.resolve_token",
                new_callable=AsyncMock,
                side_effect=AuthenticationError("User is inactive"),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await get_current_user(credentials=credentials, session=session)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["error"] == "user_unauthorized"
        # The public message must NOT reveal "inactive"
        assert "inactive" not in exc_info.value.detail["message"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# require_role
# ─────────────────────────────────────────────────────────────────────────────


class TestRequireRole:
    """Tests for the require_role FastAPI dependency factory."""

    @pytest.mark.asyncio
    async def test_matching_role_passes(self) -> None:
        """User with the required role passes through unchanged."""
        user = _make_user("alice", {"admin"})
        checker = require_role({"admin"})
        result = await checker(current_user=user)
        assert result == user

    @pytest.mark.asyncio
    async def test_non_matching_role_raises_403(self) -> None:
        """User without the required role => 403 insufficient_permissions."""
        user = _make_user("engineer.demo", {"engineer"})
        checker = require_role({"admin"})

        with pytest.raises(HTTPException) as exc_info:
            await checker(current_user=user)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["error"] == "insufficient_permissions"

    @pytest.mark.asyncio
    async def test_empty_user_roles_raises_403(self) -> None:
        """User with no roles => 403 insufficient_permissions."""
        user = _make_user("novice", set())
        checker = require_role({"admin"})

        with pytest.raises(HTTPException) as exc_info:
            await checker(current_user=user)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["error"] == "insufficient_permissions"

    @pytest.mark.asyncio
    async def test_multiple_required_roles_any_match_passes(self) -> None:
        """If any of a set of allowed roles is present, access is granted."""
        user = _make_user("multi", {"auditor", "procurement"})
        checker = require_role({"auditor"})
        result = await checker(current_user=user)
        assert result == user

    @pytest.mark.asyncio
    async def test_multiple_required_roles_no_match_raises_403(self) -> None:
        """Multiple required roles, none present => 403."""
        user = _make_user("engineer.demo", {"engineer"})
        checker = require_role({"admin", "procurement"})

        with pytest.raises(HTTPException) as exc_info:
            await checker(current_user=user)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["error"] == "insufficient_permissions"
