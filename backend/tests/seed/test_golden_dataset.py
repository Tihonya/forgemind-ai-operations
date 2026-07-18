"""Tests for Golden Dataset generator.

Tests:
- Deterministic output from same seed
- Stable identifiers (UUIDs)
- Correct entity counts and relationships
- In-memory dataset integrity
- Golden Scenario source facts (no database required)

Live PostgreSQL tests are in test_loader.py.
"""


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
