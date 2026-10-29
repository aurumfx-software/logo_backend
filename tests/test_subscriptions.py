from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models.user import User, UserRole


def _auth_headers(client: TestClient, email: str, password: str = "Password123!") -> dict:
    res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _create_user(db_session: Session, email: str, role: UserRole = UserRole.FIELD_STAFF) -> User:
    user = User(
        name="Test User",
        email=email,
        password_hash=hash_password("Password123!"),
        role=role,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_list_subscription_packages(client: TestClient):
    res = client.get("/api/v1/subscriptions/packages?audience=USER")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert len(body["data"]) >= 2
    codes = {p["code"] for p in body["data"]}
    assert "USER_SELLER_500" in codes


def test_user_subscribe_seller_plan(client: TestClient, db_session: Session):
    user = _create_user(db_session, "subuser@example.com")
    headers = _auth_headers(client, user.email)

    packages = client.get("/api/v1/subscriptions/packages?audience=USER").json()["data"]
    seller = next(p for p in packages if p["code"] == "USER_SELLER_500")

    sub_res = client.post(
        "/api/v1/subscriptions/subscribe",
        headers=headers,
        json={"package_id": seller["id"], "payment_reference": "TEST-PAY-001"},
    )
    assert sub_res.status_code == 201
    assert sub_res.json()["data"]["status"] == "ACTIVE"

    active = client.get("/api/v1/subscriptions/me/active", headers=headers)
    assert active.status_code == 200
    summary = active.json()["data"]
    assert summary["can_sell_products"] is True
    assert summary["is_subscriber"] is True
    assert summary["subscription_plan"] == "500_SELLER"


def test_admin_assign_merchant_subscription(client: TestClient, db_session: Session):
    from app.db.models.merchant import MerchantProfile

    merchant_user = _create_user(db_session, "merchsub@example.com", UserRole.MERCHANT)
    merchant = MerchantProfile(
        user_id=merchant_user.id,
        business_name="Sub Shop",
        approval_status="APPROVED",
        status="APPROVED",
        is_active=True,
    )
    db_session.add(merchant)
    db_session.commit()
    db_session.refresh(merchant)

    admin = _create_user(db_session, "subadmin@example.com", UserRole.ADMIN)
    admin_headers = _auth_headers(client, admin.email)

    packages = client.get("/api/v1/subscriptions/packages?audience=MERCHANT").json()["data"]
    promo = next(p for p in packages if p["code"] == "MERCHANT_PROMO_BASIC")

    assign_res = client.post(
        "/api/v1/subscriptions/admin/assign",
        headers=admin_headers,
        json={
            "user_id": merchant_user.id,
            "package_id": promo["id"],
            "merchant_profile_id": merchant.id,
        },
    )
    assert assign_res.status_code == 201
    assert assign_res.json()["data"]["merchant_profile_id"] == merchant.id
