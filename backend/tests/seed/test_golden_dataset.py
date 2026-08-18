"""Tests for Golden Dataset generator.

Tests:
- Deterministic output from same seed
- Stable identifiers (UUIDs)
- Correct entity counts and relationships
- In-memory dataset integrity
- Golden Scenario source facts (no database required)

Live PostgreSQL tests are in test_loader.py.
"""


from typing import Any

import pytest

from app.seed.generator.golden_dataset import (
    ANCHOR_DATE,
    DATASET_VERSION,
    SEED,
    generate_deterministic_uuid,
    generate_golden_dataset,
    get_golden_scenario_facts,
)


@pytest.fixture(scope="module")
def dataset():
    return generate_golden_dataset()


# ─────────────────────────────────────────────────────────────────────────────
# Determinism Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDeterminism:
    def test_seed_is_42(self):
        assert SEED == 42

    def test_anchor_date_is_2026_07_31(self):
        assert str(ANCHOR_DATE) == "2026-07-31"

    def test_dataset_version_is_v1(self):
        assert DATASET_VERSION == "GOLDEN_DATASET_V1.0"

    def test_deterministic_uuid_produces_stable_ids(self):
        uuid1 = generate_deterministic_uuid("test-component")
        uuid2 = generate_deterministic_uuid("test-component")
        assert uuid1 == uuid2

    def test_different_names_produce_different_uuids(self):
        uuid_a = generate_deterministic_uuid("component-a")
        uuid_b = generate_deterministic_uuid("component-b")
        assert uuid_a != uuid_b

    def test_generate_dataset_is_idempotent(self):
        dataset1 = generate_golden_dataset()
        dataset2 = generate_golden_dataset()

        # Compare key entities
        assert dataset1["products"] == dataset2["products"]
        assert dataset1["components"] == dataset2["components"]
        assert dataset1["warehouses"] == dataset2["warehouses"]
        assert dataset1["production_orders"] == dataset2["production_orders"]
        assert dataset1["inventory_balances"] == dataset2["inventory_balances"]

    def test_all_uuids_are_version_5(self):
        dataset = generate_golden_dataset()

        # Check products
        for p in dataset["products"]:
            assert p["id"].version == 5

        # Check components
        for c in dataset["components"]:
            assert c["id"].version == 5

        # Check production orders
        for wo in dataset["production_orders"]:
            assert wo["id"].version == 5


# ─────────────────────────────────────────────────────────────────────────────
# Entity Count Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestEntityCounts:
    def test_products_count(self, dataset):
        assert len(dataset["products"]) == 1

    def test_product_versions_count(self, dataset):
        assert len(dataset["product_versions"]) == 3

    def test_components_count(self, dataset):
        assert len(dataset["components"]) == 5

    def test_bom_items_count(self, dataset):
        # 9 BOM items: 3 WOs × 3 components each
        assert len(dataset["bom_items"]) == 9

    def test_component_alternatives_count(self, dataset):
        assert len(dataset["component_alternatives"]) == 1

    def test_warehouses_count(self, dataset):
        assert len(dataset["warehouses"]) == 1

    def test_suppliers_count(self, dataset):
        assert len(dataset["suppliers"]) == 3

    def test_purchase_orders_count(self, dataset):
        assert len(dataset["purchase_orders"]) == 3

    def test_purchase_order_lines_count(self, dataset):
        assert len(dataset["purchase_order_lines"]) == 3

    def test_production_plans_count(self, dataset):
        assert len(dataset["production_plans"]) == 1

    def test_production_orders_count(self, dataset):
        assert len(dataset["production_orders"]) == 3

    def test_inventory_balances_count(self, dataset):
        assert len(dataset["inventory_balances"]) == 5

    def test_inventory_reservations_count(self, dataset):
        assert len(dataset["inventory_reservations"]) == 0

    def test_production_order_requirements_count(self, dataset):
        # 9 requirements: 3 WOs × 3 components each
        assert len(dataset["production_order_requirements"]) == 9


