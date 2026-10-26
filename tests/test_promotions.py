from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.db.models.promotion import Promotion


def test_list_promotions_active(client: TestClient, db_session):
    now = datetime.now(timezone.utc)
    active = Promotion(
        title="Weekend Sale",
        description="20% off",
        discount_label="20% OFF",
        status="ACTIVE",
        is_active=True,
        start_at=now - timedelta(days=1),
        end_at=now + timedelta(days=7),
        priority=10,
    )
    inactive = Promotion(
        title="Old Promo",
        status="INACTIVE",
        is_active=False,
    )
    db_session.add_all([active, inactive])
    db_session.commit()

    res = client.get("/api/v1/promotions?status=active")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["title"] == "Weekend Sale"


def test_list_promotions_without_status_returns_active_window(client: TestClient, db_session):
    now = datetime.now(timezone.utc)
    db_session.add(
        Promotion(
            title="Live",
            status="ACTIVE",
            is_active=True,
            end_at=now + timedelta(days=1),
        )
    )
    db_session.add(
        Promotion(
            title="Expired",
            status="ACTIVE",
            is_active=True,
            end_at=now - timedelta(days=1),
        )
    )
    db_session.commit()

    res = client.get("/api/v1/promotions")
    assert res.status_code == 200
    titles = [p["title"] for p in res.json()["items"]]
    assert "Live" in titles
    assert "Expired" not in titles
