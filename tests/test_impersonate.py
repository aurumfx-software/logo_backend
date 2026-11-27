from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import decode_token, hash_password
from app.db.models.merchant import MerchantProfile
from app.db.models.user import User, UserRole


def _user(db: Session, email: str, role: UserRole, status_value: str = "ACTIVE", active: bool = True) -> User:
    user = User(
        name=email.split("@")[0],
        email=email,
        password_hash=hash_password("Password123!"),
        role=role,
        status=status_value,
        is_active=active,
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _login(client: TestClient, email: str) -> str:
    res = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
    assert res.status_code == 200
    return res.json()["access_token"]


def test_admin_impersonates_customer_and_merchant_then_switches_back(client: TestClient, db_session: Session):
    super_admin = _user(db_session, "imp.superadmin@example.com", UserRole.SUPER_ADMIN)
    admin = _user(db_session, "imp.admin@example.com", UserRole.ADMIN)
    customer = _user(db_session, "imp.customer@example.com", UserRole.FIELD_STAFF)
    merchant_user = _user(db_session, "imp.merchant@example.com", UserRole.MERCHANT)
    shop = MerchantProfile(user_id=merchant_user.id, business_name="Impersonate Shop", email=merchant_user.email)
    db_session.add(shop)
    db_session.commit()
    db_session.refresh(shop)

    super_headers = {"Authorization": f"Bearer {_login(client, super_admin.email)}"}
    headers = {"Authorization": f"Bearer {_login(client, admin.email)}"}

    admin_member_ok = client.post(f"/api/v1/admin/members/{customer.id}/impersonate", headers=headers)
    assert admin_member_ok.status_code == 200
    assert admin_member_ok.json()["impersonated_by"] == admin.id
    assert admin_member_ok.json()["role"] == "FIELD_STAFF"
    assert admin_member_ok.json()["user"]["id"] == customer.id

    as_customer = client.post(f"/api/v1/admin/members/{customer.id}/impersonate", headers=super_headers)
    assert as_customer.status_code == 200
    body = as_customer.json()
    assert body["is_impersonation"] is True
    assert body["impersonated_by"] == super_admin.id
    assert body["role"] == "FIELD_STAFF"
    assert body["user"]["id"] == customer.id
    claims = decode_token(body["access_token"])
    assert claims["sub"] == str(customer.id)
    assert claims["is_impersonation"] is True
    assert claims["impersonated_by"] == super_admin.id

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == customer.email

    switched = client.post(
        "/api/v1/auth/switch-back",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert switched.status_code == 200
    admin_body = switched.json()
    assert admin_body["is_impersonation"] is False
    assert admin_body["role"] == "SUPER_ADMIN"
    assert admin_body["user"]["id"] == super_admin.id

    as_merchant = client.post(f"/api/v1/admin/merchants/{shop.id}/impersonate", headers=headers)
    assert as_merchant.status_code == 200
    assert as_merchant.json()["role"] == "MERCHANT"
    assert as_merchant.json()["user"]["id"] == merchant_user.id

    plain = client.post("/api/v1/auth/switch-back", headers=headers)
    assert plain.status_code == 403


def test_impersonation_rejects_inactive_and_non_admin(client: TestClient, db_session: Session):
    super_admin = _user(db_session, "imp.superadmin2@example.com", UserRole.SUPER_ADMIN)
    blocked = _user(db_session, "imp.blocked@example.com", UserRole.FIELD_STAFF, status_value="BLOCKED")
    customer = _user(db_session, "imp.customer2@example.com", UserRole.FIELD_STAFF)
    headers = {"Authorization": f"Bearer {_login(client, super_admin.email)}"}
    customer_headers = {"Authorization": f"Bearer {_login(client, customer.email)}"}

    blocked_res = client.post(f"/api/v1/admin/members/{blocked.id}/impersonate", headers=headers)
    assert blocked_res.status_code == 403

    denied = client.post(f"/api/v1/admin/members/{customer.id}/impersonate", headers=customer_headers)
    assert denied.status_code == 403

    missing = client.post("/api/v1/admin/members/999999/impersonate", headers=headers)
    assert missing.status_code == 404
