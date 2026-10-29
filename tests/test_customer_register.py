from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models.user import User


def test_customer_register_with_email(client: TestClient, db_session: Session):
    res = client.post(
        "/api/v1/customer/register",
        json={
            "name": "Anjali Nair",
            "phone": "9123456789",
            "password": "Pass1234",
            "district": "Ernakulam",
            "city": "Kochi",
            "email": "anjali.register@example.com",
        },
    )
    assert res.status_code == 201
    body = res.json()
    assert body["access_token"]
    assert body["user"]["email"] == "anjali.register@example.com"
    assert body["user"]["phone"] == "9123456789"
    assert body["user"]["district"] == "Ernakulam"
    assert body["user"]["city"] == "Kochi"

    row = db_session.query(User).filter(User.phone == "9123456789").first()
    assert row is not None
    assert row.password_hash is not None


def test_customer_register_without_email(client: TestClient, db_session: Session):
    res = client.post(
        "/api/v1/customer/register",
        json={
            "name": "Phone Only User",
            "phone": "9988112233",
            "password": "Pass1234",
            "district": "Thiruvananthapuram",
            "city": "Varkala",
        },
    )
    assert res.status_code == 201
    assert res.json()["user"]["phone"] == "9988112233"
    assert "@logo.customer" in res.json()["user"]["email"]


def test_customer_register_duplicate_phone(client: TestClient):
    payload = {
        "name": "User One",
        "phone": "9111223344",
        "password": "Pass1234",
        "district": "Ernakulam",
        "city": "Kochi",
    }
    assert client.post("/api/v1/customer/register", json=payload).status_code == 201
    dup = client.post("/api/v1/customer/register", json=payload)
    assert dup.status_code == 409


def test_customer_logout(client: TestClient):
    reg = client.post(
        "/api/v1/customer/register",
        json={
            "name": "Logout User",
            "phone": "9000001122",
            "password": "Pass1234",
            "district": "Ernakulam",
            "city": "Kochi",
        },
    )
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    out = client.post("/api/v1/customer/logout", headers=headers)
    assert out.status_code == 200
    assert out.json()["success"] is True
    assert "logged out" in out.json()["message"].lower()

    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 401
