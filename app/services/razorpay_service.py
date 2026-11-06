import hashlib
import hmac
import json
import uuid
from decimal import Decimal
from typing import Any, Dict, Optional

import httpx
from fastapi import HTTPException, status

from app.core.config import settings


class RazorpayService:
    API_BASE = "https://api.razorpay.com/v1"

    @staticmethod
    def is_configured() -> bool:
        return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)

    @staticmethod
    def get_public_key() -> str:
        return settings.RAZORPAY_KEY_ID or ""

    @staticmethod
    def _auth() -> tuple[str, str]:
        if not RazorpayService.is_configured():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Razorpay is not configured. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET.",
            )
        return settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET

    @staticmethod
    def inr_to_paise(amount_inr: Decimal) -> int:
        paise = int((amount_inr * 100).quantize(Decimal("1")))
        if paise <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Amount must be greater than zero.",
            )
        return paise

    @staticmethod
    def create_order(
        *,
        amount_paise: int,
        receipt: str,
        notes: Optional[Dict[str, str]] = None,
        currency: str = "INR",
    ) -> Dict[str, Any]:
        if settings.ENVIRONMENT == "development" and not RazorpayService.is_configured():
            return {
                "id": f"order_dev_{uuid.uuid4().hex[:14]}",
                "amount": amount_paise,
                "currency": currency,
                "receipt": receipt,
                "status": "created",
            }

        payload = {
            "amount": amount_paise,
            "currency": currency,
            "receipt": receipt,
            "payment_capture": 1,
        }
        if notes:
            payload["notes"] = notes

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{RazorpayService.API_BASE}/orders",
                json=payload,
                auth=RazorpayService._auth(),
            )
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Razorpay order creation failed: {resp.text}",
            )
        return resp.json()

    @staticmethod
    def fetch_order(order_id: str) -> Dict[str, Any]:
        """Load the Razorpay order so checkout uses the same amount and key."""
        if order_id.startswith("order_dev_"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This is a local test order. Razorpay checkout needs a real order from the configured key.",
            )
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(
                f"{RazorpayService.API_BASE}/orders/{order_id}",
                auth=RazorpayService._auth(),
            )
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Razorpay rejected this order. Create a new top-up order and try again.",
            )
        return resp.json()

    @staticmethod
    def checkout_amount_paise(query_amount: int, stored_paise: Optional[int] = None) -> int:
        """Checkout amount must match the order in paise. Callers sometimes send rupees."""
        if stored_paise and stored_paise > 0:
            return int(stored_paise)
        if query_amount < 1000:
            return query_amount * 100
        return query_amount

    @staticmethod
    def checkout_contact(value: str) -> str:
        digits = "".join(ch for ch in (value or "") if ch.isdigit())
        if digits.startswith("91") and len(digits) == 12:
            digits = digits[2:]
        if len(digits) == 10 and digits[0] in "6789":
            return digits
        return ""

    @staticmethod
    def checkout_email(value: str) -> str:
        email = (value or "").strip()
        if "@" not in email or " " in email or email.endswith("@logo.customer"):
            return ""
        return email[:120]

    @staticmethod
    def verify_payment_signature(
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str,
    ) -> None:
        if settings.ENVIRONMENT == "development" and not RazorpayService.is_configured():
            if razorpay_signature == "dev_signature_ok":
                return
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid payment signature (dev mode expects dev_signature_ok).",
            )

        secret = settings.RAZORPAY_KEY_SECRET
        if not secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Razorpay secret not configured.",
            )
        message = f"{razorpay_order_id}|{razorpay_payment_id}".encode()
        expected = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, razorpay_signature):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Razorpay payment signature.",
            )

    @staticmethod
    def verify_webhook_signature(body: bytes, signature: str) -> None:
        secret = settings.RAZORPAY_WEBHOOK_SECRET or settings.RAZORPAY_KEY_SECRET
        if not secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Razorpay webhook secret not configured.",
            )
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature or ""):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Razorpay webhook signature.",
            )

    @staticmethod
    def parse_webhook_payment(body: bytes) -> Optional[Dict[str, str]]:
        try:
            payload = json.loads(body.decode())
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        event = payload.get("event") or ""
        if event not in ("payment.captured", "order.paid"):
            return None
        entity = (payload.get("payload") or {}).get("payment") or {}
        payment = entity.get("entity") if isinstance(entity, dict) else None
        if not payment:
            order_wrap = (payload.get("payload") or {}).get("order") or {}
            payment = order_wrap.get("entity") if isinstance(order_wrap, dict) else None
        if not payment or not isinstance(payment, dict):
            return None
        order_id = payment.get("order_id")
        payment_id = payment.get("id")
        if not order_id or not payment_id:
            return None
        return {
            "razorpay_order_id": str(order_id),
            "razorpay_payment_id": str(payment_id),
        }
