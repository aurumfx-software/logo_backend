from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models.merchant import MerchantProfile
from app.db.models.user import User, UserRole


def test_merchant_favorites_guest_empty_list(client: TestClient):
    res = client.get("/api/v1/favorites/merchants")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_merchant_favorites_save_and_list(client: TestClient, db_session: Session):
    user = User(
        name="Fav User",
        email="fav.merchant@example.com",
        password_hash=hash_password("Pass12345!"),
        role=UserRole.FIELD_STAFF,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    merchant = MerchantProfile(
        user_id=user.id,
        business_name="Favorite Shop",
        approval_status="APPROVED",
        is_active=True,
    )
    db_session.add(merchant)
    db_session.commit()
    db_session.refresh(merchant)

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "fav.merchant@example.com", "password": "Pass12345!"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    save = client.post(f"/api/v1/favorites/merchants/{merchant.id}", headers=headers)
    assert save.status_code == 201
    assert save.json()["merchant_id"] == merchant.id

    listing = client.get("/api/v1/favorites/merchants", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["business_name"] == "Favorite Shop"

    delete = client.delete(f"/api/v1/favorites/merchants/{merchant.id}", headers=headers)
    assert delete.status_code == 200

    empty = client.get("/api/v1/favorites/merchants", headers=headers)
    assert empty.json()["total"] == 0
