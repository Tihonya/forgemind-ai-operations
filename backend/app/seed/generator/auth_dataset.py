"""Auth seed data generator for WP-2.5.

Generates deterministic role definitions and demo user accounts per DEC-009 and DEC-028.
Auth data is intentionally EXCLUDED from Golden Dataset V1.0 checksum to preserve
WP-2.4 integrity verification contract.
"""

from typing import Any, cast
from uuid import UUID

from app.seed.generator.golden_dataset import generate_deterministic_uuid

# Type aliases for clarity
RoleDict = dict[str, Any]
UserDict = dict[str, Any]
UserRoleMappingDict = dict[str, Any]
ResolvedUserRoleDict = dict[str, UUID]
AuthDatasetDict = dict[str, list[dict[str, Any]]]

# Canonical role definitions per DEC-009
# These 5 roles represent the complete RBAC model for Phase 2 MVP
ROLES: list[RoleDict] = [
    {
        "id": generate_deterministic_uuid("role:PRODUCTION_MANAGER"),
        "code": "PRODUCTION_MANAGER",
        "name": "Production Manager",
    },
    {
        "id": generate_deterministic_uuid("role:PROCUREMENT_SPECIALIST"),
        "code": "PROCUREMENT_SPECIALIST",
        "name": "Procurement Specialist",
    },
    {
        "id": generate_deterministic_uuid("role:ENGINEER"),
        "code": "ENGINEER",
        "name": "Engineer",
    },
    {
        "id": generate_deterministic_uuid("role:AI_ADMINISTRATOR"),
        "code": "AI_ADMINISTRATOR",
        "name": "AI Administrator",
    },
    {
        "id": generate_deterministic_uuid("role:AUDITOR"),
        "code": "AUDITOR",
        "name": "Auditor",
    },
]

# Demo user accounts per DEC-028
# Each user maps to exactly one role (Phase 2 scope)
# Precomputed bcrypt hashes (cost factor 12) for WP-2.6 authentication
DEMO_USERS: list[UserDict] = [
    {
        "id": generate_deterministic_uuid("user:manager.demo"),
        "username": "manager.demo",
        "display_name": "Production Manager",
        "hashed_password": "$2b$12$xoVwLIcKmZYsClXN9wcWwuDArbGT0ro7AYhv30DpJiHN4WcQmbyVK",
        "is_active": True,
    },
    {
        "id": generate_deterministic_uuid("user:procurement.demo"),
        "username": "procurement.demo",
        "display_name": "Procurement Specialist",
        "hashed_password": "$2b$12$o7h8Qe2mcQNPRKyitSsP3Ox9HJhxS6vAq10nzLc7BMMvJ4yLQR5WS",
        "is_active": True,
    },
    {
        "id": generate_deterministic_uuid("user:engineer.demo"),
        "username": "engineer.demo",
        "display_name": "Engineer",
        "hashed_password": "$2b$12$dS9PB25W7.k.pt0ZK.6V4uU0IH.6b1sOTj7UQKmrPM5bnFaavt1Vy",
        "is_active": True,
    },
    {
        "id": generate_deterministic_uuid("user:admin.demo"),
        "username": "admin.demo",
        "display_name": "AI Administrator",
        "hashed_password": "$2b$12$CYkHaMB9fQut622oLr5OYea7PyB4zQnxVWYMWmT5AZnbiqlx1BdGy",
        "is_active": True,
    },
    {
        "id": generate_deterministic_uuid("user:auditor.demo"),
        "username": "auditor.demo",
        "display_name": "Auditor",
        "hashed_password": "$2b$12$Fvbj44eYYdLCkv0hro2rK.TMRHTAycAkMTMLb3c8Imo/EqcChJkQG",
        "is_active": True,
    },
]

# User-to-role mappings for DEC-028 Phase 2
# Each user has exactly one role assignment
# user_roles N:N schema supports multi-role future (Phase 6+)
USER_ROLE_MAPPINGS: list[UserRoleMappingDict] = [
    {
        "id": generate_deterministic_uuid("user_role:manager.demo:PRODUCTION_MANAGER"),
        "username": "manager.demo",
        "role_code": "PRODUCTION_MANAGER",
    },
    {
        "id": generate_deterministic_uuid("user_role:procurement.demo:PROCUREMENT_SPECIALIST"),
        "username": "procurement.demo",
        "role_code": "PROCUREMENT_SPECIALIST",
    },
    {
        "id": generate_deterministic_uuid("user_role:engineer.demo:ENGINEER"),
        "username": "engineer.demo",
        "role_code": "ENGINEER",
    },
    {
        "id": generate_deterministic_uuid("user_role:admin.demo:AI_ADMINISTRATOR"),
        "username": "admin.demo",
        "role_code": "AI_ADMINISTRATOR",
    },
    {
        "id": generate_deterministic_uuid("user_role:auditor.demo:AUDITOR"),
        "username": "auditor.demo",
        "role_code": "AUDITOR",
    },
]


def generate_auth_dataset() -> AuthDatasetDict:
    """Generate complete auth dataset for seeding.

    Returns:
        Dictionary with three keys:
        - roles: 5 role definitions (with id, code, name)
        - users: 5 demo user accounts (with id, username, display_name, hashed_password, is_active)
        - user_roles: 5 role assignments (with id, user_id, role_id)

    All IDs are deterministic UUIDs (v5) for reproducible seeding.
    The user_roles contain resolved user_id/role_id UUIDs (not username/role_code).
    """
    resolved_user_roles: list[ResolvedUserRoleDict] = []
    for mapping in USER_ROLE_MAPPINGS:
        resolved_user_roles.append(
            {
                "id": mapping["id"],  # deterministic UUID from mapping definition
                "user_id": get_user_id_by_username(str(mapping["username"])),
                "role_id": get_role_id_by_code(str(mapping["role_code"])),
            }
        )

    return {
        "roles": [r.copy() for r in ROLES],
        "users": [u.copy() for u in DEMO_USERS],
        "user_roles": resolved_user_roles,
    }


def get_role_id_by_code(role_code: str) -> UUID:
    """Look up role ID by code.

    Args:
        role_code: One of PRODUCTION_MANAGER, PROCUREMENT_SPECIALIST,
                  ENGINEER, AI_ADMINISTRATOR, AUDITOR

    Returns:
        Deterministic UUID for the role

    Raises:
        ValueError: If role_code not found
    """
    for role in ROLES:
        if role["code"] == role_code:
            return cast(UUID, role["id"])
    raise ValueError(f"Unknown role code: {role_code}")


def get_user_id_by_username(username: str) -> UUID:
    """Look up user ID by username.

    Args:
        username: One of manager.demo, procurement.demo, engineer.demo,
                 admin.demo, auditor.demo

    Returns:
        Deterministic UUID for the user

    Raises:
        ValueError: If username not found
    """
    for user in DEMO_USERS:
        if user["username"] == username:
            return cast(UUID, user["id"])
    raise ValueError(f"Unknown username: {username}")
