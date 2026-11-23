import re

from fastapi.testclient import TestClient


LOGIN_ID = re.compile(r"^[A-Z]{3}\d{5,6}$")


def test_customer_and_merchant_login_with_name_id(client: TestClient):
    customer = client.post(
        "/api/v1/customer/register",
        json={
            "name": "Anjali Nair",
            "phone": "9011122233",
            "password": "Pass1234",
            "district": "Ernakulam",
            "city": "Kochi",
            "email": "anjali.loginid@example.com",
        },
    )
    assert customer.status_code == 201
    customer_id = customer.json()["user"]["login_id"]
    assert customer_id.startswith("ANJ")
    assert LOGIN_ID.match(customer_id)

    signed_in = client.post(
        "/api/v1/auth/login",
        json={"email": customer_id.lower(), "password": "Pass1234"},
    )
    assert signed_in.status_code == 200
    assert signed_in.json()["login_id"] == customer_id

    merchant = client.post(
        "/api/v1/merchants/register",
        json={
            "name": "Rajesh Merchant",
            "email": "rajesh.loginid@example.com",
            "password": "MerchantPassword123",
            "business_name": "Royal Unisex Salon",
            "categories": ["Salon"],
            "location": "Edappally, Kochi",
            "services": ["Haircut"],
            "service_timing": "Mon-Sun: 09:00 AM - 09:00 PM",
            "contact_number": "9876501199",
            "address": "Door No 14, Edappally, Kochi",
        },
    )
    assert merchant.status_code == 201
    merchant_id = merchant.json()["user"]["login_id"]
    assert merchant_id.startswith("RAJ")
    assert merchant_id != customer_id

    merchant_login = client.post(
        "/api/v1/auth/login",
        json={"email": merchant_id, "password": "MerchantPassword123"},
    )
    assert merchant_login.status_code == 200
    assert merchant_login.json()["user"]["role"] == "MERCHANT"
    assert merchant_login.json()["login_id"] == merchant_id
