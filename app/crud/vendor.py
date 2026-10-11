"""CRUD operations for vendors, including proximity search."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.geo import (
    distance_km,
    latitude_of,
    longitude_of,
    make_geography,
    within_radius,
)
from app.models.vendor import Vendor
from app.schemas.vendor import VendorCreate, VendorUpdate

# Row shape returned by coordinate-aware queries.
VendorRow = tuple[Vendor, float, float]
VendorNearbyRow = tuple[Vendor, float, float, float]


def _with_coordinates() -> Select:
    return select(
        Vendor,
        latitude_of(Vendor.location).label("latitude"),
        longitude_of(Vendor.location).label("longitude"),
    )


async def get_vendor(db: AsyncSession, vendor_id: uuid.UUID) -> Vendor | None:
    return await db.get(Vendor, vendor_id)


async def get_vendor_row(
    db: AsyncSession, vendor_id: uuid.UUID
) -> VendorRow | None:
    result = await db.execute(_with_coordinates().where(Vendor.id == vendor_id))
    return result.one_or_none()


async def get_vendor_by_owner(db: AsyncSession, owner_id: uuid.UUID) -> Vendor | None:
    result = await db.execute(select(Vendor).where(Vendor.owner_id == owner_id))
    return result.scalar_one_or_none()


async def get_vendor_by_owner_row(
    db: AsyncSession, owner_id: uuid.UUID
) -> VendorRow | None:
    result = await db.execute(_with_coordinates().where(Vendor.owner_id == owner_id))
    return result.one_or_none()


async def create_vendor(
    db: AsyncSession, owner_id: uuid.UUID, data: VendorCreate
) -> Vendor:
    vendor = Vendor(
        owner_id=owner_id,
        name=data.name,
        description=data.description,
        address=data.address,
        location=make_geography(data.latitude, data.longitude),
        is_open=data.is_open,
    )
    db.add(vendor)
    await db.flush()
    await db.refresh(vendor)
    return vendor


async def update_vendor(
    db: AsyncSession, vendor: Vendor, data: VendorUpdate
) -> Vendor:
    payload = data.model_dump(exclude_unset=True)
    latitude = payload.pop("latitude", None)
    longitude = payload.pop("longitude", None)
    for field, value in payload.items():
        setattr(vendor, field, value)
    if latitude is not None and longitude is not None:
        vendor.location = make_geography(latitude, longitude)
    await db.flush()
    await db.refresh(vendor)
    return vendor


async def list_nearby_vendors(
    db: AsyncSession,
    *,
    latitude: float,
    longitude: float,
    radius_km: float,
    limit: int = 50,
    offset: int = 0,
    only_open: bool = False,
) -> list[VendorNearbyRow]:
    distance = distance_km(Vendor.location, latitude, longitude).label("distance_km")
    stmt = (
        select(
            Vendor,
            latitude_of(Vendor.location).label("latitude"),
            longitude_of(Vendor.location).label("longitude"),
            distance,
        )
        .where(Vendor.is_active.is_(True))
        .where(within_radius(Vendor.location, latitude, longitude, radius_km))
    )
    if only_open:
        stmt = stmt.where(Vendor.is_open.is_(True))
    stmt = stmt.order_by(distance).limit(limit).offset(offset)

    result = await db.execute(stmt)
    return [tuple(row) for row in result.all()]  # type: ignore[misc]


async def count_nearby_vendors(
    db: AsyncSession,
    *,
    latitude: float,
    longitude: float,
    radius_km: float,
    only_open: bool = False,
) -> int:
    stmt = (
        select(func.count(Vendor.id))
        .where(Vendor.is_active.is_(True))
        .where(within_radius(Vendor.location, latitude, longitude, radius_km))
    )
    if only_open:
        stmt = stmt.where(Vendor.is_open.is_(True))
    result = await db.execute(stmt)
    return int(result.scalar_one())
