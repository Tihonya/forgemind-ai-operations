"""Golden Dataset definition for Phase 2.

Deterministic synthetic data producing RISK-001, RISK-002, RISK-003 facts.

All identifiers, quantities, dates, and relationships are derived from:
- Fixed seed: 42
- Anchor date: 2026-07-31 (ISO format)
- Deterministic UUID generation using uuid5 with stable namespace

Dataset version: GOLDEN_DATASET_V1.0

Architecture:
- 1 product (PROD-PUMP-001)
- 3 product versions (2.1, 2.2, 2.3) — each with a different BOM set
  so each WO triggers exactly one shortage
- 5 components (CTRL-X4, MOTOR-M2, SENSOR-L9, VALVE-V3, PIPE-P1)
- 1 component alternative (SENSOR-L9 → VALVE-V3, PROPOSED)
- 1 warehouse (WH-MAIN)
- 3 suppliers
- 1 production plan (PLAN-2026-W31)
- 3 production orders (WO-2026-0142, WO-2026-0150, WO-2026-0156)
- 5 inventory balances
- 3 purchase orders with 3 lines
- 15 production order requirements (3 WOs × 5 components each)

Risk-scenario design:
  Each product version's BOM contains only the risk component (qty=1) plus
  two safe components with sufficient stock. This ensures each WO contributes
  exactly one shortage to the risk engine.

  WO-2026-0142 uses version 2.1 (BOM: CTRL-X4, VALVE-V3, PIPE-P1)
    → CTRL-X4 shortage=8 → RISK-001 CRITICAL

  WO-2026-0150 uses version 2.2 (BOM: MOTOR-M2, VALVE-V3, PIPE-P1)
    → MOTOR-M2 shortage=6 with late confirmed supply=10 → RISK-002 HIGH

  WO-2026-0156 uses version 2.3 (BOM: SENSOR-L9, VALVE-V3, PIPE-P1)
    → SENSOR-L9 shortage=5 with proposed alternative → RISK-003 MEDIUM
"""

import uuid
from collections import OrderedDict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

# Fixed seed for reproducibility
SEED = 42

# Anchor date (ISO format)
ANCHOR_DATE = date(2026, 7, 31)

# Dataset version
DATASET_VERSION = "GOLDEN_DATASET_V1.0"

# Deterministic UUID namespace (stable, known RFC 4122 UUID)
DETERMINISTIC_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def generate_deterministic_uuid(name: str) -> uuid.UUID:
    """Generate deterministic UUID using uuid5 with stable namespace.

    Args:
        name: Business identifier or unique name

    Returns:
        Deterministic UUID (version 5)
    """
    return uuid.uuid5(DETERMINISTIC_NAMESPACE, f"golden-dataset-v1:{name}")


