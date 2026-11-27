from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models.product import CustomerProduct, ProductOrder
from app.db.models.user import User, UserRole
from app.db.models.wallet import Wallet


def _user(db: Session, email: str, role: UserRole, phone: str) -> User:
    user = User(
        name=email.split("@")[0],
        email=email,
        phone=phone,
        password_hash=hash_password("Password123!"),
        role=role,
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _headers(client: TestClient, email: str) -> dict:
    res = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _order(db: Session, seller: User, buyer: User, status: str = "DELIVERED", quantity: int = 2) -> ProductOrder:
    product = CustomerProduct(
        seller_id=seller.id,
        name="Linen shirt",
        price=Decimal("500.00"),
        stock_quantity=10,
        images=["https://example.com/shirt.jpg"],
        is_active=True,
        approval_status="APPROVED",
    )
    db.add(product)
    db.flush()
    order = ProductOrder(
        order_code=f"ORD-{product.id}{buyer.id}",
        product_id=product.id,
        seller_id=seller.id,
        buyer_user_id=buyer.id,
        buyer_name=buyer.name,
        buyer_phone=buyer.phone,
        buyer_address="House 1, Kochi",
        buyer_pincode="682001",
        quantity=quantity,
        unit_price=Decimal("500.00"),
        total_price=Decimal("1000.00"),
        status=status,
        payment_status="PAID",
        payment_method="UPI",
        status_history=[{"status": status, "at": datetime.now(timezone.utc).isoformat()}],
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def test_shipment_return_refund_and_replacement(client: TestClient, db_session: Session):
    seller = _user(db_session, "seller.track@example.com", UserRole.MERCHANT, "9000000001")
    buyer = _user(db_session, "buyer.track@example.com", UserRole.FIELD_STAFF, "9000000002")
    other = _user(db_session, "other.track@example.com", UserRole.FIELD_STAFF, "9000000003")
    admin = _user(db_session, "admin.track@example.com", UserRole.ADMIN, "9000000004")
    buyer_headers = _headers(client, buyer.email)
    other_headers = _headers(client, other.email)
    admin_headers = _headers(client, admin.email)
    order = _order(db_session, seller, buyer)

    denied = client.post(
        "/api/v1/shipments",
        headers=buyer_headers,
        json={"order_id": order.id, "courier_name": "DTDC", "tracking_number": "AWB1", "shipment_status": "DISPATCHED"},
    )
    assert denied.status_code == 403

    created = client.post(
        "/api/v1/shipments",
        headers=admin_headers,
        json={
            "order_id": order.id,
            "courier_name": "DTDC",
            "tracking_number": "AWB100",
            "tracking_url": "https://track.example/AWB100",
            "shipment_status": "DISPATCHED",
            "remarks": "Left the warehouse",
            "estimated_delivery": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    shipment_id = created.json()["data"]["id"]

    hidden = client.get(f"/api/v1/shipments/order/{order.id}", headers=other_headers)
    assert hidden.status_code == 403

    seen = client.get(f"/api/v1/shipments/order/{order.id}", headers=buyer_headers)
    assert seen.status_code == 200
    assert seen.json()["data"]["tracking_number"] == "AWB100"
    assert seen.json()["data"]["product_name"] == "Linen shirt"

    updated = client.put(
        f"/api/v1/shipments/{shipment_id}/status",
        headers=admin_headers,
        json={"shipment_status": "DELIVERED", "location": "Kochi", "description": "Handed to customer"},
    )
    assert updated.status_code == 200
    history = client.get(f"/api/v1/shipments/{shipment_id}/history", headers=buyer_headers)
    assert history.status_code == 200
    assert [row["status"] for row in history.json()["data"]] == ["DISPATCHED", "DELIVERED"]

    too_many = client.post(
        "/api/v1/returns",
        headers=buyer_headers,
        json={"order_id": order.id, "quantity": 3, "return_reason": "Quality issue", "return_type": "MANUAL_PICKUP"},
    )
    assert too_many.status_code == 400

    requested = client.post(
        "/api/v1/returns",
        headers=buyer_headers,
        json={
            "order_id": order.id,
            "quantity": 1,
            "return_reason": "Product damaged",
            "description": "Torn sleeve",
            "return_type": "MANUAL_PICKUP",
            "image_urls": ["https://example.com/damage.jpg"],
        },
    )
    assert requested.status_code == 201, requested.text
    return_id = requested.json()["data"]["id"]

    partial = client.post(
        "/api/v1/returns",
        headers=buyer_headers,
        json={"order_id": order.id, "quantity": 2, "return_reason": "Other", "return_type": "SELF_SHIPPING"},
    )
    assert partial.status_code == 400

    other_view = client.get(f"/api/v1/returns/{return_id}", headers=other_headers)
    assert other_view.status_code == 403

    approved = client.put(f"/api/v1/returns/{return_id}/approve", headers=admin_headers, json={"remarks": "Accepted"})
    assert approved.status_code == 200
    pickup = client.post(
        f"/api/v1/returns/{return_id}/pickup",
        headers=admin_headers,
        json={"pickup_date": "2026-12-01", "pickup_remarks": "Morning slot"},
    )
    assert pickup.status_code == 200
    assert pickup.json()["data"]["return_status"] == "PICKUP_SCHEDULED"

    received = client.post(f"/api/v1/returns/{return_id}/receive", headers=admin_headers, json={"remarks": "Box opened"})
    assert received.status_code == 200
    inspected = client.post(
        f"/api/v1/returns/{return_id}/inspect",
        headers=admin_headers,
        json={"product_condition": "DAMAGED", "remarks": "Matches the photo"},
    )
    assert inspected.status_code == 200

    over = client.post(
        f"/api/v1/returns/{return_id}/refund",
        headers=admin_headers,
        json={"refund_amount": "900.00", "refund_method": "STORE_WALLET"},
    )
    assert over.status_code == 400

    refund = client.post(
        f"/api/v1/returns/{return_id}/refund",
        headers=admin_headers,
        json={"refund_amount": "500.00", "refund_method": "STORE_WALLET", "admin_remarks": "Half order"},
    )
    assert refund.status_code == 201
    assert refund.json()["data"]["refund_status"] == "PENDING"
    refund_id = refund.json()["data"]["id"]
    duplicate = client.post(
        f"/api/v1/returns/{return_id}/refund",
        headers=admin_headers,
        json={"refund_amount": "100.00", "refund_method": "UPI"},
    )
    assert duplicate.status_code == 409

    confirmed = client.put(
        f"/api/v1/refunds/{refund_id}/status",
        headers=admin_headers,
        json={"refund_status": "SUCCESS", "transaction_reference": "WALLET-1"},
    )
    assert confirmed.status_code == 200
    wallet = db_session.query(Wallet).filter(Wallet.user_id == buyer.id).first()
    assert wallet is not None
    assert Decimal(wallet.balance) == Decimal("500.00")

    second_order = _order(db_session, seller, buyer)
    second = client.post(
        "/api/v1/returns",
        headers=buyer_headers,
        json={"order_id": second_order.id, "quantity": 1, "return_reason": "Size or fit issue", "return_type": "REPLACEMENT"},
    )
    assert second.status_code == 201
    second_id = second.json()["data"]["id"]
    shipped = client.post(
        f"/api/v1/returns/{second_id}/shipping",
        headers=buyer_headers,
        json={"courier_name": "India Post", "awb_number": "RP123", "shipping_date": "2026-12-02"},
    )
    assert shipped.status_code == 200
    assert shipped.json()["data"]["return_status"] == "RETURN_SHIPPED"
    replaced = client.post(
        f"/api/v1/returns/{second_id}/replace",
        headers=admin_headers,
        json={"quantity": 1, "price_difference": "0"},
    )
    assert replaced.status_code == 201, replaced.text
    assert replaced.json()["data"]["replacement_order_code"]

    stats = client.get("/api/v1/returns/stats", headers=admin_headers)
    assert stats.status_code == 200
    assert stats.json()["data"]["total"] >= 2

    rejected_order = _order(db_session, seller, buyer)
    reject_req = client.post(
        "/api/v1/returns",
        headers=buyer_headers,
        json={"order_id": rejected_order.id, "quantity": 1, "return_reason": "Other", "return_type": "MANUAL_PICKUP"},
    )
    rejected = client.put(
        f"/api/v1/returns/{reject_req.json()['data']['id']}/reject",
        headers=admin_headers,
        json={"reason": "Photos do not match"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["data"]["return_status"] == "REJECTED"

    placed = _order(db_session, seller, buyer, status="PLACED")
    invalid = client.post(
        "/api/v1/returns",
        headers=buyer_headers,
        json={"order_id": placed.id, "quantity": 1, "return_reason": "Other", "return_type": "MANUAL_PICKUP"},
    )
    assert invalid.status_code == 400
