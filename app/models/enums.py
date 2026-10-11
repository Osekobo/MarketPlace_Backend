"""Domain enums and the order status state machine."""
from __future__ import annotations

import enum


class UserRole(str, enum.Enum):
    CUSTOMER = "customer"
    VENDOR = "vendor"
    RIDER = "rider"


class OrderStatus(str, enum.Enum):
    PLACED = "placed"
    CONFIRMED = "confirmed"
    DISPATCHED = "dispatched"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


# Strict order lifecycle: Placed -> Confirmed -> Dispatched -> Delivered.
# CANCELLED is a terminal escape hatch reachable only before dispatch.
ORDER_STATUS_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.PLACED: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED: {OrderStatus.DISPATCHED, OrderStatus.CANCELLED},
    OrderStatus.DISPATCHED: {OrderStatus.DELIVERED},
    OrderStatus.DELIVERED: set(),
    OrderStatus.CANCELLED: set(),
}


def can_transition(current: OrderStatus, target: OrderStatus) -> bool:
    """Return ``True`` if ``current`` may legally move to ``target``."""
    return target in ORDER_STATUS_TRANSITIONS.get(current, set())


def next_statuses(current: OrderStatus) -> set[OrderStatus]:
    return ORDER_STATUS_TRANSITIONS.get(current, set())
