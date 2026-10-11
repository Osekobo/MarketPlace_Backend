"""Product endpoints (vendor-owned catalogue)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, require_vendor
from app.crud import product as crud_product
from app.crud import vendor as crud_vendor
from app.db.session import get_db
from app.models.user import User
from app.schemas.product import ProductCreate, ProductRead, ProductUpdate

router = APIRouter(prefix="/products", tags=["products"])


async def _get_owned_vendor(db: AsyncSession, user: User):
    vendor = await crud_vendor.get_vendor_by_owner(db, user.id)
    if vendor is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Create a vendor storefront before managing products",
        )
    return vendor


@router.post(
    "",
    response_model=ProductRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a product (Vendor only)",
)
async def create_product(
    payload: ProductCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_vendor),
):
    vendor = await _get_owned_vendor(db, current_user)
    return await crud_product.create_product(db, vendor.id, payload)


@router.get(
    "",
    response_model=list[ProductRead],
    summary="List products, optionally filtered by vendor",
)
async def list_products(
    vendor_id: uuid.UUID = Query(..., description="Vendor to list products for"),
    only_available: bool = Query(False),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    return await crud_product.list_products_by_vendor(
        db, vendor_id, only_available=only_available, limit=limit, offset=offset
    )


@router.get("/{product_id}", response_model=ProductRead, summary="Get a product")
async def read_product(
    product_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    product = await crud_product.get_product(db, product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )
    return product


@router.patch(
    "/{product_id}",
    response_model=ProductRead,
    summary="Update a product (owning Vendor only)",
)
async def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_vendor),
):
    vendor = await _get_owned_vendor(db, current_user)
    product = await crud_product.get_product(db, product_id)
    if product is None or product.vendor_id != vendor.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found for this vendor",
        )
    return await crud_product.update_product(db, product, payload)


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a product (owning Vendor only)",
)
async def delete_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_vendor),
) -> None:
    vendor = await _get_owned_vendor(db, current_user)
    product = await crud_product.get_product(db, product_id)
    if product is None or product.vendor_id != vendor.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found for this vendor",
        )
    await crud_product.delete_product(db, product)
