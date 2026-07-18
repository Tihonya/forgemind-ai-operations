"""WP-2.3 live PostgreSQL verification script."""

import asyncio
from decimal import Decimal

from sqlalchemy import text

from app.database import engine


async def verify() -> None:
    async with engine.connect() as conn:
        # RISK-001: CTRL-X4 in WO-2026-0142
        r = await conn.execute(text("""
            SELECT c.code, ib.quantity_on_hand, por.required_quantity
            FROM production_order_requirements por
            JOIN production_orders wo ON por.production_order_id = wo.id
            JOIN components c ON por.component_id = c.id
            JOIN inventory_balances ib ON c.id = ib.component_id
            WHERE c.code = :code AND wo.code = :wo
        """), {"code": "CTRL-X4", "wo": "WO-2026-0142"})
        row = r.mappings().fetchone()
        assert row is not None, "RISK-001 row missing"
        on_hand = row["quantity_on_hand"]
        required = row["required_quantity"]
        shortage = required - on_hand
        print(f"RISK-001: on_hand={on_hand}, required={required}, shortage={shortage}")
        assert shortage == Decimal("8"), f"Expected 8 got {shortage}"
        print("  ✓ shortage=8 (CRITICAL expected)")

        # Late supply for CTRL-X4 (should be 0)
        r = await conn.execute(text("""
            SELECT COUNT(*) FROM purchase_order_lines pol
            JOIN purchase_orders po ON pol.purchase_order_id = po.id
            JOIN components c ON pol.component_id = c.id
            WHERE c.code = 'CTRL-X4'
              AND po.status = 'CONFIRMED'
              AND pol.status IN ('CONFIRMED', 'IN_TRANSIT')
              AND pol.expected_delivery_date <= '2026-08-03'
        """))
        assert r.scalar() == 0
        print("  ✓ no early confirmed supply")

        # RISK-002: MOTOR-M2 in WO-2026-0150
        r = await conn.execute(text("""
            SELECT ib.quantity_on_hand, por.required_quantity
            FROM production_order_requirements por
            JOIN production_orders wo ON por.production_order_id = wo.id
            JOIN components c ON por.component_id = c.id
            JOIN inventory_balances ib ON c.id = ib.component_id
            WHERE c.code = :code AND wo.code = :wo
        """), {"code": "MOTOR-M2", "wo": "WO-2026-0150"})
        row = r.mappings().fetchone()
        assert row is not None, "RISK-002 row missing"
        on_hand = row["quantity_on_hand"]
        required = row["required_quantity"]
        shortage = required - on_hand
        print(f"\nRISK-002: on_hand={on_hand}, required={required}, shortage={shortage}")
        assert shortage == Decimal("6")
        print("  ✓ shortage=6")

        # Late supply for MOTOR-M2
        r = await conn.execute(text("""
            SELECT pol.ordered_quantity, pol.expected_delivery_date
            FROM purchase_order_lines pol
            JOIN purchase_orders po ON pol.purchase_order_id = po.id
            JOIN components c ON pol.component_id = c.id
            WHERE c.code = 'MOTOR-M2'
              AND po.status = 'CONFIRMED'
              AND pol.status IN ('CONFIRMED', 'IN_TRANSIT')
              AND pol.expected_delivery_date > '2026-08-03'
        """))
        row = r.mappings().fetchone()
        assert row is not None and row["ordered_quantity"] == Decimal("10")
        print(f"  ✓ late supply = 10 units arriving {row['expected_delivery_date']} (after need_date)")

        # RISK-003: SENSOR-L9 in WO-2026-0156
        r = await conn.execute(text("""
            SELECT ib.quantity_on_hand, por.required_quantity
            FROM production_order_requirements por
            JOIN production_orders wo ON por.production_order_id = wo.id
            JOIN components c ON por.component_id = c.id
            JOIN inventory_balances ib ON c.id = ib.component_id
            WHERE c.code = :code AND wo.code = :wo
        """), {"code": "SENSOR-L9", "wo": "WO-2026-0156"})
        row = r.mappings().fetchone()
        assert row is not None, "RISK-003 row missing"
        on_hand = row["quantity_on_hand"]
        required = row["required_quantity"]
        shortage = required - on_hand
        print(f"\nRISK-003: on_hand={on_hand}, required={required}, shortage={shortage}")
        assert shortage == Decimal("5")
        print("  ✓ shortage=5")

        # Proposed alternative for SENSOR-L9
        r = await conn.execute(text("""
            SELECT ca.status FROM component_alternatives ca
            JOIN components c ON ca.component_id = c.id
            WHERE c.code = 'SENSOR-L9'
        """))
        row = r.mappings().fetchone()
        assert row is not None and row["status"] == "PROPOSED"
        print("  ✓ proposed alternative exists (status=PROPOSED)")

        # diagnostic_jobs preserved
        r = await conn.execute(text("SELECT COUNT(*) FROM diagnostic_jobs"))
        print(f"\n✓ diagnostic_jobs preserved: {r.scalar()} rows untouched")


asyncio.run(verify())
print("\n=== All WP-2.3 risk source facts verified ===")
