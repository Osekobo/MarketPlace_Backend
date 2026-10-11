"""CRUD operations for products."""
from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.schemas.product import ProductCreate, ProductUpdate


async def get_product(db: AsyncSession, product_id: uuid.UUID) -> Product | None:
    return await db.get(Product, product_id)


async def get_products_by_ids(
    db: AsyncSession, product_ids: Sequence[uuid.UUID]
) -> list[Product]:
    if not product_ids:
        return []
    result = await db.execute(select(Product).where(Product.id.in_(product_ids)))
    return list(result.scalars().all())


async def list_products_by_vendor(
    db: AsyncSession,
    vendor_id: uuid.UUID,
    *,
    only_available: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[Product]:
    stmt = select(Product).where(Product.vendor_id == vendor_id)
    if only_available:
        stmt = stmt.where(Product.is_available.is_(True))
    stmt = stmt.order_by(Product.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_product(
    db: AsyncSession, vendor_id: uuid.UUID, data: ProductCreate
) -> Product:
    product = Product(vendor_id=vendor_id, **data.model_dump())
    db.add(product)
    await db.flush()
    await db.refresh(product)
    return product


async def update_product(
    db: AsyncSession, product: Product, data: ProductUpdate
) -> Product:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    await db.flush()
    await db.refresh(product)
    return product


async def delete_product(db: AsyncSession, product: Product) -> None:
    await db.delete(product)
    await db.flush()