def generate_golden_dataset() -> dict[str, Any]:
    """Generate the Phase 2 Golden Dataset.

    Returns:
        Dictionary containing all dataset entities with deterministic data
    """

    dataset: dict[str, Any] = OrderedDict()

    # ═══════════════════════════════════════════════════════════════
    # PRODUCTS (1 product)
    # ═══════════════════════════════════════════════════════════════
    products = [
        {
            "id": generate_deterministic_uuid("PROD-PUMP-001"),
            "code": "PROD-PUMP-001",
            "name": "Industrial Pump MK-III",
            "description": "Heavy-duty industrial pump for manufacturing plants",
        }
    ]
    dataset["products"] = products

    # ═══════════════════════════════════════════════════════════════
    # PRODUCT VERSIONS (3 versions — one per WO)
    # ═══════════════════════════════════════════════════════════════
    product_versions = [
        {
            "id": generate_deterministic_uuid("PROD-PUMP-001-v2.1"),
            "product_id": products[0]["id"],
            "version": "2.1",
            "status": "RELEASED",
        },
        {
            "id": generate_deterministic_uuid("PROD-PUMP-001-v2.2"),
            "product_id": products[0]["id"],
            "version": "2.2",
            "status": "RELEASED",
        },
        {
            "id": generate_deterministic_uuid("PROD-PUMP-001-v2.3"),
            "product_id": products[0]["id"],
            "version": "2.3",
            "status": "RELEASED",
        },
    ]
    dataset["product_versions"] = product_versions

    # ═══════════════════════════════════════════════════════════════
    # COMPONENTS (5 components)
    # ═══════════════════════════════════════════════════════════════
    components = [
        {
            "id": generate_deterministic_uuid("CTRL-X4"),
            "code": "CTRL-X4",
            "name": "Control Unit X4",
            "unit": "PCS",
            "description": "Electronic control module",
        },
        {
            "id": generate_deterministic_uuid("MOTOR-M2"),
            "code": "MOTOR-M2",
            "name": "Motor M2",
            "unit": "PCS",
            "description": "High-efficiency motor",
        },
        {
            "id": generate_deterministic_uuid("SENSOR-L9"),
            "code": "SENSOR-L9",
            "name": "Sensor L9",
            "unit": "PCS",
            "description": "Pressure sensor module",
        },
        {
            "id": generate_deterministic_uuid("VALVE-V3"),
            "code": "VALVE-V3",
            "name": "Valve V3",
            "unit": "PCS",
            "description": "Flow control valve",
        },
        {
            "id": generate_deterministic_uuid("PIPE-P1"),
            "code": "PIPE-P1",
            "name": "Pipe P1",
            "unit": "PCS",
            "description": "Stainless steel pipe segment",
        },
    ]
    dataset["components"] = components

    # ═══════════════════════════════════════════════════════════════
    # BOM ITEMS (per product version — 3 components each, 9 total)
    # ═══════════════════════════════════════════════════════════════
    # Version 2.1 (WO-2026-0142): CTRL-X4 (risk), VALVE-V3, PIPE-P1
    # Version 2.2 (WO-2026-0150): MOTOR-M2 (risk), VALVE-V3, PIPE-P1
    # Version 2.3 (WO-2026-0156): SENSOR-L9 (risk), VALVE-V3, PIPE-P1
    bom_items = [
        # Version 2.1 BOM
        {
            "id": generate_deterministic_uuid("v2.1-CTRL-X4"),
            "product_version_id": product_versions[0]["id"],
            "component_id": components[0]["id"],  # CTRL-X4
            "quantity_per_unit": Decimal("1.0000"),
        },
        {
            "id": generate_deterministic_uuid("v2.1-VALVE-V3"),
            "product_version_id": product_versions[0]["id"],
            "component_id": components[3]["id"],  # VALVE-V3
            "quantity_per_unit": Decimal("2.0000"),
        },
        {
            "id": generate_deterministic_uuid("v2.1-PIPE-P1"),
            "product_version_id": product_versions[0]["id"],
            "component_id": components[4]["id"],  # PIPE-P1
            "quantity_per_unit": Decimal("3.0000"),
        },
        # Version 2.2 BOM
        {
            "id": generate_deterministic_uuid("v2.2-MOTOR-M2"),
            "product_version_id": product_versions[1]["id"],
            "component_id": components[1]["id"],  # MOTOR-M2
            "quantity_per_unit": Decimal("1.0000"),
        },
        {
            "id": generate_deterministic_uuid("v2.2-VALVE-V3"),
            "product_version_id": product_versions[1]["id"],
            "component_id": components[3]["id"],  # VALVE-V3
            "quantity_per_unit": Decimal("2.0000"),
        },
        {
            "id": generate_deterministic_uuid("v2.2-PIPE-P1"),
            "product_version_id": product_versions[1]["id"],
            "component_id": components[4]["id"],  # PIPE-P1
            "quantity_per_unit": Decimal("3.0000"),
        },
        # Version 2.3 BOM
        {
            "id": generate_deterministic_uuid("v2.3-SENSOR-L9"),
            "product_version_id": product_versions[2]["id"],
            "component_id": components[2]["id"],  # SENSOR-L9
            "quantity_per_unit": Decimal("1.0000"),
        },
        {
            "id": generate_deterministic_uuid("v2.3-VALVE-V3"),
            "product_version_id": product_versions[2]["id"],
            "component_id": components[3]["id"],  # VALVE-V3
            "quantity_per_unit": Decimal("2.0000"),
        },
        {
            "id": generate_deterministic_uuid("v2.3-PIPE-P1"),
            "product_version_id": product_versions[2]["id"],
            "component_id": components[4]["id"],  # PIPE-P1
            "quantity_per_unit": Decimal("3.0000"),
        },
    ]
    dataset["bom_items"] = bom_items

    # ═══════════════════════════════════════════════════════════════
    # COMPONENT ALTERNATIVES (1 PROPOSED for SENSOR-L9)
    # ═══════════════════════════════════════════════════════════════
    component_alternatives = [
        {
            "id": generate_deterministic_uuid("SENSOR-L9-to-VALVE-V3"),
            "component_id": components[2]["id"],  # SENSOR-L9
            "alternative_component_id": components[3]["id"],  # VALVE-V3
            "status": "PROPOSED",
            "rationale": "VALVE-V3 can substitute for SENSOR-L9 pending engineering review",
        }
    ]
    dataset["component_alternatives"] = component_alternatives

    # ═══════════════════════════════════════════════════════════════
    # WAREHOUSES (1)
    # ═══════════════════════════════════════════════════════════════
    warehouses = [
        {
            "id": generate_deterministic_uuid("WH-MAIN"),
            "code": "WH-MAIN",
            "name": "Main Warehouse",
        }
    ]
    dataset["warehouses"] = warehouses

    # ═══════════════════════════════════════════════════════════════
    # INVENTORY BALANCES (per component per warehouse)
    # ═══════════════════════════════════════════════════════════════
    # Designed so each risk component has exactly the on_hand needed
    inventory_balances = [
        # CTRL-X4: 12 on hand (RISK-001 requires 20 → shortage 8)
        {
            "id": generate_deterministic_uuid("CTRL-X4-WH-MAIN"),
            "component_id": components[0]["id"],
            "warehouse_id": warehouses[0]["id"],
            "quantity_on_hand": Decimal("12.0000"),
        },
        # MOTOR-M2: 10 on hand (RISK-002 requires 16 → shortage 6)
        {
            "id": generate_deterministic_uuid("MOTOR-M2-WH-MAIN"),
            "component_id": components[1]["id"],
            "warehouse_id": warehouses[0]["id"],
            "quantity_on_hand": Decimal("10.0000"),
        },
        # SENSOR-L9: 7 on hand (RISK-003 requires 12 → shortage 5)
        {
            "id": generate_deterministic_uuid("SENSOR-L9-WH-MAIN"),
            "component_id": components[2]["id"],
            "warehouse_id": warehouses[0]["id"],
            "quantity_on_hand": Decimal("7.0000"),
        },
        # VALVE-V3: 50 on hand (sufficient for all WOs)
        {
            "id": generate_deterministic_uuid("VALVE-V3-WH-MAIN"),
            "component_id": components[3]["id"],
            "warehouse_id": warehouses[0]["id"],
            "quantity_on_hand": Decimal("50.0000"),
        },
        # PIPE-P1: 70 on hand (sufficient for all WOs)
        {
            "id": generate_deterministic_uuid("PIPE-P1-WH-MAIN"),
            "component_id": components[4]["id"],
            "warehouse_id": warehouses[0]["id"],
            "quantity_on_hand": Decimal("70.0000"),
        },
    ]
    dataset["inventory_balances"] = inventory_balances

    # ═══════════════════════════════════════════════════════════════
    # SUPPLIERS (3)
    # ═══════════════════════════════════════════════════════════════
    suppliers = [
        {
            "id": generate_deterministic_uuid("SUP-ACME"),
            "code": "SUP-ACME",
            "name": "Acme Industrial Supply",
        },
        {
            "id": generate_deterministic_uuid("SUP-GLOBAL"),
            "code": "SUP-GLOBAL",
            "name": "Global Components Ltd",
        },
        {
            "id": generate_deterministic_uuid("SUP-TECH"),
            "code": "SUP-TECH",
            "name": "TechParts International",
        },
    ]
    dataset["suppliers"] = suppliers

    # ═══════════════════════════════════════════════════════════════
    # PRODUCTION PLANS (1 plan)
    # ═══════════════════════════════════════════════════════════════
    production_plans = [
        {
            "id": generate_deterministic_uuid("PLAN-2026-W31"),
            "code": "PLAN-2026-W31",
            "status": "EXECUTING",
            "period_start": ANCHOR_DATE,  # 2026-07-31
            "period_end": ANCHOR_DATE + timedelta(days=6),  # 2026-08-06
            "created_at": datetime(2026, 7, 28, 9, 0, 0, tzinfo=timezone.utc),  # noqa: UP017
        }
    ]
    dataset["production_plans"] = production_plans

    # ═══════════════════════════════════════════════════════════════
    # PRODUCTION ORDERS (3 WOs — each uses different product version)
    # ═══════════════════════════════════════════════════════════════
    production_orders = [
        {
            # RISK-001: CTRL-X4 shortage
            "id": generate_deterministic_uuid("WO-2026-0142"),
            "code": "WO-2026-0142",
            "production_plan_id": production_plans[0]["id"],
            "product_version_id": product_versions[0]["id"],  # v2.1
            "quantity": Decimal("20.0000"),
            "need_date": ANCHOR_DATE + timedelta(days=3),  # 2026-08-03
            "status": "RELEASED",
        },
        {
            # RISK-002: MOTOR-M2 shortage with late supply
            "id": generate_deterministic_uuid("WO-2026-0150"),
            "code": "WO-2026-0150",
            "production_plan_id": production_plans[0]["id"],
            "product_version_id": product_versions[1]["id"],  # v2.2
            "quantity": Decimal("16.0000"),
            "need_date": ANCHOR_DATE + timedelta(days=3),  # 2026-08-03
            "status": "RELEASED",
        },
        {
            # RISK-003: SENSOR-L9 shortage with proposed alternative
            "id": generate_deterministic_uuid("WO-2026-0156"),
            "code": "WO-2026-0156",
            "production_plan_id": production_plans[0]["id"],
            "product_version_id": product_versions[2]["id"],  # v2.3
            "quantity": Decimal("12.0000"),
            "need_date": ANCHOR_DATE + timedelta(days=5),  # 2026-08-05
            "status": "RELEASED",
        },
    ]
    dataset["production_orders"] = production_orders

    # ═══════════════════════════════════════════════════════════════
    # INVENTORY RESERVATIONS (none — keeps math clean)
    # ═══════════════════════════════════════════════════════════════
    inventory_reservations: list[dict[str, Any]] = []
    dataset["inventory_reservations"] = inventory_reservations

    # ═══════════════════════════════════════════════════════════════
    # PURCHASE ORDERS (3 — exercising status combinations)
    # ═══════════════════════════════════════════════════════════════
    purchase_orders = [
        {
            # PO-001: CONFIRMED header + line arriving AFTER need_date (RISK-002 HIGH evidence)
            "id": generate_deterministic_uuid("PO-001"),
            "supplier_id": suppliers[0]["id"],  # SUP-ACME
            "po_number": "PO-2026-0421",
            "status": "CONFIRMED",
            "placed_at": datetime(2026, 7, 25, 10, 0, 0, tzinfo=timezone.utc),  # noqa: UP017
        },
        {
            # PO-002: CONFIRMED header + line arriving well before need_date (no risk impact)
            "id": generate_deterministic_uuid("PO-002"),
            "supplier_id": suppliers[1]["id"],  # SUP-GLOBAL
            "po_number": "PO-2026-0422",
            "status": "CONFIRMED",
            "placed_at": datetime(2026, 7, 26, 14, 0, 0, tzinfo=timezone.utc),  # noqa: UP017
        },
        {
            # PO-003: CANCELLED header (excluded from supply calculations entirely)
            "id": generate_deterministic_uuid("PO-003"),
            "supplier_id": suppliers[2]["id"],  # SUP-TECH
            "po_number": "PO-2026-0423",
            "status": "CANCELLED",
            "placed_at": datetime(2026, 7, 20, 9, 0, 0, tzinfo=timezone.utc),  # noqa: UP017
        },
    ]
    dataset["purchase_orders"] = purchase_orders

    # ═══════════════════════════════════════════════════════════════
    # PURCHASE ORDER LINES
    # ═══════════════════════════════════════════════════════════════
    purchase_order_lines = [
        {
            # PO-001 line: MOTOR-M2, 10 units, arriving AFTER need_date 2026-08-03
            # Status IN_TRANSIT on CONFIRMED header → confirmed_late_supply = 10
            "id": generate_deterministic_uuid("PO-001-line-MOTOR-M2"),
            "purchase_order_id": purchase_orders[0]["id"],
            "component_id": components[1]["id"],  # MOTOR-M2
            "ordered_quantity": Decimal("10.0000"),
            "received_quantity": Decimal("0.0000"),
            "expected_delivery_date": ANCHOR_DATE + timedelta(days=9),  # 2026-08-09
            "status": "IN_TRANSIT",
        },
        {
            # PO-002 line: PIPE-P1, arriving well before any need_date (safe supply)
            "id": generate_deterministic_uuid("PO-002-line-PIPE-P1"),
            "purchase_order_id": purchase_orders[1]["id"],
            "component_id": components[4]["id"],  # PIPE-P1
            "ordered_quantity": Decimal("20.0000"),
            "received_quantity": Decimal("0.0000"),
            "expected_delivery_date": ANCHOR_DATE + timedelta(days=1),  # 2026-08-01
            "status": "CONFIRMED",
        },
        {
            # PO-003 line: CANCELLED (excluded from calculations)
            "id": generate_deterministic_uuid("PO-003-line-CTRL-X4"),
            "purchase_order_id": purchase_orders[2]["id"],
            "component_id": components[0]["id"],  # CTRL-X4
            "ordered_quantity": Decimal("30.0000"),
            "received_quantity": Decimal("0.0000"),
            "expected_delivery_date": ANCHOR_DATE + timedelta(days=5),  # 2026-08-05
            "status": "CANCELLED",
        },
    ]
    dataset["purchase_order_lines"] = purchase_order_lines

    # ═══════════════════════════════════════════════════════════════
    # PRODUCTION ORDER REQUIREMENTS (one per WO per component in its BOM)
    # ═══════════════════════════════════════════════════════════════
    production_order_requirements = []

    for wo in production_orders:
        wo_qty = Decimal(str(wo["quantity"]))
        pv_id = wo["product_version_id"]

        for bom_item in bom_items:
            if bom_item["product_version_id"] != pv_id:
                continue
            component_id = uuid.UUID(str(bom_item["component_id"]))
            quantity_per_unit = Decimal(str(bom_item["quantity_per_unit"]))
            required_quantity = wo_qty * quantity_per_unit

            production_order_requirements.append(
                {
                    "id": generate_deterministic_uuid(
                        f"{wo['code']}-component-{component_id}"
                    ),
                    "production_order_id": wo["id"],
                    "component_id": component_id,
                    "required_quantity": required_quantity,
                    "reserved_quantity": Decimal("0.0000"),
                }
            )

    dataset["production_order_requirements"] = production_order_requirements

    return dataset


