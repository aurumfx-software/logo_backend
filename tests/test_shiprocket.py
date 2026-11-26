from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.models.fulfillment import ShipmentHistory
from app.db.models.product import CustomerProduct, ProductOrder
from app.db.models.user import User, UserRole


class FakeShiprocket:
    def configured(self):
        return True

    def request(self, method, path, json=None, params=None, _retry=True):
        if path.endswith("/orders/create/adhoc"):
            return {"order_id": 11, "shipment_id": 22}
        if path.endswith("/orders/create/return"):
            return {"order_id": 33, "shipment_id": 44}
        if "serviceability" in path:
            return {
                "data": {
                    "recommended_courier_company_id": 7,
                    "available_courier_companies": [{"courier_company_id": 7, "courier_name": "Delhivery", "etd": "Dec 01"}],
                }
            }
        if path.endswith("/courier/assign/awb"):
            shipment_id = (json or {}).get("shipment_id")
            awb = "RET900" if shipment_id == 44 else "AWB900"
            return {"awb_assign_status": 1, "response": {"data": {"awb_code": awb, "courier_name": "Delhivery", "courier_company_id": 7}}}
        if path.endswith("/courier/generate/label"):
            return {"label_created": 1, "label_url": "https://labels.example/label.pdf"}
        if path.endswith("/courier/generate/pickup"):
            return {"pickup_status": 1}
        if "/courier/track/awb/" in path:
            return {
                "tracking_data": {
                    "shipment_track": [{"current_status": "IN TRANSIT", "edd": "2026-12-02 18:00:00", "courier_name": "Delhivery"}],
                    "shipment_track_activities": [
                        {"date": "2026-12-01 09:00:00", "status": "IN TRANSIT", "activity": "Left hub", "location": "Kochi"}
                    ],
                }
            }
        if path.endswith("/orders/cancel"):
            return {"status": 200}
        return {}


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