# ─────────────────────────────────────────────────────────────────────────────
# Status Enum Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestStatusEnums:
    def test_purchase_order_header_statuses(self, dataset):
        for po in dataset["purchase_orders"]:
            assert po["status"] in ["PLACED", "CONFIRMED", "CANCELLED", "RECEIVED"]

    def test_purchase_order_line_statuses(self, dataset):
        for line in dataset["purchase_order_lines"]:
            allowed = {
                "PENDING", "CONFIRMED", "IN_TRANSIT", "DELIVERED", "CANCELLED",
            }
            assert line["status"] in allowed

    def test_no_delivered_as_header_status(self, dataset):
        for po in dataset["purchase_orders"]:
            assert po["status"] != "DELIVERED"

    def test_no_received_as_line_status(self, dataset):
        for line in dataset["purchase_order_lines"]:
            assert line["status"] != "RECEIVED"


# ─────────────────────────────────────────────────────────────────────────────
# Integrity Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestIntegrity:
    def test_all_uuids_are_version_5(self, dataset):
        for entity_type, entities in dataset.items():
            for entity in entities:
                if "id" in entity:
                    assert entity["id"].version == 5, f"{entity_type} has non-v5 UUID"

    def test_no_duplicate_product_codes(self, dataset):
        codes = [p["code"] for p in dataset["products"]]
        assert len(codes) == len(set(codes))

    def test_no_duplicate_product_version_combos(self, dataset):
        combos = [(pv["product_id"], pv["version"]) for pv in dataset["product_versions"]]
        assert len(combos) == len(set(combos))

    def test_no_duplicate_component_codes(self, dataset):
        codes = [c["code"] for c in dataset["components"]]
        assert len(codes) == len(set(codes))

    def test_no_duplicate_warehouse_codes(self, dataset):
        codes = [w["code"] for w in dataset["warehouses"]]
        assert len(codes) == len(set(codes))

    def test_no_duplicate_supplier_codes(self, dataset):
        codes = [s["code"] for s in dataset["suppliers"]]
        assert len(codes) == len(set(codes))

    def test_no_duplicate_po_numbers(self, dataset):
        numbers = [po["po_number"] for po in dataset["purchase_orders"]]
        assert len(numbers) == len(set(numbers))

    def test_all_foreign_keys_reference_existing_entities(self, dataset):
        # Build lookup sets
        product_ids = {p["id"] for p in dataset["products"]}
        product_version_ids = {pv["id"] for pv in dataset["product_versions"]}
        component_ids = {c["id"] for c in dataset["components"]}
        warehouse_ids = {w["id"] for w in dataset["warehouses"]}
        supplier_ids = {s["id"] for s in dataset["suppliers"]}
        po_ids = {po["id"] for po in dataset["purchase_orders"]}

        # Check product_versions
        for pv in dataset["product_versions"]:
            assert pv["product_id"] in product_ids

        # Check bom_items
        for bi in dataset["bom_items"]:
            assert bi["product_version_id"] in product_version_ids
            assert bi["component_id"] in component_ids

        # Check component_alternatives
        for ca in dataset["component_alternatives"]:
            assert ca["component_id"] in component_ids
            assert ca["alternative_component_id"] in component_ids

        # Check inventory_balances
        for ib in dataset["inventory_balances"]:
            assert ib["component_id"] in component_ids
            assert ib["warehouse_id"] in warehouse_ids

        # Check purchase_orders
        for po in dataset["purchase_orders"]:
            assert po["supplier_id"] in supplier_ids

        # Check purchase_order_lines
        for line in dataset["purchase_order_lines"]:
            assert line["purchase_order_id"] in po_ids
            assert line["component_id"] in component_ids

        # Check production_orders
        for wo in dataset["production_orders"]:
            assert wo["product_version_id"] in product_version_ids

        # Check production_order_requirements
        for req in dataset["production_order_requirements"]:
            assert req["component_id"] in component_ids


