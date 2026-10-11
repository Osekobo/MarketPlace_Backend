"""Helpers for building PostGIS geography expressions with SQLAlchemy."""
from __future__ import annotations

from typing import Any

from geoalchemy2 import Geography, Geometry
from sqlalchemy import cast, func


def make_point(latitude: float, longitude: float) -> Any:
    """Build a POINT geometry expression in SRID 4326 (lon, lat ordering)."""
    return func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326)


def make_geography(latitude: float, longitude: float) -> Any:
    """Build a geography expression suitable for ST_DWithin / ST_Distance."""
    return cast(make_point(latitude, longitude), Geography(srid=4326))


def longitude_of(column: Any) -> Any:
    return func.ST_X(cast(column, Geometry))


def latitude_of(column: Any) -> Any:
    return func.ST_Y(cast(column, Geometry))


def distance_km(column: Any, latitude: float, longitude: float) -> Any:
    """SQL expression: distance in kilometres between ``column`` and the point."""
    return func.ST_Distance(column, make_geography(latitude, longitude)) / 1000.0


def within_radius(column: Any, latitude: float, longitude: float, radius_km: float) -> Any:
    """SQL expression: ``ST_DWithin`` predicate (radius converted to metres)."""
    return func.ST_DWithin(
        column, make_geography(latitude, longitude), radius_km * 1000.0
    )
