"""Golden Dataset PostgreSQL loader.

Transactional loader for Phase 2 Golden Dataset. Implements:
- Alembic head verification
- Transaction boundaries with rollback
- Idempotent loading (safe to run multiple times)
- Preservation of Phase 1 diagnostic_jobs
- Async ingestion bridge for document versions (WP-4.3B4)

Dataset version: GOLDEN_DATASET_V1.0
"""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, create_engine, insert, or_, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models.component import BomItem, Component, ComponentAlternative
from app.models.document import Document, DocumentPermission, DocumentVersion
from app.models.product import Product, ProductVersion
from app.models.production import (
    ProductionOrder,
    ProductionOrderRequirement,
    ProductionPlan,
)
from app.models.supplier import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.user import Role, User, UserRole
from app.models.warehouse import InventoryBalance, InventoryReservation, Warehouse
from app.seed.generator.auth_dataset import (
    DEMO_USERS,
    USER_ROLE_MAPPINGS,
    generate_auth_dataset,
)
from app.seed.generator.golden_dataset import (
    ANCHOR_DATE,
    DATASET_VERSION,
    SEED,
    generate_golden_dataset,
    generate_golden_rag_corpus,
    get_golden_rag_corpus_document_ids,
    get_golden_rag_corpus_version_ids,
)

logger = logging.getLogger(__name__)

# Expected Alembic revision after WP-REC-04C procurement-task migration.
EXPECTED_ALEMBIC_HEAD = "d00f71c78f67"


def _get_sync_engine() -> Engine:
    """Create synchronous SQLAlchemy engine for loader operations.

    Returns:
        Synchronous SQLAlchemy engine
    """
    # Convert async URL to sync URL (like Alembic does)
    sync_url = settings.database_url
    if "+asyncpg" in sync_url:
        sync_url = sync_url.replace("+asyncpg", "+psycopg")

    return create_engine(sync_url, echo=False, pool_pre_ping=True)


# Create sync engine for loader operations
_sync_engine = _get_sync_engine()
_SessionFactory = sessionmaker(bind=_sync_engine)


def _find_alembic_ini() -> Path:
    """Locate alembic.ini using multiple fallback strategies.

    Strategy 1: Walk upward from this module's filesystem location.
    Strategy 2: Search from the current working directory.
    Strategy 3: Use the AIAUTOMATION_REPO_ROOT environment variable.

    Returns:
        Resolved Path to alembic.ini

    Raises:
        RuntimeError: If alembic.ini cannot be found by any strategy
    """
    import os

    candidates: list[Path] = []

    # Strategy 1: walk upward from this module
    # Module is at backend/app/seed/generator/, so backend/ is 4 levels up.
    module_root = Path(__file__).resolve().parent.parent.parent.parent
    candidates.append(module_root / "alembic.ini")

    # Strategy 2: search from current working directory
    cwd = Path.cwd()
    candidates.append(cwd / "backend" / "alembic.ini")
    candidates.append(cwd / "alembic.ini")

    # Strategy 3: AIAUTOMATION_REPO_ROOT environment variable
    repo_root_env = os.environ.get("AIAUTOMATION_REPO_ROOT")
    if repo_root_env:
        repo_root = Path(repo_root_env).resolve()
        candidates.append(repo_root / "backend" / "alembic.ini")
        candidates.append(repo_root / "alembic.ini")

    alembic_ini_path = next((p for p in candidates if p.exists()), None)
    if alembic_ini_path:
        return alembic_ini_path

    raise RuntimeError(
        f"alembic.ini not found. Tried: {', '.join(str(p) for p in candidates)}\n"
        f"Set AIAUTOMATION_REPO_ROOT or run from the repository root."
    )


