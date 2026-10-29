"""In-process WebSocket fan-out for wallet / sale-QR events (single API instance).

For multiple workers, add Redis pub/sub and forward to local connections.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass
class WalletWSConnection:
    websocket: WebSocket
    user_id: int
    subscribed_tokens: Set[str] = field(default_factory=set)


class WalletWSManager:
    def __init__(self) -> None:
        self._connections: Dict[int, Set[WalletWSConnection]] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def bind_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, websocket: WebSocket, user_id: int) -> WalletWSConnection:
        conn = WalletWSConnection(websocket=websocket, user_id=user_id)
        self._connections.setdefault(user_id, set()).add(conn)
        await self._send_json(
            conn,
            {
                "event": "connected",
                "user_id": user_id,
                "message": "Wallet realtime connected. Send subscribe with a sale QR token while waiting for payment.",
            },
        )
        return conn

    def disconnect(self, conn: WalletWSConnection) -> None:
        bucket = self._connections.get(conn.user_id)
        if not bucket:
            return
        bucket.discard(conn)
        if not bucket:
            self._connections.pop(conn.user_id, None)

    async def handle_client_message(self, conn: WalletWSConnection, raw: str) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            await self._send_json(conn, {"event": "error", "message": "Invalid JSON"})
            return

        action = (data.get("action") or "").strip().lower()
        if action in ("ping", "pong"):
            await self._send_json(conn, {"event": "pong"})
            return

        if action == "subscribe":
            token = (data.get("token") or "").strip()
            if not token:
                await self._send_json(conn, {"event": "error", "message": "token is required for subscribe"})
                return
            conn.subscribed_tokens.add(token)
            await self._send_json(
                conn,
                {"event": "subscribed", "token": token, "message": f"Listening for sale QR {token}"},
            )
            return

        if action == "unsubscribe":
            token = (data.get("token") or "").strip()
            if token and token in conn.subscribed_tokens:
                conn.subscribed_tokens.discard(token)
            await self._send_json(conn, {"event": "unsubscribed", "token": token or None})
            return

        await self._send_json(conn, {"event": "error", "message": f"Unknown action: {action}"})

    def publish_sale_qr_redeemed(self, merchant_user_id: int, payload: Dict[str, Any]) -> None:
        """Thread-safe entry from sync wallet code after DB commit."""
        message = {"event": "sale_qr.redeemed", **payload}
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self._broadcast_to_merchant(merchant_user_id, message))
            )
            return
        logger.warning("Wallet WS: no event loop bound; skipping realtime push for merchant %s", merchant_user_id)

    async def _broadcast_to_merchant(self, merchant_user_id: int, message: Dict[str, Any]) -> None:
        token = message.get("token")
        for conn in list(self._connections.get(merchant_user_id, set())):
            if conn.subscribed_tokens and token and token not in conn.subscribed_tokens:
                continue
            try:
                await self._send_json(conn, message)
            except Exception:
                logger.exception("Wallet WS: failed to send to user %s", merchant_user_id)

    @staticmethod
    async def _send_json(conn: WalletWSConnection, payload: Dict[str, Any]) -> None:
        await conn.websocket.send_json(payload)


wallet_ws_manager = WalletWSManager()
