"""Vendor schemas, including geospatial search results."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VendorBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    address: str = Field(..., min_length=1, max_length=512)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class VendorCreate(VendorBase):
    is_open: bool = True


class VendorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    address: str | None = Field(default=None, min_length=1, max_length=512)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    is_open: bool | None = None
    is_active: bool | None = None

    @field_validator("longitude")
    @classmethod
    def _require_pair(cls, v: float | None, info) -> float | None:  # noqa: ANN001
        # latitude/longitude must be supplied together when updating location.
        if v is not None and info.data.get("latitude") is None:
            raise ValueError("latitude must be provided together with longitude")
        return v


class VendorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    description: str | None
    address: str
    latitude: float
    longitude: float
    is_active: bool
    is_open: bool
    rating: float
    created_at: datetime


class VendorWithDistance(VendorRead):
    distance_km: float


class NearbySearchResponse(BaseModel):
    center_latitude: float
    center_longitude: float
    radius_km: float
    count: int
    results: list[VendorWithDistance]
