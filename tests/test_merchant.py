from fastapi.testclient import TestClient


def test_merchant_registration_success(client: TestClient):
    payload = {
        "name": "Rajesh Merchant",
        "email": "rajesh.merchant@example.com",
        "password": "MerchantPassword123",
        "business_name": "Royal Unisex Salon & Spa",
        "categories": ["Salon", "Spa", "Beauty"],
        "location": "Edappally, Kochi",
        "services": ["Haircut", "Hair Spa", "Facial"],
        "service_timing": "Mon-Sun: 09:00 AM - 09:00 PM",
        "merchant_photos": [
            "https://example.com/photos/front.jpg",
            "https://example.com/photos/inside.jpg",
        ],
        "contact_number": "9876543999",
        "address": "Door No 14/204, Toll Junction, Edappally, Kochi - 682024",
    }
    response = client.post("/api/v1/merchants/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["message"] == "Merchant registered successfully"
    assert data["user"]["email"] == "rajesh.merchant@example.com"
    assert data["user"]["role"] == "MERCHANT"
    assert data["merchant"]["user_id"] == data["user"]["id"]
    assert data["user"]["phone"] == "9876543999"
    assert data["user"]["address"] == "Door No 14/204, Toll Junction, Edappally, Kochi - 682024"

    assert data["merchant"]["business_name"] == "Royal Unisex Salon & Spa"
    assert "Salon" in data["merchant"]["categories"]
    assert "Haircut" in data["merchant"]["services"]
    assert data["merchant"]["service_timing"] == "Mon-Sun: 09:00 AM - 09:00 PM"
    assert len(data["merchant"]["merchant_photos"]) == 2


def test_merchant_login_and_get_profile(client: TestClient):
    reg_payload = {
        "name": "Anil Cafe",
        "email": "anil.cafe@example.com",
        "password": "CafePassword123",
        "business_name": "Anil Coffee House",
        "categories": ["Cafe", "Bakery"],
        "location": "Panampilly Nagar, Kochi",
        "services": ["Espresso", "Pastries", "Snacks"],
        "service_timing": "08:00 AM - 10:00 PM",
        "merchant_photos": [],
        "contact_number": "9876543888",
        "address": "Main Avenue, Panampilly Nagar, Kochi",
    }
    client.post("/api/v1/merchants/register", json=reg_payload)

    # Login as merchant
    login_res = client.post("/api/v1/auth/login", json={
        "email": "anil.cafe@example.com",
        "password": "CafePassword123",
    })
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]

    # Get merchant profile via /api/v1/merchants/me
    profile_res = client.get(
        "/api/v1/merchants/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert profile_res.status_code == 200
    m_data = profile_res.json()
    assert m_data["business_name"] == "Anil Coffee House"
    assert m_data["location"] == "Panampilly Nagar, Kochi"


def test_merchant_update_profile(client: TestClient):
    reg_payload = {
        "name": "Kumar Plumber",
        "email": "kumar.plumber@example.com",
        "password": "PlumberPass123",
        "business_name": "Kumar Plumbing Services",
        "categories": ["Home Services", "Plumbing"],
        "location": "Kaloor, Kochi",
        "services": ["Pipe repair", "Water heater installation"],
        "service_timing": "24/7 Emergency",
        "merchant_photos": [],
        "contact_number": "9876543777",
        "address": "Kaloor Stadium Link Road, Kochi",
    }
    client.post("/api/v1/merchants/register", json=reg_payload)

    login_res = client.post("/api/v1/auth/login", json={
        "email": "kumar.plumber@example.com",
        "password": "PlumberPass123",
    })
    token = login_res.json()["access_token"]

    # Update timing and business name
    update_res = client.put(
        "/api/v1/merchants/me",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "business_name": "Kumar 24/7 Super Plumbing",
            "service_timing": "06:00 AM - 11:00 PM",
        },
    )
    assert update_res.status_code == 200
    updated_data = update_res.json()
    assert updated_data["business_name"] == "Kumar 24/7 Super Plumbing"
    assert updated_data["service_timing"] == "06:00 AM - 11:00 PM"


def test_user_without_merchant_profile_gets_404_on_me(client: TestClient):
    # Register regular staff user
    client.post("/api/v1/auth/register", json={
        "name": "Normal Staff User",
        "email": "normal.staff@example.com",
        "password": "StaffPassword123",
    })
    login_res = client.post("/api/v1/auth/login", json={
        "email": "normal.staff@example.com",
        "password": "StaffPassword123",
    })
    token = login_res.json()["access_token"]

    # User without merchant profile accessing merchant/me -> 404 Not Found
    res = client.get("/api/v1/merchants/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 404


def test_list_and_filter_merchants(client: TestClient):
    res = client.get("/api/v1/merchants")
    assert res.status_code == 200
    assert isinstance(res.json(), list)

    res_limit = client.get("/api/v1/merchants?limit=500")
    assert res_limit.status_code == 200
    assert isinstance(res_limit.json(), list)


def test_list_merchants_by_category_column(client: TestClient, db_session):
    from app.db.models.merchant import MerchantProfile
    from app.db.models.user import User
    from app.core.security import hash_password

    user = User(
        name="Advocate Owner",
        email="advocate.shop@example.com",
        password_hash=hash_password("Pass12345!"),
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    merchant = MerchantProfile(
        user_id=user.id,
        business_name="Legal Aid Office",
        category="Advocates",
        categories=["Advocates"],
        location="Kochi",
        approval_status="APPROVED",
        status="APPROVED",
        is_active=True,
        is_verified=True,
    )
    db_session.add(merchant)
    db_session.commit()

    res = client.get("/api/v1/merchants?category=Advocates&limit=500")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 1
    assert any(m["business_name"] == "Legal Aid Office" for m in data)


def test_list_merchants_merges_linked_user(client: TestClient, db_session):
    from app.db.models.merchant import MerchantProfile
    from app.db.models.user import User
    from app.core.security import hash_password

    user = User(
        name="Shop Owner",
        email="owner@shop.example.com",
        phone="9876543210",
        password_hash=hash_password("Pass12345!"),
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    merchant = MerchantProfile(
        user_id=user.id,
        business_name="Merged Shop",
        categories=["Retail"],
        location="Kochi",
        approval_status="APPROVED",
        status="APPROVED",
        is_active=True,
        is_verified=True,
    )
    db_session.add(merchant)
    db_session.commit()

    res = client.get("/api/v1/merchants?limit=500")
    assert res.status_code == 200
    row = next(m for m in res.json() if m["business_name"] == "Merged Shop")
    assert row["user"]["email"] == "owner@shop.example.com"
    assert row["owner_name"] == "Shop Owner"
    assert row["contact_number"] == "9876543210"
