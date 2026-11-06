from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models.merchant import MerchantProfile
from app.db.models.user import User, UserRole


def _admin_headers(client: TestClient, db_session: Session) -> dict:
    admin = User(
        name="Geo Admin",
        email="geo.admin@example.com",
        password_hash=hash_password("Password123!"),
        role=UserRole.ADMIN,
        is_active=True,
        is_verified=True,
    )
    db_session.add(admin)
    db_session.commit()
    login = client.post(
        "/api/v1/auth/login",
        json={"email": admin.email, "password": "Password123!"},
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_geography_screen(client: TestClient, db_session: Session):
    headers = _admin_headers(client, db_session)
    owner = User(
        name="Owner",
        email="geo.owner@example.com",
        password_hash=hash_password("Password123!"),
        role=UserRole.MERCHANT,
        is_active=True,
    )
    customer = User(
        name="Customer",
        email="geo.customer@logo.customer",
        password_hash=hash_password("Password123!"),
        role=UserRole.FIELD_STAFF,
        district="Kannur",
        city="Payyanur",
        module_access=[],
        is_active=True,
    )
    db_session.add_all([owner, customer])
    db_session.commit()
    db_session.add(
        MerchantProfile(
            user_id=owner.id,
            business_name="Payyanur Store",
            district="Kannur",
            city="Payyanur",
            location="Old Bus Stand",
            approval_status="APPROVED",
            is_verified=True,
            is_active=True,
        )
    )
    db_session.commit()

    created = client.post(
        "/api/v1/admin/geography/towns",
        headers=headers,
        json={"district": "Kannur", "town": "Payyanur", "zones": ["Payyanur Hub"]},
    )
    assert created.status_code == 201
    assert created.json()["registered_merchants"] == 1
    assert created.json()["customer_reach"] == 1
    assert created.json()["coverage_status"] == "COVERED"
    assert "Old Bus Stand" in created.json()["zones"]

    screen = client.get(
        "/api/v1/admin/geography",
        headers=headers,
        params={"district": "Kannur", "search": "Payyanur"},
    )
    assert screen.status_code == 200
    body = screen.json()
    assert body["cards"]["kerala_districts_total"] == 14
    assert body["cards"]["real_merchants"] == 1
    assert body["cards"]["verified_merchants"] == 1
    assert body["cards"]["active_users_reach"] == 1
    assert body["cards"]["active_municipalities"] == 1
    assert body["total"] == 1
    assert len(body["districts"]) == 14
    assert body["towns"][0]["town"] == "Payyanur"

    duplicate = client.post(
        "/api/v1/admin/geography/towns",
        headers=headers,
        json={"district": "Kannur", "town": "Payyanur"},
    )
    assert duplicate.status_code == 409