def get_golden_scenario_facts() -> dict[str, Any]:
    """Return the expected Golden Scenario facts for validation.

    Returns:
        Dictionary with RISK-001, RISK-002, RISK-003 expected facts
    """
    return {
        "RISK-001": {
            "component_code": "CTRL-X4",
            "affected_wo": "WO-2026-0142",
            "required": Decimal("20.0000"),
            "available": Decimal("12.0000"),
            "shortage": Decimal("8.0000"),
            "severity": "CRITICAL",
            "confirmed_early_supply": Decimal("0.0000"),
            "has_approved_alternative": False,
        },
        "RISK-002": {
            "component_code": "MOTOR-M2",
            "affected_wo": "WO-2026-0150",
            "required": Decimal("16.0000"),
            "available": Decimal("10.0000"),
            "confirmed_early_supply": Decimal("0.0000"),
            "confirmed_late_supply": Decimal("10.0000"),
            "shortage": Decimal("6.0000"),
            "severity": "HIGH",
            "has_approved_alternative": False,
        },
        "RISK-003": {
            "component_code": "SENSOR-L9",
            "affected_wo": "WO-2026-0156",
            "required": Decimal("12.0000"),
            "available": Decimal("7.0000"),
            "shortage": Decimal("5.0000"),
            "severity": "MEDIUM",
            "confirmed_early_supply": Decimal("0.0000"),
            "has_proposed_alternative": True,
        },
    }
