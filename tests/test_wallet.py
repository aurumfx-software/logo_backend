from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models.merchant import MerchantProfile
from app.db.models.user import User, UserRole
from app.services.wallet_service import WalletService


def _auth_headers(client: TestClient, email: str, password: str) -> dict:
    token = _access_token(client, email, password)
    return {"Authorization": f"Bearer {token}"}


def _access_token(client: TestClient, email: str, password: str = "Password123!") -> str:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert res.status_code == 200
    return res.json()["access_token"]


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
        email=email,
        password_hash=user.password_hash,
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

    status_res = client.get(
        f"/api/v1/wallet/sales/qr/{token}/status",
        headers=merchant_headers,
    )
    assert status_res.status_code == 200
    status_body = status_res.json()
    assert status_body["is_redeemed"] is True
    assert status_body["status"] == "REDEEMED"
    assert status_body["merchant_wallet_balance"] == "950.00"
    assert status_body["transaction_group_id"]


def test_sale_qr_uses_merchant_table_cashback_percent(client: TestClient, db_session: Session):
    merchant_user = _create_merchant(db_session, "rate.merchant@example.com")
    customer = _create_user(db_session, "rate.customer@example.com", "Customer")
    admin = _create_user(db_session, "rate.admin@example.com", "Admin", UserRole.ADMIN)
    profile = (
        db_session.query(MerchantProfile)
        .filter(MerchantProfile.user_id == merchant_user.id)
        .first()
    )
    profile.cashback_percent = Decimal("5.00")
    profile.company_fee_percent = Decimal("3.00")
    db_session.commit()

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
    qr = qr_res.json()
    assert qr["cashback_percent"] == 5.0
    assert qr["company_fee_percent"] == 3.0
    assert qr["estimated_user_cashback"] == "50.00"
    assert qr["estimated_company_fee"] == "30.00"
    assert qr["estimated_cashback_total"] == "80.00"

    customer_headers = _auth_headers(client, customer.email, "Password123!")
    redeem_res = client.post(
        "/api/v1/wallet/sales/redeem",
        headers=customer_headers,
        json={"token": qr["token"]},
    )
    assert redeem_res.status_code == 200
    body = redeem_res.json()
    assert body["cashback_percent"] == 5.0
    assert body["company_fee_percent"] == 3.0
    assert body["user_cashback"] == "50.00"
    assert body["company_fee"] == "30.00"
    assert body["merchant_debit"] == "80.00"

    platform = client.get("/api/v1/wallet/platform", headers=admin_headers)
    assert platform.status_code == 200
    screen = platform.json()
    assert screen["balance"] == "30.00"
    assert screen["total_platform_revenue"] == "30.00"
    assert screen["cashback_distributed"] == "50.00"
    assert screen["gross_sales_volume"] == "1000.00"
    assert screen["qr_redemptions"] == 1
    assert screen["transactions"][0]["amount"] == "30.00"
    assert screen["transactions"][0]["direction"] == "CREDIT"


def test_merchant_qr_status_pending_then_redeemed(client: TestClient, db_session: Session):
    merchant_user = _create_merchant(db_session, "statusmerchant@example.com")
    customer = _create_user(db_session, "statuscustomer@example.com", "Customer")
    admin = _create_user(db_session, "statusadmin@example.com", "Admin", UserRole.ADMIN)
    admin_headers = _auth_headers(client, admin.email, "Password123!")
    client.post(
        "/api/v1/wallet/admin/adjust",
        headers=admin_headers,
        json={"user_id": merchant_user.id, "amount": "500.00", "operation": "credit"},
    )

    merchant_headers = _auth_headers(client, merchant_user.email, "Password123!")
    qr_res = client.post(
        "/api/v1/wallet/sales/qr",
        headers=merchant_headers,
        json={"sale_amount": "200.00", "expires_in_minutes": 5},
    )
    token = qr_res.json()["token"]

    pending = client.get(
        f"/api/v1/wallet/sales/qr/{token}/status",
        headers=merchant_headers,
    )
    assert pending.status_code == 200
    assert pending.json()["is_pending"] is True
    assert pending.json()["is_redeemed"] is False
    assert pending.json()["qr_payload"]

    customer_headers = _auth_headers(client, customer.email, "Password123!")
    client.post(
        "/api/v1/wallet/sales/redeem",
        headers=customer_headers,
        json={"token": token},
    )

    done = client.get(
        f"/api/v1/wallet/sales/qr/{token}/status",
        headers=merchant_headers,
    )
    assert done.json()["is_redeemed"] is True
    assert done.json()["merchant_debit"] == "10.00"


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