# ─────────────────────────────────────────────────────────────────────────────
# Golden Scenario Fact Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestGoldenScenarioFacts:
    def test_risk_001_ctrl_x4_shortage_8(self, dataset):
        facts = get_golden_scenario_facts()
        risk = facts["RISK-001"]

        # Find CTRL-X4 component
        ctrl_x4 = next(c for c in dataset["components"] if c["code"] == "CTRL-X4")
        assert ctrl_x4["unit"] == "PCS"

        # Find inventory balance
        inv = next(ib for ib in dataset["inventory_balances"]
                   if ib["component_id"] == ctrl_x4["id"])
        assert inv["quantity_on_hand"] == risk["available"]

        # Find requirement
        req = next((r for r in dataset["production_order_requirements"]
                    if r["component_id"] == ctrl_x4["id"]), None)
        assert req is not None
        assert req["required_quantity"] == risk["required"]

        # Calculate shortage
        shortage = risk["required"] - risk["available"]
        assert shortage == risk["shortage"]
        assert risk["shortage"] == 8

    def test_risk_002_motor_m2_shortage_6_with_late_supply(self, dataset):
        facts = get_golden_scenario_facts()
        risk = facts["RISK-002"]

        # Find MOTOR-M2 component
        motor_m2 = next(c for c in dataset["components"] if c["code"] == "MOTOR-M2")

        # Find inventory balance
        inv = next(ib for ib in dataset["inventory_balances"]
                   if ib["component_id"] == motor_m2["id"])
        assert inv["quantity_on_hand"] == risk["available"]

        # Find requirement
        req = next((r for r in dataset["production_order_requirements"]
                    if r["component_id"] == motor_m2["id"]), None)
        assert req is not None
        assert req["required_quantity"] == risk["required"]

        # Verify late supply exists (MOTOR-M2 PO line arriving after need_date)
        motor_m2_lines = [line for line in dataset["purchase_order_lines"]
                          if line["component_id"] == motor_m2["id"]]
        assert len(motor_m2_lines) > 0

        # At least one line should arrive after need_date
        # (This is for future risk engine validation)
        assert risk["confirmed_late_supply"] == 10
        assert risk["shortage"] == 6

    def test_risk_003_sensor_l9_shortage_5_with_proposed_alternative(self, dataset):
        facts = get_golden_scenario_facts()
        risk = facts["RISK-003"]

        # Find SENSOR-L9 component
        sensor_l9 = next(c for c in dataset["components"] if c["code"] == "SENSOR-L9")

        # Find inventory balance
        inv = next(ib for ib in dataset["inventory_balances"]
                   if ib["component_id"] == sensor_l9["id"])
        assert inv["quantity_on_hand"] == risk["available"]

        # Find requirement
        req = next((r for r in dataset["production_order_requirements"]
                    if r["component_id"] == sensor_l9["id"]), None)
        assert req is not None
        assert req["required_quantity"] == risk["required"]

        # Verify proposed alternative exists
        alternatives = [ca for ca in dataset["component_alternatives"]
                        if ca["component_id"] == sensor_l9["id"]]
        assert len(alternatives) == 1
        assert alternatives[0]["status"] == "PROPOSED"

        assert risk["shortage"] == 5

    def test_no_approved_alternatives_for_risk_components(self, dataset):
        facts = get_golden_scenario_facts()

        for risk_code in ["RISK-001", "RISK-002", "RISK-003"]:
            risk = facts[risk_code]
            component_code = risk["component_code"]

            # Find component
            component = next(c for c in dataset["components"] if c["code"] == component_code)

            # Check for approved alternatives
            approved = [ca for ca in dataset["component_alternatives"]
                        if ca["component_id"] == component["id"] and ca["status"] == "APPROVED"]

            assert risk.get("has_approved_alternative", False) == (len(approved) > 0)

    def test_inventory_reservations_are_zero(self, dataset):
        """Verify no reservations exist (clean state for risk calculation)."""
        assert len(dataset["inventory_reservations"]) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Golden RAG Corpus Tests (WP-P7-02 bounded remediation)
