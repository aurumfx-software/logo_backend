import logging

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.api.deps import authenticate_websocket_user
from app.db.database import get_db
from app.services.wallet_ws_manager import wallet_ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wallet", tags=["Wallet"])


@router.websocket(
    "/ws",
    name="wallet_realtime",
)
async def wallet_realtime_socket(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token (same as Authorization Bearer)"),
    db: Session = Depends(get_db),
) -> None:
    """
    Realtime wallet events (sale QR redeemed, balances).

    Connect: ``wss://<host>/api/v1/wallet/ws?token=<access_token>``

    Client JSON messages:
    - ``{"action": "subscribe", "token": "<sale_qr_token>"}``
    - ``{"action": "ping"}``

    Server push: ``{"event": "sale_qr.redeemed", ...}``
    """
    conn = None
    try:
        user = authenticate_websocket_user(token=token, db=db)
        await websocket.accept()
        conn = await wallet_ws_manager.connect(websocket, user.id)
        while True:
            raw = await websocket.receive_text()
            await wallet_ws_manager.handle_client_message(conn, raw)
    except WebSocketDisconnect:
        pass
    finally:
        if conn is not None:
            wallet_ws_manager.disconnect(conn)
