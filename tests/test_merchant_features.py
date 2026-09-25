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


def test_field_staff_merchant_onboarding(client: TestClient, db_session: Session):
    # 1. Test onboarding without email (synthetic email generated)
    payload_no_email = {
        "business_name": "Royal Grand Bakery",
        "category": "Food & Dining",
        "owner_name": "Rajesh Sharma",
        "phone_number": "+91 98765 43210",
        "district": "Bangalore Urban",
        "city": "Bangalore",
        "location": "Indiranagar",
        "address": "Shop #12, 100ft Road, Near Metro Station",
        "landmark": "Near Metro Station",
        "merchant_photos": ["/static/merchants/photos/photo1.jpg"],
        "verification_documents": ["/static/merchants/documents/lic.pdf"],
        "merchant_videos": ["/static/merchants/videos/tour.mp4"],
    }
    res = client.post("/api/v1/merchants/onboard", json=payload_no_email)
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["message"] == "Merchant onboarded successfully"
    merchant = data["merchant"]
    assert merchant["business_name"] == "Royal Grand Bakery"
    assert merchant["owner_name"] == "Rajesh Sharma"
    assert merchant["district"] == "Bangalore Urban"
    assert merchant["city"] == "Bangalore"
    assert merchant["location"] == "Indiranagar"
    assert merchant["landmark"] == "Near Metro Station"
    assert "Food & Dining" in merchant["categories"]
    assert len(merchant["merchant_photos"]) == 1
    assert len(merchant["verification_documents"]) == 1
    assert len(merchant["merchant_videos"]) == 1
    assert merchant["approval_status"] == "PENDING"
    assert data["user"] is not None

    # 2. Test onboarding with email and field staff auth
    admin_token = create_admin(client, db_session)
    staff_headers = {"Authorization": f"Bearer {admin_token}"}
    payload_with_email = {
        "business_name": "Spice Garden Cafe",
        "categories": ["Food & Dining", "Cafe"],
        "owner_name": "Ananya Nair",
        "phone_number": "9847123456",
        "email": "ananya.cafe@example.com",
        "district": "Ernakulam",
        "city": "Kochi",
        "location": "Panampilly Nagar",
        "address": "Plot 45, Main Avenue",
        "landmark": "Opposite Central Park",
    }
    res2 = client.post("/api/v1/merchants/onboard", json=payload_with_email, headers=staff_headers)
    assert res2.status_code == 201
    m2 = res2.json()["merchant"]
    assert m2["business_name"] == "Spice Garden Cafe"
    assert m2["district"] == "Ernakulam"
    assert m2["city"] == "Kochi"
    assert m2["onboarded_by_id"] is not None