def test_websocket_merchant_receives_sale_redeemed(client: TestClient, db_session: Session):
    merchant_user = _create_merchant(db_session, "wsmerchant@example.com")
    customer = _create_user(db_session, "wscustomer@example.com", "Customer")
    admin = _create_user(db_session, "wsadmin@example.com", "Admin", UserRole.ADMIN)
    admin_headers = _auth_headers(client, admin.email, "Password123!")
    client.post(
        "/api/v1/wallet/admin/adjust",
        headers=admin_headers,
        json={"user_id": merchant_user.id, "amount": "1000.00", "operation": "credit"},
    )

    merchant_headers = _auth_headers(client, merchant_user.email, "Password123!")
    access = _access_token(client, merchant_user.email, "Password123!")

    with client.websocket_connect(f"/api/v1/wallet/ws?token={access}") as ws:
        hello = ws.receive_json()
        assert hello["event"] == "connected"

        qr_res = client.post(
            "/api/v1/wallet/sales/qr",
            headers=merchant_headers,
            json={"sale_amount": "1000.00"},
        )
        assert qr_res.status_code == 201
        sale_token = qr_res.json()["token"]

        ws.send_json({"action": "subscribe", "token": sale_token})
        assert ws.receive_json()["event"] == "subscribed"

        customer_headers = _auth_headers(client, customer.email, "Password123!")
        redeem_res = client.post(
            "/api/v1/wallet/sales/redeem",
            headers=customer_headers,
            json={"token": sale_token},
        )
        assert redeem_res.status_code == 200

        event = ws.receive_json()
        assert event["event"] == "sale_qr.redeemed"
        assert event["token"] == sale_token
        assert event["merchant_wallet_balance"] == "950.00"
        assert event["merchant_debit"] == "50.00"
        assert event["transaction_group_id"]


def test_admin_list_all_transactions(client: TestClient, db_session: Session):
    sender = _create_user(db_session, "txsender@example.com", "Sender")
    recipient = _create_user(db_session, "txrecipient@example.com", "Recipient")
    admin = _create_user(db_session, "txadmin@example.com", "Admin", UserRole.ADMIN)
    admin_headers = _auth_headers(client, admin.email, "Password123!")

    client.post(
        "/api/v1/wallet/admin/adjust",
        headers=admin_headers,
        json={"user_id": sender.id, "amount": "200.00", "operation": "credit", "note": "seed"},
    )
    sender_headers = _auth_headers(client, sender.email, "Password123!")
    client.post(
        "/api/v1/wallet/transfer",
        headers=sender_headers,
        json={"to_user_id": recipient.id, "amount": "25.00", "note": "pay"},
    )

    list_res = client.get("/api/v1/admin/transactions", headers=admin_headers)
    assert list_res.status_code == 200
    body = list_res.json()
    assert body["success"] is True
    assert body["meta"]["total_items"] >= 2
    assert len(body["data"]) >= 2
    assert body["data"][0].get("transaction_type") is not None

    merchant = _create_merchant(db_session, "txmerchant@example.com")
    merchant_headers = _auth_headers(client, merchant.email, "Password123!")
    topup_res = client.post(
        "/api/v1/wallet/topup",
        headers=merchant_headers,
        json={"amount": "150.00", "payment_method": "UPI", "note": "merchant add funds"},
    )
    assert topup_res.status_code == 200

    withdraw_res = client.post(
        "/api/v1/wallet/withdrawals",
        headers=sender_headers,
        json={
            "amount": "40.00",
            "account_holder_name": "Sender User",
            "account_number": "1234567890",
            "ifsc": "HDFC0001234",
        },
    )
    assert withdraw_res.status_code == 201

    wallet_res = client.get("/api/v1/wallet/admin/transactions", headers=admin_headers)
    assert wallet_res.status_code == 200
    wallet_body = wallet_res.json()
    assert wallet_body["total"] >= 2
    movements = {row["movement"] for row in wallet_body["platform_cash"]}
    assert "RECEIVED" in movements
    assert "DEDUCTED" in movements
    assert Decimal(wallet_body["total_received"]) >= Decimal("150.00")
    assert Decimal(wallet_body["total_deducted"]) >= Decimal("40.00")
    assert Decimal(wallet_body["real_balance"]) == (
        Decimal(wallet_body["total_received"]) - Decimal(wallet_body["total_deducted"])
    )

    txn_id = wallet_body["data"][0]["id"]
    detail_res = client.get(f"/api/v1/wallet/admin/transactions/{txn_id}", headers=admin_headers)
    assert detail_res.status_code == 200
    assert detail_res.json()["id"] == txn_id
    assert "ledger_entries" in detail_res.json()

    missing = client.get("/api/v1/wallet/admin/transactions/999999", headers=admin_headers)
    assert missing.status_code == 404

    filtered = client.get(
        "/api/v1/admin/transactions",
        headers=admin_headers,
        params={"transaction_type": "P2P_TRANSFER"},
    )
    assert filtered.status_code == 200
    assert filtered.json()["meta"]["total_items"] >= 1
    for row in filtered.json()["data"]:
        assert row["transaction_type"] == "P2P_TRANSFER"

    member = _create_user(db_session, "txmember@example.com", "Member")
    member_headers = _auth_headers(client, member.email, "Password123!")
    forbidden = client.get("/api/v1/admin/transactions", headers=member_headers)
    assert forbidden.status_code == 403