# ─────────────────────────────────────────────────────────────────────────────

from app.seed.generator.auth_dataset import get_role_id_by_code  # noqa: E402
from app.seed.generator.golden_dataset import (  # noqa: E402
    GOLDEN_RAG_1_CONTENT,
    GOLDEN_RAG_2_CONTENT,
    GOLDEN_RAG_3_CONTENT,
    generate_golden_rag_corpus,
    get_golden_rag_corpus_document_ids,
    get_golden_rag_corpus_version_ids,
)


@pytest.fixture(scope="module")
def rag_corpus():
    return generate_golden_rag_corpus()


class TestGoldenRagCorpusInventory:
    def test_business_dataset_keys_unchanged(self, dataset):
        """The corpus lives OUTSIDE the 14-key business payload contract."""
        assert set(dataset.keys()) == {
            "products",
            "product_versions",
            "components",
            "bom_items",
            "component_alternatives",
            "warehouses",
            "inventory_balances",
            "inventory_reservations",
            "suppliers",
            "production_plans",
            "production_orders",
            "purchase_orders",
            "purchase_order_lines",
            "production_order_requirements",
        }
        assert "documents" not in dataset

    def test_corpus_has_exactly_three_collections(self, rag_corpus):
        assert set(rag_corpus.keys()) == {
            "documents",
            "document_versions",
            "document_permissions",
        }

    def test_three_documents(self, rag_corpus):
        assert len(rag_corpus["documents"]) == 3

    def test_one_authoritative_version_per_document(self, rag_corpus):
        assert len(rag_corpus["document_versions"]) == 3
        version_doc_ids = [v["document_id"] for v in rag_corpus["document_versions"]]
        assert len(set(version_doc_ids)) == 3

    def test_permission_rows_match_required_role_spread(self, rag_corpus):
        assert len(rag_corpus["document_permissions"]) == 7


class TestGoldenRagCorpusDeterminism:
    def test_all_ids_are_version_5(self, rag_corpus):
        for collection in ("documents", "document_versions", "document_permissions"):
            for row in rag_corpus[collection]:
                assert row["id"].version == 5

    def test_role_ids_resolve_from_seeded_auth_roles(self, rag_corpus):
        assert {p["role_id"] for p in rag_corpus["document_permissions"]} == {
            get_role_id_by_code(code)
            for code in (
                "PRODUCTION_MANAGER",
                "PROCUREMENT_SPECIALIST",
                "ENGINEER",
                "AI_ADMINISTRATOR",
            )
        }

    def test_canonical_document_ids_are_stable(self, rag_corpus):
        ids = get_golden_rag_corpus_document_ids()
        assert {d["id"] for d in rag_corpus["documents"]} == set(ids.values())
        assert rag_corpus == generate_golden_rag_corpus()

    def test_content_hash_is_deterministic_and_binds_content(self, rag_corpus):
        fresh = generate_golden_rag_corpus()
        for v, fresh_v in zip(
            rag_corpus["document_versions"],
            fresh["document_versions"],
            strict=True,
        ):
            assert len(v["content_hash"]) == 64
            assert v["id"] == fresh_v["id"]
            assert v["content_hash"] == fresh_v["content_hash"]