def _verify_alembic_head() -> None:
    """Verify the database is at the expected Alembic revision.

    Checks three things:
      1. Alembic migration scripts declare the expected head revision.
      2. The `alembic_version` table exists in the database.
      3. The stored version matches the expected head.

    This uses direct DB queries (no alembic.ini file path lookup) for reliability
    across host/container filesystem layouts.

    Raises:
        RuntimeError: If any check fails
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    alembic_ini_path = _find_alembic_ini()
    alembic_cfg = Config(str(alembic_ini_path))
    script_dir = ScriptDirectory.from_config(alembic_cfg)
    expected_head = script_dir.get_current_head()

    if expected_head != EXPECTED_ALEMBIC_HEAD:
        raise RuntimeError(
            f"Migration scripts declare head '{expected_head}', "
            f"expected '{EXPECTED_ALEMBIC_HEAD}'. Migrations may be out of date."
        )

    # Verify actual DB state
    try:
        with _sync_engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            row = result.fetchone()
    except Exception as e:
        raise RuntimeError(f"Failed to query alembic_version: {e}") from e

    if not row:
        raise RuntimeError("alembic_version table is empty; run 'alembic upgrade head'")

    db_version = str(row[0])
    if db_version != EXPECTED_ALEMBIC_HEAD:
        raise RuntimeError(
            f"Database at revision '{db_version}', expected '{EXPECTED_ALEMBIC_HEAD}'. "
            f"Run 'alembic upgrade head' before loading seed data."
        )

    logger.info(f"Alembic revision verified: {EXPECTED_ALEMBIC_HEAD}")


def _delete_existing_business_data(session: Session) -> int:
    """Delete existing business data while preserving diagnostic_jobs.

    Returns:
        Number of records deleted

    Raises:
        Exception: If deletion fails
    """
    total_deleted = 0

    # Delete in reverse dependency order (children before parents)
    # Note: No FK from diagnostic_jobs, so it's preserved automatically

    total_deleted += session.query(ProductionOrderRequirement).delete()
    total_deleted += session.query(PurchaseOrderLine).delete()
    total_deleted += session.query(PurchaseOrder).delete()
    total_deleted += session.query(Supplier).delete()
    total_deleted += session.query(InventoryReservation).delete()
    total_deleted += session.query(InventoryBalance).delete()
    total_deleted += session.query(ProductionOrder).delete()
    total_deleted += session.query(ProductionPlan).delete()
    total_deleted += session.query(ComponentAlternative).delete()
    total_deleted += session.query(BomItem).delete()
    total_deleted += session.query(ProductVersion).delete()
    total_deleted += session.query(Product).delete()
    total_deleted += session.query(Warehouse).delete()
    total_deleted += session.query(Component).delete()

    logger.info(f"Deleted {total_deleted} existing business records")
    return total_deleted


def _delete_existing_auth_data(session: Session) -> int:
    """Reset seed-owned demo auth rows while preserving unrelated identities.

    Scope (F-1 remediation semantics):
    - seed-owned demo users and their seed-owned user-role mappings are
      deleted and recreated on every seed (mapping rows are selected by
      canonical seed-normal ID or by demo-user ownership);
    - canonical Role rows (the 5 deterministic DEC-009 role UUIDs) are NEVER
      deleted — deleting them cascades ``document_permissions.role_id``
      (document.py: role FK ON DELETE CASCADE) and silently destroyed the
      authorization binding of surviving non-Golden documents.  Canonical
      role ``code`` / ``name`` fields are updated in place by the caller's
      canonical-role sync;
    - unrelated users, unrelated roles, and unrelated user-role mappings
      are preserved.

    Returns:
        Number of records deleted (demo users + user-role mappings).
    """
    demo_user_ids = [UUID(str(user["id"])) for user in DEMO_USERS]
    seed_mapping_ids = [UUID(str(mapping["id"])) for mapping in USER_ROLE_MAPPINGS]

    # Delete only seed-owned rows: user-role mappings whose canonical ID is
    # seed-declared or whose user is a seed-declared demo user (FK order:
    # mappings first, then demo users).  Unrelated users, unrelated mappings
    # and ALL role rows are untouched; canonical role identity is synced in
    # place by _sync_roles_to_canonical().
    total_deleted = (
        session.query(UserRole)
        .filter(
            or_(
                UserRole.id.in_(seed_mapping_ids),
                UserRole.user_id.in_(demo_user_ids),
            )
        )
        .delete(synchronize_session=False)
        + session.query(User)
        .filter(User.id.in_(demo_user_ids))
        .delete(synchronize_session=False)
    )

    logger.info(f"Deleted {total_deleted} existing auth records")
    return total_deleted


def _sync_roles_to_canonical(session: Session, roles: list[dict[str, Any]]) -> None:
    """Fail-closed canonical-role upsert for the seeded auth dataset.

    The five deterministic DEC-009 Role rows keep their primary-key identity
    across seeds.  Behavior:
    - identify the deterministic seeded Role IDs;
    - insert them on a clean database;
    - update their canonical ``code`` / ``name`` fields in place on reseed;
    - NEVER delete any Role row;
    - fail closed on identity conflicts — if a canonical role code is
      already owned by a different UUID, raise instead of rewriting
      unrelated identity.

    Args:
        session: Active SQLAlchemy session (transaction owned by caller).
        roles: Canonical role definitions from generate_auth_dataset().

    Raises:
        RuntimeError: If a canonical role code is owned by a non-canonical
            UUID (identity conflict) or if a canonical ID points at a row
            whose code differs with no insert-match (integrity conflict).
    """
    canonical_by_id: dict[UUID, dict[str, Any]] = {
        UUID(str(role["id"])): role for role in roles
    }

    # Single query: all existing rows for canonical IDs in one round-trip.
    existing_rows = (
        session.query(Role)
        .filter(Role.id.in_(list(canonical_by_id.keys())))
        .all()
    )
    existing_by_id: dict[UUID, Role] = {row.id: row for row in existing_rows}

    for role_id, role_data in canonical_by_id.items():
        code = str(role_data["code"])
        name = str(role_data["name"])

        # Fail closed on code-ownership conflicts.
        owner_row = (
            session.query(Role)
            .filter(Role.code == code, Role.id != role_id)
            .first()
        )
        if owner_row is not None:
            raise RuntimeError(
                f"Canonical role code '{code}' is already owned by role "
                f"{owner_row.id}; refusing to rewrite unrelated identity"
            )

        row = existing_by_id.get(role_id)
        if row is None:
            session.execute(
                insert(Role).values(id=role_id, code=code, name=name)
            )
        else:
            # In-place update preserves primary-key identity.
            if row.code != code:
                # Canonical ID must keep its canonical code.
                raise RuntimeError(
                    f"Canonical role id {role_id} holds code '{row.code}', "
                    f"expected '{code}'; refusing to mutate unrelated identity"
                )
            if row.name != name:
                row.name = name


def _insert_products(session: Session, products: list[dict[str, Any]]) -> None:
    """Insert products into database."""
    for product_data in products:
        product = Product(**product_data)
        session.add(product)


def _insert_product_versions(
    session: Session, product_versions: list[dict[str, Any]]
) -> None:
    """Insert product versions into database."""
    for pv_data in product_versions:
        product_version = ProductVersion(**pv_data)
        session.add(product_version)


def _insert_components(session: Session, components: list[dict[str, Any]]) -> None:
    """Insert components into database."""
    for component_data in components:
        component = Component(**component_data)
        session.add(component)


def _insert_bom_items(session: Session, bom_items: list[dict[str, Any]]) -> None:
    """Insert BOM items into database."""
    for bom_item_data in bom_items:
        bom_item = BomItem(**bom_item_data)
        session.add(bom_item)


def _insert_component_alternatives(
    session: Session, component_alternatives: list[dict[str, Any]]
) -> None:
    """Insert component alternatives into database."""
    for alt_data in component_alternatives:
        alternative = ComponentAlternative(**alt_data)
        session.add(alternative)


def _insert_warehouses(session: Session, warehouses: list[dict[str, Any]]) -> None:
    """Insert warehouses into database."""
    for warehouse_data in warehouses:
        warehouse = Warehouse(**warehouse_data)
        session.add(warehouse)


def _insert_suppliers(session: Session, suppliers: list[dict[str, Any]]) -> None:
    """Insert suppliers into database."""
    for supplier_data in suppliers:
        supplier = Supplier(**supplier_data)
        session.add(supplier)


def _insert_production_plans(
    session: Session, production_plans: list[dict[str, Any]]
) -> None:
    """Insert production plans into database."""
    for plan_data in production_plans:
        plan = ProductionPlan(**plan_data)
        session.add(plan)


def _insert_production_orders(
    session: Session, production_orders: list[dict[str, Any]]
) -> None:
    """Insert production orders into database."""
    for order_data in production_orders:
        order = ProductionOrder(**order_data)
        session.add(order)


def _insert_inventory_balances(
    session: Session, inventory_balances: list[dict[str, Any]]
) -> None:
    """Insert inventory balances into database."""
    for balance_data in inventory_balances:
        balance = InventoryBalance(**balance_data)
        session.add(balance)


def _insert_inventory_reservations(
    session: Session, inventory_reservations: list[dict[str, Any]]
) -> None:
    """Insert inventory reservations into database."""
    for reservation_data in inventory_reservations:
        reservation = InventoryReservation(**reservation_data)
        session.add(reservation)


def _insert_purchase_orders(
    session: Session, purchase_orders: list[dict[str, Any]]
) -> None:
    """Insert purchase orders into database."""
    for po_data in purchase_orders:
        po = PurchaseOrder(**po_data)
        session.add(po)


def _insert_purchase_order_lines(
    session: Session, purchase_order_lines: list[dict[str, Any]]
) -> None:
    """Insert purchase order lines into database."""
    for line_data in purchase_order_lines:
        line = PurchaseOrderLine(**line_data)
        session.add(line)


def _insert_production_order_requirements(
    session: Session, production_order_requirements: list[dict[str, Any]]
) -> None:
    """Insert production order requirements into database."""
    for req_data in production_order_requirements:
        requirement = ProductionOrderRequirement(**req_data)
        session.add(requirement)


def _insert_roles(session: Session, roles: list[dict[str, Any]]) -> None:
    """Insert canonical role rows into the database.

    The main seed flow uses the identity-preserving
    ``_sync_roles_to_canonical()`` upsert instead.  This plain-insert form
    remains as the seed-family insertion primitive (used directly by
    established auth-integration tests to exercise unique-constraint
    behavior on conflicting codes).
    """
    for role_data in roles:
        role = Role(**role_data)
        session.add(role)


def _insert_users(session: Session, users: list[dict[str, Any]]) -> None:
    """Insert users into database."""
    for user_data in users:
        user = User(**user_data)
        session.add(user)


def _insert_user_roles(
    session: Session, user_roles: list[dict[str, Any]]
) -> None:
    """Insert user-role mappings into database.

    Args:
        user_roles: List of dicts with id, user_id, role_id (all UUIDs)
    """
    for ur_data in user_roles:
        user_role = UserRole(**ur_data)
        session.add(user_role)


def _delete_golden_rag_corpus(session: Session) -> int:
    """Delete previously seeded Golden RAG corpus rows (canonical IDs only).

    Deletes ONLY documents whose IDs belong to the deterministic
    ``generator.get_golden_rag_corpus_document_ids()`` canonical set.
    All FK relationships (document_versions, document_permissions,
    knowledge_chunks) cascade from documents, so the bounded delete
    removes exactly the corpus footprint without touching any other
    operator/test document.

    Returns:
        Number of deleted documents (0 on first run).
    """
    canonical_ids = list(get_golden_rag_corpus_document_ids().values())
    deleted = (
        session.query(Document)
        .filter(Document.id.in_(canonical_ids))
        .delete(synchronize_session=False)
    )
    if deleted:
        logger.info(f"Deleted {deleted} existing Golden RAG corpus document(s)")
    return deleted


def _insert_golden_rag_corpus(session: Session) -> dict[str, int]:
    """Insert the deterministic Golden RAG corpus (documents, versions,
    permissions) into the current transaction.

    No KnowledgeChunk and no embedding rows are created here: chunking and
    embedding remain owned by the ingestion phase (IngestionOrchestrator)
    via the authoritative seed bridge.

    Returns:
        Counts for documents / document_versions / document_permissions.
    """
    corpus = generate_golden_rag_corpus()

    for doc_data in corpus["documents"]:
        session.add(Document(**doc_data))
    for version_data in corpus["document_versions"]:
        session.add(DocumentVersion(**version_data))
    for permission_data in corpus["document_permissions"]:
        session.add(DocumentPermission(**permission_data))

    logger.info("Golden RAG corpus staged: 3 documents, 3 versions, 7 permissions")
    return {
        "documents": len(corpus["documents"]),
        "document_versions": len(corpus["document_versions"]),
        "document_permissions": len(corpus["document_permissions"]),
    }


def load_golden_dataset() -> dict[str, int]:
    """Load the Golden Dataset into PostgreSQL with transaction safety.

    Implements:
    - Alembic head verification
    - Delete existing auth data (preserves business data)
    - Delete existing business data (preserves diagnostic_jobs)
    - Insert all entities in dependency order (auth + business)
    - Commit transaction or rollback on failure

    Returns:
        Dictionary with counts of inserted records per entity type

    Raises:
        RuntimeError: If Alembic head is not at expected revision
        Exception: If insertion fails (transaction rolls back)
    """
    logger.info("=" * 70)
    logger.info(f"Loading Golden Dataset v{DATASET_VERSION}")
    logger.info(f"Seed: {SEED}")
    logger.info(f"Anchor Date: {ANCHOR_DATE}")
    logger.info("=" * 70)

    # Verify Alembic head
    _verify_alembic_head()

    # Generate datasets
    dataset = generate_golden_dataset()
    auth_data = generate_auth_dataset()

    # Create session and begin transaction
    session = _SessionFactory()

    try:
        # Reset seed-owned auth rows while preserving canonical role
        # primary-key identity.  Replacing the demo users and their join
        # rows here CANNOT cascade into document_permissions: the
        # deterministic canonical Role rows are never deleted, so the
        # role-side FK (ON DELETE CASCADE) of surviving non-Golden
        # document permissions stays valid across seeds.
        _delete_existing_auth_data(session)

        # Replace previously seeded Golden RAG corpus rows: deterministic
        # canonical rows owned by this seed, deleted by canonical document
        # ID only.  Both orderings relative to the auth reset are
        # FK-legal now (canonical roles survive the reset), so the delete
        # runs BEFORE the corpus re-insert below.  The cascade clears
        # document_versions, document_permissions and knowledge_chunks
        # rows for the canonical documents only; unrelated documents,
        # versions, permissions and chunks are never touched.
        _delete_golden_rag_corpus(session)

        # Delete existing business data
        deleted_count = _delete_existing_business_data(session)

        # Insert/refresh canonical roles in place (identity-preserving
        # upsert; unrelated roles are preserved by construction), then
        # recreate the seed-owned demo users and their mappings.
        _sync_roles_to_canonical(session, auth_data["roles"])
        _insert_users(session, auth_data["users"])
        _insert_user_roles(session, auth_data["user_roles"])

        # Insert the deterministic Golden RAG corpus (documents ->
        # versions -> permissions).  Chunk/embedding creation stays with
        # the async ingestion phase below.
        corpus_counts = _insert_golden_rag_corpus(session)

        # Insert business data in dependency order
        _insert_products(session, dataset["products"])
        _insert_product_versions(session, dataset["product_versions"])
        _insert_components(session, dataset["components"])
        _insert_bom_items(session, dataset["bom_items"])
        _insert_component_alternatives(session, dataset["component_alternatives"])
        _insert_warehouses(session, dataset["warehouses"])
        _insert_suppliers(session, dataset["suppliers"])
        _insert_production_plans(session, dataset["production_plans"])
        _insert_production_orders(session, dataset["production_orders"])
        _insert_inventory_balances(session, dataset["inventory_balances"])
        _insert_inventory_reservations(session, dataset["inventory_reservations"])
        _insert_purchase_orders(session, dataset["purchase_orders"])
        _insert_purchase_order_lines(session, dataset["purchase_order_lines"])
        _insert_production_order_requirements(
            session, dataset["production_order_requirements"]
        )

        # Commit transaction
        session.commit()

        logger.info("Golden Dataset loaded successfully")
        logger.info("=" * 70)

        # Return counts
        return {
            "roles": len(auth_data["roles"]),
            "users": len(auth_data["users"]),
            "user_roles": len(auth_data["user_roles"]),
            "products": len(dataset["products"]),
            "product_versions": len(dataset["product_versions"]),
            "components": len(dataset["components"]),
            "bom_items": len(dataset["bom_items"]),
            "component_alternatives": len(dataset["component_alternatives"]),
            "warehouses": len(dataset["warehouses"]),
            "suppliers": len(dataset["suppliers"]),
            "production_plans": len(dataset["production_plans"]),
            "production_orders": len(dataset["production_orders"]),
            "inventory_balances": len(dataset["inventory_balances"]),
            "inventory_reservations": len(dataset["inventory_reservations"]),
            "purchase_orders": len(dataset["purchase_orders"]),
            "purchase_order_lines": len(dataset["purchase_order_lines"]),
            "production_order_requirements": len(
                dataset["production_order_requirements"]
            ),
            "documents": corpus_counts["documents"],
            "document_versions": corpus_counts["document_versions"],
            "document_permissions": corpus_counts["document_permissions"],
            "deleted": deleted_count,
        }

    except Exception as e:
        # Rollback transaction on failure
        session.rollback()
        logger.error(f"Failed to load Golden Dataset: {e}")
        logger.error("Transaction rolled back")
        logger.error("=" * 70)
        raise
    finally:
        session.close()


@dataclass
class IngestionResult:
    """Result summary of async ingestion phase."""

    attempted_count: int
    succeeded_count: int
    failed_count: int
    failed_version_ids: list[UUID]


async def _ingest_seed_documents(version_ids: list[UUID]) -> IngestionResult:
    """Ingest all seed document versions asynchronously.

    This function is called after synchronous seed commit completes.
    Each version gets its own transaction (session + orchestrator).
    Failures are aggregated and reported without exposing sensitive details.

    Args:
        version_ids: List of DocumentVersion UUIDs to ingest

    Returns:
        IngestionResult with counts and failed version IDs

    Raises:
        RuntimeError: If critical setup fails (provider creation, etc.)
    """
    from app.database import async_session_factory
    from app.services.embedding_provider_factory import create_embedding_provider
    from app.services.ingestion import IngestionOrchestrator

    logger.info("=" * 70)
    logger.info("Phase 2: Async ingestion of seed documents")
    logger.info(f"Versions to ingest: {len(version_ids)}")
    logger.info("=" * 70)

    # Create embedding provider once (reused across all versions)
    try:
        provider = create_embedding_provider()
    except Exception as e:
        logger.error(f"Failed to create embedding provider: {type(e).__name__}")
        raise RuntimeError("Embedding provider initialization failed") from e

    failed_versions: list[UUID] = []
    succeeded_count = 0

    for version_id in version_ids:
        session = None
        try:
            # Fresh session for this version
            session = async_session_factory()

            # Fresh orchestrator with this session
            orchestrator = IngestionOrchestrator(session, provider)

            # Ingest this version
            await orchestrator.ingest_document_version(version_id)

            # Commit this version's transaction
            await session.commit()
            succeeded_count += 1

            logger.info(f"Successfully ingested version: {version_id}")

        except Exception as e:
            # Rollback this version's transaction
            if session:
                try:
                    await session.rollback()
                except Exception as rollback_error:
                    logger.warning(
                        f"Rollback failed for version {version_id}: {type(rollback_error).__name__}"
                    )

            failed_versions.append(version_id)
            # Log only the exception type, not the full message (may contain sensitive data)
            logger.error(
                f"Failed to ingest version {version_id}: {type(e).__name__}"
            )

        finally:
            # Close session
            if session:
                try:
                    await session.close()
                except Exception as close_error:
                    msg = f"Session close failed for version {version_id}: "
                    msg += f"{type(close_error).__name__}"
                    logger.warning(msg)

    # Build result summary
    result = IngestionResult(
        attempted_count=len(version_ids),
        succeeded_count=succeeded_count,
        failed_count=len(failed_versions),
        failed_version_ids=failed_versions,
    )

    logger.info("=" * 70)
    logger.info("Ingestion phase complete")
    logger.info(f"Attempted: {result.attempted_count}")
    logger.info(f"Succeeded: {result.succeeded_count}")
    logger.info(f"Failed: {result.failed_count}")
    if failed_versions:
        logger.warning(f"Failed version IDs: {[str(vid) for vid in failed_versions]}")
    logger.info("=" * 70)

    return result


def _collect_version_ids_sync() -> list[UUID]:
    """Collect exactly the canonical Golden RAG version IDs after seed commit.

    F-2 remediation semantics: the seed bridge ingests ONLY the
    deterministic Release 1 Golden RAG corpus versions.  The name is
    retained for symbol stability (established callers patch this symbol),
    but the collection is no longer database-wide: the expected canonical
    set is derived from the authoritative
    :func:`generate_golden_rag_corpus`-consistent ID helper
    (``get_golden_rag_corpus_version_ids()``), and the database is queried
    for those exact IDs — never for every DocumentVersion row.

    Fail-closed: the returned rows must exactly match the expected canonical
    set AND each must carry the retrieval-valid ``APPROVED`` status.  If the
    canonical set is incomplete or inconsistent, a RuntimeError is raised;
    the seed must never proceed on a partial Golden state at the risk of
    ingesting (or re-embedding) unrelated versions.

    Uses the existing synchronous engine to avoid a second asyncio.run call.

    Returns:
        The canonical Golden RAG version UUIDs, ordered by canonical name.

    Raises:
        RuntimeError: If any expected canonical version row is missing from
            the database or does not carry status ``APPROVED``.
    """
    expected_ids: list[UUID] = list(get_golden_rag_corpus_version_ids().values())

    with _sync_engine.connect() as conn:
        rows = conn.execute(
            select(DocumentVersion.id, DocumentVersion.status).where(
                DocumentVersion.id.in_(expected_ids)
            )
        ).all()

    found: dict[UUID, str] = {row[0]: str(row[1]) for row in rows}
    missing = [vid for vid in expected_ids if vid not in found]
    if missing:
        raise RuntimeError(
            "Golden RAG version set incomplete: "
            f"{len(missing)} canonical version(s) missing from the database"
        )
    not_approved = [vid for vid in expected_ids if found[vid] != "APPROVED"]
    if not_approved:
        raise RuntimeError(
            "Golden RAG version set inconsistent: "
            f"{len(not_approved)} canonical version(s) not in APPROVED "
            "retrieval-valid state"
        )

    return expected_ids


def main() -> None:
    """CLI entry point for seed generator.

    Two-phase execution:
    1. Synchronous seed data creation (existing behavior)
    2. Asynchronous document ingestion (new bridge)
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        # Phase 1: Synchronous seed data creation
        counts = load_golden_dataset()

        logger.info("Golden Dataset loaded successfully")
        logger.info("Inserted records:")
        for k, v in counts.items():
            logger.info(f"  {k}: {v}")

        # Collect the canonical Golden RAG version IDs after sync commit.
        # Bounded (F-2): unrelated document versions are never ingested.
        version_ids = _collect_version_ids_sync()
        logger.info(
            f"Collected {len(version_ids)} canonical Golden RAG document "
            "versions for ingestion"
        )

        # Phase 2: Asynchronous ingestion
        if version_ids:
            result = asyncio.run(_ingest_seed_documents(version_ids))

            # Exit with non-zero status if any versions failed
            if result.failed_count > 0:
                logger.error(
                    f"Ingestion completed with {result.failed_count} failure(s)"
                )
                raise SystemExit(1)

            logger.info("All seed documents ingested successfully")

    except RuntimeError as e:
        logger.error(f"Error: {e}")
        raise SystemExit(1) from None
    except SystemExit:
        # Re-raise SystemExit without wrapping
        raise
    except Exception as e:
        logger.error(f"Database error: {e}")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
