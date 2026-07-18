"""Unit tests for WP-2.6 auth service components."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import jwt
import pytest

from app.models.user import User
from app.services.auth_service import (
    AuthenticatedUser,
    AuthenticationError,
    TokenError,
    authenticate,
    issue_token,
    resolve_token,
)


def _make_mock_user(
    *,
    user_id: UUID | None = None,
    username: str = "test_user",
    is_active: bool = True,
    role_codes: list[str] | None = None,
) -> User:
    """Create a mock User with proper user_roles relationships."""
    user = MagicMock(spec=User)
    user.id = user_id or uuid4()
    user.username = username
    user.is_active = is_active

    user.user_roles = []
    if role_codes:
        if isinstance(role_codes, str):
            role_codes = [role_codes]
        for code in role_codes:
            role_mock = MagicMock()
            role_mock.code = code
            ur_mock = MagicMock()
            ur_mock.role = role_mock
            user.user_roles.append(ur_mock)

    return user


@pytest.mark.asyncio
async def test_authenticate_success() -> None:
    user = _make_mock_user(username="test_user", is_active=True, role_codes=["ADMIN", "MANAGER"])

    with (
        patch("app.services.auth_service._load_user_with_roles", return_value=user),
        patch("app.services.auth_service.verify_password", return_value=True),
    ):
        session = MagicMock()
        result_user, role_codes = await authenticate(session, "test_user", "password")

    assert result_user == user
    assert role_codes == ["ADMIN", "MANAGER"]


@pytest.mark.asyncio
async def test_authenticate_invalid_user() -> None:
    with patch("app.services.auth_service._load_user_with_roles", return_value=None):
        session = MagicMock()
        with pytest.raises(AuthenticationError, match="Invalid credentials"):
            await authenticate(session, "nonexistent", "password")


@pytest.mark.asyncio
async def test_authenticate_inactive_user() -> None:
    user = _make_mock_user(username="inactive", is_active=False)

    with patch("app.services.auth_service._load_user_with_roles", return_value=user):
        session = MagicMock()
        with pytest.raises(AuthenticationError, match="Invalid credentials"):
            await authenticate(session, "inactive", "password")


@pytest.mark.asyncio
async def test_authenticate_wrong_password() -> None:
    user = _make_mock_user(username="test_user", is_active=True)

    with (
        patch("app.services.auth_service._load_user_with_roles", return_value=user),
        patch("app.services.auth_service.verify_password", return_value=False),
    ):
        session = MagicMock()
        with pytest.raises(AuthenticationError, match="Invalid credentials"):
            await authenticate(session, "test_user", "wrong_password")


@pytest.mark.asyncio
async def test_authenticate_all_errors_generic() -> None:
    """All auth failures return identical generic message (no user enumeration)."""
    session = MagicMock()
    messages = []

    # Case 1: user not found
    with patch("app.services.auth_service._load_user_with_roles", return_value=None):
        try:
            await authenticate(session, "nonexistent", "password")
        except AuthenticationError as e:
            messages.append(str(e))

    # Case 2: inactive user
    inactive = _make_mock_user(username="inactive", is_active=False)
    with patch("app.services.auth_service._load_user_with_roles", return_value=inactive):
        try:
            await authenticate(session, "inactive", "password")
        except AuthenticationError as e:
            messages.append(str(e))

    # Case 3: wrong password
    active = _make_mock_user(username="active", is_active=True)
    with (
        patch("app.services.auth_service._load_user_with_roles", return_value=active),
        patch("app.services.auth_service.verify_password", return_value=False),
    ):
        try:
            await authenticate(session, "active", "wrong")
        except AuthenticationError as e:
            messages.append(str(e))

    # All messages must be identical
    assert len(messages) == 3
    assert messages[0] == messages[1] == messages[2] == "Invalid credentials"


def test_issue_token_returns_jwt() -> None:
    user = _make_mock_user(role_codes=["ADMIN"])
    token = issue_token(user, ["ADMIN"])
    assert isinstance(token, str)
    assert len(token.split(".")) == 3


def test_issue_token_claims() -> None:
    user = _make_mock_user(role_codes=["ADMIN"])
    token = issue_token(user, ["ADMIN"])

    payload = jwt.decode(token, options={"verify_signature": False})
    assert payload["sub"] == str(user.id)
    assert payload["roles"] == ["ADMIN"]
    assert payload["iss"] == "forgemind-api"
    assert "exp" in payload
    assert "iat" in payload


def test_issue_token_expiry() -> None:
    user = _make_mock_user(role_codes=["ADMIN"])
    token = issue_token(user, ["ADMIN"])

    payload = jwt.decode(token, options={"verify_signature": False})
    expected_exp = payload["iat"] + (30 * 60)  # 30 minutes
    assert payload["exp"] == expected_exp


@pytest.mark.asyncio
async def test_resolve_token_success() -> None:
    """token resolves → DB user with roles reloaded from DB, not taken from token."""
    user_id = uuid4()
    user = _make_mock_user(user_id=user_id, username="test_user", role_codes=["ADMIN"])

    token = issue_token(user, ["ADMIN"])

    db_user = _make_mock_user(user_id=user_id, username="db_user", role_codes=["MANAGER"])

    with (
        patch("app.services.auth_service.select") as mock_select,
        patch.object(MagicMock(return_value=None), "execute", new_callable=lambda: MagicMock),
    ):
        # Build query chain: select().where().options().scalar_one_or_none()
        stmt = MagicMock()
        mock_select.return_value = stmt

        session = MagicMock()

        async def mock_execute(s):
            result = MagicMock()
            result.scalar_one_or_none.return_value = db_user
            return result

        session.execute = mock_execute

        # This won't work due to complex async query chain. Use different approach.
        pass

    # Direct test: create token, manually resolve via patched decode
    with patch("app.services.auth_service.decode_access_token") as mock_decode:
        mock_decode.return_value = {
            "sub": str(user_id),
            "roles": ["ADMIN"],
            "iss": "forgemind-api",
            "exp": 9999999999,
            "iat": 0,
        }

        session = MagicMock()

        async def mock_db_execute(stmt):
            result = MagicMock()
            result.scalar_one_or_none.return_value = db_user
            return result

        session.execute = mock_db_execute

        # Need to patch the select() to return a proper chain
        with patch("app.services.auth_service.select") as mock_select:
            chain = MagicMock()
            mock_select.return_value = chain
            chain.where.return_value = chain
            chain.options.return_value = chain

            auth_user = await resolve_token(session, token)

    assert isinstance(auth_user, AuthenticatedUser)
    assert auth_user.user_id == user_id
    assert auth_user.username == "db_user"
    assert auth_user.roles == frozenset(["MANAGER"])


@pytest.mark.asyncio
async def test_resolve_token_expired() -> None:
    token = issue_token(_make_mock_user(role_codes=["ADMIN"]), ["ADMIN"])

    # Patch decode to raise expired
    with patch("app.services.auth_service.decode_access_token") as mock_decode:
        mock_decode.side_effect = jwt.ExpiredSignatureError("Token expired")

        session = MagicMock()
        with pytest.raises(TokenError, match="expired"):
            await resolve_token(session, token)


@pytest.mark.asyncio
async def test_resolve_token_invalid_signature() -> None:
    fake_token = jwt.encode(
        {"sub": str(uuid4()), "roles": [], "exp": 0, "iat": 0},
        "wrong-key",
        algorithm="HS256",
    )

    with patch("app.services.auth_service.decode_access_token") as mock_decode:
        mock_decode.side_effect = jwt.InvalidSignatureError("Signature verification failed")

        session = MagicMock()
        with pytest.raises(TokenError, match="Invalid token"):
            await resolve_token(session, fake_token)


@pytest.mark.asyncio
async def test_resolve_token_user_not_in_db() -> None:
    user_id = uuid4()
    token = issue_token(_make_mock_user(user_id=user_id, role_codes=["ADMIN"]), ["ADMIN"])

    with patch("app.services.auth_service.decode_access_token") as mock_decode:
        mock_decode.return_value = {
            "sub": str(user_id),
            "roles": ["ADMIN"],
            "iss": "forgeforgemind-api",
            "exp": 9999999999,
            "iat": 0,
        }

        session = MagicMock()

        async def mock_db_execute(stmt):
            result = MagicMock()
            result.scalar_one_or_none.return_value = None  # User not found
            return result

        session.execute = mock_db_execute

        with patch("app.services.auth_service.select") as mock_select:
            chain = MagicMock()
            mock_select.return_value = chain
            chain.where.return_value = chain
            chain.options.return_value = chain

            with pytest.raises(AuthenticationError, match="no longer exists"):
                await resolve_token(session, token)
