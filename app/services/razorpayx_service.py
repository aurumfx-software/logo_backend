import hashlib
import hmac
import uuid
from decimal import Decimal
from typing import Any, Dict, Optional

import httpx
from fastapi import HTTPException, status

from app.core.config import settings


class RazorpayXService:
    """Send wallet withdrawals through RazorpayX Payouts (IMPS is near real time)."""

    API_BASE = "https://api.razorpay.com/v1"
    _FAILED = {"rejected", "failed", "reversed", "cancelled"}
    _DONE = {"processed"}

    @staticmethod
    def _usable(value: Optional[str]) -> str:
        text = (value or "").strip()
        if not text or "dummy" in text.lower():
            return ""
        return text

    @staticmethod
    def _credentials() -> tuple[str, str, str]:
        """Dummy .env values are ignored. RazorpayX uses the same key pair as Payments."""
        key_id = RazorpayXService._usable(settings.RAZORPAYX_KEY_ID) or RazorpayXService._usable(
            settings.RAZORPAY_KEY_ID
        )
        key_secret = RazorpayXService._usable(settings.RAZORPAYX_KEY_SECRET) or RazorpayXService._usable(
            settings.RAZORPAY_KEY_SECRET
        )
        account_number = RazorpayXService._usable(settings.RAZORPAYX_ACCOUNT_NUMBER)
        return key_id, key_secret, account_number

    @staticmethod
    def is_configured() -> bool:
        key_id, key_secret, account_number = RazorpayXService._credentials()
        return bool(key_id and key_secret and account_number)

    @staticmethod
    def _auth() -> tuple[str, str]:
        key_id, key_secret, _account = RazorpayXService._credentials()
        if not key_id or not key_secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="RazorpayX is not configured. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET, or real RAZORPAYX keys.",
            )
        return key_id, key_secret

    @staticmethod
    def local_status(razorpay_status: Optional[str]) -> str:
        value = (razorpay_status or "processing").strip().lower()
        if value in RazorpayXService._DONE:
            return "COMPLETED"
        if value in RazorpayXService._FAILED:
            return "FAILED"
        return "PROCESSING"

    @staticmethod
    def create_payout(
        *,
        amount: Decimal,
        account_holder_name: str,
        account_number: str,
        ifsc: str,
        mode: str,
        reference_id: str,
        user_name: str,
        user_email: Optional[str],
        user_phone: Optional[str],
        user_id: int,
    ) -> Dict[str, Any]:
        payout_mode = (mode or "IMPS").strip().upper()
        if payout_mode not in {"IMPS", "NEFT", "RTGS", "UPI"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="payout_mode must be IMPS, NEFT, RTGS, or UPI.",
            )
        if not RazorpayXService.is_configured():
            if settings.ENVIRONMENT == "development":
                return {
                    "id": f"pout_dev_{uuid.uuid4().hex[:12]}",
                    "status": "processing",
                    "fund_account_id": None,
                }
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="RazorpayX is not configured. Withdrawal cannot be sent.",
            )

        contact_payload: Dict[str, Any] = {
            "name": (user_name or account_holder_name)[:50],
            "type": "customer",
            "reference_id": f"user_{user_id}"[:40],
        }
        if user_email and "@" in user_email and not user_email.endswith("@logo.customer"):
            contact_payload["email"] = user_email[:64]
        phone = "".join(ch for ch in (user_phone or "") if ch.isdigit())
        if phone.startswith("91") and len(phone) == 12:
            phone = phone[2:]
        if len(phone) == 10:
            contact_payload["contact"] = phone

        contact = RazorpayXService._post("/contacts", contact_payload)
        fund = RazorpayXService._post(
            "/fund_accounts",
            {
                "contact_id": contact["id"],
                "account_type": "bank_account",
                "bank_account": {
                    "name": account_holder_name[:50],
                    "ifsc": ifsc.strip().upper(),
                    "account_number": account_number.strip(),
                },
            },
        )
        amount_paise = int((amount * 100).quantize(Decimal("1")))
        payout = RazorpayXService._post(
            "/payouts",
            {
                "account_number": RazorpayXService._credentials()[2],
                "fund_account_id": fund["id"],
                "amount": amount_paise,
                "currency": "INR",
                "mode": payout_mode,
                "purpose": "payout",
                "queue_if_low_balance": False,
                "reference_id": reference_id[:40],
                "narration": "LOGO WALLET",
            },
            extra_headers={"X-Payout-Idempotency": reference_id},
        )
        payout["fund_account_id"] = fund.get("id")
        if RazorpayXService.local_status(payout.get("status")) == "FAILED":
            reason = payout.get("failure_reason") or payout.get("status_details", {}).get("description")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=reason or "RazorpayX rejected the payout.",
            )
        return payout

    @staticmethod
    def fetch_payout(payout_id: str) -> Dict[str, Any]:
        if not payout_id or payout_id.startswith("pout_dev_") or not RazorpayXService.is_configured():
            return {"id": payout_id, "status": "processing"}
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(
                f"{RazorpayXService.API_BASE}/payouts/{payout_id}",
                auth=RazorpayXService._auth(),
            )
        if resp.status_code >= 400:
            return {"id": payout_id, "status": "processing"}
        return resp.json()

    @staticmethod
    def verify_webhook_signature(body: bytes, signature: str) -> None:
        secret = RazorpayXService._usable(settings.RAZORPAYX_WEBHOOK_SECRET) or RazorpayXService._credentials()[1]
        if not secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="RazorpayX webhook secret is not configured.",
            )
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature or ""):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid RazorpayX webhook signature.",
            )

    @staticmethod
    def _post(path: str, payload: Dict[str, Any], extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if extra_headers:
            headers.update(extra_headers)
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{RazorpayXService.API_BASE}{path}",
                json=payload,
                auth=RazorpayXService._auth(),
                headers=headers,
            )
        if resp.status_code >= 400:
            description = resp.text
            try:
                description = resp.json().get("error", {}).get("description") or description
            except Exception:
                pass
            denied = "access denied" in description.lower() or resp.status_code in (401, 403)
            if denied:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "RazorpayX access denied. Enable RazorpayX on this Razorpay account, "
                        "whitelist server IP 168.144.18.149, and set RAZORPAYX_ACCOUNT_NUMBER "
                        "to the RazorpayX current account number. Dummy keys are ignored."
                    ),
                )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"RazorpayX payout failed: {description}",
            )
        return resp.json()
