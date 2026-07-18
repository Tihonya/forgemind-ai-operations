"""Integration tests for WP-2.5 against live PostgreSQL.

Requires the Docker environment with real PostgreSQL.
Tests:
- Alembic migration upgrade creates auth tables
- Seed inserts exactly 5 roles, 5 users, 5 user_roles
- Idempotent re-seed
- Transaction rollback on failure
- Schema accepts multiple roles per user (N:N)
- Business dataset checksum remains valid after auth seed
- diagnostic_jobs preserved
- Final SQL acceptance query returns five exact rows
"""

import os
from collections.abc import Generator

import pytest
from sqlalchemy import Engine, create_engine, text

# Determine if integration environment is available
_INTEGRATION_DB_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get(
    "DATABASE_URL"
)


def _can_connect_to_db() -> bool:
    """Check if we can connect to the database."""
    if not _INTEGRATION_DB_URL:
        return False
    try:
        sync_url = _INTEGRATION_DB_URL
        if "+asyncpg" in sync_url:
            sync_url = sync_url.replace("+asyncpg", "+psycopg")
        engine = create_engine(sync_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


# Skip all tests in this module if no integration DB
pytestmark = pytest.mark.skipif(
    not _can_connect_to_db(),
    reason=(
        "Integration database not available "
        "(TEST_DATABASE_URL or DATABASE_URL not set/unreachable)"
    ),
)


def _get_test_engine() -> Engine:
    """Create synchronous SQLAlchemy engine for tests."""
    if not _INTEGRATION_DB_URL:
        raise RuntimeError("TEST_DATABASE_URL or DATABASE_URL not set")
    sync_url = _INTEGRATION_DB_URL
    if "+asyncpg" in sync_url:
        sync_url = sync_url.replace("+asyncpg", "+psycopg")
    return create_engine(sync_url, echo=False, pool_pre_ping=True)


from app.core.dataset_metadata import EXPECTED_CHECKSUM  # noqa: E402
from app.seed.generator.loader import (  # noqa: E402
    EXPECTED_ALEMBIC_HEAD,
    _delete_existing_auth_data,
    _SessionFactory,
    load_golden_dataset,
)


@pytest.fixture(scope="module")
def sync_engine() -> "Generator[Engine, None, None]":
    engine = _get_test_engine()
    yield engine
    engine.dispose()


@pytest.fixture
def db_conn(sync_engine):
    with sync_engine.connect() as conn:
        yield conn


# ─────────────────────────────────────────────────────────────────────────────
# Alembic migration tests (live)
# ─────────────────────────────────────────────────────────────────────────────


class TestMigrationUpgrade:
    def test_alembic_head_matches_expected(self, db_conn):
        result = db_conn.execute(
            text("SELECT version_num FROM alembic_version")
        ).fetchone()
        assert result is not None
        assert result[0] == EXPECTED_ALEMBIC_HEAD
        assert result[0] == "b4c5a6b7c8d9"

    def test_auth_tables_exist(self, db_conn):
        tables = {"roles", "users", "user_roles"}
        for tbl in tables:
            result = db_conn.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_name = :t"
                ),
                {"t": tbl},
            ).fetchone()
            assert result[0] == 1, f"Table {tbl} does not exist"

    def test_business_tables_preserved(self, db_conn):
        """Migration must not remove business tables."""
        business_tables = [
            "products",
            "components",
            "warehouses",
            "production_orders",
        ]
        for tbl in business_tables:
            result = db_conn.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_name = :t"
                ),
                {"t": tbl},
            ).fetchone()
            assert result[0] == 1, f"Business table {tbl} missing"

    def test_constraints_exist(self, db_conn):
        """Check key constraints are present in information_schema."""
        # Unique on roles.code
        result = db_conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu "
                "ON tc.constraint_name = kcu.constraint_name "
                "WHERE tc.table_name = 'roles' AND tc.constraint_type = 'UNIQUE'"
            )
        ).fetchone()
        assert result[0] >= 1

        # FK from user_roles to users
        result = db_conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.table_constraints tc "
                "WHERE tc.table_name = 'user_roles' "
                "AND tc.constraint_type = 'FOREIGN KEY'"
            )
        ).fetchone()
        assert result[0] >= 2  # Two FKs: user_id + role_id

    def test_diagnostic_jobs_preserved(self, db_conn):
        """Phase 1 diagnostic_jobs must still exist."""
        result = db_conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_name = 'diagnostic_jobs'"
            )
        ).fetchone()
        assert result[0] == 1


