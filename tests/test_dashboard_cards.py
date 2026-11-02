from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models.merchant import MerchantProfile
from app.db.models.subscription import (
    SubscriptionAudience,
    SubscriptionBillingPeriod,
    SubscriptionPackage,
    UserSubscription,
    UserSubscriptionStatus,
)
from app.db.models.user import User, UserRole


def test_dashboard_cards(client: TestClient, db_session: Session):
    admin = User(
        name="Cards Admin",
        email="cards.admin@example.com",
        password_hash=hash_password("AdminPass123!"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    owner = User(
        name="Shop Owner",
        email="cards.owner@example.com",
        password_hash=hash_password("OwnerPass123!"),
        role=UserRole.MERCHANT,
        is_active=True,
    )
    db_session.add(admin)
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(admin)
    db_session.refresh(owner)

    db_session.add(
        MerchantProfile(
            user_id=owner.id,
            business_name="Card Shop",
            approval_status="APPROVED",
            status="APPROVED",
            is_active=True,
            password_hash=owner.password_hash,
        )
    )
    package = SubscriptionPackage(
        code="CARD_PLAN",
        name="Card Plan",
        audience=SubscriptionAudience.USER,
        price=Decimal("500.00"),
        billing_period=SubscriptionBillingPeriod.MONTHLY,
        duration_days=30,
    )
    db_session.add(package)
    db_session.commit()
    db_session.refresh(package)
    db_session.add(
        UserSubscription(
            user_id=admin.id,
            package_id=package.id,
            status=UserSubscriptionStatus.ACTIVE,
            amount_paid=Decimal("500.00"),
            started_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "cards.admin@example.com", "password": "AdminPass123!"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    search = client.get("/api/v1/merchants/search", params={"q": "salon"})
    assert search.status_code == 200
    client.get("/api/v1/merchants/search/location", params={"location": "Kochi"})

    denied = client.get("/api/v1/admin/dashboard/cards")
    assert denied.status_code == 401

    res = client.get("/api/v1/admin/dashboard/cards", headers=headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["total_users"]["value"] >= 1
    assert data["total_merchants"]["value"] == 1
    assert data["total_searches"]["value"] == 2
    assert Decimal(str(data["revenue"]["value"])) == Decimal("500.00")
    assert data["revenue"]["currency"] == "INR"
    assert data["total_users"]["change_percent"] == 100.0
    assert data["total_searches"]["change_percent"] == 100.0
    assert data["revenue"]["change_percent"] == 100.0
