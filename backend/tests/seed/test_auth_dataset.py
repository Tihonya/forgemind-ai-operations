"""Unit tests for WP-2.5 deterministic auth seed dataset.

Verifies exact role codes, usernames, mappings, deterministic UUIDs,
and that loader receives resolved user_id/role_id (not raw mappings).
"""

from uuid import UUID

import pytest

from app.seed.generator.auth_dataset import (
    DEMO_USERS,
    ROLES,
    USER_ROLE_MAPPINGS,
    generate_auth_dataset,
    get_role_id_by_code,
    get_user_id_by_username,
)

# ─────────────────────────────────────────────────────────────────────────────
# Exact role definitions (DEC-009)
# ─────────────────────────────────────────────────────────────────────────────


EXPECTED_ROLE_CODES = {
    "PRODUCTION_MANAGER",
    "PROCUREMENT_SPECIALIST",
    "ENGINEER",
    "AI_ADMINISTRATOR",
    "AUDITOR",
}


class TestRoleDefinitions:
    def test_exactly_five_roles(self) -> None:
        assert len(ROLES) == 5

    def test_role_codes_exact(self) -> None:
        actual_codes = {r["code"] for r in ROLES}
        assert actual_codes == EXPECTED_ROLE_CODES

    def test_roles_have_required_keys(self) -> None:
        for role in ROLES:
            assert "id" in role
            assert "code" in role
            assert "name" in role

    def test_role_ids_are_uuid5(self) -> None:
        for role in ROLES:
            assert isinstance(role["id"], UUID)
            assert role["id"].version == 5

    def test_role_ids_deterministic(self) -> None:
        dataset1 = generate_auth_dataset()
        dataset2 = generate_auth_dataset()
        ids1 = {r["id"] for r in dataset1["roles"]}
        ids2 = {r["id"] for r in dataset2["roles"]}
        assert ids1 == ids2


# ─────────────────────────────────────────────────────────────────────────────
# Exact user definitions (DEC-028)
# ─────────────────────────────────────────────────────────────────────────────


EXPECTED_USERNAMES = {
    "manager.demo",
    "procurement.demo",
    "engineer.demo",
    "admin.demo",
    "auditor.demo",
}


class TestUserDefinitions:
    def test_exactly_five_users(self) -> None:
        assert len(DEMO_USERS) == 5

    def test_usernames_exact(self) -> None:
        actual = {u["username"] for u in DEMO_USERS}
        assert actual == EXPECTED_USERNAMES

    def test_users_have_required_keys(self) -> None:
        for user in DEMO_USERS:
            assert "id" in user
            assert "username" in user
            assert "display_name" in user
            assert "is_active" in user
            # WP-2.6 adds bcrypt precomputed hashes
            assert "hashed_password" in user

    def test_no_plaintext_credentials_in_users(self) -> None:
        """WP-2.5/2.6 must NOT seed plaintext passwords or secrets.

        hashed_password IS present (WP-2.6 bcrypt) but plaintext password is not.
        """
        for user in DEMO_USERS:
            assert "password" not in user
            assert "secret" not in user
            # bcrypt hashes start with $2b$ or $2a$
            assert user["hashed_password"].startswith("$2b$")

    def test_all_users_active(self) -> None:
        for user in DEMO_USERS:
            assert user["is_active"] is True

    def test_user_ids_are_uuid5(self) -> None:
        for user in DEMO_USERS:
            assert isinstance(user["id"], UUID)
            assert user["id"].version == 5

    def test_user_ids_deterministic(self) -> None:
        dataset1 = generate_auth_dataset()
        dataset2 = generate_auth_dataset()
        ids1 = {u["id"] for u in dataset1["users"]}
        ids2 = {u["id"] for u in dataset2["users"]}
        assert ids1 == ids2


# ─────────────────────────────────────────────────────────────────────────────
# Exact user→role mappings (DEC-028)
# ─────────────────────────────────────────────────────────────────────────────