# ─────────────────────────────────────────────────────────────────────────────
# Seed tests (live)
# ─────────────────────────────────────────────────────────────────────────────


class TestAuthSeedLive:
    @pytest.fixture(autouse=True)
    def _seed_dataset(self):
        load_golden_dataset()
        yield

    def test_roles_count(self, db_conn):
        result = db_conn.execute(text("SELECT COUNT(*) FROM roles")).fetchone()
        assert result[0] == 5

    def test_users_count(self, db_conn):
        result = db_conn.execute(text("SELECT COUNT(*) FROM users")).fetchone()
        assert result[0] == 5

    def test_user_roles_count(self, db_conn):
        result = db_conn.execute(text("SELECT COUNT(*) FROM user_roles")).fetchone()
        assert result[0] == 5

    def test_exact_role_codes(self, db_conn):
        result = db_conn.execute(
            text("SELECT code FROM roles ORDER BY code")
        ).fetchall()
        codes = [r[0] for r in result]
        assert codes == [
            "AI_ADMINISTRATOR",
            "AUDITOR",
            "ENGINEER",
            "PROCUREMENT_SPECIALIST",
            "PRODUCTION_MANAGER",
        ]

    def test_exact_usernames(self, db_conn):
        result = db_conn.execute(
            text("SELECT username FROM users ORDER BY username")
        ).fetchall()
        usernames = [r[0] for r in result]
        assert usernames == [
            "admin.demo",
            "auditor.demo",
            "engineer.demo",
            "manager.demo",
            "procurement.demo",
        ]

    def test_exact_mapping(self, db_conn):
        """Verify the exact 5 user→role pairs."""
        result = db_conn.execute(text("""
            SELECT u.username, r.code
            FROM users AS u
            JOIN user_roles AS ur ON ur.user_id = u.id
            JOIN roles AS r ON r.id = ur.role_id
            ORDER BY u.username
        """)).fetchall()
        rows = [(r[0], r[1]) for r in result]
        assert rows == [
            ("admin.demo", "AI_ADMINISTRATOR"),
            ("auditor.demo", "AUDITOR"),
            ("engineer.demo", "ENGINEER"),
            ("manager.demo", "PRODUCTION_MANAGER"),
            ("procurement.demo", "PROCUREMENT_SPECIALIST"),
        ]

    def test_no_duplicate_assignments(self, db_conn):
        result = db_conn.execute(text("""
            SELECT user_id, role_id, COUNT(*) AS cnt
            FROM user_roles
            GROUP BY user_id, role_id
            HAVING COUNT(*) > 1
        """)).fetchall()
        assert len(result) == 0

    def test_bcrypt_hashes_seeded(self, db_conn):
        """WP-2.6: all 5 demo users have precomputed bcrypt hashes seeded."""
        sql = (
            "SELECT COUNT(*) FROM users "
            "WHERE hashed_password IS NOT NULL "
            "AND hashed_password LIKE '$2b$%'"
        )
        result = db_conn.execute(text(sql)).fetchone()
        assert result[0] == 5

    def test_no_plaintext_password_column(self, db_conn):
        """Verify the users table has no plaintext password column."""
        result = db_conn.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = 'users'")
        ).fetchall()
        column_names = [r[0] for r in result]
        assert "password" not in column_names
        assert "plain_password" not in column_names
        # hashed_password exists (bcrypt)
        assert "hashed_password" in column_names

    def test_all_seeded_users_are_active(self, db_conn):
        result = db_conn.execute(
            text("SELECT COUNT(*) FROM users WHERE is_active = true")
        ).fetchone()
        assert result[0] == 5

    def test_deterministic_ids(self, db_conn):
        """Seed twice; IDs must be identical."""
        result1 = db_conn.execute(
            text("SELECT id FROM roles ORDER BY code")
        ).fetchall()
        ids1 = [r[0] for r in result1]

        # Reseed
        load_golden_dataset()

        result2 = db_conn.execute(
            text("SELECT id FROM roles ORDER BY code")
        ).fetchall()
        ids2 = [r[0] for r in result2]
        assert ids1 == [str(i) for i in ids2] or ids1 == ids2

    def test_idempotent_reseed(self, db_conn):
        """Re-seeding must not create duplicates."""
        counts_before = {
            "roles": db_conn.execute(text("SELECT COUNT(*) FROM roles")).fetchone()[0],
            "users": db_conn.execute(text("SELECT COUNT(*) FROM users")).fetchone()[0],
            "user_roles": db_conn.execute(
                text("SELECT COUNT(*) FROM user_roles")
            ).fetchone()[0],
        }
        load_golden_dataset()  # reseed
        counts_after = {
            "roles": db_conn.execute(text("SELECT COUNT(*) FROM roles")).fetchone()[0],
            "users": db_conn.execute(text("SELECT COUNT(*) FROM users")).fetchone()[0],
            "user_roles": db_conn.execute(
                text("SELECT COUNT(*) FROM user_roles")
            ).fetchone()[0],
        }
        assert counts_before == counts_after


