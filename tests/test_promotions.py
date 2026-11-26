from fastapi.testclient import TestClient

from app.db.models.promotion import Promotion
from app.db.models.product import CustomerProduct
from app.db.models.user import User
from app.core.security import hash_password


def test_promotion_option_types_api(client: TestClient):
    for path in ("/api/v1/promotions/option-types", "/api/v1/promotions/types", "/api/v1/promotions/options"):
        res = client.get(path)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["success"] is True
        data = body["data"]
        assert "Featured" in data["types"]
        assert data["option_types"] == data["types"]
        assert "Home Top" in data["placements"]
        assert "image" in data["media_types"]


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
    assert data[0]["rating_count"] == 0

    from types import SimpleNamespace
    from app.schemas.product import ProductResponse

    legacy = ProductResponse.model_validate(
        SimpleNamespace(
            id=1,
            seller_id=1,
            name="Old listing",
            category="General",
            price=10,
            stock_status="IN_STOCK",
            is_active=True,
            approval_status="APPROVED",
            views_count=None,
            orders_count=None,
            rating_count=None,
            images=[],
            sizes=[],
        )
    )
    assert legacy.rating_count == 0
    assert legacy.rating_average == 0


def test_merchant_store_ad_requires_999_subscription_and_saves_formats(client: TestClient, db_session, monkeypatch):
    import hashlib
    import hmac
    from app.core.config import settings
    from app.db.models.merchant import MerchantProfile
    from app.db.models.user import UserRole
    from app.services.razorpay_service import RazorpayService

    merch_user = User(
        name="Ad Shop Owner",
        email="adowner@example.com",
        password_hash=hash_password("Pass12345!"),
        role=UserRole.MERCHANT,
        is_active=True,
        is_verified=True,
    )
    db_session.add(merch_user)
    db_session.commit()
    db_session.refresh(merch_user)

    shop = MerchantProfile(
        user_id=merch_user.id,
        business_name="Ad Store Kerala",
        email=merch_user.email,
        approval_status="APPROVED",
        status="APPROVED",
        is_active=True,
        has_active_subscription=False,
    )
    db_session.add(shop)
    db_session.commit()
    db_session.refresh(shop)

    login_res = client.post("/api/v1/auth/login", json={"email": merch_user.email, "password": "Pass12345!"})
    assert login_res.status_code == 200
    headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    # Blocked before ₹999 subscription
    blocked_res = client.post(
        "/api/v1/promotions",
        headers=headers,
        json={
            "title": "Blocked Text Ad",
            "media_type": "text",
            "bg_color": "#1d4ed8",
            "text_color": "#ffffff",
            "placement": "Merchant Store",
            "merchant_id": shop.id,
        },
    )
    assert blocked_res.status_code == 403

    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_test_unit")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "unit_test_secret_key")
    monkeypatch.setattr(
        RazorpayService,
        "create_order",
        staticmethod(
            lambda *, amount_paise, receipt, notes=None, currency="INR": {
                "id": "order_unit_999",
                "amount": amount_paise,
                "currency": currency,
                "receipt": receipt,
                "status": "created",
            }
        ),
    )

    # Subscribe to MERCHANT_PROMO_BASIC (₹999) via Razorpay order + HMAC signature verification
    order_res = client.post(
        "/api/v1/subscriptions/razorpay/order",
        headers=headers,
        json={"package_code": "MERCHANT_PROMO_BASIC", "merchant_profile_id": shop.id},
    )
    assert order_res.status_code == 201, order_res.text
    order_data = order_res.json()
    assert float(order_data["amount"]) == 999.0
    assert order_data["razorpay_order_id"] == "order_unit_999"

    pay_id = "pay_unit_999_ok"
    sig = hmac.new(
        b"unit_test_secret_key",
        f"{order_data['razorpay_order_id']}|{pay_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    verify_res = client.post(
        "/api/v1/subscriptions/razorpay/verify",
        headers=headers,
        json={
            "package_id": order_data["package_id"],
            "merchant_profile_id": shop.id,
            "razorpay_order_id": order_data["razorpay_order_id"],
            "razorpay_payment_id": pay_id,
            "razorpay_signature": sig,
        },
    )
    assert verify_res.status_code == 200, verify_res.text

    # Now Text-with-bg, Image & Video store ads succeed and save immediately
    created = client.post(
        "/api/v1/promotions",
        headers=headers,
        json={
            "title": "Flat 30% Off Opening Offer",
            "description": "Valid all weekend",
            "media_type": "text",
            "bg_color": "linear-gradient(135deg, #1d4ed8 0%, #6d28d9 100%)",
            "text_color": "#ffffff",
            "placement": "Merchant Store",
            "merchant_id": shop.id,
        },
    )
    assert created.status_code == 201, created.text
    ad = created.json()["data"]
    assert ad["media_type"] == "text"
    assert ad["bg_color"] == "linear-gradient(135deg, #1d4ed8 0%, #6d28d9 100%)"
    assert ad["text_color"] == "#ffffff"
    assert ad["status"] == "active"

    created_img = client.post(
        "/api/v1/promotions",
        headers=headers,
        json={
            "title": "Festive Banner",
            "media_type": "image",
            "image_url": "/static/merchants/photos/test.jpg",
            "placement": "Merchant Store",
            "merchant_id": shop.id,
        },
    )
    assert created_img.status_code == 201, created_img.text

    created_vid = client.post(
        "/api/v1/promotions",
        headers=headers,
        json={
            "title": "Store Tour Video",
            "media_type": "video",
            "video_url": "/static/merchants/videos/test.mp4",
            "placement": "Merchant Store",
            "merchant_id": shop.id,
        },
    )
    assert created_vid.status_code == 201, created_vid.text

    store_ads = client.get(f"/api/v1/promotions/merchant/{shop.id}?status=active&placement=Merchant Store")
    assert store_ads.status_code == 200
    assert len(store_ads.json()["data"]) == 3

    # Home hero endpoint must NOT leak store-specific ads
    home_ads = client.get("/api/v1/promotions/active")
    assert home_ads.status_code == 200
    assert all(p["placement"] != "Merchant Store" for p in home_ads.json()["data"])

    # Owner merchant can pause/update & delete
    upd = client.put(f"/api/v1/promotions/{ad['id']}", headers=headers, json={"status": "inactive"})
    assert upd.status_code == 200
    assert upd.json()["data"]["status"] == "inactive"

    dele = client.delete(f"/api/v1/promotions/{ad['id']}", headers=headers)
    assert dele.status_code == 200


