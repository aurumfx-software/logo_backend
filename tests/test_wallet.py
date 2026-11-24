from decimal import Decimal

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import text
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
    assert withdraw_res.json()["status"] == "PENDING"
    assert not withdraw_res.json()["payout_id"]

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


def test_withdrawal_sends_razorpayx_payout(client: TestClient, db_session: Session, monkeypatch):
    user = _create_user(db_session, "payout.user@example.com", "Payout User")
    admin = _create_user(db_session, "payout.admin@example.com", "Admin", UserRole.ADMIN)
    admin_headers = _auth_headers(client, admin.email, "Password123!")
    client.post(
        "/api/v1/wallet/admin/adjust",
        headers=admin_headers,
        json={"user_id": user.id, "amount": "80.00", "operation": "credit"},
    )

    def fake_payout(**kwargs):
        assert kwargs["amount"] == Decimal("30.00")
        assert kwargs["mode"] == "IMPS"
        assert kwargs["account_number"] == "1234567890"
        return {"id": "pout_live_1", "status": "processed", "fund_account_id": "fa_1"}

    monkeypatch.setattr("app.services.wallet_service.RazorpayXService.create_payout", fake_payout)
    headers = _auth_headers(client, user.email, "Password123!")
    res = client.post(
        "/api/v1/wallet/withdrawals",
        headers=headers,
        json={
            "amount": "30.00",
            "account_holder_name": "Payout User",
            "account_number": "1234567890",
            "ifsc": "HDFC0001234",
            "payout_mode": "IMPS",
        },
    )
    assert res.status_code == 201
    assert res.json()["status"] == "PENDING"
    group_id = res.json()["transaction_group_id"]

    listed = client.get("/api/v1/wallet/admin/withdrawals", headers=admin_headers, params={"status": "PENDING"})
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["data"][0]["account_number_masked"].endswith("7890")

    sent = client.post(f"/api/v1/wallet/admin/withdrawals/{group_id}/send", headers=admin_headers)
    assert sent.status_code == 200
    body = sent.json()
    assert body["payout_id"] == "pout_live_1"
    assert body["status"] == "COMPLETED"
    balance = client.get("/api/v1/wallet/me", headers=headers)
    assert balance.json()["wallet"]["balance"] == "50.00"

    def fail_payout(**kwargs):
        raise HTTPException(status_code=502, detail="RazorpayX payout failed: low balance")

    monkeypatch.setattr("app.services.wallet_service.RazorpayXService.create_payout", fail_payout)
    second = client.post(
        "/api/v1/wallet/withdrawals",
        headers=headers,
        json={
            "amount": "10.00",
            "account_holder_name": "Payout User",
            "account_number": "1234567890",
            "ifsc": "HDFC0001234",
        },
    )
    assert second.status_code == 201
    failed = client.post(
        f"/api/v1/wallet/admin/withdrawals/{second.json()['transaction_group_id']}/send",
        headers=admin_headers,
    )
    assert failed.status_code == 502
    me = client.get("/api/v1/wallet/me", headers=headers)
    assert me.json()["wallet"]["balance"] == "40.00"


