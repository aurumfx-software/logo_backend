from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models.merchant import MerchantProfile
from app.db.models.promotion import Promotion
from app.db.models.user import User, UserRole


def _admin_headers(client: TestClient, db_session: Session) -> dict:
    admin = User(
        name="Report Admin",
        email="reports.admin@example.com",
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
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_admin_reports_dashboard(client: TestClient, db_session: Session):
    headers = _admin_headers(client, db_session)
    owner = User(
        name="Shop Owner",
        email="shop.owner@example.com",
        password_hash=hash_password("Password123!"),
        role=UserRole.MERCHANT,
        is_active=True,
        is_verified=True,
    )
    customer = User(
        name="App Customer",
        email="app.user@logo.customer",
        password_hash=hash_password("Password123!"),
        role=UserRole.FIELD_STAFF,
        district="Kannur",
        module_access=[],
        is_active=True,
        is_verified=True,
    )
    db_session.add_all([owner, customer])
    db_session.commit()

    paid = MerchantProfile(
        user_id=owner.id,
        business_name="Paid Mart",
        category="Retail, Supermarkets & Groceries",
        district="Kannur",
        approval_status="APPROVED",
        status="APPROVED",
        is_verified=True,
        has_active_subscription=True,
        whatsapp="919999999999",
        created_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
    )
    free = MerchantProfile(
        user_id=owner.id,
        business_name="Free Mart",
        category="Hotels, Restaurants & Dining",
        district="Thrissur",
        approval_status="PENDING",
        status="PENDING",
        created_at=datetime(2026, 1, 4, tzinfo=timezone.utc),
    )
    db_session.add_all([paid, free])
    db_session.add(
        Promotion(
            title="Deal",
            impressions=120,
            clicks=15,
            created_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        )
    )
    db_session.commit()

    res = client.get("/api/v1/admin/reports", headers=headers, params={"year": 2026})
    assert res.status_code == 200
    body = res.json()
    additions = body["cards"]["merchant_additions"]
    assert additions["total"] == 2
    assert additions["paid"] == 1
    assert additions["free"] == 1
    assert body["cards"]["active_customers"] == 1
    assert body["cards"]["customer_leads_and_calls"] == 15
    july = next(point for point in body["monthly_trend"] if point["label"] == "Jul")
    assert july["paid"] == 1
    assert july["cumulative"] == 2
    districts = {row["district"]: row["merchants"] for row in body["districts"]}
    assert districts["Kannur"] == 1
    assert districts["Thrissur"] == 1
    assert body["sectors"][0]["shops"] == 1
    assert body["cards"]["verification"]["approved"] == 1

    export = client.get("/api/v1/admin/reports/export", headers=headers, params={"year": 2026})
    assert export.status_code == 200
    assert "text/csv" in export.headers["content-type"]
    assert "merchant_additions" in export.text

    forbidden = client.get("/api/v1/admin/reports")
    assert forbidden.status_code == 401
