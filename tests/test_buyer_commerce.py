from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models.user import User, UserRole


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


def test_buyer_cart_payment_tracking_and_review(client: TestClient, db_session: Session):
    seller = _user(db_session, "seller.shop@example.com", "Seller", "9876500011")
    buyer = _user(db_session, "buyer.shop@example.com", "Buyer", "9876500012")
    seller_headers = _headers(client, seller.email)
    buyer_headers = _headers(client, buyer.email)

    listed = client.post(
        "/api/v1/customer/products",
        headers=seller_headers,
        json={
            "name": "Cotton shirt",
            "category": "Clothing",
            "price": 499,
            "stock_quantity": 5,
            "sizes": ["M"],
            "images": ["https://example.com/shirt.jpg"],
        },
    )
    assert listed.status_code == 201
    product_id = listed.json()["id"]

    saved = client.post(f"/api/v1/marketplace/wishlist/{product_id}", headers=buyer_headers)
    assert saved.status_code == 200
    assert saved.json()["total"] == 1

    address = client.post(
        "/api/v1/marketplace/addresses",
        headers=buyer_headers,
        json={
            "label": "Home",
            "recipient_name": "Buyer",
            "phone": "9876500012",
            "address_line": "House 4, Panampilly Nagar",
            "city": "Kochi",
            "district": "Ernakulam",
            "pincode": "682036",
            "is_default": True,
        },
    )
    assert address.status_code == 201
    address_id = address.json()["id"]
    assert address.json()["is_default"] is True

    synced = client.put(
        "/api/v1/marketplace/cart",
        headers=buyer_headers,
        json={"items": [{"product_id": product_id, "quantity": 1, "selected_size": "M"}]},
    )
    assert synced.status_code == 200
    assert synced.json()["subtotal"] == 499
    assert synced.json()["item_count"] == 1

    checked = client.post(
        "/api/v1/marketplace/cart/checkout",
        headers=buyer_headers,
        json={"address_id": address_id},
    )
    assert checked.status_code == 200
    order_id = checked.json()[0]["id"]
    assert checked.json()[0]["buyer_address"] == "House 4, Panampilly Nagar"
    assert client.get("/api/v1/marketplace/cart", headers=buyer_headers).json()["item_count"] == 0

    pay = client.post(
        f"/api/v1/marketplace/orders/{order_id}/pay",
        headers=buyer_headers,
        json={"method": "UPI"},
    )
    assert pay.status_code == 200
    pay_body = pay.json()
    assert pay_body["payment_status"] == "PENDING"
    assert pay_body["amount_paise"] == 49900
    verified = client.post(
        f"/api/v1/marketplace/orders/{order_id}/pay/verify",
        headers=buyer_headers,
        json={
            "razorpay_order_id": pay_body["razorpay_order_id"],
            "razorpay_payment_id": "pay_dev_1",
            "razorpay_signature": "dev_signature_ok",
        },
    )
    assert verified.status_code == 200
    assert verified.json()["payment_status"] == "PAID"

    client.put(
        f"/api/v1/customer/products/orders/{order_id}/status",
        headers=seller_headers,
        json={"status": "CONFIRMED"},
    )
    dispatched = client.put(
        f"/api/v1/customer/products/orders/{order_id}/dispatch",
        headers=seller_headers,
        json={
            "courier_partner": "DTDC",
            "tracking_number": "DTDC123456",
            "event": "IN_TRANSIT",
            "note": "Picked up from Kochi",
        },
    )
    assert dispatched.status_code == 200
    assert dispatched.json()["status"] == "SHIPPED"
    assert dispatched.json()["tracking_number"] == "DTDC123456"

    tracking = client.get(f"/api/v1/marketplace/orders/{order_id}/tracking", headers=buyer_headers)
    assert tracking.status_code == 200
    track = tracking.json()
    assert track["courier_partner"] == "DTDC"
    assert track["events"][0]["note"] == "Picked up from Kochi"
    assert track["payment_status"] == "PAID"

    client.put(
        f"/api/v1/customer/products/orders/{order_id}/dispatch",
        headers=seller_headers,
        json={"courier_partner": "DTDC", "tracking_number": "DTDC123456", "event": "OUT_FOR_DELIVERY"},
    )
    delivered = client.put(
        f"/api/v1/customer/products/orders/{order_id}/dispatch",
        headers=seller_headers,
        json={"courier_partner": "DTDC", "tracking_number": "DTDC123456", "event": "DELIVERED"},
    )
    assert delivered.json()["status"] == "DELIVERED"

    review = client.post(
        f"/api/v1/marketplace/orders/{order_id}/review",
        headers=buyer_headers,
        json={"rating": 5, "title": "Good shirt", "comment": "Fits well."},
    )
    assert review.status_code == 201
    reviews = client.get(f"/api/v1/products/{product_id}/reviews")
    assert reviews.status_code == 200
    assert reviews.json()["rating_average"] == 5
    assert reviews.json()["rating_count"] == 1

    history = client.get("/api/v1/marketplace/orders/history", headers=buyer_headers)
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert history.json()["orders"][0]["status"] == "DELIVERED"

    too_late = client.post(f"/api/v1/marketplace/orders/{order_id}/cancel", headers=buyer_headers, json={"reason": "Changed mind"})
    assert too_late.status_code == 400


