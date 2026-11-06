from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models.merchant import MerchantProfile
from app.db.models.user import User, UserRole
from app.services.razorpay_service import RazorpayService
from app.services.wallet_service import WalletService


def _auth_headers(client: TestClient, email: str) -> dict:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _merchant(db_session: Session, email: str = "rpmerchant@example.com") -> User:
    user = User(
        name="RP Merchant",
        email=email,
        password_hash=hash_password("Password123!"),
        role=UserRole.MERCHANT,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    WalletService.ensure_wallet_for_user(db_session, user.id)
    profile = MerchantProfile(
        user_id=user.id,
        business_name="RP Shop",
        email=email,
        password_hash=user.password_hash,
        approval_status="APPROVED",
        status="APPROVED",
        is_active=True,
    )
    db_session.add(profile)
    db_session.commit()
    return user


def test_razorpay_topup_dev_flow(client: TestClient, db_session: Session):
    user = _merchant(db_session)
    headers = _auth_headers(client, user.email)

    cfg = client.get("/api/v1/wallet/topup/razorpay/config")
    assert cfg.status_code == 200

    order_res = client.post(
        "/api/v1/wallet/topup/razorpay/order",
        headers=headers,
        json={"amount": "500.00"},
    )
    assert order_res.status_code == 201
    body = order_res.json()
    assert body["amount"] == "500.00"
    assert body["razorpay_order_id"]
    assert body["amount_paise"] == 50000

    verify_res = client.post(
        "/api/v1/wallet/topup/razorpay/verify",
        headers=headers,
        json={
            "razorpay_order_id": body["razorpay_order_id"],
            "razorpay_payment_id": "pay_dev_test_001",
            "razorpay_signature": "dev_signature_ok",
        },
    )
    assert verify_res.status_code == 200
    assert verify_res.json()["wallet_balance"] == "500.00"

    wallet_res = client.get("/api/v1/wallet/me", headers=headers)
    assert wallet_res.json()["wallet"]["balance"] == "500.00"

    dup = client.post(
        "/api/v1/wallet/topup/razorpay/verify",
        headers=headers,
        json={
            "razorpay_order_id": body["razorpay_order_id"],
            "razorpay_payment_id": "pay_dev_test_001",
            "razorpay_signature": "dev_signature_ok",
        },
    )
    assert dup.status_code == 200
    assert "already credited" in dup.json()["message"].lower()


def test_checkout_amount_and_contact():
    assert RazorpayService.checkout_amount_paise(500, 50000) == 50000
    assert RazorpayService.checkout_amount_paise(500, None) == 50000
    assert RazorpayService.checkout_amount_paise(25000, None) == 25000
    assert RazorpayService.checkout_contact("+91 98765 43210") == "9876543210"
    assert RazorpayService.checkout_contact("123") == ""
    assert RazorpayService.checkout_email("shop@example.com") == "shop@example.com"
    assert RazorpayService.checkout_email("user@logo.customer") == ""


def test_checkout_page_without_razorpay_key(client: TestClient):
    res = client.get(
        "/api/v1/wallet/topup/razorpay/checkout",
        params={"order_id": "order_test_missing", "amount": 50000},
    )
    assert res.status_code == 503
    assert "not configured" in res.text.lower()
    assert "rzp_test_TvBAWzKfk5F60i" not in res.text
