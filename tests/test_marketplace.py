from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models.user import User, UserRole


def _user(db: Session, email: str, name: str) -> User:
    user = User(
        name=name,
        email=email,
        phone="9876500001" if "seller" in email else "9876500002",
        password_hash=hash_password("Password123!"),
        role=UserRole.FIELD_STAFF,
        is_active=True,
        is_verified=True,
        can_sell_products=False,
        is_subscriber=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _headers(client: TestClient, email: str) -> dict:
    res = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_any_customer_can_sell_and_buyer_tracks_delivery(client: TestClient, db_session: Session):
    seller = _user(db_session, "seller.market@example.com", "Seller")
    buyer = _user(db_session, "buyer.market@example.com", "Buyer")
    seller_headers = _headers(client, seller.email)
    buyer_headers = _headers(client, buyer.email)

    listed = client.post(
        "/api/v1/customer/products",
        headers=seller_headers,
        json={
            "name": "Used bicycle",
            "description": "Any item, not only a shop category.",
            "category": "Cycles",
            "price": 2500,
            "stock_quantity": 1,
            "sizes": ["M"],
            "images": ["https://example.com/bike.jpg"],
            "district": "Ernakulam",
            "city": "Kochi",
        },
    )
    assert listed.status_code == 201
    product_id = listed.json()["id"]

    page = client.get("/api/v1/marketplace", params={"search": "bicycle"})
    assert page.status_code == 200
    body = page.json()
    assert body["total"] == 1
    assert body["products"][0]["name"] == "Used bicycle"
    assert "Delivered" in body["delivery_steps"]

    bought = client.post(
        "/api/v1/marketplace/orders",
        headers=buyer_headers,
        json={
            "product_id": product_id,
            "buyer_name": "Buyer",
            "buyer_phone": "9876500002",
            "buyer_address": "House 12, Marine Drive",
            "buyer_pincode": "682031",
            "selected_size": "M",
            "quantity": 1,
        },
    )
    assert bought.status_code == 201
    order = bought.json()
    assert order["status"] == "PLACED"
    assert order["delivery_steps"][0]["current"] is True
    order_id = order["id"]

    mine = client.get("/api/v1/marketplace/orders", headers=buyer_headers)
    assert mine.status_code == 200
    assert mine.json()[0]["id"] == order_id

    skipped = client.put(
        f"/api/v1/customer/products/orders/{order_id}/status",
        headers=seller_headers,
        json={"status": "SHIPPED"},
    )
    assert skipped.status_code == 400

    confirmed = client.put(
        f"/api/v1/customer/products/orders/{order_id}/status",
        headers=seller_headers,
        json={"status": "CONFIRMED"},
    )
    assert confirmed.status_code == 200
    shipped = client.put(
        f"/api/v1/customer/products/orders/{order_id}/status",
        headers=seller_headers,
        json={"status": "SHIPPED", "notes": "Sent by courier"},
    )
    assert shipped.status_code == 200

    detail = client.get(f"/api/v1/marketplace/orders/{order_id}", headers=buyer_headers)
    assert detail.status_code == 200
    assert detail.json()["status"] == "SHIPPED"
    assert float(detail.json()["unit_price"]) == 2500
    assert float(detail.json()["total_price"]) == 2500
    current = [step for step in detail.json()["delivery_steps"] if step["current"]]
    assert current[0]["key"] == "SHIPPED"

    own = client.post(
        "/api/v1/marketplace/orders",
        headers=seller_headers,
        json={
            "product_id": product_id,
            "buyer_name": "Seller",
            "buyer_phone": "9876500001",
            "buyer_address": "Same house",
            "buyer_pincode": "682031",
        },
    )
    assert own.status_code == 400
