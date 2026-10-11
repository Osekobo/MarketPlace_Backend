"""Order schemas."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import OrderStatus


class OrderItemCreate(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(..., gt=0)


class OrderCreate(BaseModel):
    vendor_id: uuid.UUID
    items: list[OrderItemCreate] = Field(..., min_length=1)
    delivery_address: str = Field(..., min_length=1, max_length=512)
    delivery_latitude: float | None = Field(default=None, ge=-90, le=90)
    delivery_longitude: float | None = Field(default=None, ge=-180, le=180)


class OrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    unit_price: float
    line_total: float


class OrderStatusEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_status: OrderStatus | None
    to_status: OrderStatus
    actor_id: uuid.UUID | None
    note: str | None
    created_at: datetime


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    vendor_id: uuid.UUID
    rider_id: uuid.UUID | None
    status: OrderStatus
    total_amount: float
    currency: str
    delivery_address: str
    placed_at: datetime
    confirmed_at: datetime | None
    dispatched_at: datetime | None
    delivered_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemRead] = []


class OrderStatusTransition(BaseModel):
    """Payload for lifecycle transitions that accept an optional note."""

    note: str | None = Field(default=None, max_length=500)
