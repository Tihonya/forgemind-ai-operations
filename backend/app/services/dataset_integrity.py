"""Dataset integrity service for Golden Dataset checksum verification.

Computes semantic checksums of the Golden Dataset to verify that the loaded
database contains the exact expected fixture data. The checksum is computed on
canonicalized business data (not database surrogate IDs or Python source bytes),
ensuring:

- Source code formatting changes do not affect the checksum;
- Only semantic changes to the dataset change the checksum;
- The checksum is reproducible across machines and environments;
- Relationships are expressed via stable business keys, not UUIDs.

Canonicalization v1 (`sha256:v1`) is documented in `app/core/dataset_metadata.py`.
"""

import hashlib
import json
from collections import OrderedDict
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.component import BomItem, Component, ComponentAlternative
from app.models.product import Product, ProductVersion
from app.models.production import (
    ProductionOrder,
    ProductionOrderRequirement,
    ProductionPlan,
)
from app.models.supplier import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.warehouse import InventoryBalance, InventoryReservation, Warehouse


def _serialize_value(value: Any) -> Any:
    """Convert a value to its canonical JSON-serializable form.

    Rules (canonicalization v1):
      None              → JSON null
      bool              → JSON boolean
      int, float        → JSON number
      Decimal           → normalized string (no trailing zeros)
      datetime          → ISO-8601 UTC with "Z"
      date              → ISO-8601 "YYYY-MM-DD"
      str               → pass through
    """
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
        # Normalize removes trailing zeros: Decimal("20.0000") → "2E+1"
        # But we want "20" — use quantize to strip while remaining readable.
        normalized = value.normalize()
        # If exponent is positive (e.g. 2E+1), convert to integer form.
        exp = normalized.as_tuple().exponent
        if isinstance(exp, int) and exp > 0:
            return str(int(normalized))
        # Otherwise: drop trailing zeros via string manipulation
        return str(normalized)
    if isinstance(value, datetime):
        # Normalize to UTC, then format with trailing Z.
        utc_value = value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return utc_value.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _serialize_entity(fields: OrderedDict[str, Any]) -> dict[str, Any]:
    """Convert a field order dict to a plain dict with canonical values.

    Field order is preserved through JSON sort_keys=False + OrderedDict input.
    """
    return {k: _serialize_value(v) for k, v in fields.items()}


