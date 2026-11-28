from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import merchant_reg_payment_payload


def test_merchant_registration_success(client: TestClient):
    payload = {
        "name": "Rajesh Merchant",
        "email": "rajesh.merchant@example.com",
        "password": "MerchantPassword123",
        "business_name": "Royal Unisex Salon & Spa",
        "categories": ["Salon", "Spa", "Beauty"],
        "location": "Edappally, Kochi",
        "services": ["Haircut", "Hair Spa", "Facial"],
        "service_timing": "Mon-Sun: 09:00 AM - 09:00 PM",
        "merchant_photos": [
            "https://example.com/photos/front.jpg",
            "https://example.com/photos/inside.jpg",
        ],
        "contact_number": "9876543999",
        "address": "Door No 14/204, Toll Junction, Edappally, Kochi - 682024",
        **merchant_reg_payment_payload(client),
    }
    response = client.post("/api/v1/merchants/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["message"] == "Merchant registered successfully"
    assert data["user"]["email"] == "rajesh.merchant@example.com"
    assert data["user"]["role"] == "MERCHANT"
    assert data["merchant"]["user_id"] == data["user"]["id"]
    assert data["user"]["phone"] == "9876543999"
    assert data["user"]["address"] == "Door No 14/204, Toll Junction, Edappally, Kochi - 682024"

    assert data["merchant"]["business_name"] == "Royal Unisex Salon & Spa"
    assert "Salon" in data["merchant"]["categories"]
    assert "Haircut" in data["merchant"]["services"]
    assert data["merchant"]["service_timing"] == "Mon-Sun: 09:00 AM - 09:00 PM"
    assert len(data["merchant"]["merchant_photos"]) == 2


def test_merchant_login_and_get_profile(client: TestClient):
    reg_payload = {
        "name": "Anil Cafe",
        "email": "anil.cafe@example.com",
        "password": "CafePassword123",
        "business_name": "Anil Coffee House",
        "categories": ["Cafe", "Bakery"],
        "location": "Panampilly Nagar, Kochi",
        "services": ["Espresso", "Pastries", "Snacks"],
        "service_timing": "08:00 AM - 10:00 PM",
        "merchant_photos": [],
        "contact_number": "9876543888",
        "address": "Main Avenue, Panampilly Nagar, Kochi",
        **merchant_reg_payment_payload(client),
    }
    client.post("/api/v1/merchants/register", json=reg_payload)

    # Login as merchant
    login_res = client.post("/api/v1/auth/login", json={
        "email": "anil.cafe@example.com",
        "password": "CafePassword123",
    })
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]

    # Get merchant profile via /api/v1/merchants/me
    profile_res = client.get(
        "/api/v1/merchants/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert profile_res.status_code == 200
    m_data = profile_res.json()
    assert m_data["business_name"] == "Anil Coffee House"
    assert m_data["location"] == "Panampilly Nagar, Kochi"


def test_merchant_me_returns_cashback_rates_from_table(client: TestClient, db_session: Session):
    from decimal import Decimal

    from app.db.models.merchant import MerchantProfile

    created = client.post(
        "/api/v1/merchants/register",
        json={
            "name": "Rate Shop",
            "email": "rates.shop@example.com",
            "password": "RatePassword123",
            "business_name": "Rate Shop",
            "categories": ["Salon"],
            "location": "Kochi",
            "services": ["Haircut"],
            "service_timing": "09:00 AM - 09:00 PM",
            "contact_number": "9876501122",
            "address": "MG Road, Kochi",
            **merchant_reg_payment_payload(client),
        },
    )
    assert created.status_code == 201
    merchant = (
        db_session.query(MerchantProfile)
        .filter(MerchantProfile.email == "rates.shop@example.com")
        .first()
    )
    merchant.cashback_percent = Decimal("5.00")
    merchant.company_fee_percent = Decimal("3.00")
    db_session.commit()

    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "rates.shop@example.com", "password": "RatePassword123"},
    )
    assert login_res.status_code == 200
    profile_res = client.get(
        "/api/v1/merchants/me",
        headers={"Authorization": f"Bearer {login_res.json()['access_token']}"},
    )
    assert profile_res.status_code == 200
    body = profile_res.json()
    assert body["cashback_percent"] == 5.0
    assert body["company_fee_percent"] == 3.0


