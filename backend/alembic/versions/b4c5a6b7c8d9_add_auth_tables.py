"""add auth tables

Revision ID: b4c5a6b7c8d9
Revises: 3f5e7a9b21cd
Create Date: 2026-07-18

WP-2.5: Authentication Data Foundation
Adds roles, users, and user_roles tables per DEC-009 and DEC-028.

Schema:
- roles: id, code, name
- users: id, username, display_name, hashed_password (nullable), is_active
- user_roles: id, user_id, role_id (N:N junction table)
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4c5a6b7c8d9"
down_revision: str | None = "3f5e7a9b21cd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create roles table (DEC-009: 5 canonical roles)
    op.create_table(
        "roles",
        sa.Column(
            "id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True
        ),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.UniqueConstraint("code", name="uq_roles_code"),
    )
    op.create_index("idx_roles_code", "roles", ["code"], unique=True)

    # Create users table (DEC-028: demo accounts)
    op.create_table(
        "users",
        sa.Column(
            "id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True
        ),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("hashed_password", sa.Text(), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )
    op.create_index("idx_users_username", "users", ["username"], unique=True)

    # Create user_roles junction table (N:N relationship)
    op.create_table(
        "user_roles",
        sa.Column(
            "id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True
        ),
        sa.Column(
            "user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column(
            "role_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_user_roles_user_id"
        ),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], name="fk_user_roles_role_id"
        ),
        sa.UniqueConstraint(
            "user_id", "role_id", name="uq_user_roles_user_role"
        ),
    )


def downgrade() -> None:
    # Drop user_roles first (depends on users and roles)
    op.drop_table("user_roles")

    # Drop users
    op.drop_table("users")

    # Drop roles
    op.drop_table("roles")