class DatasetIntegrityService:
    """Service for verifying Golden Dataset integrity via semantic checksums."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def compute_actual_checksum(self) -> str:
        """Compute the semantic checksum of the current database state.

        Reads all Golden Dataset business tables, canonicalizes their content,
        and returns a SHA-256 checksum prefixed with "sha256:".

        Raises:
            RuntimeError: On unexpected DB access failure.
        """
        # 1. Build lookup maps for resolving FK IDs → business keys.
        ref = await self._build_reference_maps()

        # 2. Canonicalize all 14 collections in declared order.
        canonical = OrderedDict()
        canonical["products"] = await self._products(ref)
        canonical["product_versions"] = await self._product_versions(ref)
        canonical["components"] = await self._components()
        canonical["bom_items"] = await self._bom_items(ref)
        canonical["warehouses"] = await self._warehouses()
        canonical["inventory_balances"] = await self._inventory_balances(ref)
        canonical["suppliers"] = await self._suppliers()
        canonical["production_plans"] = await self._production_plans()
        canonical["production_orders"] = await self._production_orders(ref)
        canonical["inventory_reservations"] = await self._inventory_reservations(ref)
        canonical["purchase_orders"] = await self._purchase_orders(ref)
        canonical["purchase_order_lines"] = await self._purchase_order_lines(ref)
        canonical["production_order_requirements"] = await self._production_order_requirements(ref)
        canonical["component_alternatives"] = await self._component_alternatives(ref)

        # 3. Serialize to canonical JSON (compact, no trailing newline, UTF-8).
        json_bytes = json.dumps(canonical, separators=(",", ":"), sort_keys=False).encode("utf-8")

        # 4. SHA-256
        digest = hashlib.sha256(json_bytes).hexdigest()
        return f"sha256:{digest}"

    async def _build_reference_maps(self) -> dict[str, dict[str, Any]]:
        """Build FK-ID → business-key lookup maps."""
        products = await self._session.execute(select(Product))
        product_map: dict[str, str] = {
            str(p.id): p.code for p in products.scalars()
        }

        pvs = await self._session.execute(select(ProductVersion))
        pv_map: dict[str, tuple[str, str]] = {
            str(pv.id): (product_map[str(pv.product_id)], pv.version)
            for pv in pvs.scalars()
        }

        components = await self._session.execute(select(Component))
        component_map: dict[str, str] = {
            str(c.id): c.code for c in components.scalars()
        }

        warehouses = await self._session.execute(select(Warehouse))
        warehouse_map: dict[str, str] = {
            str(w.id): w.code for w in warehouses.scalars()
        }

        suppliers = await self._session.execute(select(Supplier))
        supplier_map: dict[str, str] = {
            str(s.id): s.code for s in suppliers.scalars()
        }

        plans = await self._session.execute(select(ProductionPlan))
        plan_map: dict[str, str] = {
            str(p.id): p.code for p in plans.scalars()
        }

        orders = await self._session.execute(select(ProductionOrder))
        order_map: dict[str, str] = {
            str(o.id): o.code for o in orders.scalars()
        }

        pos = await self._session.execute(select(PurchaseOrder))
        po_map: dict[str, str] = {
            str(po.id): po.po_number for po in pos.scalars()
        }

        return {
            "products": product_map,
            "product_versions": pv_map,
            "components": component_map,
            "warehouses": warehouse_map,
            "suppliers": supplier_map,
            "production_plans": plan_map,
            "production_orders": order_map,
            "purchase_orders": po_map,
        }

    async def _products(self, ref: dict[str, Any]) -> list[dict[str, Any]]:
        result = await self._session.execute(select(Product).order_by(Product.code))
        return [
            _serialize_entity(OrderedDict([
                ("code", p.code),
                ("description", p.description),
                ("name", p.name),
            ]))
            for p in result.scalars()
        ]

    async def _product_versions(self, ref: dict[str, Any]) -> list[dict[str, Any]]:
        result = await self._session.execute(select(ProductVersion))
        rows = []
        for pv in result.scalars():
            product_code, version = ref["product_versions"][str(pv.id)]
            rows.append((product_code, version, _serialize_entity(OrderedDict([
                ("product_code", product_code),
                ("status", pv.status),
                ("version", version),
            ]))))
        rows.sort(key=lambda r: (r[0], r[1]))
        return [r[2] for r in rows]

    async def _components(self) -> list[dict[str, Any]]:
        result = await self._session.execute(select(Component).order_by(Component.code))
        return [
            _serialize_entity(OrderedDict([
                ("code", c.code),
                ("description", c.description),
                ("name", c.name),
                ("unit", c.unit),
            ]))
            for c in result.scalars()
        ]

    async def _bom_items(self, ref: dict[str, Any]) -> list[dict[str, Any]]:
        result = await self._session.execute(select(BomItem))
        rows = []
        for bi in result.scalars():
            product_code, product_version = ref["product_versions"][str(bi.product_version_id)]
            component_code = ref["components"][str(bi.component_id)]
            rows.append((product_code, product_version, component_code, _serialize_entity(
                OrderedDict([
                    ("component_code", component_code),
                    ("product_code", product_code),
                    ("product_version", product_version),
                    ("quantity_per_unit", bi.quantity_per_unit),
                ])
            )))
        rows.sort(key=lambda r: (r[0], r[1], r[2]))
        return [r[3] for r in rows]

    async def _warehouses(self) -> list[dict[str, Any]]:
        result = await self._session.execute(select(Warehouse).order_by(Warehouse.code))
        return [
            _serialize_entity(OrderedDict([
                ("code", w.code),
                ("name", w.name),
            ]))
            for w in result.scalars()
        ]

    async def _inventory_balances(self, ref: dict[str, Any]) -> list[dict[str, Any]]:
        result = await self._session.execute(select(InventoryBalance))
        rows = []
        for ib in result.scalars():
            component_code = ref["components"][str(ib.component_id)]
            warehouse_code = ref["warehouses"][str(ib.warehouse_id)]
            rows.append((component_code, warehouse_code, _serialize_entity(OrderedDict([
                ("component_code", component_code),
                ("quantity_on_hand", ib.quantity_on_hand),
                ("warehouse_code", warehouse_code),
            ]))))
        rows.sort(key=lambda r: (r[0], r[1]))
        return [r[2] for r in rows]

    async def _suppliers(self) -> list[dict[str, Any]]:
        result = await self._session.execute(select(Supplier).order_by(Supplier.code))
        return [
            _serialize_entity(OrderedDict([
                ("code", s.code),
                ("name", s.name),
            ]))
            for s in result.scalars()
        ]

    async def _production_plans(self) -> list[dict[str, Any]]:
        # Excluded: created_at (volatile, excluded per canonicalization v1)
        result = await self._session.execute(
            select(ProductionPlan).order_by(ProductionPlan.code)
        )
        return [
            _serialize_entity(OrderedDict([
                ("code", pp.code),
                ("period_end", pp.period_end),
                ("period_start", pp.period_start),
                ("status", pp.status),
            ]))
            for pp in result.scalars()
        ]

    async def _production_orders(self, ref: dict[str, Any]) -> list[dict[str, Any]]:
        result = await self._session.execute(select(ProductionOrder))
        rows = []
        for po in result.scalars():
            product_code, product_version = ref["product_versions"][str(po.product_version_id)]
            plan_code = ref["production_plans"][str(po.production_plan_id)]
            rows.append((po.code, _serialize_entity(OrderedDict([
                ("code", po.code),
                ("need_date", po.need_date),
                ("product_code", product_code),
                ("product_version", product_version),
                ("production_plan_code", plan_code),
                ("quantity", po.quantity),
                ("status", po.status),
            ]))))
        rows.sort(key=lambda r: r[0])
        return [r[1] for r in rows]

    async def _inventory_reservations(
            self, ref: dict[str, Any]
    ) -> list[dict[str, Any]]:
        result = await self._session.execute(select(InventoryReservation))
        rows = []
        for ir in result.scalars():
            order_code = ref["production_orders"][str(ir.production_order_id)]
            component_code = ref["components"][str(ir.component_id)]
            warehouse_code = ref["warehouses"][str(ir.warehouse_id)]
            rows.append((order_code, component_code, warehouse_code, _serialize_entity(
                OrderedDict([
                    ("component_code", component_code),
                    ("production_order_code", order_code),
                    ("quantity", ir.quantity),
                    ("warehouse_code", warehouse_code),
                ])
            )))
        rows.sort(key=lambda r: (r[0], r[1], r[2]))
        return [r[3] for r in rows]

    async def _purchase_orders(self, ref: dict[str, Any]) -> list[dict[str, Any]]:
        result = await self._session.execute(select(PurchaseOrder))
        rows = []
        for po in result.scalars():
            po_number = po.po_number
            supplier_code = ref["suppliers"][str(po.supplier_id)]
            rows.append((po_number, _serialize_entity(OrderedDict([
                ("placed_at", po.placed_at),
                ("po_number", po_number),
                ("status", po.status),
                ("supplier_code", supplier_code),
            ]))))
        rows.sort(key=lambda r: r[0])
        return [r[1] for r in rows]

    async def _purchase_order_lines(self, ref: dict[str, Any]) -> list[dict[str, Any]]:
        result = await self._session.execute(select(PurchaseOrderLine))
        rows = []
        for line in result.scalars():
            po_number = ref["purchase_orders"][str(line.purchase_order_id)]
            component_code = ref["components"][str(line.component_id)]
            rows.append((po_number, component_code, _serialize_entity(OrderedDict([
                ("component_code", component_code),
                ("expected_delivery_date", line.expected_delivery_date),
                ("ordered_quantity", line.ordered_quantity),
                ("po_number", po_number),
                ("received_quantity", line.received_quantity),
                ("status", line.status),
            ]))))
        rows.sort(key=lambda r: (r[0], r[1]))
        return [r[2] for r in rows]

    async def _production_order_requirements(
            self, ref: dict[str, Any]
    ) -> list[dict[str, Any]]:
        result = await self._session.execute(select(ProductionOrderRequirement))
        rows = []
        for req in result.scalars():
            order_code = ref["production_orders"][str(req.production_order_id)]
            component_code = ref["components"][str(req.component_id)]
            rows.append((order_code, component_code, _serialize_entity(
                OrderedDict([
                    ("component_code", component_code),
                    ("production_order_code", order_code),
                    ("required_quantity", req.required_quantity),
                    ("reserved_quantity", req.reserved_quantity),
                ])
            )))
        rows.sort(key=lambda r: (r[0], r[1]))
        return [r[2] for r in rows]

    async def _component_alternatives(self, ref: dict[str, Any]) -> list[dict[str, Any]]:
        result = await self._session.execute(select(ComponentAlternative))
        rows = []
        for ca in result.scalars():
            component_code = ref["components"][str(ca.component_id)]
            alt_code = ref["components"][str(ca.alternative_component_id)]
            rows.append((component_code, alt_code, _serialize_entity(OrderedDict([
                ("alternative_component_code", alt_code),
                ("component_code", component_code),
                ("rationale", ca.rationale),
                ("status", ca.status),
            ]))))
        rows.sort(key=lambda r: (r[0], r[1]))
        return [r[2] for r in rows]

    async def get_entity_counts(self) -> dict[str, int]:
        """Return the count of each Golden Dataset collection currently loaded."""
        from sqlalchemy import func

        models: list[tuple[str, type]] = [
            ("products", Product),
            ("product_versions", ProductVersion),
            ("components", Component),
            ("bom_items", BomItem),
            ("warehouses", Warehouse),
            ("inventory_balances", InventoryBalance),
            ("suppliers", Supplier),
            ("production_plans", ProductionPlan),
            ("production_orders", ProductionOrder),
            ("inventory_reservations", InventoryReservation),
            ("purchase_orders", PurchaseOrder),
            ("purchase_order_lines", PurchaseOrderLine),
            ("production_order_requirements", ProductionOrderRequirement),
            ("component_alternatives", ComponentAlternative),
        ]
        counts: dict[str, int] = {}
        for name, model in models:
            result = await self._session.execute(select(func.count()).select_from(model))
            counts[name] = int(result.scalar_one())
        return counts