def test_merchant_update_profile(client: TestClient):
    reg_payload = {
        "name": "Kumar Plumber",
        "email": "kumar.plumber@example.com",
        "password": "PlumberPass123",
        "business_name": "Kumar Plumbing Services",
        "categories": ["Home Services", "Plumbing"],
        "location": "Kaloor, Kochi",
        "services": ["Pipe repair", "Water heater installation"],
        "service_timing": "24/7 Emergency",
        "merchant_photos": [],
        "contact_number": "9876543777",
        "address": "Kaloor Stadium Link Road, Kochi",
        **merchant_reg_payment_payload(client),
    }
    client.post("/api/v1/merchants/register", json=reg_payload)

    login_res = client.post("/api/v1/auth/login", json={
        "email": "kumar.plumber@example.com",
        "password": "PlumberPass123",
    })
    token = login_res.json()["access_token"]

    # Update timing and business name
    update_res = client.put(
        "/api/v1/merchants/me",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "business_name": "Kumar 24/7 Super Plumbing",
            "service_timing": "06:00 AM - 11:00 PM",
        },
    )
    assert update_res.status_code == 200
    updated_data = update_res.json()
    assert updated_data["business_name"] == "Kumar 24/7 Super Plumbing"
    assert updated_data["service_timing"] == "06:00 AM - 11:00 PM"