def test_withdrawal_status_repairs_missing_payout_columns(client: TestClient, db_session: Session):
    user = _create_user(db_session, "repair.user@example.com", "Repair User")
    admin = _create_user(db_session, "repair.admin@example.com", "Admin", UserRole.ADMIN)
    admin_headers = _auth_headers(client, admin.email, "Password123!")
    client.post(
        "/api/v1/wallet/admin/adjust",
        headers=admin_headers,
        json={"user_id": user.id, "amount": "80.00", "operation": "credit"},
    )
    headers = _auth_headers(client, user.email, "Password123!")
    created = client.post(
        "/api/v1/wallet/withdrawals",
        headers=headers,
        json={
            "amount": "20.00",
            "account_holder_name": "Repair User",
            "account_number": "1234567890",
            "ifsc": "HDFC0001234",
        },
    )
    assert created.status_code == 201
    group_id = created.json()["transaction_group_id"]

    db_session.execute(text("DROP INDEX IF EXISTS ix_wallet_withdrawals_payout_id"))
    db_session.execute(text("ALTER TABLE wallet_withdrawals DROP COLUMN payout_id"))
    db_session.execute(text("ALTER TABLE wallet_withdrawals DROP COLUMN fund_account_id"))
    db_session.execute(text("ALTER TABLE wallet_withdrawals DROP COLUMN razorpay_status"))
    db_session.commit()
    db_session.info.pop("withdrawal_schema_ready", None)

    status_res = client.get(f"/api/v1/wallet/withdrawals/{group_id}", headers=headers)
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "PENDING"

    listed = client.get("/api/v1/wallet/admin/withdrawals", headers=admin_headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1


def test_admin_platform_cards_use_real_pool_totals(client: TestClient, db_session: Session):
    admin = _create_user(db_session, "cards.admin@example.com", "Cards Admin", UserRole.ADMIN)
    member = _create_user(db_session, "cards.member@example.com", "Cards Member")
    headers = _auth_headers(client, admin.email, "Password123!")

    added = client.post(
        "/api/v1/wallet/admin/added-fund",
        headers=headers,
        json={"amount": "100.00", "source": "Bank Deposit", "note": "Capital injection"},
    )
    assert added.status_code == 200
    assert Decimal(added.json()["balance"]) == Decimal("100.00")

    sent = client.post(
        "/api/v1/wallet/admin/send",
        headers=headers,
        json={
            "recipient_type": "user",
            "user_id": member.id,
            "amount": "30.00",
            "source_wallet": "added_fund",
            "note": "Send from added fund",
        },
    )
    assert sent.status_code == 200
    assert Decimal(sent.json()["source_balance"]) == Decimal("70.00")

    too_much = client.post(
        "/api/v1/wallet/admin/send",
        headers=headers,
        json={
            "recipient_type": "user",
            "user_id": member.id,
            "amount": "5.00",
            "source_wallet": "commission",
        },
    )
    assert too_much.status_code == 400

    cards = client.get("/api/v1/wallet/admin/platform-cards", headers=headers)
    assert cards.status_code == 200
    body = cards.json()
    assert Decimal(body["added_fund"]["balance"]) == Decimal("100.00")
    assert Decimal(body["commission"]["balance"]) == Decimal("0.00")
    withdrawn = client.post(
        "/api/v1/wallet/withdrawals",
        headers=_auth_headers(client, member.email, "Password123!"),
        json={
            "amount": "20.00",
            "account_holder_name": "Cards Member",
            "account_number": "9988776655",
            "ifsc": "SBIN0001234",
        },
    )
    assert withdrawn.status_code == 201

    cards = client.get("/api/v1/wallet/admin/platform-cards", headers=headers)
    assert cards.status_code == 200
    body = cards.json()
    assert Decimal(body["added_fund"]["balance"]) == Decimal("100.00")
    assert Decimal(body["commission"]["balance"]) == Decimal("0.00")
    assert Decimal(body["cash_received"]["balance"]) == Decimal("20.00")
    request_row = body["cash_received"]["transactions"][0]
    assert request_row["movement"] == "RECEIVED"
    assert request_row["can_approve"] is True
    assert request_row["status"] == "PENDING"
    assert request_row["party_role"] == "customer"
    assert request_row["transaction_group_id"]
    assert Decimal(body["cash_sent"]["balance"]) == Decimal("30.00")
    movements = {row["movement"] for row in body["added_fund"]["transactions"]}
    assert movements == {"ADDED_FUND"}
    assert body["added_fund"]["transactions"][0]["transaction_type"] in ("ADMIN_CAPITAL", "ADMIN_SEND_FUNDS")
    assert body["cash_sent"]["transactions"][0]["movement"] == "SENT"
    capital_rows = [row for row in body["added_fund"]["transactions"] if row["movement"] == "ADDED_FUND"]
    assert sum(Decimal(row["amount"]) for row in capital_rows) == Decimal("100.00")

    missing = client.get("/api/v1/wallet/admin/transactions/1795512686370", headers=headers)
    assert missing.status_code == 404


def test_wallet_list_adds_missing_source_pool_column(client: TestClient, db_session: Session):
    import app.db.database as database

    admin = _create_user(db_session, "pool.admin@example.com", "Pool Admin", UserRole.ADMIN)
    headers = _auth_headers(client, admin.email, "Password123!")
    db_session.execute(text("DROP INDEX IF EXISTS ix_wallet_transactions_source_pool"))
    db_session.execute(text("ALTER TABLE wallet_transactions DROP COLUMN source_pool"))
    db_session.commit()
    database._source_pool_ready = False
    db_session.info.pop("source_pool_ready", None)

    listed = client.get("/api/v1/wallet/admin/transactions", headers=headers)
    assert listed.status_code == 200
    columns = {
        row[1]
        for row in db_session.execute(text("PRAGMA table_info(wallet_transactions)")).fetchall()
    }
    assert "source_pool" in columns
