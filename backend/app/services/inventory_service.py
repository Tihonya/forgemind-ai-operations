"""Inventory and supply service.

Calculates available inventory (on_hand minus active reservations for other orders),
confirmed incoming supply (early and late), and alternative availability for components.

All calculations use Decimal arithmetic to avoid floating-point drift.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.component import ComponentAlternative
from app.models.supplier import PurchaseOrder, PurchaseOrderLine
from app.models.warehouse import InventoryBalance, InventoryReservation


@dataclass(frozen=True)
class InventoryAvailability:
    """Available inventory for a component on a specific need_date.

    Attributes:
        component_id: UUID of the component
        available: Available quantity (on_hand - other active reservations)
        confirmed_early: Confirmed supply arriving on or before need_date
        confirmed_late: Confirmed supply arriving after need_date
        has_approved_alternative: Whether an APPROVED alternative exists
        has_proposed_alternative: Whether a PROPOSED alternative exists
    """

    component_id: UUID
    available: Decimal
    confirmed_early: Decimal
    confirmed_late: Decimal
    has_approved_alternative: bool
    has_proposed_alternative: bool


async def calculate_inventory_availability(
    session: AsyncSession,
    component_id: UUID,
    need_date: date,
    exclude_wo_id: UUID,
) -> InventoryAvailability:
    """Calculate available inventory and confirmed supply for a component.

    Available = sum(on_hand) - sum(reservations where parent_wo.status in
    (PLANNED, RELEASED, IN_PROGRESS) and wo_id != exclude_wo_id)

    Confirmed early = sum(PO line ordered_quantity where PO.status = CONFIRMED
    and line.status in (CONFIRMED, IN_TRANSIT) and expected_delivery <= need_date)

    Confirmed late = same but expected_delivery > need_date

    Args:
        session: Async database session.
        component_id: UUID of the component to check.
        need_date: Date when the component is needed.
        exclude_wo_id: UUID of the work order being analysed (own reservation excluded).

    Returns:
        InventoryAvailability with all calculated fields.
    """
    # Calculate total on_hand
    on_hand_stmt = select(InventoryBalance).where(
        InventoryBalance.component_id == component_id
    )
    on_hand_result = await session.execute(on_hand_stmt)
    balances: Sequence[InventoryBalance] = on_hand_result.scalars().all()
    total_on_hand = sum((b.quantity_on_hand for b in balances), Decimal("0"))

    # Calculate active reservations for OTHER work orders
    # Parent order status must be PLANNED, RELEASED, or IN_PROGRESS
    from app.models.production import ProductionOrder

    reservation_stmt = (
        select(InventoryReservation)
        .join(ProductionOrder, InventoryReservation.production_order_id == ProductionOrder.id)
        .where(
            and_(
                InventoryReservation.component_id == component_id,
                InventoryReservation.production_order_id != exclude_wo_id,
                ProductionOrder.status.in_(["PLANNED", "RELEASED", "IN_PROGRESS"]),
            )
        )
    )
    reservation_result = await session.execute(reservation_stmt)
    reservations: Sequence[InventoryReservation] = reservation_result.scalars().all()
    total_reserved = sum((r.quantity for r in reservations), Decimal("0"))

    available = total_on_hand - total_reserved

    # Calculate confirmed incoming supply
    # PO header status = CONFIRMED
    # PO line status in (CONFIRMED, IN_TRANSIT)
    # Exclude DELIVERED (already in on_hand), CANCELLED, PENDING
    po_stmt = (
        select(PurchaseOrderLine)
        .join(PurchaseOrder, PurchaseOrderLine.purchase_order_id == PurchaseOrder.id)
        .where(
            and_(
                PurchaseOrderLine.component_id == component_id,
                PurchaseOrder.status == "CONFIRMED",
                PurchaseOrderLine.status.in_(["CONFIRMED", "IN_TRANSIT"]),
            )
        )
        .options(selectinload(PurchaseOrderLine.purchase_order))
    )
    po_result = await session.execute(po_stmt)
    po_lines: Sequence[PurchaseOrderLine] = po_result.scalars().all()

    confirmed_early = Decimal("0")
    confirmed_late = Decimal("0")

    for line in po_lines:
        if line.expected_delivery_date <= need_date:
            confirmed_early += line.ordered_quantity
        else:
            confirmed_late += line.ordered_quantity

    # Check for alternative components
    alt_stmt = select(ComponentAlternative).where(
        ComponentAlternative.component_id == component_id
    )
    alt_result = await session.execute(alt_stmt)
    alternatives: Sequence[ComponentAlternative] = alt_result.scalars().all()

    has_approved = any(alt.status == "APPROVED" for alt in alternatives)
    has_proposed = any(alt.status == "PROPOSED" for alt in alternatives)

    return InventoryAvailability(
        component_id=component_id,
        available=available,
        confirmed_early=confirmed_early,
        confirmed_late=confirmed_late,
        has_approved_alternative=has_approved,
        has_proposed_alternative=has_proposed,
    )
