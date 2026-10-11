"""Aggregate API v1 routers."""
from fastapi import APIRouter

from app.api.v1.endpoints import auth, orders, products, vendors

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(vendors.router)
api_router.include_router(products.router)
api_router.include_router(orders.router)