def test_merchant_media_upload_flow(client: TestClient, db_session: Session):
    import io

    # 1. Upload photo, video, and document together
    photo_file = ("shop.jpg", io.BytesIO(b"fake image data"), "image/jpeg")
    video_file = ("shop_tour.mp4", io.BytesIO(b"fake video data"), "video/mp4")
    doc_file = ("license.pdf", io.BytesIO(b"%PDF fake document data"), "application/pdf")

    res = client.post(
        "/api/v1/merchants/upload-media",
        files={
            "photos": photo_file,
            "videos": video_file,
            "documents": doc_file,
        },
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert len(data["photos"]) == 1
    assert data["photos"][0].startswith("/static/merchants/photos/")
    assert len(data["videos"]) == 1
    assert data["videos"][0].startswith("/static/merchants/videos/")
    assert len(data["documents"]) == 1
    assert data["documents"][0].startswith("/static/merchants/documents/")
    assert data["total_files"] == 3

    # 2. Upload media and attach directly to an onboarded merchant
    onboard_res = client.post(
        "/api/v1/merchants/onboard",
        json={
            "business_name": "Quick Fix Auto",
            "category": "Automobile",
            "owner_name": "Sunil Kumar",
            "phone_number": "9112233445",
            "address": "Service Bay 3",
        },
    )
    assert onboard_res.status_code == 201
    merchant_id = onboard_res.json()["merchant"]["id"]

    extra_photo = ("engine.png", io.BytesIO(b"png data"), "image/png")
    attach_res = client.post(
        f"/api/v1/merchants/{merchant_id}/upload-media",
        files={"photos": extra_photo},
    )
    assert attach_res.status_code == 200
    assert len(attach_res.json()["photos"]) == 1


def test_merchant_regions_api(client: TestClient):
    res = client.get("/api/v1/merchants/regions")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    regions = data["data"]
    assert "districts" in regions
    assert "cities" in regions
    assert "locations" in regions
    assert len(regions["districts"]) > 0
    assert "Bangalore Urban" in regions["districts"]
    assert "Kochi" in regions["cities"]


def test_creator_detail_and_multiple_merchants_per_field_staff(client: TestClient, db_session: Session):
    # 1. Create a field staff user
    staff = User(
        name="Staff User One",
        email="staff.one@example.com",
        phone="9876543210",
        password_hash=hash_password("StaffPass123!"),
        role=UserRole.FIELD_STAFF,
        is_active=True,
    )
    db_session.add(staff)
    db_session.commit()
    db_session.refresh(staff)

    staff_token = get_token(client, "staff.one@example.com", "StaffPass123!")
    staff_headers = {"Authorization": f"Bearer {staff_token}"}

    # 2. Onboard merchant 1 with staff token
    payload_m1 = {
        "business_name": "Staff 1 Shop Alpha",
        "category": "Salon & Spa",
        "owner_name": "Alpha Owner",
        "phone_number": "9811111111",
        "district": "Ernakulam",
        "city": "Kochi",
        "location": "Edappally",
        "address": "Edappally Toll",
    }
    res1 = client.post("/api/v1/merchants/onboard", json=payload_m1, headers=staff_headers)
    assert res1.status_code == 201
    m1 = res1.json()["merchant"]
    assert m1["user_id"] == staff.id
    assert m1["creator"] is not None
    assert m1["creator"]["id"] == staff.id
    assert m1["creator"]["name"] == "Staff User One"
    assert m1["creator"]["role"] == "FIELD_STAFF"
    assert m1["created_by"]["id"] == staff.id

    # 3. Onboard merchant 2 with SAME staff token (validating multiple merchants per user_id)
    payload_m2 = {
        "business_name": "Staff 1 Shop Beta",
        "category": "Restaurant",
        "owner_name": "Beta Owner",
        "phone_number": "9822222222",
        "district": "Ernakulam",
        "city": "Kochi",
        "location": "Kaloor",
        "address": "Stadium Road",
    }
    res2 = client.post("/api/v1/merchants/onboard", json=payload_m2, headers=staff_headers)
    assert res2.status_code == 201
    m2 = res2.json()["merchant"]
    assert m2["user_id"] == staff.id
    assert m2["creator"]["id"] == staff.id
    assert m2["creator"]["user_code"] is not None

    # 4. Fetch merchant by ID (GET /api/v1/merchants/{merchant_id})
    get_res = client.get(f"/api/v1/merchants/{m1['id']}")
    assert get_res.status_code == 200
    fetched = get_res.json()
    assert fetched["id"] == m1["id"]
    assert fetched["creator"]["id"] == staff.id
    assert fetched["creator"]["name"] == "Staff User One"


def test_field_staff_merchant_scoping(client: TestClient, db_session: Session):
    admin_token = create_admin(client, db_session)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Staff A
    staff_a = User(
        name="Staff A",
        email="staff.a@example.com",
        phone="9800000001",
        password_hash=hash_password("Pass123!"),
        role=UserRole.FIELD_STAFF,
        is_active=True,
    )
    # Staff B
    staff_b = User(
        name="Staff B",
        email="staff.b@example.com",
        phone="9800000002",
        password_hash=hash_password("Pass123!"),
        role=UserRole.FIELD_STAFF,
        is_active=True,
    )
    db_session.add_all([staff_a, staff_b])
    db_session.commit()

    token_a = get_token(client, "staff.a@example.com", "Pass123!")
    token_b = get_token(client, "staff.b@example.com", "Pass123!")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Staff A creates Merchant A
    res_a = client.post(
        "/api/v1/merchants/onboard",
        json={
            "business_name": "Merchant of Staff A",
            "category": "Retail",
            "owner_name": "Owner A",
            "phone_number": "9100000001",
            "address": "Street A",
        },
        headers=headers_a,
    )
    assert res_a.status_code == 201
    m_a_id = res_a.json()["merchant"]["id"]

    # Staff B creates Merchant B
    res_b = client.post(
        "/api/v1/merchants/onboard",
        json={
            "business_name": "Merchant of Staff B",
            "category": "Retail",
            "owner_name": "Owner B",
            "phone_number": "9100000002",
            "address": "Street B",
        },
        headers=headers_b,
    )
    assert res_b.status_code == 201
    m_b_id = res_b.json()["merchant"]["id"]

    # Staff A lists merchants -> sees only Merchant A
    my_a = client.get("/api/v1/merchants/my-merchants", headers=headers_a)
    assert my_a.status_code == 200
    my_a_ids = [m["id"] for m in my_a.json()]
    assert m_a_id in my_a_ids
    assert m_b_id not in my_a_ids

    list_a = client.get("/api/v1/merchants", headers=headers_a)
    assert list_a.status_code == 200
    list_a_ids = [m["id"] for m in list_a.json()]
    assert m_a_id in list_a_ids
    assert m_b_id not in list_a_ids

    # Staff B lists merchants -> sees only Merchant B
    my_b = client.get("/api/v1/merchants/my-merchants", headers=headers_b)
    assert my_b.status_code == 200
    my_b_ids = [m["id"] for m in my_b.json()]
    assert m_b_id in my_b_ids
    assert m_a_id not in my_b_ids

    # Admin view -> sees both
    admin_list = client.get("/api/v1/admin/merchants", headers=admin_headers)
    assert admin_list.status_code == 200
    admin_ids = [m["id"] for m in admin_list.json()["data"]]
    assert m_a_id in admin_ids
    assert m_b_id in admin_ids


def test_direct_merchant_approve_and_reject_apis(client: TestClient, db_session: Session):
    admin_token = create_admin(client, db_session)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Create staff and merchant
    staff = User(
        name="Staff Approvals",
        email="staff.appr@example.com",
        phone="9833333333",
        password_hash=hash_password("Pass123!"),
        role=UserRole.FIELD_STAFF,
        is_active=True,
    )
    db_session.add(staff)
    db_session.commit()
    staff_token = get_token(client, "staff.appr@example.com", "Pass123!")
    staff_headers = {"Authorization": f"Bearer {staff_token}"}

    # Onboard merchant 1
    res1 = client.post(
        "/api/v1/merchants/onboard",
        json={
            "business_name": "Approve Me Shop",
            "category": "Services",
            "owner_name": "Owner One",
            "phone_number": "9844444441",
            "address": "Kochi",
        },
        headers=staff_headers,
    )
    m1_id = res1.json()["merchant"]["id"]

    # Onboard merchant 2
    res2 = client.post(
        "/api/v1/merchants/onboard",
        json={
            "business_name": "Reject Me Shop",
            "category": "Services",
            "owner_name": "Owner Two",
            "phone_number": "9844444442",
            "address": "Kochi",
        },
        headers=staff_headers,
    )
    m2_id = res2.json()["merchant"]["id"]

    # 1. Staff cannot approve (Forbidden 403)
    staff_try = client.post(f"/api/v1/merchants/{m1_id}/approve", headers=staff_headers)
    assert staff_try.status_code == 403

    # 2. Admin approves via POST /api/v1/merchants/{m1_id}/approve
    appr_res = client.post(f"/api/v1/merchants/{m1_id}/approve", headers=admin_headers)
    assert appr_res.status_code == 200
    assert appr_res.json()["success"] is True
    assert appr_res.json()["data"]["approval_status"] == "APPROVED"
    assert appr_res.json()["data"]["is_verified"] is True
    assert appr_res.json()["data"]["creator"]["id"] == staff.id

    # 3. Admin rejects via POST /api/v1/merchants/{m2_id}/reject
    rej_res = client.post(
        f"/api/v1/merchants/{m2_id}/reject",
        json={"rejection_reason": "Incomplete documentation submitted"},
        headers=admin_headers,
    )
    assert rej_res.status_code == 200
    assert rej_res.json()["success"] is True
    assert rej_res.json()["data"]["approval_status"] == "REJECTED"
    assert rej_res.json()["data"]["rejection_reason"] == "Incomplete documentation submitted"
