from fastapi.testclient import TestClient


def _register_and_login(client: TestClient) -> tuple[str, int]:
    created = client.post(
        "/api/v1/merchants/register",
        json={
            "name": "Ad Merchant",
            "email": "ads.merchant@example.com",
            "password": "MerchantPassword123",
            "business_name": "Ad Shop",
            "categories": ["Retail"],
            "location": "Kochi",
            "services": ["Sales"],
            "service_timing": "09:00 AM - 06:00 PM",
            "merchant_photos": [],
            "contact_number": "9876500111",
            "address": "MG Road, Kochi",
        },
    )
    assert created.status_code == 201
    merchant_id = created.json()["merchant"]["id"]
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "ads.merchant@example.com", "password": "MerchantPassword123"},
    )
    assert login.status_code == 200
    return login.json()["access_token"], merchant_id


def test_merchant_advertisement_shows_on_details(client: TestClient):
    token, merchant_id = _register_and_login(client)
    headers = {"Authorization": f"Bearer {token}"}
    packages = client.get("/api/v1/subscriptions/packages?audience=MERCHANT").json()["data"]
    detail_plan = next(item for item in packages if item["code"] == "MERCHANT_DETAIL_3999")
    subscribed = client.post(
        "/api/v1/subscriptions/subscribe",
        headers=headers,
        json={"package_id": detail_plan["id"], "merchant_profile_id": merchant_id, "payment_reference": "AD-3999"},
    )
    assert subscribed.status_code == 201, subscribed.text

    created = client.post(
        "/api/v1/merchants/me/advertisements",
        headers=headers,
        json={
            "title": "Festival offer",
            "description": "20 percent off this week",
            "image_url": "https://example.com/ad.jpg",
            "link_url": "https://example.com/offer",
        },
    )
    assert created.status_code == 201
    ad = created.json()["data"]
    assert ad["title"] == "Festival offer"
    assert ad["status"] == "active"

    details = client.get(f"/api/v1/merchants/{merchant_id}")
    assert details.status_code == 200
    shown = details.json()["advertisements"]
    assert len(shown) == 1
    assert shown[0]["title"] == "Festival offer"
    assert shown[0]["image_url"] == "https://example.com/ad.jpg"

    public_list = client.get(f"/api/v1/merchants/{merchant_id}/advertisements")
    assert public_list.status_code == 200
    assert public_list.json()["data"][0]["id"] == ad["id"]

    hidden = client.put(
        f"/api/v1/merchants/me/advertisements/{ad['id']}",
        headers=headers,
        json={"status": "inactive"},
    )
    assert hidden.status_code == 200
    details_after = client.get(f"/api/v1/merchants/{merchant_id}")
    assert details_after.json()["advertisements"] == []

    mine = client.get("/api/v1/merchants/me/advertisements", headers=headers)
    assert mine.status_code == 200
    assert mine.json()["data"][0]["status"] == "inactive"
