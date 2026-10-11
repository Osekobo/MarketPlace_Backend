"""WebSocket route for real-time order status updates."""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError

from app.core.security import ACCESS_TOKEN_TYPE, decode_token
from app.crud import order as crud_order
from app.crud import user as crud_user
from app.crud import vendor as crud_vendor
from app.db.session import AsyncSessionLocal
from app.websockets.manager import json_dumps, manager

logger = logging.getLogger("app.websockets")

router = APIRouter()

# Custom close codes (application range 4000-4999).
WS_UNAUTHORIZED = 4401
WS_FORBIDDEN = 4403
WS_NOT_FOUND = 4404


async def _authorize(token: str, order_id: uuid.UUID) -> bool:
    """Validate the JWT and confirm the user is a party to the order."""
    try:
        claims = decode_token(token)
    except JWTError:
        return False
    if claims.get("type") != ACCESS_TOKEN_TYPE:
        return False
    try:
        user_id = uuid.UUID(str(claims.get("sub")))
    except (ValueError, TypeError):
        return False

    async with AsyncSessionLocal() as db:
        user = await crud_user.get_user(db, user_id)
        if user is None or not user.is_active:
            return False

        order = await crud_order.get_order(db, order_id)
        if order is None:
            return False
        if order.customer_id == user.id or order.rider_id == user.id:
            return True

        vendor = await crud_vendor.get_vendor(db, order.vendor_id)
        return vendor is not None and vendor.owner_id == user.id


@router.websocket("/ws/orders/{order_id}")
async def order_status_socket(websocket: WebSocket, order_id: uuid.UUID) -> None:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=WS_UNAUTHORIZED, reason="Missing token")
        return

    if not await _authorize(token, order_id):
        await websocket.close(code=WS_FORBIDDEN, reason="Not authorized for this order")
        return

    key = str(order_id)
    await manager.connect(key, websocket)

    # Send a snapshot so late joiners immediately see the current state.
    async with AsyncSessionLocal() as db:
        order = await crud_order.get_order(db, order_id)
        if order is not None:
            await websocket.send_text(
                json_dumps(
                    {
                        "event": "connected",
                        "order_id": key,
                        "data": {
                            "status": order.status.value,
                            "rider_id": str(order.rider_id) if order.rider_id else None,
                        },
                    }
                )
            )

    try:
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_text(json_dumps({"event": "pong"}))
    except WebSocketDisconnect:
        pass
    except Exception:  # pragma: no cover
        logger.exception("WebSocket error for order %s", key)
    finally:
        await manager.disconnect(key, websocket)
