import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models.user import User, UserRole
from app.db.models.merchant import MerchantProfile


def get_token(client: TestClient, email: str, password: str) -> str:
    res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return res.json()["access_token"]


def setup_admin_and_merchant(client: TestClient, db_session: Session):
    # Create Admin
    admin = User(
        name="Platform Admin",
        email="admin.platform@example.com",
        password_hash=hash_password("AdminPass123!"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()
    admin_token = get_token(client, "admin.platform@example.com", "AdminPass123!")

    # Register Merchant
    reg_payload = {
        "name": "Suresh Salon",
        "email": "suresh.salon@example.com",
        "password": "MerchantPass123!",
        "business_name": "Suresh Unisex Salon",
        "categories": ["Salon", "Beauty"],
        "location": "Palarivattom, Kochi",
        "services": ["Haircut", "Beard Trim", "Head Massage"],
        "service_timing": "09:00 AM - 09:00 PM",
        "merchant_photos": ["https://example.com/salon1.jpg"],
        "contact_number": "9876500001",
        "address": "Opposite Metro Pillar 490, Palarivattom, Kochi",
    }
    client.post("/api/v1/merchants/register", json=reg_payload)
    merchant_token = get_token(client, "suresh.salon@example.com", "MerchantPass123!")

    merchant_user = db_session.query(User).filter(User.email == "suresh.salon@example.com").first()
    merchant_profile = db_session.query(MerchantProfile).filter(MerchantProfile.user_id == merchant_user.id).first()

    return admin, admin_token, merchant_user, merchant_profile, merchant_token


def test_merchant_statistics_api(client: TestClient, db_session: Session):
    admin, admin_token, merchant_user, merchant_profile, _ = setup_admin_and_merchant(client, db_session)

    # 1. Public / Merchant stats endpoint
    res = client.get("/api/v1/merchants/stats")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "Merchant statistics retrieved" in data["message"]
    stats = data["data"]
    assert stats["total_merchants"] >= 1
    assert stats["active_merchants"] >= 1
    assert stats["pending_merchants"] >= 1
    assert len(stats["top_locations"]) >= 1
    assert len(stats["top_categories"]) >= 1

    # 2. Admin stats endpoint
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    admin_res = client.get("/api/v1/admin/merchants/stats", headers=admin_headers)
    assert admin_res.status_code == 200
    admin_data = admin_res.json()
    assert admin_data["success"] is True
    assert admin_data["data"]["total_merchants"] >= 1


def test_merchant_approval_and_rejection_flow(client: TestClient, db_session: Session):
    admin, admin_token, merchant_user, merchant_profile, merchant_token = setup_admin_and_merchant(client, db_session)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    merchant_headers = {"Authorization": f"Bearer {merchant_token}"}

    # Verify initial pending state
    assert merchant_profile.approval_status == "PENDING"
    assert merchant_profile.is_verified is False

    # 1. Approve Merchant
    approve_res = client.post(
        f"/api/v1/admin/merchants/{merchant_profile.id}/approve",
        headers=admin_headers,
    )
    assert approve_res.status_code == 200
    app_data = approve_res.json()
    assert app_data["success"] is True
    assert app_data["data"]["approval_status"] == "APPROVED"
    assert app_data["data"]["is_verified"] is True

    # Check notification received by merchant
    notif_res = client.get("/api/v1/notifications", headers=merchant_headers)
    assert notif_res.status_code == 200
    notifs = notif_res.json()["data"]
    assert len(notifs) >= 1
    assert "Approved" in notifs[0]["title"]
    assert notifs[0]["type"] == "MERCHANT_APPROVAL"

    # Check activity log generated for admin
    logs_res = client.get("/api/v1/admin/activity-logs?action=MERCHANT_APPROVED", headers=admin_headers)
    assert logs_res.status_code == 200
    logs = logs_res.json()["data"]
    assert len(logs) >= 1
    assert any(log["action"] == "MERCHANT_APPROVED" for log in logs)

    # 2. Reject Merchant
    reject_res = client.post(
        f"/api/v1/admin/merchants/{merchant_profile.id}/reject",
        json={"rejection_reason": "Missing trade license copy."},
        headers=admin_headers,
    )
    assert reject_res.status_code == 200
    rej_data = reject_res.json()
    assert rej_data["success"] is True
    assert rej_data["data"]["approval_status"] == "REJECTED"
    assert rej_data["data"]["rejection_reason"] == "Missing trade license copy."

    # Check rejection notification received by merchant
    notif_res2 = client.get("/api/v1/notifications", headers=merchant_headers)
    assert notif_res2.status_code == 200
    notifs2 = notif_res2.json()["data"]
    assert len(notifs2) >= 2
    assert "Application Update" in notifs2[0]["title"]
    assert "Missing trade license" in notifs2[0]["message"]


def test_location_and_service_search_apis(client: TestClient, db_session: Session):
    admin, admin_token, merchant_user, merchant_profile, _ = setup_admin_and_merchant(client, db_session)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Approve merchant so they appear in public search
    client.post(f"/api/v1/admin/merchants/{merchant_profile.id}/approve", headers=admin_headers)

    # 1. Test /merchants/locations
    loc_res = client.get("/api/v1/merchants/locations")
    assert loc_res.status_code == 200
    loc_data = loc_res.json()
    assert loc_data["success"] is True
    assert len(loc_data["data"]) >= 1
    assert any("Palarivattom" in item["location"] for item in loc_data["data"])

    # Filtered location query
    loc_q_res = client.get("/api/v1/merchants/locations?query=Palari")
    assert loc_q_res.status_code == 200
    assert len(loc_q_res.json()["data"]) >= 1

    # 2. Test /merchants/services
    svc_res = client.get("/api/v1/merchants/services")
    assert svc_res.status_code == 200
    svc_data = svc_res.json()
    assert svc_data["success"] is True
    assert len(svc_data["data"]) >= 1
    assert any("Haircut" in item["service"] for item in svc_data["data"])

    # Filtered service query
    svc_q_res = client.get("/api/v1/merchants/services?query=Beard")
    assert svc_q_res.status_code == 200
    assert len(svc_q_res.json()["data"]) >= 1

    # 3. Test /merchants/search
    search_res = client.get("/api/v1/merchants/search?location=Palarivattom&service=Haircut")
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert search_data["success"] is True
    assert search_data["meta"]["total_items"] >= 1
    assert search_data["data"][0]["business_name"] == "Suresh Unisex Salon"

    # 4. Test /merchants/discovery-meta
    meta_res = client.get("/api/v1/merchants/discovery-meta")
    assert meta_res.status_code == 200
    meta_data = meta_res.json()
    assert meta_data["success"] is True
    assert "locations" in meta_data["data"]
    assert "services" in meta_data["data"]
    assert "categories" in meta_data["data"]


def test_notification_and_activity_logs_api(client: TestClient, db_session: Session):
    admin, admin_token, merchant_user, merchant_profile, merchant_token = setup_admin_and_merchant(client, db_session)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    merchant_headers = {"Authorization": f"Bearer {merchant_token}"}

    # Trigger an approval notification
    client.post(f"/api/v1/admin/merchants/{merchant_profile.id}/approve", headers=admin_headers)

    # 1. Unread count
    count_res = client.get("/api/v1/notifications/unread-count", headers=merchant_headers)
    assert count_res.status_code == 200
    assert count_res.json()["data"]["unread_count"] >= 1

    # 2. Get notifications list
    notif_list_res = client.get("/api/v1/notifications", headers=merchant_headers)
    assert notif_list_res.status_code == 200
    items = notif_list_res.json()["data"]
    target_notif_id = items[0]["id"]

    # 3. Mark single notification as read
    read_res = client.patch(f"/api/v1/notifications/{target_notif_id}/read", headers=merchant_headers)
    assert read_res.status_code == 200
    assert read_res.json()["data"]["is_read"] is True

    # 4. Mark all as read
    read_all_res = client.patch("/api/v1/notifications/read-all", headers=merchant_headers)
    assert read_all_res.status_code == 200
    assert "Marked" in read_all_res.json()["message"]

    # 5. Delete notification
    del_res = client.delete(f"/api/v1/notifications/{target_notif_id}", headers=merchant_headers)
    assert del_res.status_code == 200
    assert del_res.json()["data"]["deleted_id"] == target_notif_id

    # 6. Admin activity logs
    logs_res = client.get("/api/v1/admin/activity-logs", headers=admin_headers)
    assert logs_res.status_code == 200
    assert len(logs_res.json()["data"]) >= 1

    # 7. Admin activity actions list
    actions_res = client.get("/api/v1/admin/activity-logs/actions", headers=admin_headers)
    assert actions_res.status_code == 200
    assert isinstance(actions_res.json()["data"], list)
    assert "MERCHANT_APPROVED" in actions_res.json()["data"] or "MERCHANT_REGISTERED" in actions_res.json()["data"]
