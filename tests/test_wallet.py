from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models.merchant import MerchantProfile
from app.db.models.user import User, UserRole
from app.services.wallet_service import WalletService


def _auth_headers(client: TestClient, email: str, password: str) -> dict:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert res.status_code == 200
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_user(db_session: Session, email: str, name: str, role: UserRole = UserRole.FIELD_STAFF) -> User:
    user = User(
        name=name,
        email=email,
        password_hash=hash_password("Password123!"),
        role=role,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    WalletService.ensure_wallet_for_user(db_session, user.id)
    db_session.commit()
    return user


def _create_merchant(db_session: Session, email: str) -> User:
    user = _create_user(db_session, email, "Merchant Owner")
    merchant = MerchantProfile(
        user_id=user.id,
        business_name="Test Shop",
        approval_status="APPROVED",
        status="APPROVED",
        is_active=True,
    )
    db_session.add(merchant)
    db_session.commit()
    return user


def test_wallet_created_and_p2p_transfer(client: TestClient, db_session: Session):
    sender = _create_user(db_session, "sender@example.com", "Sender")
    recipient = _create_user(db_session, "recipient@example.com", "Recipient")

    admin = _create_user(db_session, "admin@example.com", "Admin", UserRole.ADMIN)
    admin_headers = _auth_headers(client, admin.email, "Password123!")

    fund_res = client.post(
        "/api/v1/wallet/admin/adjust",
        headers=admin_headers,
        json={"user_id": sender.id, "amount": "500.00", "operation": "credit", "note": "seed"},
    )
    assert fund_res.status_code == 200

    sender_headers = _auth_headers(client, sender.email, "Password123!")
    transfer_res = client.post(
        "/api/v1/wallet/transfer",
        headers=sender_headers,
        json={"to_user_id": recipient.id, "amount": "100.50", "note": "thanks"},
    )
    assert transfer_res.status_code == 200
    data = transfer_res.json()
    assert data["sender_balance"] == "399.50"
    assert data["recipient_balance"] == "100.50"

    tx_res = client.get("/api/v1/wallet/transactions", headers=sender_headers)
    assert tx_res.status_code == 200
    assert tx_res.json()["total"] >= 2


def test_sale_qr_cashback_split(client: TestClient, db_session: Session):
    merchant_user = _create_merchant(db_session, "merchant@example.com")
    customer = _create_user(db_session, "customer@example.com", "Customer")
    admin = _create_user(db_session, "walletadmin@example.com", "Wallet Admin", UserRole.ADMIN)
    admin_headers = _auth_headers(client, admin.email, "Password123!")

    client.post(
        "/api/v1/wallet/admin/adjust",
        headers=admin_headers,
        json={"user_id": merchant_user.id, "amount": "1000.00", "operation": "credit"},
    )

    merchant_headers = _auth_headers(client, merchant_user.email, "Password123!")
    qr_res = client.post(
        "/api/v1/wallet/sales/qr",
        headers=merchant_headers,
        json={"sale_amount": "1000.00"},
    )
    assert qr_res.status_code == 201
    token = qr_res.json()["token"]
    assert qr_res.json()["estimated_user_cashback"] == "30.00"
    assert qr_res.json()["estimated_company_fee"] == "20.00"

    customer_headers = _auth_headers(client, customer.email, "Password123!")
    redeem_res = client.post(
        "/api/v1/wallet/sales/redeem",
        headers=customer_headers,
        json={"token": token},
    )
    assert redeem_res.status_code == 200
    body = redeem_res.json()
    assert body["user_cashback"] == "30.00"
    assert body["company_fee"] == "20.00"
    assert body["merchant_debit"] == "50.00"
    assert body["user_wallet_balance"] == "30.00"

    wallet_res = client.get("/api/v1/wallet/me", headers=merchant_headers)
    assert wallet_res.json()["wallet"]["balance"] == "950.00"

    dup_res = client.post(
        "/api/v1/wallet/sales/redeem",
        headers=customer_headers,
        json={"token": token},
    )
    assert dup_res.status_code == 400


def test_insufficient_merchant_balance_blocks_redeem(client: TestClient, db_session: Session):
    merchant_user = _create_merchant(db_session, "poormerchant@example.com")
    customer = _create_user(db_session, "buyer@example.com", "Buyer")

    merchant_headers = _auth_headers(client, merchant_user.email, "Password123!")
    qr_res = client.post(
        "/api/v1/wallet/sales/qr",
        headers=merchant_headers,
        json={"sale_amount": "1000.00"},
    )
    token = qr_res.json()["token"]

    customer_headers = _auth_headers(client, customer.email, "Password123!")
    redeem_res = client.post(
        "/api/v1/wallet/sales/redeem",
        headers=customer_headers,
        json={"token": token},
    )
    assert redeem_res.status_code == 400
    assert "Insufficient" in redeem_res.json()["message"]