def test_user_without_merchant_profile_gets_404_on_me(client: TestClient):
    # Register regular staff user
    client.post("/api/v1/auth/register", json={
        "name": "Normal Staff User",
        "email": "normal.staff@example.com",
        "password": "StaffPassword123",
    })
    login_res = client.post("/api/v1/auth/login", json={
        "email": "normal.staff@example.com",
        "password": "StaffPassword123",
    })
    token = login_res.json()["access_token"]

    # User without merchant profile accessing merchant/me -> 404 Not Found
    res = client.get("/api/v1/merchants/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 404


def test_list_and_filter_merchants(client: TestClient):
    res = client.get("/api/v1/merchants")
    assert res.status_code == 200
    assert isinstance(res.json(), list)

    res_limit = client.get("/api/v1/merchants?limit=500")
    assert res_limit.status_code == 200
    assert isinstance(res_limit.json(), list)


def test_list_merchants_by_category_column(client: TestClient, db_session):
    from app.db.models.merchant import MerchantProfile
    from app.db.models.user import User
    from app.core.security import hash_password

    user = User(
        name="Advocate Owner",
        email="advocate.shop@example.com",
        password_hash=hash_password("Pass12345!"),
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    merchant = MerchantProfile(
        user_id=user.id,
        business_name="Legal Aid Office",
        category="Advocates",
        categories=["Advocates"],
        location="Kochi",
        approval_status="APPROVED",
        status="APPROVED",
        is_active=True,
        is_verified=True,
    )
    db_session.add(merchant)
    db_session.commit()

    res = client.get("/api/v1/merchants?category=Advocates&limit=500")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 1
    assert any(m["business_name"] == "Legal Aid Office" for m in data)


def test_list_merchants_merges_linked_user(client: TestClient, db_session):
    from app.db.models.merchant import MerchantProfile
    from app.db.models.user import User
    from app.core.security import hash_password

    user = User(
        name="Shop Owner",
        email="owner@shop.example.com",
        phone="9876543210",
        password_hash=hash_password("Pass12345!"),
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    merchant = MerchantProfile(
        user_id=user.id,
        business_name="Merged Shop",
        categories=["Retail"],
        location="Kochi",
        approval_status="APPROVED",
        status="APPROVED",
        is_active=True,
        is_verified=True,
    )
    db_session.add(merchant)
    db_session.commit()

    res = client.get("/api/v1/merchants?limit=500")
    assert res.status_code == 200
    row = next(m for m in res.json() if m["business_name"] == "Merged Shop")
    assert row["user"]["email"] == "owner@shop.example.com"
    assert row["owner_name"] == "Shop Owner"
    assert row["contact_number"] == "9876543210"


def test_merchant_logout(client: TestClient):
    reg_payload = {
        "name": "Logout Merchant",
        "email": "logout.merchant@example.com",
        "password": "LogoutPass123",
        "business_name": "Logout Shop",
        "categories": ["Retail"],
        "location": "Kochi",
        "services": ["General"],
        "service_timing": "9-9",
        "merchant_photos": [],
        "contact_number": "9876500001",
        "address": "Kochi Kerala",
        **merchant_reg_payment_payload(client),
    }
    client.post("/api/v1/merchants/register", json=reg_payload)
    login_res = client.post(
        "/api/v1/merchants/login",
        json={"email": "logout.merchant@example.com", "password": "LogoutPass123"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    out = client.post("/api/v1/merchants/logout", headers=headers)
    assert out.status_code == 200
    assert out.json()["success"] is True
    assert "logged out" in out.json()["message"].lower()

    me = client.get("/api/v1/merchants/me", headers=headers)
    assert me.status_code == 401


def test_create_merchant_accepts_password_and_zero_commission(client: TestClient):
    created = client.post(
        "/api/v1/merchants",
        json={
            "business_name": "Zero Commission Shop",
            "owner_name": "Nila Menon",
            "phone_number": "9876504411",
            "email": "zero.shop@example.com",
            "password": "ZeroPass123",
            "district": "Ernakulam",
            "city": "Kochi",
            "location": "Edappally",
            "category": "Retail",
            "cashback_percent": 0,
            "company_fee_percent": 4,
            **merchant_reg_payment_payload(client),
        },
    )
    assert created.status_code == 201
    merchant = created.json()["merchant"]
    assert merchant["cashback_percent"] == 0
    assert merchant["company_fee_percent"] == 0
    assert merchant["has_password"] is True

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "zero.shop@example.com", "password": "ZeroPass123"},
    )
    assert login.status_code == 200

    updated = client.put(
        f"/api/v1/merchants/{merchant['id']}",
        json={"cashback_percent": 5, "company_fee_percent": 2},
    )
    assert updated.status_code == 200
    assert updated.json()["cashback_percent"] == 5
    assert updated.json()["company_fee_percent"] == 2

    cleared = client.put(
        f"/api/v1/merchants/{merchant['id']}",
        json={"company_fee_percent": 0},
    )
    assert cleared.status_code == 200
    assert cleared.json()["cashback_percent"] == 0
    assert cleared.json()["company_fee_percent"] == 0


def test_merchant_register_requires_1000_payment_and_grants_zero_features(client: TestClient):
    unpaid_reg = client.post(
        "/api/v1/merchants/register",
        json={
            "name": "Unpaid Merchant",
            "email": "unpaid.mreg@example.com",
            "password": "MerchantPassword123",
            "business_name": "Unpaid Shop",
            "categories": ["Retail"],
            "location": "Kochi",
            "services": ["Sales"],
            "service_timing": "9-9",
            "contact_number": "9876541111",
            "address": "Kochi",
        },
    )
    assert unpaid_reg.status_code == 402

    unpaid_onboard = client.post(
        "/api/v1/merchants/onboard",
        json={
            "business_name": "Unpaid Onboard Shop",
            "category": "Retail",
            "owner_name": "Owner",
            "phone_number": "9876541112",
            "address": "Kochi",
        },
    )
    assert unpaid_onboard.status_code == 402

    paid_reg = client.post(
        "/api/v1/merchants/register",
        json={
            "name": "Paid Merchant",
            "email": "paid.mreg@example.com",
            "password": "MerchantPassword123",
            "business_name": "Paid Shop",
            "categories": ["Retail"],
            "location": "Kochi",
            "services": ["Sales"],
            "service_timing": "9-9",
            "contact_number": "9876541113",
            "address": "Kochi",
            **merchant_reg_payment_payload(client),
        },
    )
    assert paid_reg.status_code == 201
    grants = paid_reg.json()["merchant"]["merchant_grants"]
    assert all(bool(grants.get(k)) is False for k in (
        "merchant_profile_photos",
        "merchant_profile_video",
        "merchant_store_ad",
        "merchant_store_video_ad",
        "merchant_product_section",
        "ad_home_top",
    ))


def test_old_merchant_stale_subscription_column_stays_locked(client: TestClient, db_session: Session):
    from app.core.security import hash_password
    from app.db.models.merchant import MerchantProfile
    from app.db.models.user import User, UserRole

    old_user = User(
        name="Legacy Merchant",
        email="legacy.locked@example.com",
        password_hash=hash_password("MerchantPass123!"),
        role=UserRole.MERCHANT,
        is_active=True,
    )
    db_session.add(old_user)
    db_session.commit()
    db_session.refresh(old_user)

    old_shop = MerchantProfile(
        user_id=old_user.id,
        business_name="Legacy Stale Flags Shop",
        email="legacy.locked@example.com",
        approval_status="APPROVED",
        status="APPROVED",
        has_active_subscription=True,
        can_create_promotions=True,
    )
    db_session.add(old_shop)
    db_session.commit()
    db_session.refresh(old_shop)

    token = client.post(
        "/api/v1/auth/login",
        json={"email": "legacy.locked@example.com", "password": "MerchantPass123!"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    sub_state = client.get(
        f"/api/v1/subscriptions/me/active?merchant_profile_id={old_shop.id}",
        headers=headers,
    )
    assert sub_state.status_code == 200
    body = sub_state.json()["data"]
    assert body["merchant_has_active_subscription"] is False
    assert body["merchant_grants"]["merchant_store_ad"] is False
    assert body["merchant_grants"]["ad_home_top"] is False

    promo_attempt = client.post(
        "/api/v1/promotions/",
        headers=headers,
        json={
            "title": "Should Stay Locked",
            "placement": "Merchant Store",
            "media_type": "image",
            "image_url": "https://example.com/ad.jpg",
            "merchant_id": old_shop.id,
        },
    )
    assert promo_attempt.status_code == 403


def test_merchant_platform_banner_requires_admin_approval_before_active(client: TestClient, db_session: Session):
    from app.core.security import hash_password
    from app.db.models.user import User, UserRole

    admin = User(
        name="Banner Admin",
        email="banner.admin@example.com",
        password_hash=hash_password("AdminPass123!"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()
    admin_token = client.post(
        "/api/v1/auth/login",
        json={"email": "banner.admin@example.com", "password": "AdminPass123!"},
    ).json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    created_m = client.post(
        "/api/v1/merchants/register",
        json={
            "name": "Banner Merchant",
            "email": "banner.merchant@example.com",
            "password": "MerchantPassword123",
            "business_name": "Banner World",
            "categories": ["Retail"],
            "location": "Kochi",
            "services": ["Sales"],
            "service_timing": "9-9",
            "contact_number": "9876542222",
            "address": "Kochi",
            **merchant_reg_payment_payload(client),
        },
    )
    assert created_m.status_code == 201
    merchant_id = created_m.json()["merchant"]["id"]

    m_token = client.post(
        "/api/v1/auth/login",
        json={"email": "banner.merchant@example.com", "password": "MerchantPassword123"},
    ).json()["access_token"]
    m_headers = {"Authorization": f"Bearer {m_token}"}

    packages = client.get("/api/v1/subscriptions/packages?audience=MERCHANT").json()["data"]
    landing_pkg = next(p for p in packages if p["code"] == "MERCHANT_LANDING_4999")
    sub_res = client.post(
        "/api/v1/subscriptions/subscribe",
        headers=m_headers,
        json={"package_id": landing_pkg["id"], "merchant_profile_id": merchant_id, "payment_reference": "LAND-4999"},
    )
    assert sub_res.status_code == 201

    created_promo = client.post(
        "/api/v1/promotions/",
        headers=m_headers,
        json={
            "title": "Hero Top Merchant Promo",
            "placement": "Home Top",
            "media_type": "image",
            "image_url": "https://example.com/hero.jpg",
            "merchant_id": merchant_id,
        },
    )
    assert created_promo.status_code in (200, 201), created_promo.text
    promo_data = created_promo.json()["data"]
    assert promo_data["status"] == "pending"

    active_before = client.get("/api/v1/promotions/active").json()["data"]
    assert not any(p["id"] == promo_data["id"] for p in active_before)

    approved = client.post(f"/api/v1/promotions/{promo_data['id']}/approve", headers=admin_headers)
    assert approved.status_code == 200
    assert approved.json()["data"]["status"].lower() in ("active", "approved")

    active_after = client.get("/api/v1/promotions/active").json()["data"]
    assert any(p["id"] == promo_data["id"] for p in active_after)


def test_merchant_registration_succeeds_even_if_register_1000_deactivated(client: TestClient, db_session):
    from app.db.models.subscription import SubscriptionPackage
    from app.services.subscription_service import SubscriptionService
    from tests.conftest import merchant_reg_payment_payload

    SubscriptionService.ensure_default_packages(db_session)
    reg_pkg = (
        db_session.query(SubscriptionPackage)
        .filter(SubscriptionPackage.code == "MERCHANT_REGISTER_1000")
        .first()
    )
    assert reg_pkg is not None
    reg_pkg.is_active = False
    db_session.commit()

    # Should not show mandatory registration plan in storefront active packages list
    merchant_pkgs = client.get("/api/v1/subscriptions/packages?audience=MERCHANT&active_only=true").json()["data"]
    assert not any(p["code"] == "MERCHANT_REGISTER_1000" for p in merchant_pkgs)

    onboard_res = client.post(
        "/api/v1/merchants/onboard",
        json={
            "business_name": "Inactive Pkg Onboard Shop",
            "owner_name": "Owner",
            "category": "Retail",
            "phone_number": "9876548881",
            "email": "inactive.onboard@example.com",
            "password": "MerchantPassword123",
            "address": "Kochi",
            **merchant_reg_payment_payload(client),
        },
    )
    assert onboard_res.status_code == 201, onboard_res.text

    reg_res = client.post(
        "/api/v1/merchants/register",
        json={
            "name": "Inactive Pkg Reg Merchant",
            "email": "inactive.reg@example.com",
            "password": "MerchantPassword123",
            "business_name": "Inactive Pkg Reg Shop",
            "categories": ["Retail"],
            "location": "Kochi",
            "services": ["Sales"],
            "service_timing": "9-9",
            "contact_number": "9876548882",
            "address": "Kochi",
            **merchant_reg_payment_payload(client),
        },
    )
    assert reg_res.status_code == 201, reg_res.text


def test_merchant_register_with_chosen_plan_pending_then_unlocks_on_approve(client: TestClient, db_session: Session):
    from app.core.security import hash_password
    from app.db.models.user import User, UserRole
    from app.services.auth_service import AuthService

    admin = User(
        name="Sub Admin",
        email="subplan.admin@example.com",
        password_hash=hash_password("AdminPass123!"),
        role=UserRole.ADMIN,
        is_active=True,
        is_verified=True,
    )
    db_session.add(admin)
    db_session.commit()
    admin_token = AuthService.generate_token_pair(admin).access_token
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Admin creates a custom merchant plan (only Store Profile Photos + Hero Ad, no Video)
    pkg_res = client.post(
        "/api/v1/subscriptions/admin/packages",
        headers=admin_headers,
        json={
            "code": "REG_CUSTOM_HERO",
            "name": "Starter Hero & Photo Plan",
            "description": "Custom registration subscription",
            "audience": "MERCHANT",
            "price": 1499,
            "billing_period": "MONTHLY",
            "duration_days": 30,
            "grants": {
                "_granular": True,
                "merchant_profile_photos": True,
                "merchant_profile_video": False,
                "ad_home_top": True,
            },
        },
    )
    assert pkg_res.status_code == 201, pkg_res.text
    chosen_pkg = pkg_res.json()["data"]

    # Step 1: Create Razorpay order specifically for chosen plan
    order_res = client.post(
        "/api/v1/merchants/register/razorpay-order",
        json={
            "email": "chosenplan.shop@example.com",
            "business_name": "Chosen Plan Store",
            "package_id": chosen_pkg["id"],
            "package_code": chosen_pkg["code"],
        },
    )
    assert order_res.status_code == 201, order_res.text
    order_data = order_res.json()
    assert order_data["amount"] == 1499.0
    assert order_data["package_code"] == "REG_CUSTOM_HERO"

    # Step 2: Register/onboard without photos, passing chosen package_id + Razorpay proof
    onboard_res = client.post(
        "/api/v1/merchants/onboard",
        json={
            "business_name": "Chosen Plan Store",
            "owner_name": "Plan Owner",
            "category": "Retail",
            "phone_number": "9876501234",
            "email": "chosenplan.shop@example.com",
            "password": "MerchantPassword123",
            "address": "MG Road, Kochi",
            "package_id": chosen_pkg["id"],
            "package_code": chosen_pkg["code"],
            "razorpay_order_id": order_data["razorpay_order_id"],
            "razorpay_payment_id": "pay_dev_chosen_1499",
            "razorpay_signature": "dev_signature_ok",
        },
    )
    assert onboard_res.status_code == 201, onboard_res.text
    created_merchant = onboard_res.json()["merchant"]
    # Must stay PENDING until Admin approves, and features remain locked until approval
    assert created_merchant["approval_status"] == "PENDING"
    assert created_merchant["merchant_grants"]["merchant_profile_photos"] is False
    assert created_merchant["merchant_grants"]["ad_home_top"] is False
    assert created_merchant["subscription_plan_name"] == "Starter Hero & Photo Plan"
    assert created_merchant["subscription_amount_paid"] == 1499.0

    # Admin checks registration requests -> sees chosen plan name & price!
    reqs = client.get("/api/v1/admin/merchants/registration-requests?status=pending", headers=admin_headers)
    assert reqs.status_code == 200
    row = next(item for item in reqs.json()["data"] if item["id"] == created_merchant["id"])
    assert row["subscription_plan_name"] == "Starter Hero & Photo Plan"
    assert len(row["active_subscriptions"]) == 1
    assert row["active_subscriptions"][0]["days_remaining"] == 30

    # Step 3: Admin approves -> chosen plan's features unlock immediately!
    approve_res = client.post(f"/api/v1/merchants/{created_merchant['id']}/approve", headers=admin_headers)
    assert approve_res.status_code == 200, approve_res.text
    approved_merchant = approve_res.json()["data"]
    assert approved_merchant["approval_status"] == "APPROVED"
    assert approved_merchant["merchant_grants"]["merchant_profile_photos"] is True
    assert approved_merchant["merchant_grants"]["ad_home_top"] is True
    assert approved_merchant["merchant_grants"]["merchant_profile_video"] is False

    # Same active plan cannot be subscribed twice concurrently unless renew=True
    m_token = AuthService.generate_token_pair(
        db_session.query(User).filter(User.email == "chosenplan.shop@example.com").first()
    ).access_token
    m_headers = {"Authorization": f"Bearer {m_token}"}

    dup_order = client.post(
        "/api/v1/subscriptions/razorpay/order",
        headers=m_headers,
        json={"package_id": chosen_pkg["id"], "merchant_profile_id": created_merchant["id"]},
    )
    assert dup_order.status_code == 400
    assert "already subscribed" in dup_order.json()["detail"].lower()

    dup_sub = client.post(
        "/api/v1/subscriptions/subscribe",
        headers=m_headers,
        json={"package_id": chosen_pkg["id"], "merchant_profile_id": created_merchant["id"], "payment_reference": "DUP"},
    )
    assert dup_sub.status_code == 400

    # Explicit renew extends remaining days instead of creating duplicate row
    renew_sub = client.post(
        "/api/v1/subscriptions/subscribe",
        headers=m_headers,
        json={"package_id": chosen_pkg["id"], "merchant_profile_id": created_merchant["id"], "payment_reference": "RENEW", "renew": True},
    )
    assert renew_sub.status_code == 201, renew_sub.text
    assert renew_sub.json()["data"]["days_remaining"] >= 59
