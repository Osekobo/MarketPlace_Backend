"""CRUD operations for orders and the lifecycle state machine."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import OrderStatus, can_transition
from app.models.order import Order, OrderItem, OrderStatusEvent
from app.models.product import Product

# Maps a target status to the timestamp column that should be stamped.
_STATUS_TIMESTAMP: dict[OrderStatus, str] = {
    OrderStatus.CONFIRMED: "confirmed_at",
    OrderStatus.DISPATCHED: "dispatched_at",
    OrderStatus.DELIVERED: "delivered_at",
    OrderStatus.CANCELLED: "cancelled_at",
}


class InvalidOrderTransition(Exception):
    """Raised when an order cannot move to the requested status."""

    def __init__(self, current: OrderStatus, target: OrderStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Cannot transition order from '{current.value}' to '{target.value}'")


async def create_order(
    db: AsyncSession,
    *,
    customer_id: uuid.UUID,
    vendor_id: uuid.UUID,
    line_items: list[tuple[Product, int]],
    delivery_address: str,
    delivery_latitude: float | None = None,
    delivery_longitude: float | None = None,
) -> Order:
    from app.core.geo import make_geography  # local import avoids import cycle

    all_items = [
        OrderItem(
            product_id=product.id,
            quantity=quantity,
            unit_price=product.price,
        )
        for product, quantity in line_items
    ]
    total = sum(float(product.price) * quantity for product, quantity in line_items)

    order = Order(
        customer_id=customer_id,
        vendor_id=vendor_id,
        status=OrderStatus.PLACED,
        total_amount=total,
        delivery_address=delivery_address,
        delivery_location=(
            make_geography(delivery_latitude, delivery_longitude)
            if delivery_latitude is not None and delivery_longitude is not None
            else None
        ),
        items=all_items,
    )
    order.events.append(
        OrderStatusEvent(from_status=None, to_status=OrderStatus.PLACED, actor_id=customer_id)
    )
    db.add(order)
    await db.flush()
    return order


async def get_order(
    db: AsyncSession, order_id: uuid.UUID, *, with_events: bool = False
) -> Order | None:
    stmt = select(Order).where(Order.id == order_id).options(selectinload(Order.items))
    if with_events:
        stmt = stmt.options(selectinload(Order.events))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_orders_for_customer(
    db: AsyncSession,
    customer_id: uuid.UUID,
    *,
    status: OrderStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Order]:
    stmt = select(Order).where(Order.customer_id == customer_id)
    return await _execute_order_list(db, stmt, status, limit, offset)


async def list_orders_for_vendor(
    db: AsyncSession,
    vendor_id: uuid.UUID,
    *,
    status: OrderStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Order]:
    stmt = select(Order).where(Order.vendor_id == vendor_id)
    return await _execute_order_list(db, stmt, status, limit, offset)


async def list_orders_for_rider(
    db: AsyncSession,
    rider_id: uuid.UUID,
    *,
    status: OrderStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Order]:
    stmt = select(Order).where(Order.rider_id == rider_id)
    return await _execute_order_list(db, stmt, status, limit, offset)


async def list_available_for_riders(
    db: AsyncSession, *, limit: int = 50, offset: int = 0
) -> list[Order]:
    stmt = select(Order).where(
        Order.status == OrderStatus.CONFIRMED, Order.rider_id.is_(None)
    )
    stmt = (
        stmt.options(selectinload(Order.items))
        .order_by(Order.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _execute_order_list(
    db: AsyncSession,
    stmt,  # noqa: ANN001
    status: OrderStatus | None,
    limit: int,
    offset: int,
) -> list[Order]:
    if status is not None:
        stmt = stmt.where(Order.status == status)
    stmt = (
        stmt.options(selectinload(Order.items))
        .order_by(Order.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


def assign_rider(order: Order, rider_id: uuid.UUID) -> None:
    order.rider_id = rider_id


async def transition_order(
    db: AsyncSession,
    order: Order,
    target: OrderStatus,
    *,
    actor_id: uuid.UUID | None = None,
    note: str | None = None,
) -> Order:
    """Advance an order through the state machine, recording an audit event."""
    if not can_transition(order.status, target):
        raise InvalidOrderTransition(order.status, target)

    previous = order.status
    order.status = target
    timestamp_field = _STATUS_TIMESTAMP.get(target)
    if timestamp_field is not None:
        setattr(order, timestamp_field, datetime.now(timezone.utc))

    db.add(
        OrderStatusEvent(
            order_id=order.id,
            from_status=previous,
            to_status=target,
            actor_id=actor_id,
            note=note,
        )
    )
    await db.flush()
    return order
