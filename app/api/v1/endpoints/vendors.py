"""Vendor endpoints: onboarding and geospatial proximity search."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_vendor
from app.crud import vendor as crud_vendor
from app.db.session import get_db
from app.models.user import User
from app.models.vendor import Vendor
from app.schemas.vendor import (
    NearbySearchResponse,
    VendorCreate,
    VendorRead,
    VendorUpdate,
    VendorWithDistance,
)

router = APIRouter(prefix="/vendors", tags=["vendors"])


def _serialize_vendor(
    vendor: Vendor,
    latitude: float,
    longitude: float,
    distance_km: float | None = None,
) -> dict:
    payload: dict = {
        "id": vendor.id,
        "owner_id": vendor.owner_id,
        "name": vendor.name,
        "description": vendor.description,
        "address": vendor.address,
        "latitude": latitude,
        "longitude": longitude,
        "is_active": vendor.is_active,
        "is_open": vendor.is_open,
        "rating": float(vendor.rating),
        "created_at": vendor.created_at,
    }
    if distance_km is not None:
        payload["distance_km"] = round(distance_km, 3)
    return payload


@router.post(
    "",
    response_model=VendorRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create the vendor storefront for the authenticated vendor",
)
async def create_vendor(
    payload: VendorCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_vendor),
) -> dict:
    existing = await crud_vendor.get_vendor_by_owner(db, current_user.id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This vendor account already has a storefront",
        )
    vendor = await crud_vendor.create_vendor(db, current_user.id, payload)
    return _serialize_vendor(vendor, payload.latitude, payload.longitude)


@router.get(
    "/nearby",
    response_model=NearbySearchResponse,
    summary="Find vendors within a radius (PostGIS ST_DWithin), ordered by distance",
)
async def nearby_vendors(
    latitude: float = Query(..., ge=-90, le=90, description="Search origin latitude"),
    longitude: float = Query(..., ge=-180, le=180, description="Search origin longitude"),
    radius_km: float = Query(5, gt=0, le=100, description="Search radius in kilometres"),
    only_open: bool = Query(False, description="Return only currently open vendors"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> NearbySearchResponse:
    rows = await crud_vendor.list_nearby_vendors(
        db,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        limit=limit,
        offset=offset,
        only_open=only_open,
    )
    total = await crud_vendor.count_nearby_vendors(
        db,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        only_open=only_open,
    )
    results = [
        VendorWithDistance(
            **_serialize_vendor(vendor, vendor_lat, vendor_lon, distance)
        )
        for vendor, vendor_lat, vendor_lon, distance in rows
    ]
    return NearbySearchResponse(
        center_latitude=latitude,
        center_longitude=longitude,
        radius_km=radius_km,
        count=total,
        results=results,
    )


@router.get(
    "/me",
    response_model=VendorRead,
    summary="Get the authenticated vendor's storefront",
)
async def read_my_vendor(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_vendor),
) -> dict:
    row = await crud_vendor.get_vendor_by_owner_row(db, current_user.id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Vendor storefront not found"
        )
    vendor, vendor_lat, vendor_lon = row
    return _serialize_vendor(vendor, vendor_lat, vendor_lon)


@router.patch(
    "/me",
    response_model=VendorRead,
    summary="Update the authenticated vendor's storefront",
)
async def update_my_vendor(
    payload: VendorUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_vendor),
) -> dict:
    vendor = await crud_vendor.get_vendor_by_owner(db, current_user.id)
    if vendor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Vendor storefront not found"
        )
    if (payload.latitude is None) ^ (payload.longitude is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="latitude and longitude must be provided together",
        )
    await crud_vendor.update_vendor(db, vendor, payload)
    row = await crud_vendor.get_vendor_row(db, vendor.id)
    assert row is not None
    vendor_obj, vendor_lat, vendor_lon = row
    return _serialize_vendor(vendor_obj, vendor_lat, vendor_lon)


@router.get(
    "/{vendor_id}",
    response_model=VendorRead,
    summary="Get a vendor by id",
)
async def read_vendor(
    vendor_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> dict:
    row = await crud_vendor.get_vendor_row(db, vendor_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found"
        )
    vendor, vendor_lat, vendor_lon = row
    return _serialize_vendor(vendor, vendor_lat, vendor_lon)
