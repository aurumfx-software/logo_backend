from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models.user import User, UserRole


def get_token(client: TestClient, email: str, password: str) -> str:
    res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return res.json()["access_token"]


def create_admin(client: TestClient, db_session: Session) -> str:
    admin = User(
        name="Admin User",
        email="admin.features@example.com",
        password_hash=hash_password("AdminPass123!"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()
    return get_token(client, "admin.features@example.com", "AdminPass123!")


def register_merchant_helper(client: TestClient, name: str, email: str, loc: str, services: list, categories: list):
    import hashlib
    phone_digits = "".join(filter(str.isdigit, hashlib.md5(email.encode()).hexdigest()))[:10].ljust(10, "9")
    payload = {
        "name": name,
        "email": email,
        "password": "MerchantPass123!",
        "business_name": f"{name}'s Store",
        "categories": categories,
        "location": loc,
        "services": services,
        "service_timing": "09:00 AM - 08:00 PM",
        "merchant_photos": [],
        "contact_number": phone_digits,
        "address": f"123 Main Street, {loc}",
    }
    res = client.post("/api/v1/merchants/register", json=payload)
    assert res.status_code == 201
    return res.json()["merchant"]


def test_merchant_statistics_api(client: TestClient, db_session: Session):
    admin_token = create_admin(client, db_session)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Register 2 merchants
    m1 = register_merchant_helper(
        client, "Merchant One", "m1@example.com", "Kochi", ["Haircut", "Shave"], ["Salon"]
    )
    m2 = register_merchant_helper(
        client, "Merchant Two", "m2@example.com", "Trivandrum", ["Car Wash"], ["Automobile"]
    )

    # Approve m1
    approve_res = client.post(
        f"/api/v1/admin/merchants/{m1['id']}/approve",
        headers=admin_headers,
    )
    assert approve_res.status_code == 200
    assert approve_res.json()["success"] is True

    # Check stats
    stats_res = client.get("/api/v1/admin/merchants/stats", headers=admin_headers)
    assert stats_res.status_code == 200
    body = stats_res.json()
    assert body["success"] is True
    stats = body["data"]

    assert stats["total_merchants"] == 2
    assert stats["approved_merchants"] == 1
    assert stats["pending_merchants"] == 1
    assert stats["active_merchants"] == 2
    assert len(stats["top_locations"]) > 0
    assert len(stats["top_categories"]) > 0


def test_merchant_approval_and_rejection_flow(client: TestClient, db_session: Session):
    admin_token = create_admin(client, db_session)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Register merchant
    m = register_merchant_helper(
        client, "Approval Test", "approval.test@example.com", "Calicut", ["Oil Change"], ["Automobile"]
    )
    assert m["approval_status"] == "PENDING"
    assert m["is_verified"] is False

    # 2. Check pending list
    pending_res = client.get("/api/v1/admin/merchants/pending", headers=admin_headers)
    assert pending_res.status_code == 200
    assert pending_res.json()["success"] is True
    assert any(item["id"] == m["id"] for item in pending_res.json()["data"])

    # 3. Approve merchant
    approve_res = client.post(
        f"/api/v1/admin/merchants/{m['id']}/approve",
        headers=admin_headers,
    )
    assert approve_res.status_code == 200
    app_data = approve_res.json()["data"]
    assert app_data["approval_status"] == "APPROVED"
    assert app_data["is_verified"] is True
    assert app_data["approved_by_id"] is not None

    # 4. Verify notification was sent to merchant user
    merchant_token = get_token(client, "approval.test@example.com", "MerchantPass123!")
    merchant_headers = {"Authorization": f"Bearer {merchant_token}"}
    notif_res = client.get("/api/v1/notifications", headers=merchant_headers)
    assert notif_res.status_code == 200
    notifs = notif_res.json()["data"]
    assert len(notifs) >= 1
    assert any("Approved" in n["title"] for n in notifs)

    # 5. Register second merchant and test rejection
    m2 = register_merchant_helper(
        client, "Reject Test", "reject.test@example.com", "Kollam", ["Massage"], ["Spa"]
    )
    reject_res = client.post(
        f"/api/v1/admin/merchants/{m2['id']}/reject",
        json={"rejection_reason": "Incomplete verification documents provided."},
        headers=admin_headers,
    )
    assert reject_res.status_code == 200
    rej_data = reject_res.json()["data"]
    assert rej_data["approval_status"] == "REJECTED"
    assert rej_data["rejection_reason"] == "Incomplete verification documents provided."

    # Verify rejection notification
    m2_token = get_token(client, "reject.test@example.com", "MerchantPass123!")
    m2_notif = client.get("/api/v1/notifications", headers={"Authorization": f"Bearer {m2_token}"})
    assert any("not approved" in n["message"] for n in m2_notif.json()["data"])


def test_location_and_service_search(client: TestClient, db_session: Session):
    admin_token = create_admin(client, db_session)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Register and approve 2 distinct merchants
    m1 = register_merchant_helper(
        client, "Kochi Salon", "kochi.salon@example.com", "Edappally, Kochi", ["Haircut", "Beard Trim"], ["Salon"]
    )
    m2 = register_merchant_helper(
        client, "Calicut Auto", "calicut.auto@example.com", "Mavoor Road, Calicut", ["Wheel Alignment", "Car Wash"], ["Automobile"]
    )

    # Approve both
    client.post(f"/api/v1/admin/merchants/{m1['id']}/approve", headers=admin_headers)
    client.post(f"/api/v1/admin/merchants/{m2['id']}/approve", headers=admin_headers)

    # 1. Location search
    loc_res = client.get("/api/v1/merchants/search/location?location=Kochi")
    assert loc_res.status_code == 200
    loc_data = loc_res.json()
    assert loc_data["success"] is True
    assert len(loc_data["data"]) == 1
    assert "Kochi" in loc_data["data"][0]["location"]

    # 2. Service search
    svc_res = client.get("/api/v1/merchants/search/service?service=Car Wash")
    assert svc_res.status_code == 200
    svc_data = svc_res.json()
    assert svc_data["success"] is True
    assert len(svc_data["data"]) == 1
    assert "Car Wash" in svc_data["data"][0]["services"]

    # 3. Unified keyword search
    uni_res = client.get("/api/v1/merchants/search?q=Haircut")
    assert uni_res.status_code == 200
    assert len(uni_res.json()["data"]) == 1

    # 4. Metadata discovery
    meta_res = client.get("/api/v1/merchants/meta/discovery")
    assert meta_res.status_code == 200
    meta = meta_res.json()["data"]
    assert any("Kochi" in loc for loc in meta["locations"])
    assert "Haircut" in meta["services"]
    assert "Automobile" in meta["categories"]


def test_notification_operations(client: TestClient, db_session: Session):
    admin_token = create_admin(client, db_session)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Register merchant (will receive notifications upon approval)
    m = register_merchant_helper(
        client, "Notif User", "notif.user@example.com", "Alappuzha", ["Boat Ride"], ["Tourism"]
    )
    client.post(f"/api/v1/admin/merchants/{m['id']}/approve", headers=admin_headers)

    user_token = get_token(client, "notif.user@example.com", "MerchantPass123!")
    user_headers = {"Authorization": f"Bearer {user_token}"}

    # 1. Check unread count
    count_res = client.get("/api/v1/notifications/unread-count", headers=user_headers)
    assert count_res.status_code == 200
    assert count_res.json()["data"]["unread_count"] >= 1

    # 2. List notifications
    list_res = client.get("/api/v1/notifications", headers=user_headers)
    assert list_res.status_code == 200
    notif_id = list_res.json()["data"][0]["id"]

    # 3. Mark as read
    read_res = client.patch(f"/api/v1/notifications/{notif_id}/read", headers=user_headers)
    assert read_res.status_code == 200
    assert read_res.json()["data"]["is_read"] is True

    # 4. Mark all read
    all_read_res = client.post("/api/v1/notifications/mark-all-read", headers=user_headers)
    assert all_read_res.status_code == 200
    assert all_read_res.json()["success"] is True

    # 5. Delete notification
    del_res = client.delete(f"/api/v1/notifications/{notif_id}", headers=user_headers)
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True


def test_activity_logs_api(client: TestClient, db_session: Session):
    admin_token = create_admin(client, db_session)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Register and approve a merchant to generate logs
    m = register_merchant_helper(
        client, "Log Test", "log.test@example.com", "Thrissur", ["Jewellery Clean"], ["Retail"]
    )
    client.post(f"/api/v1/admin/merchants/{m['id']}/approve", headers=admin_headers)

    # 1. Fetch activity logs
    logs_res = client.get("/api/v1/admin/activity-logs", headers=admin_headers)
    assert logs_res.status_code == 200
    logs_data = logs_res.json()
    assert logs_data["success"] is True
    assert len(logs_data["data"]) >= 2  # MERCHANT_REGISTERED and MERCHANT_APPROVED

    # 2. Filter by action
    filt_res = client.get("/api/v1/admin/activity-logs?action=MERCHANT_APPROVED", headers=admin_headers)
    assert filt_res.status_code == 200
    for item in filt_res.json()["data"]:
        assert "MERCHANT_APPROVED" in item["action"]

    # 3. Get action types
    act_res = client.get("/api/v1/admin/activity-logs/actions", headers=admin_headers)
    assert act_res.status_code == 200
    actions = act_res.json()["data"]
    assert "MERCHANT_APPROVED" in actions
    assert "MERCHANT_REGISTERED" in actions