def test_buyer_can_cancel_before_shipping(client: TestClient, db_session: Session):
    seller = _user(db_session, "seller.cancel@example.com", "Seller", "9876500021")
    buyer = _user(db_session, "buyer.cancel@example.com", "Buyer", "9876500022")
    seller_headers = _headers(client, seller.email)
    buyer_headers = _headers(client, buyer.email)
    listed = client.post(
        "/api/v1/customer/products",
        headers=seller_headers,
        json={"name": "Lamp", "price": 100, "stock_quantity": 2},
    )
    product_id = listed.json()["id"]
    bought = client.post(
        "/api/v1/marketplace/orders",
        headers=buyer_headers,
        json={
            "product_id": product_id,
            "buyer_name": "Buyer",
            "buyer_phone": "9876500022",
            "buyer_address": "Flat 2, Kadavanthra",
            "buyer_pincode": "682020",
            "quantity": 1,
        },
    )
    order_id = bought.json()["id"]
    cod = client.post(
        f"/api/v1/marketplace/orders/{order_id}/pay",
        headers=buyer_headers,
        json={"method": "COD"},
    )
    assert cod.json()["payment_status"] == "COD"
    cancelled = client.post(
        f"/api/v1/marketplace/orders/{order_id}/cancel",
        headers=buyer_headers,
        json={"reason": "Ordered by mistake"},
    )
    assert cancelled.status_code == 200
    body = cancelled.json()
    assert body["status"] == "CANCELLED"
    assert body["cancellation_reason"] == "Ordered by mistake"
    assert client.get(f"/api/v1/products/{product_id}").json()["stock_quantity"] == 2


def test_shop_reads_without_a_token_and_raw_jwt(client: TestClient, db_session: Session):
    guest_cart = client.get("/api/v1/marketplace/cart")
    assert guest_cart.status_code == 200
    assert guest_cart.json()["items"] == []

    guest_orders = client.get("/api/v1/marketplace/orders/history")
    assert guest_orders.status_code == 200
    assert guest_orders.json()["total"] == 0

    buyer = _user(db_session, "buyer.token@example.com", "Buyer", "9876500099")
    login = client.post("/api/v1/auth/login", json={"email": buyer.email, "password": "Password123!"})
    raw = login.json()["access_token"]
    cart = client.get("/api/v1/marketplace/cart", headers={"Authorization": raw})
    assert cart.status_code == 200
    wishlist = client.get("/api/v1/marketplace/wishlist", headers={"X-Access-Token": raw})
    assert wishlist.status_code == 200


def test_order_detail_without_token(client: TestClient, db_session: Session):
    seller = _user(db_session, "seller.open@example.com", "Seller", "9876500081")
    buyer = _user(db_session, "buyer.open@example.com", "Buyer", "9876500082")
    seller_headers = _headers(client, seller.email)
    buyer_headers = _headers(client, buyer.email)
    listed = client.post(
        "/api/v1/customer/products",
        headers=seller_headers,
        json={"name": "Open lamp", "price": 80, "stock_quantity": 2},
    )
    bought = client.post(
        "/api/v1/marketplace/orders",
        headers=buyer_headers,
        json={
            "product_id": listed.json()["id"],
            "buyer_name": "Buyer",
            "buyer_phone": "9876500082",
            "buyer_address": "House 8, Kochi",
            "buyer_pincode": "682001",
            "quantity": 1,
        },
    )
    order_id = bought.json()["id"]
    open_order = client.get(f"/api/v1/marketplace/orders/{order_id}")
    assert open_order.status_code == 200
    assert open_order.json()["id"] == order_id
    tracking = client.get(f"/api/v1/marketplace/orders/{order_id}/tracking")
    assert tracking.status_code == 200
    assert tracking.json()["order_id"] == order_id

    cancelled = client.post(f"/api/v1/marketplace/orders/{order_id}/cancel", json={"reason": "Changed mind"})
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
