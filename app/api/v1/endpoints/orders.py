"""Order lifecycle endpoints.

State machine: ``placed -> confirmed -> dispatched -> delivered``, with a
terminal ``cancelled`` branch before dispatch. Every transition is persisted as
an :class:`OrderStatusEvent` and broadcast over Redis pub/sub.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, require_customer, require_rider, require_vendor
from app.crud import order as crud_order
from app.crud import product as crud_product
from app.crud import vendor as crud_vendor
from app.crud.order import InvalidOrderTransition
from app.db.session import get_db
from app.models.enums import OrderStatus, UserRole
from app.models.order import Order
from app.models.user import User
from app.schemas.order import (
    OrderCreate,
    OrderRead,
    OrderStatusEventRead,
    OrderStatusTransition,
)
from app.websockets.events import publish_order_event

logger = logging.getLogger("app.orders")

router = APIRouter(prefix="/orders", tags=["orders"])


async def _publish(order: Order, event: str, previous: OrderStatus | None = None) -> None:
    try:
        await publish_order_event(
            order.id,
            event,
            {
                "status": order.status.value,
                "previous_status": previous.value if previous else None,
                "customer_id": str(order.customer_id),
                "vendor_id": str(order.vendor_id),
                "rider_id": str(order.rider_id) if order.rider_id else None,
            },
        )
    except Exception:  # pragma: no cover - broker outage must not fail the API
        logger.exception("Failed to publish '%s' event for order %s", event, order.id)


async def _load_order(db: AsyncSession, order_id: uuid.UUID) -> Order:
    order = await crud_order.get_order(db, order_id)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Order not found"
        )
    return order


async def _require_participant(db: AsyncSession, order: Order, user: User) -> None:
    if user.role == UserRole.VENDOR:
        vendor = await crud_vendor.get_vendor_by_owner(db, user.id)
        if vendor is not None and vendor.id == order.vendor_id:
            return
    elif user.role == UserRole.RIDER:
        if order.rider_id == user.id or (
            order.rider_id is None and order.status == OrderStatus.CONFIRMED
        ):
            return
    elif user.role == UserRole.CUSTOMER:
        if order.customer_id == user.id:
            return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You are not a participant of this order",
    )


async def _require_owning_vendor(db: AsyncSession, order: Order, user: User):
    vendor = await crud_vendor.get_vendor_by_owner(db, user.id)
    if vendor is None or vendor.id != order.vendor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owning vendor can perform this action",
        )
    return vendor


async def _apply_transition(
    db: AsyncSession,
    order: Order,
    target: OrderStatus,
    *,
    actor: User,
    event: str,
    note: str | None = None,
) -> Order:
    previous = order.status
    try:
        await crud_order.transition_order(
            db, order, target, actor_id=actor.id, note=note
        )
    except InvalidOrderTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    await db.commit()
    await _publish(order, event, previous)
    return order


@router.post(
    "",
    response_model=OrderRead,
    status_code=status.HTTP_201_CREATED,
    summary="Place a new order (Customer only)",
)
async def create_order(
    payload: OrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_customer),
) -> Order:
    vendor = await crud_vendor.get_vendor(db, payload.vendor_id)
    if vendor is None or not vendor.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found"
        )

    product_ids = [item.product_id for item in payload.items]
    products = await crud_product.get_products_by_ids(db, product_ids)
    products_by_id = {product.id: product for product in products}

    line_items: list[tuple] = []
    for item in payload.items:
        product = products_by_id.get(item.product_id)
        if product is None or product.vendor_id != vendor.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product {item.product_id} is not sold by this vendor",
            )
        if not product.is_available or product.stock < item.quantity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Product {product.name} is unavailable or out of stock",
            )
        line_items.append((product, item.quantity))

    order = await crud_order.create_order(
        db,
        customer_id=current_user.id,
        vendor_id=vendor.id,
        line_items=line_items,
        delivery_address=payload.delivery_address,
        delivery_latitude=payload.delivery_latitude,
        delivery_longitude=payload.delivery_longitude,
    )
    order_id = order.id
    await db.commit()

    order = await _load_order(db, order_id)
    await _publish(order, "order.created", None)
    return order


@router.get(
    "",
    response_model=list[OrderRead],
    summary="List orders relevant to the current user's role",
)
async def list_my_orders(
    order_status: OrderStatus | None = Query(default=None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[Order]:
    if current_user.role == UserRole.CUSTOMER:
        return await crud_order.list_orders_for_customer(
            db, current_user.id, status=order_status, limit=limit, offset=offset
        )
    if current_user.role == UserRole.VENDOR:
        vendor = await crud_vendor.get_vendor_by_owner(db, current_user.id)
        if vendor is None:
            return []
        return await crud_order.list_orders_for_vendor(
            db, vendor.id, status=order_status, limit=limit, offset=offset
        )
    return await crud_order.list_orders_for_rider(
        db, current_user.id, status=order_status, limit=limit, offset=offset
    )


@router.get(
    "/available",
    response_model=list[OrderRead],
    summary="List confirmed orders awaiting a rider (Rider only)",
)
async def list_available_orders(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_rider),
) -> list[Order]:
    return await crud_order.list_available_for_riders(db, limit=limit, offset=offset)


@router.get(
    "/{order_id}",
    response_model=OrderRead,
    summary="Get an order (participants only)",
)
async def read_order(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Order:
    order = await _load_order(db, order_id)
    await _require_participant(db, order, current_user)
    return order


@router.get(
    "/{order_id}/events",
    response_model=list[OrderStatusEventRead],
    summary="Get the status history for an order (participants only)",
)
async def read_order_events(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    order = await crud_order.get_order(db, order_id, with_events=True)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Order not found"
        )
    await _require_participant(db, order, current_user)
    return order.events


@router.post(
    "/{order_id}/confirm",
    response_model=OrderRead,
    summary="Confirm a placed order (owning Vendor only)",
)
async def confirm_order(
    order_id: uuid.UUID,
    payload: OrderStatusTransition | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_vendor),
) -> Order:
    order = await _load_order(db, order_id)
    await _require_owning_vendor(db, order, current_user)
    return await _apply_transition(
        db, order, OrderStatus.CONFIRMED, actor=current_user, event="order.confirmed",
        note=payload.note if payload else None,
    )


@router.post(
    "/{order_id}/accept",
    response_model=OrderRead,
    summary="Accept a confirmed order for delivery (Rider only)",
)
async def accept_order(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_rider),
) -> Order:
    order = await _load_order(db, order_id)
    if order.status != OrderStatus.CONFIRMED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only confirmed orders can be accepted",
        )
    if order.rider_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This order already has a rider assigned",
        )
    crud_order.assign_rider(order, current_user.id)
    await db.commit()
    await _publish(order, "order.rider_assigned", order.status)
    return order


@router.post(
    "/{order_id}/dispatch",
    response_model=OrderRead,
    summary="Dispatch a confirmed, rider-assigned order (owning Vendor only)",
)
async def dispatch_order(
    order_id: uuid.UUID,
    payload: OrderStatusTransition | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_vendor),
) -> Order:
    order = await _load_order(db, order_id)
    await _require_owning_vendor(db, order, current_user)
    if order.rider_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A rider must accept the order before it can be dispatched",
        )
    return await _apply_transition(
        db, order, OrderStatus.DISPATCHED, actor=current_user, event="order.dispatched",
        note=payload.note if payload else None,
    )


@router.post(
    "/{order_id}/deliver",
    response_model=OrderRead,
    summary="Mark a dispatched order as delivered (assigned Rider only)",
)
async def deliver_order(
    order_id: uuid.UUID,
    payload: OrderStatusTransition | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_rider),
) -> Order:
    order = await _load_order(db, order_id)
    if order.rider_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assigned rider can complete this delivery",
        )
    return await _apply_transition(
        db, order, OrderStatus.DELIVERED, actor=current_user, event="order.delivered",
        note=payload.note if payload else None,
    )


@router.post(
    "/{order_id}/cancel",
    response_model=OrderRead,
    summary="Cancel an order before dispatch (Customer or owning Vendor)",
)
async def cancel_order(
    order_id: uuid.UUID,
    payload: OrderStatusTransition | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Order:
    order = await _load_order(db, order_id)

    is_customer = current_user.role == UserRole.CUSTOMER and order.customer_id == current_user.id
    if current_user.role == UserRole.VENDOR:
        vendor = await crud_vendor.get_vendor_by_owner(db, current_user.id)
        is_vendor = vendor is not None and vendor.id == order.vendor_id
    else:
        is_vendor = False

    if not (is_customer or is_vendor):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the customer or owning vendor can cancel this order",
        )

    return await _apply_transition(
        db, order, OrderStatus.CANCELLED, actor=current_user, event="order.cancelled",
        note=payload.note if payload else None,
    )