def test_shiprocket_dispatch_webhook_return_and_refund(client: TestClient, db_session: Session, monkeypatch):
    monkeypatch.setattr("app.services.shipping_service.ShiprocketClient", FakeShiprocket)
    settings.SHIPROCKET_EMAIL = "ship@example.com"
    settings.SHIPROCKET_PASSWORD = "secret"
    settings.SHIPROCKET_WEBHOOK_SECRET = "hook-secret"
    settings.SHIPROCKET_PICKUP_PINCODE = "682001"
    settings.SHIPROCKET_PICKUP_LOCATION = "Primary"

    seller = _user(db_session, "seller.ship@example.com", UserRole.MERCHANT, "9000000101")
    buyer = _user(db_session, "buyer.ship@example.com", UserRole.FIELD_STAFF, "9000000102")
    other = _user(db_session, "other.ship@example.com", UserRole.FIELD_STAFF, "9000000103")
    admin = _user(db_session, "admin.ship@example.com", UserRole.ADMIN, "9000000104")
    product = CustomerProduct(
        seller_id=seller.id,
        name="Silk shirt",
        price=Decimal("500.00"),
        stock_quantity=4,
        images=["https://example.com/silk.jpg"],
        is_active=True,
        approval_status="APPROVED",
    )
    db_session.add(product)
    db_session.flush()
    order = ProductOrder(
        order_code="ORD-SHIP-1",
        product_id=product.id,
        seller_id=seller.id,
        buyer_user_id=buyer.id,
        buyer_name="Buyer",
        buyer_phone=buyer.phone,
        buyer_address="House 1, Kochi",
        buyer_city="Kochi",
        buyer_pincode="682036",
        quantity=2,
        unit_price=Decimal("500.00"),
        total_price=Decimal("1000.00"),
        status="DELIVERED",
        payment_status="PAID",
        payment_method="RAZORPAY",
        status_history=[{"status": "DELIVERED", "at": datetime.now(timezone.utc).isoformat()}],
    )
    db_session.add(order)
    db_session.commit()

    admin_headers = _headers(client, admin.email)
    buyer_headers = _headers(client, buyer.email)
    other_headers = _headers(client, other.email)

    denied = client.post(f"/api/v1/shipping/dispatch/{order.id}", headers=buyer_headers, json={})
    assert denied.status_code == 403

    dispatched = client.post(
        f"/api/v1/shipping/dispatch/{order.id}",
        headers=admin_headers,
        json={"schedule_pickup": True},
    )
    assert dispatched.status_code == 200, dispatched.text
    body = dispatched.json()["data"]
    assert body["awb_number"] == "AWB900"
    assert body["courier_name"] == "Delhivery"
    assert body["label_url"].endswith("label.pdf")
    assert body["tracking_url"].endswith("AWB900")

    hidden = client.get(f"/api/v1/shipping/track/{order.id}", headers=other_headers)
    assert hidden.status_code == 403

    tracked = client.get(f"/api/v1/shipping/track/{order.id}?refresh=true", headers=buyer_headers)
    assert tracked.status_code == 200, tracked.text
    assert tracked.json()["data"]["product_name"] == "Silk shirt"
    assert any(item["location"] == "Kochi" for item in tracked.json()["data"]["history"])

    event = {
        "awb": "AWB900",
        "current_status": "OUT FOR DELIVERY",
        "current_timestamp": "2026-12-02 08:00:00",
        "etd": "2026-12-02 18:00:00",
        "scans": [
            {"date": "2026-12-02 08:00:00", "status": "OUT FOR DELIVERY", "activity": "Out for delivery", "location": "Ernakulam"}
        ],
    }
    missing = client.post("/api/v1/shipping/webhook", json=event)
    assert missing.status_code == 401
    first = client.post("/api/v1/shipping/webhook", json=event, headers={"x-api-key": "hook-secret"})
    assert first.status_code == 200
    second = client.post("/api/v1/shipping/webhook", json=event, headers={"x-api-key": "hook-secret"})
    assert second.status_code == 200
    count = db_session.query(ShipmentHistory).filter(ShipmentHistory.location == "Ernakulam").count()
    assert count == 1

    requested = client.post(
        "/api/v1/returns",
        headers=buyer_headers,
        json={
            "order_id": order.id,
            "quantity": 1,
            "return_reason": "Damaged product",
            "description": "Torn sleeve",
            "return_type": "MANUAL_PICKUP",
            "image_urls": ["https://example.com/damage.jpg"],
        },
    )
    assert requested.status_code == 201, requested.text
    return_id = requested.json()["data"]["id"]
    duplicate = client.post(
        "/api/v1/returns",
        headers=buyer_headers,
        json={"order_id": order.id, "quantity": 2, "return_reason": "Other", "return_type": "MANUAL_PICKUP"},
    )
    assert duplicate.status_code == 400

    approved = client.put(f"/api/v1/returns/{return_id}/approve", headers=admin_headers, json={"remarks": "Accepted"})
    assert approved.status_code == 200
    reverse = client.post(f"/api/v1/returns/{return_id}/create-shipment", headers=admin_headers, json={})
    assert reverse.status_code == 200, reverse.text
    assert reverse.json()["data"]["awb_number"] == "RET900"

    received = client.put(
        f"/api/v1/returns/{return_id}/receive",
        headers=admin_headers,
        json={"remarks": "Checked", "inspection_status": "DAMAGED"},
    )
    assert received.status_code == 200
    assert received.json()["data"]["inspection_status"] == "DAMAGED"

    processing = client.put(
        f"/api/v1/returns/{return_id}/refund",
        headers=admin_headers,
        json={"refund_amount": "500.00", "refund_method": "UPI", "refund_status": "PROCESSING", "transaction_reference": "UPI123"},
    )
    assert processing.status_code == 200, processing.text
    completed = client.put(
        f"/api/v1/returns/{return_id}/refund",
        headers=admin_headers,
        json={"refund_amount": "500.00", "refund_method": "UPI", "refund_status": "COMPLETED", "transaction_reference": "UPI123"},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["data"]["refund_status"] == "SUCCESS"
    mine = client.get("/api/v1/returns/my-returns", headers=buyer_headers)
    assert mine.status_code == 200
    assert mine.json()["data"][0]["return_number"]