def test_slider_speed_per_ad_type_persistence(client: TestClient, db_session):
    from app.db.models.user import UserRole

    admin = User(
        name="Speed Admin",
        email="speedadmin@example.com",
        password_hash=hash_password("Pass12345!"),
        role=UserRole.SUPER_ADMIN,
        is_active=True,
        is_verified=True,
    )
    db_session.add(admin)
    db_session.commit()

    login_res = client.post("/api/v1/auth/login", json={"email": admin.email, "password": "Pass12345!"})
    assert login_res.status_code == 200
    headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    default_res = client.get("/api/v1/promotions/settings/slider")
    assert default_res.status_code == 200
    d_data = default_res.json()["data"]
    assert d_data["interval_seconds"] == 4
    assert d_data["per_type_seconds"]["home_top"] == 4
    assert d_data["per_type_seconds"]["merchant_store"] == 4

    # Set per-type speeds independently without overwriting others
    upd1 = client.put(
        "/api/v1/promotions/settings/slider",
        headers=headers,
        json={"home_top_seconds": 6, "merchant_store_seconds": 3},
    )
    assert upd1.status_code == 200
    u1 = upd1.json()["data"]
    assert u1["home_top_seconds"] == 6
    assert u1["merchant_store_seconds"] == 3
    assert u1["per_type_seconds"]["home_top"] == 6
    assert u1["per_type_seconds"]["merchant_store"] == 3

    upd2 = client.put(
        "/api/v1/promotions/settings/slider",
        headers=headers,
        json={"home_middle_seconds": 8},
    )
    assert upd2.status_code == 200
    u2 = upd2.json()["data"]
    assert u2["home_middle_seconds"] == 8
    # Previously set per-type speeds stay preserved
    assert u2["home_top_seconds"] == 6
    assert u2["merchant_store_seconds"] == 3

    fetched = client.get("/api/v1/promotions/settings/slider").json()["data"]
    assert fetched["per_type_seconds"]["home_top"] == 6
    assert fetched["per_type_seconds"]["home_middle"] == 8
    assert fetched["per_type_seconds"]["merchant_store"] == 3