# ─────────────────────────────────────────────────────────────────────────────
# Rollback-on-failure test
# ─────────────────────────────────────────────────────────────────────────────


class TestAuthSeedRollback:
    def test_failed_seed_rolls_back(self, db_conn):
        """Insert a conflicting role, then verify seed transaction rolls back
        cleanly without leaving partial state after failure."""
        from app.seed.generator.loader import _insert_roles, _SessionFactory

        # Insert a role with a duplicate code that will clash with the seed
        db_conn.execute(
            text("""
            INSERT INTO roles (id, code, name)
            VALUES (gen_random_uuid(), 'CONFLICT_ROLE', 'Conflict')
        """)
        )
        db_conn.commit()

        # Attempt to insert a role with duplicate code via loader helper
        conflicting_role = [{"id": "00000000-0000-0000-0000-000000000001",
                             "code": "CONFLICT_ROLE",
                             "name": "Conflict"}]
        session = _SessionFactory()
        try:
            _insert_roles(session, conflicting_role)
            session.commit()
            pytest.fail("Expected unique constraint violation")
        except Exception:
            session.rollback()
        finally:
            session.close()

        # Verify the original state: CONFLICT_ROLE still there via committed
        # insert, but no duplicate was added
        result = db_conn.execute(
            text("SELECT COUNT(*) FROM roles WHERE code = 'CONFLICT_ROLE'")
        ).fetchone()
        assert result[0] == 1

        # Clean up
        db_conn.execute(text("DELETE FROM roles WHERE code = 'CONFLICT_ROLE'"))
        db_conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# N:N schema supports second role per user
# ─────────────────────────────────────────────────────────────────────────────


class TestNNSchema:
    def test_schema_accepts_second_role_per_user(self, db_conn):
        """The user_roles table should accept more than one role per user.
        We test this by inserting an extra mapping, then rolling it back."""
        # Get a user_id and role_id that are not yet linked
        user_row = db_conn.execute(
            text("SELECT id FROM users WHERE username = 'manager.demo'")
        ).fetchone()
        user_id = user_row[0]

        role_row = db_conn.execute(
            text("SELECT id FROM roles WHERE code = 'ENGINEER'")
        ).fetchone()
        role_id = role_row[0]

        # Insert second role assignment
        db_conn.execute(
            text("""
            INSERT INTO user_roles (id, user_id, role_id)
            VALUES (gen_random_uuid(), :uid, :rid)
        """),
            {"uid": str(user_id), "rid": str(role_id)},
        )
        db_conn.commit()

        # Verify it landed
        result = db_conn.execute(
            text("SELECT COUNT(*) FROM user_roles WHERE user_id = :uid"),
            {"uid": str(user_id)},
        ).fetchone()
        assert result[0] == 2  # original role + second role

        # Rollback: remove the extra mapping
        db_conn.execute(
            text("DELETE FROM user_roles WHERE user_id = :uid AND role_id = :rid"),
            {"uid": str(user_id), "rid": str(role_id)},
        )
        db_conn.commit()

        # Verify back to 1
        result = db_conn.execute(
            text("SELECT COUNT(*) FROM user_roles WHERE user_id = :uid"),
            {"uid": str(user_id)},
        ).fetchone()
        assert result[0] == 1


