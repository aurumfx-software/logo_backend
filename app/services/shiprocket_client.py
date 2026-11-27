"""Thin Shiprocket API client. Tokens stay in process memory and are renewed on expiry or 401."""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from fastapi import HTTPException, status

from app.core.config import settings


class ShiprocketClient:
    _token: Optional[str] = None
    _expires_at: Optional[datetime] = None

    def __init__(self) -> None:
        self.base = (settings.SHIPROCKET_BASE_URL or "https://apiv2.shiprocket.in/v1/external").rstrip("/")

    def configured(self) -> bool:
        return bool((settings.SHIPROCKET_EMAIL or "").strip() and (settings.SHIPROCKET_PASSWORD or "").strip())

    def token(self) -> str:
        now = datetime.now(timezone.utc)
        if self._token and self._expires_at and self._expires_at > now:
            return self._token
        if not self.configured():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Shiprocket credentials are not configured on the server.",
            )
        try:
            response = httpx.post(
                f"{self.base}/auth/login",
                json={"email": settings.SHIPROCKET_EMAIL, "password": settings.SHIPROCKET_PASSWORD},
                timeout=30.0,
            )
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not reach Shiprocket.") from exc
        data = _json_or_error(response)
        token = data.get("token")
        if response.status_code >= 400 or not token:
            message = data.get("message") or "Shiprocket login failed."
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(message))
        ShiprocketClient._token = token
        # Shiprocket tokens last about 10 days. Renew a day early.
        ShiprocketClient._expires_at = now + timedelta(days=9)
        return token

    def request(self, method: str, path: str, *, json: Optional[dict] = None, params: Optional[dict] = None, _retry: bool = True) -> dict:
        try:
            response = httpx.request(
                method,
                f"{self.base}/{path.lstrip('/')}",
                json=json,
                params=params,
                headers={"Authorization": f"Bearer {self.token()}", "Content-Type": "application/json"},
                timeout=40.0,
            )
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Shiprocket request failed.") from exc
        if response.status_code == 401 and _retry:
            ShiprocketClient._token = None
            ShiprocketClient._expires_at = None
            return self.request(method, path, json=json, params=params, _retry=False)
        data = _json_or_error(response)
        if response.status_code >= 400:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=_message(data) or "Shiprocket rejected the request.")
        return data


def _json_or_error(response: httpx.Response) -> dict:
    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Shiprocket returned an invalid response.") from exc
    if isinstance(payload, dict):
        return payload
    return {"data": payload}


def _message(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    message = data.get("message") or data.get("error") or ""
    if isinstance(message, dict):
        parts = []
        for value in message.values():
            if isinstance(value, list):
                parts.extend(str(item) for item in value)
            else:
                parts.append(str(value))
        return " ".join(parts)
    return str(message)
