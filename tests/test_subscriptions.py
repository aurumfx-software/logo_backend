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
    assert summary["cashback_on_sales"] is True
    assert summary["is_subscriber"] is True
    assert summary["subscription_plan"] == "499_SELLER"
    assert float(seller["price"]) == 499.0


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


def test_merchant_business_tab_finds_shop_by_phone(client: TestClient, db_session: Session):
    """Mobile login user and the shop owner can be different rows with the same phone."""
    from app.core.security import hash_password
    from app.db.models.merchant import MerchantProfile

    owner = User(
        name="Shop Owner",
        email="owner.shop@merchant.local",
        phone="+91 98765 43210",
        password_hash=hash_password("Password123!"),
        role=UserRole.MERCHANT,
        is_active=True,
        is_verified=True,
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)
    shop = MerchantProfile(
        user_id=owner.id,
        business_name="Logo Mart",
        phone="+91-9876543210",
        contact_number="9876543210",
        approval_status="APPROVED",
        status="APPROVED",
        is_active=True,
    )
    db_session.add(shop)
    db_session.commit()

    app_user = _create_user(db_session, "app.user@logo.customer")
    app_user.phone = "9876543210"
    db_session.commit()
    headers = _auth_headers(client, app_user.email)

    active = client.get("/api/v1/subscriptions/me/active", headers=headers)
    assert active.status_code == 200
    assert active.json()["data"]["merchant_profile_id"] == shop.id
    assert active.json()["data"]["merchant_business_name"] == "Logo Mart"

    me = client.get("/api/v1/merchants/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["business_name"] == "Logo Mart"

    packages = client.get("/api/v1/subscriptions/packages?audience=MERCHANT").json()["data"]
    promo = next(p for p in packages if p["code"] == "MERCHANT_PROMO_BASIC")
    sub_res = client.post(
        "/api/v1/subscriptions/subscribe",
        headers=headers,
        json={"package_id": promo["id"], "merchant_profile_id": app_user.id},
    )
    assert sub_res.status_code == 201
    assert sub_res.json()["data"]["merchant_profile_id"] == shop.id


def test_merchant_seller_500_plan_unlocks_products(client: TestClient, db_session: Session):
    """Merchant ₹999 promo plan must NOT unlock product selling; USER_SELLER_500 unlocks it."""
    from app.db.models.merchant import MerchantProfile

    merch_user = _create_user(db_session, "merch.seller500@example.com", UserRole.MERCHANT)
    shop = MerchantProfile(
        user_id=merch_user.id,
        business_name="Merchant Seller Shop",
        contact_number="9876511122",
        district="Ernakulam",
        city="Kochi",
        approval_status="APPROVED",
        status="APPROVED",
        is_active=True,
    )
    db_session.add(shop)
    db_session.commit()
    db_session.refresh(shop)

    headers = _auth_headers(client, merch_user.email)

    # 1. Subscribe ONLY to ₹999 Merchant Promo plan -> can_sell_products remains False
    m_pkgs = client.get("/api/v1/subscriptions/packages?audience=MERCHANT").json()["data"]
    promo_pkg = next(p for p in m_pkgs if p["code"] == "MERCHANT_PROMO_BASIC")
    promo_res = client.post(
        "/api/v1/subscriptions/subscribe",
        headers=headers,
        json={"package_id": promo_pkg["id"], "merchant_profile_id": shop.id, "payment_reference": "PROMO-999"},
    )
    assert promo_res.status_code == 201

    active_before = client.get("/api/v1/subscriptions/me/active", headers=headers).json()["data"]
    assert active_before["merchant_has_active_subscription"] is True
    assert active_before["can_sell_products"] is False
    assert active_before["user_subscriptions"] == []

    # 2. Subscribe to same ₹500 Seller Plan (USER_SELLER_500) -> unlocks product selling
    u_pkgs = client.get("/api/v1/subscriptions/packages?audience=USER").json()["data"]
    seller_pkg = next(p for p in u_pkgs if p["code"] == "USER_SELLER_500")
    seller_res = client.post(
        "/api/v1/subscriptions/subscribe",
        headers=headers,
        json={"package_id": seller_pkg["id"], "payment_reference": "SELLER-500"},
    )
    assert seller_res.status_code == 201

    active_after = client.get("/api/v1/subscriptions/me/active", headers=headers).json()["data"]
    assert active_after["can_sell_products"] is True
    assert active_after["is_subscriber"] is True
    assert active_after["subscription_plan"] == "499_SELLER"
    assert len(active_after["user_subscriptions"]) >= 1

    # 3. Merchant can create, list, and manage orders on their products
    created = client.post(
        "/api/v1/customer/products",
        headers=headers,
        json={
            "name": "Merchant Gold Kasavu Saree",
            "category": "Kerala Kasavu Sarees",
            "price": 1499,
            "stock_quantity": 8,
            "sizes": ["Free Size"],
        },
    )
    assert created.status_code == 201, created.text
    my_prods = client.get("/api/v1/customer/products/my-products", headers=headers)
    assert my_prods.status_code == 200
    assert any(p["name"] == "Merchant Gold Kasavu Saree" for p in my_prods.json())
    my_orders = client.get("/api/v1/customer/products/my-orders", headers=headers)
    assert my_orders.status_code == 200


def test_catalog_has_customer_and_merchant_plans(client: TestClient):
    users = client.get("/api/v1/subscriptions/packages?audience=USER").json()["data"]
    merchants = client.get("/api/v1/subscriptions/packages?audience=MERCHANT").json()["data"]
    assert {p["code"] for p in users} >= {"USER_FREE", "USER_SELLER_500"}
    assert {p["code"] for p in merchants} >= {
        "MERCHANT_PROMO_BASIC",
        "MERCHANT_PREMIUM",
        "MERCHANT_SELL_2999",
        "MERCHANT_DETAIL_3999",
        "MERCHANT_LANDING_4999",
    }
    by_code = {p["code"]: p for p in merchants}
    assert by_code["MERCHANT_PROMO_BASIC"]["access"]["can_add_photos"] is True
    assert by_code["MERCHANT_PROMO_BASIC"]["access"]["can_add_videos"] is False
    assert by_code["MERCHANT_PREMIUM"]["access"]["can_add_videos"] is True
    assert by_code["MERCHANT_SELL_2999"]["access"]["can_sell_products"] is True
    assert by_code["MERCHANT_DETAIL_3999"]["access"]["can_add_detail_page_ad"] is True
    assert by_code["MERCHANT_LANDING_4999"]["access"]["can_promote_landing"] is True
    free = next(p for p in users if p["code"] == "USER_FREE")
    seller = next(p for p in users if p["code"] == "USER_SELLER_500")
    assert float(free["price"]) == 0.0
    assert seller["access"]["cashback_on_sales"] is True


def test_admin_checkbox_removes_selling_access(client: TestClient, db_session: Session):
    user = _create_user(db_session, "checkbox.user@example.com")
    headers = _auth_headers(client, user.email)
    admin = _create_user(db_session, "checkbox.admin@example.com", UserRole.ADMIN)
    admin_headers = _auth_headers(client, admin.email)

    seller = next(
        p
        for p in client.get("/api/v1/subscriptions/packages?audience=USER").json()["data"]
        if p["code"] == "USER_SELLER_500"
    )
    sub = client.post(
        "/api/v1/subscriptions/subscribe",
        headers=headers,
        json={"package_id": seller["id"], "payment_reference": "CHECKBOX"},
    )
    assert sub.status_code == 201

    options = client.get("/api/v1/subscriptions/admin/access-options", headers=admin_headers)
    assert options.status_code == 200
    assert "can_sell_products" in {item["key"] for item in options.json()["data"]["USER"]}

    updated = client.patch(
        f"/api/v1/subscriptions/admin/packages/{seller['id']}",
        headers=admin_headers,
        json={"access": {"can_sell_products": False, "cashback_on_sales": False}},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["access"]["can_sell_products"] is False

    active = client.get("/api/v1/subscriptions/me/active", headers=headers).json()["data"]
    assert active["can_sell_products"] is False
    assert active["cashback_on_sales"] is False


def test_landing_promotion_needs_4999_and_admin_approval(client: TestClient, db_session: Session):
    from app.db.models.merchant import MerchantProfile

    merchant_user = _create_user(db_session, "landing.merchant@example.com", UserRole.MERCHANT)
    shop = MerchantProfile(
        user_id=merchant_user.id,
        business_name="Landing Shop",
        approval_status="APPROVED",
        status="APPROVED",
        is_active=True,
    )
    db_session.add(shop)
    db_session.commit()
    db_session.refresh(shop)
    headers = _auth_headers(client, merchant_user.email)

    detail = next(
        p
        for p in client.get("/api/v1/subscriptions/packages?audience=MERCHANT").json()["data"]
        if p["code"] == "MERCHANT_DETAIL_3999"
    )
    client.post(
        "/api/v1/subscriptions/subscribe",
        headers=headers,
        json={"package_id": detail["id"], "merchant_profile_id": shop.id, "payment_reference": "D3999"},
    )
    blocked = client.post(
        "/api/v1/promotions",
        headers=headers,
        json={"title": "Home Feature", "placement": "Home Top", "merchant_id": shop.id},
    )
    assert blocked.status_code == 403

    landing = next(
        p
        for p in client.get("/api/v1/subscriptions/packages?audience=MERCHANT").json()["data"]
        if p["code"] == "MERCHANT_LANDING_4999"
    )
    subscribed = client.post(
        "/api/v1/subscriptions/subscribe",
        headers=headers,
        json={"package_id": landing["id"], "merchant_profile_id": shop.id, "payment_reference": "L4999"},
    )
    assert subscribed.status_code == 201
    created = client.post(
        "/api/v1/promotions",
        headers=headers,
        json={"title": "Landing Feature", "placement": "Home Top", "merchant_id": shop.id, "status": "active"},
    )
    assert created.status_code == 201, created.text
    promo = created.json()["data"]
    assert promo["status"] == "pending"

    public = client.get("/api/v1/promotions/active")
    assert all(item["id"] != promo["id"] for item in public.json()["data"])

    admin = _create_user(db_session, "landing.admin@example.com", UserRole.ADMIN)
    admin_headers = _auth_headers(client, admin.email)
    approved = client.post(f"/api/v1/promotions/{promo['id']}/approve", headers=admin_headers)
    assert approved.status_code == 200, approved.text
    public_after = client.get("/api/v1/promotions/active")
    assert any(item["id"] == promo["id"] for item in public_after.json()["data"])


def test_granular_merchant_subscription_permissions_and_duplication(client: TestClient, db_session: Session):
    from app.db.models.merchant import MerchantProfile

    admin = _create_user(db_session, "perm.admin@example.com", UserRole.ADMIN)
    admin_headers = _auth_headers(client, admin.email)

    merch_user = _create_user(db_session, "perm.merchant@example.com", UserRole.MERCHANT)
    shop = MerchantProfile(
        user_id=merch_user.id,
        business_name="Granular Permissions Shop",
        approval_status="APPROVED",
        status="APPROVED",
        is_active=True,
    )
    db_session.add(shop)
    db_session.commit()
    db_session.refresh(shop)
    merch_headers = _auth_headers(client, merch_user.email)

    # Unsubscribed merchant can still update timing/name, but cannot add photos, video, or ads
    ok_timing = client.put(
        "/api/v1/merchants/me",
        headers=merch_headers,
        json={"service_timing": "9 AM - 9 PM"},
    )
    assert ok_timing.status_code == 200

    blocked_photo = client.put(
        "/api/v1/merchants/me",
        headers=merch_headers,
        json={"photo_1": "/static/merchants/photos/test_lock.jpg", "merchant_photos": ["/static/merchants/photos/test_lock.jpg"]},
    )
    assert blocked_photo.status_code == 403

    blocked_video = client.put(
        "/api/v1/merchants/me",
        headers=merch_headers,
        json={"video_url": "/static/merchants/videos/test_lock.mp4"},
    )
    assert blocked_video.status_code == 403

    # Admin creates a Photo + Store Image Ad plan ONLY (no video, no hero, no product section)
    create_pkg = client.post(
        "/api/v1/subscriptions/admin/packages",
        headers=admin_headers,
        json={
            "code": "MERCH_STARTER_PHOTO_AD",
            "name": "Photo & Store Ad Plan",
            "description": "Only store photos and image ads",
            "audience": "MERCHANT",
            "price": 499,
            "billing_period": "MONTHLY",
            "duration_days": 30,
            "grants": {
                "_granular": True,
                "merchant_profile_photos": True,
                "merchant_profile_video": False,
                "merchant_store_ad": True,
                "merchant_store_video_ad": False,
                "merchant_product_section": False,
                "ad_home_top": False,
            },
        },
    )
    assert create_pkg.status_code == 201, create_pkg.text
    starter_pkg = create_pkg.json()["data"]
    assert "Store Profile Photos" in starter_pkg["features"]
    assert "Store Page Ads (Image & Text)" in starter_pkg["features"]

    # Duplicate the form plan into a full-access duplicate and customize price & ticks
    dup_res = client.post(
        f"/api/v1/subscriptions/admin/packages/{starter_pkg['id']}/duplicate",
        headers=admin_headers,
    )
    assert dup_res.status_code == 201, dup_res.text
    dup_pkg = dup_res.json()["data"]
    assert dup_pkg["code"].startswith("MERCH_STARTER_PHOTO_AD_COPY")
    assert "(Copy)" in dup_pkg["name"]
    assert dup_pkg["grants"]["merchant_profile_photos"] is True

    # Merchant subscribes ONLY to starter_pkg
    sub_res = client.post(
        "/api/v1/subscriptions/subscribe",
        headers=merch_headers,
        json={"package_id": starter_pkg["id"], "merchant_profile_id": shop.id, "payment_reference": "GRAN-499"},
    )
    assert sub_res.status_code == 201

    active = client.get("/api/v1/subscriptions/me/active", headers=merch_headers).json()["data"]
    assert active["merchant_grants"]["merchant_profile_photos"] is True
    assert active["merchant_grants"]["merchant_store_ad"] is True
    assert active["merchant_grants"]["merchant_profile_video"] is False
    assert active["merchant_grants"]["merchant_store_video_ad"] is False
    assert active["merchant_grants"]["ad_home_top"] is False
    assert active["can_sell_products"] is False

    # Photo update now succeeds, video still blocked
    ok_photo = client.put(
        "/api/v1/merchants/me",
        headers=merch_headers,
        json={"photo_1": "/static/merchants/photos/allowed.jpg", "merchant_photos": ["/static/merchants/photos/allowed.jpg"]},
    )
    assert ok_photo.status_code == 200
    assert ok_photo.json()["merchant_grants"]["merchant_profile_photos"] is True

    still_blocked_video = client.put(
        "/api/v1/merchants/me",
        headers=merch_headers,
        json={"video_url": "/static/merchants/videos/blocked.mp4"},
    )
    assert still_blocked_video.status_code == 403

    # Store Image ad allowed; Store Video ad & Home Top ad blocked!
    ok_store_img = client.post(
        "/api/v1/promotions",
        headers=merch_headers,
        json={
            "title": "Store Image Promo",
            "media_type": "image",
            "image_url": "/static/merchants/photos/allowed.jpg",
            "placement": "Merchant Store",
            "merchant_id": shop.id,
        },
    )
    assert ok_store_img.status_code == 201, ok_store_img.text

    blocked_store_video = client.post(
        "/api/v1/promotions",
        headers=merch_headers,
        json={
            "title": "Blocked Store Video",
            "media_type": "video",
            "video_url": "/static/merchants/videos/blocked.mp4",
            "placement": "Merchant Store",
            "merchant_id": shop.id,
        },
    )
    assert blocked_store_video.status_code == 403

    blocked_hero = client.post(
        "/api/v1/promotions",
        headers=merch_headers,
        json={
            "title": "Blocked Hero Ad",
            "media_type": "image",
            "image_url": "/static/merchants/photos/allowed.jpg",
            "placement": "Home Top",
            "merchant_id": shop.id,
        },
    )
    assert blocked_hero.status_code == 403

    # Admin updates starter_pkg to tick video, hero banner & product selling -> syncs live subscriber!
    upd_pkg = client.patch(
        f"/api/v1/subscriptions/admin/packages/{starter_pkg['id']}",
        headers=admin_headers,
        json={
            "price": 1499,
            "grants": {
                "_granular": True,
                "merchant_profile_photos": True,
                "merchant_profile_video": True,
                "merchant_store_ad": True,
                "merchant_store_video_ad": True,
                "merchant_product_section": True,
                "ad_home_top": True,
            },
        },
    )
    assert upd_pkg.status_code == 200

    active2 = client.get("/api/v1/subscriptions/me/active", headers=merch_headers).json()["data"]
    assert active2["can_sell_products"] is True
    assert active2["merchant_grants"]["merchant_profile_video"] is True
    assert active2["merchant_grants"]["merchant_store_video_ad"] is True
    assert active2["merchant_grants"]["ad_home_top"] is True

    assert client.put(
        "/api/v1/merchants/me",
        headers=merch_headers,
        json={"video_url": "/static/merchants/videos/now_allowed.mp4"},
    ).status_code == 200
    assert client.post(
        "/api/v1/promotions",
        headers=merch_headers,
        json={
            "title": "Now Allowed Video Ad",
            "media_type": "video",
            "video_url": "/static/merchants/videos/now_allowed.mp4",
            "placement": "Merchant Store",
            "merchant_id": shop.id,
        },
    ).status_code == 201
    assert client.post(
        "/api/v1/promotions",
        headers=merch_headers,
        json={
            "title": "Now Allowed Hero Ad",
            "media_type": "image",
            "image_url": "/static/merchants/photos/allowed.jpg",
            "placement": "Home Top",
            "merchant_id": shop.id,
        },
    ).status_code == 201
