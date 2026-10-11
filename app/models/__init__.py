"""ORM models. Importing this package registers every table on ``Base.metadata``."""
from app.models.enums import (
    ORDER_STATUS_TRANSITIONS,
    OrderStatus,
    UserRole,
    can_transition,
    next_statuses,
)
from app.models.order import Order, OrderItem, OrderStatusEvent
from app.models.product import Product
from app.models.user import User
from app.models.vendor import Vendor

__all__ = [
    "User",
    "UserRole",
    "Vendor",
    "Product",
    "Order",
    "OrderItem",
    "OrderStatusEvent",
    "OrderStatus",
    "ORDER_STATUS_TRANSITIONS",
    "can_transition",
    "next_statuses",
]