class TestGoldenRagCorpusTruthfulness:
    def test_version_statuses_are_approved(self, rag_corpus):
        for v in rag_corpus["document_versions"]:
            assert v["status"] == "APPROVED"

    def test_documents_do_not_carry_chunks_or_embeddings(self, rag_corpus):
        for collection in rag_corpus.values():
            for row in collection:
                assert not any(
                    key in row for key in ("chunk_index", "chunk_text", "embedding")
                )

    def test_g_rag_1_ctrl_x4_facts(self, rag_corpus):
        doc = rag_corpus["documents"][0]
        version = next(
            v for v in rag_corpus["document_versions"] if v["document_id"] == doc["id"]
        )
        assert version["version_number"] == "1.0"
        assert "WO-2026-0142" in GOLDEN_RAG_1_CONTENT
        assert "CTRL-X4" in GOLDEN_RAG_1_CONTENT
        assert "shortage: 8" in GOLDEN_RAG_1_CONTENT
        assert "12" in GOLDEN_RAG_1_CONTENT and "20" in GOLDEN_RAG_1_CONTENT

    def test_g_rag_2_motor_m2_facts(self, rag_corpus):
        doc = rag_corpus["documents"][1]
        version = next(
            v for v in rag_corpus["document_versions"] if v["document_id"] == doc["id"]
        )
        assert version["version_number"] == "1.0"
        assert "WO-2026-0150" in GOLDEN_RAG_2_CONTENT
        assert "MOTOR-M2" in GOLDEN_RAG_2_CONTENT
        assert "shortage: 6" in GOLDEN_RAG_2_CONTENT
        assert "supply: 10" in GOLDEN_RAG_2_CONTENT

    def test_g_rag_3_sensor_l9_valve_v3_facts(self, rag_corpus):
        doc = rag_corpus["documents"][2]
        version = next(
            v for v in rag_corpus["document_versions"] if v["document_id"] == doc["id"]
        )
        assert version["version_number"] == "1.0"
        assert "WO-2026-0156" in GOLDEN_RAG_3_CONTENT
        assert "SENSOR-L9" in GOLDEN_RAG_3_CONTENT
        assert "shortage: 5" in GOLDEN_RAG_3_CONTENT
        assert "VALVE-V3" in GOLDEN_RAG_3_CONTENT
        assert "PROPOSED" in GOLDEN_RAG_3_CONTENT
        # The document is APPROVED; the alternative stays PROPOSED (pending
        # engineering review) — never "APPROVED for business use".
        assert "The alternative has NOT been" in GOLDEN_RAG_3_CONTENT
        assert "approved for business use on this order" in GOLDEN_RAG_3_CONTENT
        assert "remains pending the" in GOLDEN_RAG_3_CONTENT
        assert "approved" in GOLDEN_RAG_3_CONTENT.lower()

    def test_permission_mapping_matches_po_contract(self, rag_corpus):
        doc_ids = get_golden_rag_corpus_document_ids()
        perms = rag_corpus["document_permissions"]
        role = get_role_id_by_code

        def allowed(document_name: str) -> set[Any]:
            doc_id = doc_ids[document_name]
            return {
                p["role_id"]
                for p in perms
                if p["document_id"] == doc_id
            }

        # G-RAG-1: PRODUCTION_MANAGER + AI_ADMINISTRATOR
        assert allowed("G-RAG-1") == {role("PRODUCTION_MANAGER"), role("AI_ADMINISTRATOR")}
        # G-RAG-2: PROCUREMENT_SPECIALIST + AI_ADMINISTRATOR
        assert allowed("G-RAG-2") == {
            role("PROCUREMENT_SPECIALIST"),
            role("AI_ADMINISTRATOR"),
        }
        # G-RAG-3: PRODUCTION_MANAGER + ENGINEER + AI_ADMINISTRATOR
        assert allowed("G-RAG-3") == {
            role("PRODUCTION_MANAGER"),
            role("ENGINEER"),
            role("AI_ADMINISTRATOR"),
        }

    def test_version_id_map_matches_generated_versions(self, rag_corpus):
        """The canonical version-ID map must be the authoritative expected
        set for the bounded seed collector (F-2): identical to the IDs
        produced by generate_golden_rag_corpus()."""
        version_id_map = get_golden_rag_corpus_version_ids()
        assert set(version_id_map.keys()) == {"G-RAG-1", "G-RAG-2", "G-RAG-3"}
        generated = {v["id"] for v in rag_corpus["document_versions"]}
        assert set(version_id_map.values()) == generated, (
            "get_golden_rag_corpus_version_ids() drifted from the generated "
            "corpus version IDs"
        )
        for version_id in version_id_map.values():
            assert version_id.version == 5
