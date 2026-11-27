from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models.product import ProductOrder
from app.db.models.user import User, UserRole
from tests.conftest import grant_seller_plan


def _user(db: Session, email: str, name: str, phone: str) -> User:
    user = User(
        name=name,
        email=email,
        phone=phone,
        password_hash=hash_password("Password123!"),
        role=UserRole.FIELD_STAFF,
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _headers(client: TestClient, email: str) -> dict:
    res = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _list(client: TestClient, headers: dict, price: float) -> int:
    listed = client.post(
        "/api/v1/customer/products",
        headers=headers,
        json={"name": "Silk saree", "category": "Clothing", "price": price, "stock_quantity": 20},
    )
    assert listed.status_code == 201
    return listed.json()["id"]


def _order(client: TestClient, product_id: int, phone: str) -> int:
    placed = client.post(
        "/api/v1/products/order",
        json={
            "product_id": product_id,
            "buyer_name": "Buyer",
            "buyer_phone": phone,
            "buyer_address": "House 1, MG Road",
            "buyer_pincode": "682001",
            "quantity": 1,
        },
    )
    assert placed.status_code == 201
    return placed.json()["id"]


def test_seller_bank_details_save_and_read(client: TestClient, db_session: Session):
    seller = _user(db_session, "bank.seller@example.com", "Rahul K", "9876500101")
    headers = _headers(client, seller.email)

    missing = client.get("/api/v1/customer/seller/bank-details")
    assert missing.status_code == 401

    empty = client.get("/api/v1/customer/seller/bank-details", headers=headers)
    assert empty.status_code == 200
    assert empty.json()["data"] is None
    assert empty.json()["message"] == "No bank details configured yet."

    bad = client.put(
        "/api/v1/customer/seller/bank-details",
        headers=headers,
        json={
            "account_holder_name": "Rahul K",
            "bank_name": "State Bank of India",
            "account_number": "123456789012",
            "ifsc_code": "not-an-ifsc",
        },
    )
    assert bad.status_code == 422

    saved = client.put(
        "/api/v1/customer/seller/bank-details",
        headers=headers,
        json={
            "account_holder_name": "Rahul K",
            "bank_name": "State Bank of India",
            "account_number": "123456789012",
            "ifsc_code": "sbin0001234",
            "upi_id": "rahul@okaxis",
        },
    )
    assert saved.status_code == 200
    assert saved.json()["message"] == "Seller bank details saved successfully"
    assert saved.json()["data"]["ifsc_code"] == "SBIN0001234"
    assert saved.json()["data"]["account_number"] == "123456789012"

    loaded = client.get("/api/v1/customer/seller/bank-details", headers=headers)
    assert loaded.status_code == 200
    assert loaded.json()["data"]["upi_id"] == "rahul@okaxis"
    assert "message" not in loaded.json() or loaded.json()["message"] is None


def test_seller_analytics_and_checkout_rules(client: TestClient, db_session: Session):
    seller = _user(db_session, "analytics.seller@example.com", "Seller", "9876500102")
    headers = _headers(client, seller.email)
    grant_seller_plan(client, headers)
    product_id = _list(client, headers, 1000)

    paid_id = _order(client, product_id, "9876501101")
    cod_id = _order(client, product_id, "9876501102")
    delivered_id = _order(client, product_id, "9876501103")
    cancelled_id = _order(client, product_id, "9876501104")
    old_id = _order(client, product_id, "9876501105")

    paid = db_session.get(ProductOrder, paid_id)
    paid.status = "PLACED"
    paid.payment_method = "UPI"
    paid.payment_status = "PAID"
    paid.total_price = 1000

    cod = db_session.get(ProductOrder, cod_id)
    cod.status = "CONFIRMED"
    cod.payment_method = "COD"
    cod.payment_status = "COD"
    cod.total_price = 1000

    delivered = db_session.get(ProductOrder, delivered_id)
    delivered.status = "DELIVERED"
    delivered.payment_method = "COD"
    delivered.payment_status = "COD"
    delivered.total_price = 1000

    cancelled = db_session.get(ProductOrder, cancelled_id)
    cancelled.status = "CANCELLED"
    cancelled.payment_method = "RAZORPAY"
    cancelled.payment_status = "PAID"
    cancelled.total_price = 1000

    old = db_session.get(ProductOrder, old_id)
    old.status = "SHIPPED"
    old.payment_method = "ONLINE"
    old.payment_status = "PAID"
    old.total_price = 1000
    old.created_at = datetime(2020, 1, 2, tzinfo=timezone.utc)
    db_session.commit()

    report = client.get("/api/v1/customer/products/seller-analytics", headers=headers)
    assert report.status_code == 200
    data = report.json()["data"]
    assert data["currency"] == "INR"
    assert data["total_sales"] == 4000
    assert data["online_paid"] == 2000
    assert data["cod_to_collect"] == 1000
    assert data["total_orders"] == 5
    assert data["pipeline"] == {
        "new_orders": 1,
        "contacted_orders": 1,
        "shipped_orders": 1,
        "delivered_orders": 1,
        "cancelled_orders": 1,
    }

    month = client.get(
        "/api/v1/customer/products/seller-analytics?period=this_month",
        headers=headers,
    )
    assert month.status_code == 200
    assert month.json()["data"]["total_orders"] == 4

    bad_period = client.get(
        "/api/v1/customer/products/seller-analytics?period=yesterday",
        headers=headers,
    )
    assert bad_period.status_code == 422

    rules = client.get("/api/v1/orders/checkout-rules")
    assert rules.status_code == 200
    body = rules.json()["data"]
    assert body["free_delivery_above"] == 499
    assert body["delivery_fee"] == 40
    assert body["cod_fee"] == 40
    assert body["free_cod_above"] == 500
    assert body["online_discount_percentage"] == 6
    assert body["online_discount_max_amount"] == 100
    assert body["cod_available"] is True
