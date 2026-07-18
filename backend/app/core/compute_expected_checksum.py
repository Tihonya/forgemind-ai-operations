"""Compute and display the expected checksum for Golden Dataset V1.0.

This utility generates the canonical form of the Golden Dataset and computes
its SHA-256 checksum. The resulting checksum must be manually reviewed and
then hardcoded into app/core/dataset_metadata.py as EXPECTED_CHECKSUM.

Usage:
    python -m app.core.compute_expected_checksum
"""

import hashlib
import json
import sys
from collections import OrderedDict
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from app.seed.generator.golden_dataset import generate_golden_dataset


def _serialize_value(value: Any) -> Any:
    """Convert a value to canonical JSON form."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, Decimal):
        normalized = value.normalize()
        exp = normalized.as_tuple().exponent
        if isinstance(exp, int) and exp > 0:
            return str(int(normalized))
        return str(normalized)
    if isinstance(value, datetime):
        utc_value = value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return utc_value.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def canonicalize_dataset(dataset: dict[str, Any]) -> OrderedDict[str, Any]:
    """Canonicalize the in-memory Golden Dataset into a deterministic form.

    Converts all UUID references to business keys, sorts all collections,
    and normalizes all values to canonical JSON representation.

    Args:
        dataset: The output of generate_golden_dataset()

    Returns:
        OrderedDict with canonicalized entity collections
    """
    # Build lookup maps: id → business key
    products = dataset["products"]
    product_map = {str(p["id"]): p["code"] for p in products}

    product_versions = dataset["product_versions"]
    pv_map = {
        str(pv["id"]): (product_map[str(pv["product_id"])], pv["version"])
        for pv in product_versions
    }

    components = dataset["components"]
    component_map = {str(c["id"]): c["code"] for c in components}

    warehouses = dataset["warehouses"]
    warehouse_map = {str(w["id"]): w["code"] for w in warehouses}

    suppliers = dataset["suppliers"]
    supplier_map = {str(s["id"]): s["code"] for s in suppliers}

    production_plans = dataset["production_plans"]
    plan_map = {str(p["id"]): p["code"] for p in production_plans}

    production_orders = dataset["production_orders"]
    order_map = {str(o["id"]): o["code"] for o in production_orders}

    purchase_orders = dataset["purchase_orders"]
    po_map = {str(po["id"]): po["po_number"] for po in purchase_orders}

    # Canonicalize each collection
    canonical = OrderedDict()

    # 1. products (sorted by code)
    canonical["products"] = sorted(
        [
            OrderedDict([
                ("code", _serialize_value(p["code"])),
                ("description", _serialize_value(p["description"])),
                ("name", _serialize_value(p["name"])),
            ])
            for p in products
        ],
        key=lambda x: x["code"],
    )

    # 2. product_versions (sorted by product_code, version)
    canonical["product_versions"] = sorted(
        [
            OrderedDict([
                ("product_code", product_map[str(pv["product_id"])]),
                ("status", _serialize_value(pv["status"])),
                ("version", _serialize_value(pv["version"])),
            ])
            for pv in product_versions
        ],
        key=lambda x: (x["product_code"], x["version"]),
    )

    # 3. components (sorted by code)
    canonical["components"] = sorted(
        [
            OrderedDict([
                ("code", _serialize_value(c["code"])),
                ("description", _serialize_value(c["description"])),
                ("name", _serialize_value(c["name"])),
                ("unit", _serialize_value(c["unit"])),
            ])
            for c in components
        ],
        key=lambda x: x["code"],
    )

    # 4. bom_items (sorted by product_code, product_version, component_code)
    canonical["bom_items"] = sorted(
        [
            OrderedDict([
                ("component_code", component_map[str(bi["component_id"])]),
                ("product_code", pv_map[str(bi["product_version_id"])][0]),
                ("product_version", pv_map[str(bi["product_version_id"])][1]),
                ("quantity_per_unit", _serialize_value(bi["quantity_per_unit"])),
            ])
            for bi in dataset["bom_items"]
        ],
        key=lambda x: (x["product_code"], x["product_version"], x["component_code"]),
    )

    # 5. warehouses (sorted by code)
    canonical["warehouses"] = sorted(
        [
            OrderedDict([
                ("code", _serialize_value(w["code"])),
                ("name", _serialize_value(w["name"])),
            ])
            for w in warehouses
        ],
        key=lambda x: x["code"],
    )

    # 6. inventory_balances (sorted by component_code, warehouse_code)
    canonical["inventory_balances"] = sorted(
        [
            OrderedDict([
                ("component_code", component_map[str(ib["component_id"])]),
                ("quantity_on_hand", _serialize_value(ib["quantity_on_hand"])),
                ("warehouse_code", warehouse_map[str(ib["warehouse_id"])]),
            ])
            for ib in dataset["inventory_balances"]
        ],
        key=lambda x: (x["component_code"], x["warehouse_code"]),
    )

    # 7. suppliers (sorted by code)
    canonical["suppliers"] = sorted(
        [
            OrderedDict([
                ("code", _serialize_value(s["code"])),
                ("name", _serialize_value(s["name"])),
            ])
            for s in suppliers
        ],
        key=lambda x: x["code"],
    )

    # 8. production_plans (sorted by code) — exclude created_at
    canonical["production_plans"] = sorted(
        [
            OrderedDict([
                ("code", _serialize_value(pp["code"])),
                ("period_end", _serialize_value(pp["period_end"])),
                ("period_start", _serialize_value(pp["period_start"])),
                ("status", _serialize_value(pp["status"])),
            ])
            for pp in production_plans
        ],
        key=lambda x: x["code"],
    )

    # 9. production_orders (sorted by code)
    canonical["production_orders"] = sorted(
        [
            OrderedDict([
                ("code", _serialize_value(po["code"])),
                ("need_date", _serialize_value(po["need_date"])),
                ("product_code", pv_map[str(po["product_version_id"])][0]),
                ("product_version", pv_map[str(po["product_version_id"])][1]),
                ("production_plan_code", plan_map[str(po["production_plan_id"])]),
                ("quantity", _serialize_value(po["quantity"])),
                ("status", _serialize_value(po["status"])),
            ])
            for po in production_orders
        ],
        key=lambda x: x["code"],
    )

    # 10. inventory_reservations (sorted by production_order_code, component_code, warehouse_code)
    canonical["inventory_reservations"] = sorted(
        [
            OrderedDict([
                ("component_code", component_map[str(ir["component_id"])]),
                ("production_order_code", order_map[str(ir["production_order_id"])]),
                ("quantity", _serialize_value(ir["quantity"])),
                ("warehouse_code", warehouse_map[str(ir["warehouse_id"])]),
            ])
            for ir in dataset["inventory_reservations"]
        ],
        key=lambda x: (x["production_order_code"], x["component_code"], x["warehouse_code"]),
    )

    # 11. purchase_orders (sorted by po_number)
    canonical["purchase_orders"] = sorted(
        [
            OrderedDict([
                ("placed_at", _serialize_value(po["placed_at"])),
                ("po_number", _serialize_value(po["po_number"])),
                ("status", _serialize_value(po["status"])),
                ("supplier_code", supplier_map[str(po["supplier_id"])]),
            ])
            for po in purchase_orders
        ],
        key=lambda x: x["po_number"],
    )

    # 12. purchase_order_lines (sorted by po_number, component_code)
    canonical["purchase_order_lines"] = sorted(
        [
            OrderedDict([
                ("component_code", component_map[str(line["component_id"])]),
                ("expected_delivery_date", _serialize_value(line["expected_delivery_date"])),
                ("ordered_quantity", _serialize_value(line["ordered_quantity"])),
                ("po_number", po_map[str(line["purchase_order_id"])]),
                ("received_quantity", _serialize_value(line["received_quantity"])),
                ("status", _serialize_value(line["status"])),
            ])
            for line in dataset["purchase_order_lines"]
        ],
        key=lambda x: (x["po_number"], x["component_code"]),
    )

    # 13. production_order_requirements (sorted by production_order_code, component_code)
    canonical["production_order_requirements"] = sorted(
        [
            OrderedDict([
                ("component_code", component_map[str(req["component_id"])]),
                ("production_order_code", order_map[str(req["production_order_id"])]),
                ("required_quantity", _serialize_value(req["required_quantity"])),
                ("reserved_quantity", _serialize_value(req["reserved_quantity"])),
            ])
            for req in dataset["production_order_requirements"]
        ],
        key=lambda x: (x["production_order_code"], x["component_code"]),
    )

    # 14. component_alternatives (sorted by component_code, alternative_component_code)
    canonical["component_alternatives"] = sorted(
        [
            OrderedDict([
                ("alternative_component_code", component_map[str(ca["alternative_component_id"])]),
                ("component_code", component_map[str(ca["component_id"])]),
                ("rationale", _serialize_value(ca["rationale"])),
                ("status", _serialize_value(ca["status"])),
            ])
            for ca in dataset["component_alternatives"]
        ],
        key=lambda x: (x["component_code"], x["alternative_component_code"]),
    )

    return canonical


def compute_checksum(canonical: OrderedDict[str, Any]) -> str:
    """Compute SHA-256 checksum of canonicalized dataset.

    Args:
        canonical: The output of canonicalize_dataset()

    Returns:
        Checksum string in format "sha256:<hex>"
    """
    json_bytes = json.dumps(canonical, separators=(",", ":"), sort_keys=False).encode("utf-8")
    digest = hashlib.sha256(json_bytes).hexdigest()
    return f"sha256:{digest}"


def main() -> None:
    """Generate and print the expected checksum."""
    sys.stdout.write("Generating Golden Dataset V1.0...\n")
    dataset = generate_golden_dataset()

    sys.stdout.write("Canonicalizing dataset...\n")
    canonical = canonicalize_dataset(dataset)

    sys.stdout.write("Computing checksum...\n")
    checksum = compute_checksum(canonical)

    sys.stdout.write(f"\nExpected checksum for Golden Dataset V1.0:\n{checksum}\n")
    msg = "\nThis value must be hardcoded into app/core/dataset_metadata.py as EXPECTED_CHECKSUM.\n"
    sys.stdout.write(msg)


if __name__ == "__main__":
    main()
