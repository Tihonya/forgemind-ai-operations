"""User, Role, and UserRole ORM models.

Authentication data foundation (WP-2.5). Implements the DEC-028 demo
accounts and DEC-009 role definitions. No login logic, password hashing,
or JWT — those belong to WP-2.6.
"""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    pass


class Role(Base):
    """ORM representation of the ``roles`` table.

    Five canonical roles per DEC-009 / DEC-028:
    PRODUCTION_MANAGER, PROCUREMENT_SPECIALIST, ENGINEER,
    AI_ADMINISTRATOR, AUDITOR.
    """

    __tablename__ = "roles"
    __table_args__ = (
        Index("idx_roles_code", "code", unique=True),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    # Relationships
    user_roles: Mapped[list["UserRole"]] = relationship(
        back_populates="role",
        cascade="all, delete-orphan",
    )


class User(Base):
    """ORM representation of the ``users`` table.

    Demo accounts per DEC-028. The ``hashed_password`` column is
    intentionally nullable — WP-2.5 does NOT seed credentials.
    WP-2.6 will populate it with bcrypt hashes.
    """

    __tablename__ = "users"
    __table_args__ = (
        Index("idx_users_username", "username", unique=True),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    username: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
    )

    display_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    hashed_password: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=func.literal_column("true"),
    )

    # Relationships
    user_roles: Mapped[list["UserRole"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserRole(Base):
    """ORM representation of the ``user_roles`` join table.

    Supports N:N cardinality between users and roles.
    In Phase 2 each demo account has exactly one role (DEC-028),
    but the schema permits multiple roles per user.
    """

    __tablename__ = "user_roles"
    __table_args__ = (
        Index(
            "idx_user_roles_user_id_role_id",
            "user_id",
            "role_id",
            unique=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    role_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship(
        back_populates="user_roles",
    )

    role: Mapped["Role"] = relationship(
        back_populates="user_roles",
    )
