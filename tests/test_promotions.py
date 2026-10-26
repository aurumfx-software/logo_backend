from fastapi.testclient import TestClient

from app.db.models.promotion import Promotion
from app.db.models.product import CustomerProduct
from app.db.models.user import User
from app.core.security import hash_password


def test_list_promotions_active(client: TestClient, db_session):
    active = Promotion(
        title="Weekend Sale",
        description="20% off",
        status="active",
        placement="Home Top",
    )
    inactive = Promotion(
        title="Old Promo",
        status="inactive",
    )
    db_session.add_all([active, inactive])
    db_session.commit()

    res = client.get("/api/v1/promotions?status=active")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert len(body["data"]) == 1
    assert body["data"][0]["title"] == "Weekend Sale"


def test_list_products_public(client: TestClient, db_session):
    seller = User(
        name="Seller",
        email="seller@example.com",
        password_hash=hash_password("Pass12345!"),
        is_active=True,
    )
    db_session.add(seller)
    db_session.commit()
    db_session.refresh(seller)

    db_session.add(
        CustomerProduct(
            seller_id=seller.id,
            name="Handmade Bag",
            price=499,
            category="Fashion",
            approval_status="APPROVED",
            is_active=True,
        )
    )
    db_session.commit()

    res = client.get("/api/v1/products?limit=16")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["name"] == "Handmade Bag"
