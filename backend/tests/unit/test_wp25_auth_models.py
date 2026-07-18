"""Unit tests for WP-2.5 authentication ORM models (Role, User, UserRole).

Verifies model metadata, column types, constraints, and relationships
without requiring a live database.
"""

from __future__ import annotations

from typing import cast

import pytest
from sqlalchemy import Table

from app.database import Base
from app.models import Role, User, UserRole

# ─────────────────────────────────────────────────────────────────────────────
# Table registration
# ─────────────────────────────────────────────────────────────────────────────


class TestAuthModelRegistration:
    """Verify auth ORM models register correctly in SQLAlchemy metadata."""

    def test_role_tablename(self) -> None:
        assert Role.__tablename__ == "roles"

    def test_user_tablename(self) -> None:
        assert User.__tablename__ == "users"

    def test_user_role_tablename(self) -> None:
        assert UserRole.__tablename__ == "user_roles"

    def test_all_auth_tables_in_metadata(self) -> None:
        auth_tables = {"roles", "users", "user_roles"}
        metadata_tables = set(Base.metadata.tables.keys())
        assert auth_tables.issubset(metadata_tables), (
            f"Missing auth tables: {auth_tables - metadata_tables}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Role model columns and constraints
# ─────────────────────────────────────────────────────────────────────────────


class TestRoleModel:
    """Verify the roles table definition."""

    def test_role_columns(self) -> None:
        cols = {c.name for c in Role.__table__.columns}
        assert cols == {"id", "code", "name"}

    def test_role_code_unique_constraint(self) -> None:
        """Role.code must have a unique index."""
        tbl = cast(Table, Role.__table__)
        idx_names = {idx.name for idx in tbl.indexes}
        assert "idx_roles_code" in idx_names

    def test_role_code_unique_flag(self) -> None:
        """idx_roles_code must be unique=True in metadata."""
        tbl = cast(Table, Role.__table__)
        for idx in tbl.indexes:
            if idx.name == "idx_roles_code":
                assert idx.unique is True
                return
        pytest.fail("idx_roles_code not found")  # noqa: F821

    def test_id_is_primary_key(self) -> None:
        assert Role.__table__.columns["id"].primary_key


# ─────────────────────────────────────────────────────────────────────────────
# User model columns and constraints
# ─────────────────────────────────────────────────────────────────────────────


class TestUserModel:
    """Verify the users table definition."""

    def test_user_columns(self) -> None:
        cols = {c.name for c in User.__table__.columns}
        assert cols == {"id", "username", "display_name", "hashed_password", "is_active"}

    def test_username_unique_index(self) -> None:
        """User.username must have a unique index."""
        tbl = cast(Table, User.__table__)
        idx_names = {idx.name for idx in tbl.indexes}
        assert "idx_users_username" in idx_names

    def test_username_index_is_unique(self) -> None:
        tbl = cast(Table, User.__table__)
        for idx in tbl.indexes:
            if idx.name == "idx_users_username":
                assert idx.unique is True
                return
        pytest.fail("idx_users_username not found")  # noqa: F821

    def test_hashed_password_is_nullable(self) -> None:
        """WP-2.5 does not seed credentials; hashed_password must be nullable."""
        col = User.__table__.columns["hashed_password"]
        assert col.nullable is True

    def test_no_plaintext_password_column(self) -> None:
        """There must be no plain password column; only hashed_password exists."""
        col_names = {c.name for c in User.__table__.columns}
        assert "password" not in col_names

    def test_is_active_not_nullable(self) -> None:
        col = User.__table__.columns["is_active"]
        assert col.nullable is False

    def test_id_is_primary_key(self) -> None:
        assert User.__table__.columns["id"].primary_key


# ─────────────────────────────────────────────────────────────────────────────
# UserRole model columns and constraints
# ─────────────────────────────────────────────────────────────────────────────


class TestUserRoleModel:
    """Verify the user_roles N:N junction table definition."""

    def test_user_role_columns(self) -> None:
        cols = {c.name for c in UserRole.__table__.columns}
        assert cols == {"id", "user_id", "role_id"}

    def test_user_role_unique_composite(self) -> None:
        """user_roles must have a unique (user_id, role_id) composite constraint."""
        tbl = cast(Table, UserRole.__table__)
        idx_names = {idx.name for idx in tbl.indexes}
        assert "idx_user_roles_user_id_role_id" in idx_names

    def test_user_role_composite_is_unique(self) -> None:
        tbl = cast(Table, UserRole.__table__)
        for idx in tbl.indexes:
            if idx.name == "idx_user_roles_user_id_role_id":
                assert idx.unique is True
                cols = {c.name for c in idx.columns}
                assert cols == {"user_id", "role_id"}
                return
        pytest.fail("idx_user_roles_user_id_role_id not found")  # noqa: F821

    def test_user_role_foreign_keys(self) -> None:
        """user_roles FKs must point to users and roles tables."""
        user_id_fk = UserRole.__table__.columns["user_id"].foreign_keys
        role_id_fk = UserRole.__table__.columns["role_id"].foreign_keys
        assert len(user_id_fk) == 1
        assert len(role_id_fk) == 1
        user_target = next(iter(user_id_fk)).column.table.name
        role_target = next(iter(role_id_fk)).column.table.name
        assert user_target == "users"
        assert role_target == "roles"

    def test_id_is_primary_key(self) -> None:
        assert UserRole.__table__.columns["id"].primary_key


# ─────────────────────────────────────────────────────────────────────────────
# N:N cardinality support
# ─────────────────────────────────────────────────────────────────────────────


class TestNNCardinality:
    """Verify the schema supports N:N (no single-role restriction)."""

    def test_no_single_role_constraint_on_user_roles(self) -> None:
        """user_roles must NOT have a unique constraint on user_id alone."""
        tbl = cast(Table, UserRole.__table__)
        for idx in tbl.indexes:
            col_names = {c.name for c in idx.columns}
            if col_names == {"user_id"} and idx.unique:
                pytest.fail(  # noqa: F821
                    "user_roles has a unique constraint on user_id alone; "
                    "this would prevent multiple roles per user"
                )

    def test_relationships_defined(self) -> None:
        """All three models must expose user_roles relationships."""
        assert hasattr(Role, "user_roles")
        assert hasattr(User, "user_roles")
        assert hasattr(UserRole, "user")
        assert hasattr(UserRole, "role")