EXPECTED_MAPPING = {
    "manager.demo": "PRODUCTION_MANAGER",
    "procurement.demo": "PROCUREMENT_SPECIALIST",
    "engineer.demo": "ENGINEER",
    "admin.demo": "AI_ADMINISTRATOR",
    "auditor.demo": "AUDITOR",
}


class TestUserRoleMappings:
    def test_exactly_five_mappings(self) -> None:
        assert len(USER_ROLE_MAPPINGS) == 5

    def test_mapping_usernames(self) -> None:
        for mapping in USER_ROLE_MAPPINGS:
            assert mapping["username"] in EXPECTED_USERNAMES

    def test_mapping_role_codes(self) -> None:
        for mapping in USER_ROLE_MAPPINGS:
            assert mapping["role_code"] in EXPECTED_ROLE_CODES

    def test_exact_mapping_pairs(self) -> None:
        actual_mapping = {m["username"]: m["role_code"] for m in USER_ROLE_MAPPINGS}
        assert actual_mapping == EXPECTED_MAPPING

    def test_mapping_ids_are_uuid5(self) -> None:
        for mapping in USER_ROLE_MAPPINGS:
            assert isinstance(mapping["id"], UUID)
            assert mapping["id"].version == 5


# ─────────────────────────────────────────────────────────────────────────────
# Resolved output from generate_auth_dataset()
# ─────────────────────────────────────────────────────────────────────────────


class TestResolvedOutput:
    def test_user_roles_contain_resolved_uuids(self) -> None:
        """Loaded user_roles must contain user_id and role_id UUIDs, not strings."""
        data = generate_auth_dataset()
        for ur in data["user_roles"]:
            assert "id" in ur
            assert "user_id" in ur
            assert "role_id" in ur
            # Must NOT contain raw username/role_code
            assert "username" not in ur
            assert "role_code" not in ur
            # Values must be actual UUIDs
            assert isinstance(ur["id"], UUID)
            assert isinstance(ur["user_id"], UUID)
            assert isinstance(ur["role_id"], UUID)

    def test_resolved_user_ids_match_demo_users(self) -> None:
        data = generate_auth_dataset()
        user_ids = {u["id"] for u in data["users"]}
        for ur in data["user_roles"]:
            assert ur["user_id"] in user_ids

    def test_resolved_role_ids_match_roles(self) -> None:
        data = generate_auth_dataset()
        role_ids = {r["id"] for r in data["roles"]}
        for ur in data["user_roles"]:
            assert ur["role_id"] in role_ids

    def test_no_duplicate_user_roles(self) -> None:
        data = generate_auth_dataset()
        pairs = {(ur["user_id"], ur["role_id"]) for ur in data["user_roles"]}
        assert len(pairs) == len(data["user_roles"])


# ─────────────────────────────────────────────────────────────────────────────
# Lookup helpers
# ─────────────────────────────────────────────────────────────────────────────


class TestLookupHelpers:
    def test_get_role_id_by_code_all(self) -> None:
        for code in EXPECTED_ROLE_CODES:
            result = get_role_id_by_code(code)
            assert isinstance(result, UUID)
            assert result.version == 5

    def test_get_role_id_by_code_unknown_raises(self) -> None:
        try:
            get_role_id_by_code("NONEXISTENT")
            pytest.fail("Expected ValueError for unknown role code")  # noqa: F821
        except ValueError:
            pass

    def test_get_user_id_by_username_all(self) -> None:
        for username in EXPECTED_USERNAMES:
            result = get_user_id_by_username(username)
            assert isinstance(result, UUID)
            assert result.version == 5

    def test_get_user_id_by_username_unknown_raises(self) -> None:
        try:
            get_user_id_by_username("nonexistent")
            pytest.fail("Expected ValueError for unknown username")  # noqa: F821
        except ValueError:
            pass

    def test_helper_results_match_generate_output(self) -> None:
        data = generate_auth_dataset()
        for ur in data["user_roles"]:
            # Look up via helper
            matched_user = next(u for u in data["users"] if u["id"] == ur["user_id"])
            user_lookup = get_user_id_by_username(matched_user["username"])
            assert user_lookup == ur["user_id"]
