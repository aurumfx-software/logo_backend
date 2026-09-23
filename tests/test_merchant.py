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
    assert data["user"]["role"] == "FIELD_STAFF"
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