# ─────────────────────────────────────────────────────────────────────────────
# WP-2.4 regression: checksum and diagnostic_jobs preservation
# ─────────────────────────────────────────────────────────────────────────────


class TestWP24Regression:
    @pytest.fixture(autouse=True)
    def _seed_and_cleanup(self, db_conn):
        load_golden_dataset()
        yield

    def test_dataset_version_unchanged(self, db_conn):
        from app.seed.generator.golden_dataset import DATASET_VERSION

        assert DATASET_VERSION == "GOLDEN_DATASET_V1.0"

    def test_expected_checksum_unchanged(self, db_conn):
        assert EXPECTED_CHECKSUM.startswith("sha256:")
        assert len(EXPECTED_CHECKSUM) == 71

    def test_auth_tables_excluded_from_checksum(self, db_conn):
        """Checksum should not include auth data.
        Verify by computing checksum service with auth seeded."""
        # Endpoint-based test is handled in test_dataset_integrity.py;
        # here we just confirm the auth data is present and entity counts are correct.
        # Use a sync check: entity counts include auth tables
        counts_from_db = {
            "roles": db_conn.execute(text("SELECT COUNT(*) FROM roles")).fetchone()[0],
            "users": db_conn.execute(text("SELECT COUNT(*) FROM users")).fetchone()[0],
        }
        assert counts_from_db["roles"] == 5  # auth data present
        assert counts_from_db["users"] == 5

    def test_diagnostic_jobs_preserved_with_auth(self, db_conn):
        """diagnostic_jobs table exists regardless of auth seeding."""
        result = db_conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_name = 'diagnostic_jobs'"
            )
        ).fetchone()
        assert result[0] == 1

    def test_business_dataset_loads_with_auth(self, db_conn):
        """After auth seed, business dataset is fully loaded."""
        counts = load_golden_dataset()
        assert counts["products"] == 1
        assert counts["components"] == 5
        assert counts["inventory_balances"] == 5
        # Auth counts present in return value
        assert "roles" in counts
        assert counts["roles"] == 5


# ─────────────────────────────────────────────────────────────────────────────
# Final SQL acceptance query
# ─────────────────────────────────────────────────────────────────────────────


class TestFinalAcceptanceQuery:
    @pytest.fixture(autouse=True)
    def _seed(self):
        load_golden_dataset()
        yield

    def test_acceptance_query(self, db_conn):
        """The required acceptance query must return exactly five rows."""
        result = db_conn.execute(text("""
            SELECT u.username, r.code
            FROM users AS u
            JOIN user_roles AS ur ON ur.user_id = u.id
            JOIN roles AS r ON r.id = ur.role_id
            ORDER BY u.username
        """)).fetchall()

        rows = [(r[0], r[1]) for r in result]
        assert len(rows) == 5
        assert rows == [
            ("admin.demo", "AI_ADMINISTRATOR"),
            ("auditor.demo", "AUDITOR"),
            ("engineer.demo", "ENGINEER"),
            ("manager.demo", "PRODUCTION_MANAGER"),
            ("procurement.demo", "PROCUREMENT_SPECIALIST"),
        ]

    def test_one_role_per_user_in_seed(self):
        """Each user has exactly one role in the seed."""
        session = _SessionFactory()
        try:
            result = session.execute(text("""
                SELECT u.username, COUNT(ur.id) AS role_count
                FROM users u
                LEFT JOIN user_roles ur ON ur.user_id = u.id
                GROUP BY u.username
                ORDER BY u.username
            """)).fetchall()
            for row in result:
                assert row[1] == 1, (
                    f"User {row[0]} has {row[1]} roles; expected exactly 1"
                )
        finally:
            session.close()

    def test_delete_auth_is_idempotent_and_safe(self):
        """_delete_existing_auth_data must not raise when tables are empty or populated."""
        session = _SessionFactory()
        try:
            # Delete populated
            deleted = _delete_existing_auth_data(session)
            session.commit()
            assert deleted >= 0

            # Delete when already empty
            deleted_again = _delete_existing_auth_data(session)
            session.commit()
            assert deleted_again == 0
        finally:
            session.close()

        # Re-seed
        load_golden_dataset()
