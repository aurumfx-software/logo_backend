import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password, create_access_token
from app.db.models.user import User, UserRole
from app.db.models.merchant import MerchantProfile


def test_super_admin_and_role_access(client: TestClient, db_session: Session):
    # Create super admin, admin, and regular user
    sa = User(
        name="Chief SuperAdmin",
        email="superadmin@example.com",
        phone="9990001111",
        password_hash=hash_password("SuperSecret123!"),
        role=UserRole.SUPER_ADMIN,
        is_active=True,
        is_verified=True,
    )
    adm = User(
        name="System Admin",
        email="sysadmin@example.com",
        phone="9990002222",
        password_hash=hash_password("AdminPass123!"),
        role=UserRole.ADMIN,
        is_active=True,
        is_verified=True,
    )
    usr = User(
        name="Normal User",
        email="normaluser@example.com",
        phone="9990003333",
        password_hash=hash_password("UserPass123!"),
        role=UserRole.FIELD_STAFF,
        is_active=True,
        is_verified=True,
    )
    db_session.add_all([sa, adm, usr])
    db_session.commit()

    sa_token = create_access_token(user_id=sa.id, role=sa.role.value)
    adm_token = create_access_token(user_id=adm.id, role=adm.role.value)
    usr_token = create_access_token(user_id=usr.id, role=usr.role.value)

    # 1. Super Admin, Admin, and User can all call /api/v1/users
    for token in [sa_token, adm_token, usr_token]:
        res = client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        assert res.json()["success"] is True

    # 2. Super Admin, Admin, and User can all call /api/v1/admin/users
    for token in [sa_token, adm_token, usr_token]:
        res = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        assert "items" in res.json()

    # 3. Filter by role=SUPER_ADMIN on /api/v1/users
    res_sa = client.get("/api/v1/users?role=SUPER_ADMIN")
    assert res_sa.status_code == 200
    assert any(u["email"] == "superadmin@example.com" for u in res_sa.json()["data"])
    assert all(u["role"] == "SUPER_ADMIN" for u in res_sa.json()["data"])

    # 4. Super Admin can access admin dashboard
    res_dash = client.get("/api/v1/admin/dashboard/stats", headers={"Authorization": f"Bearer {sa_token}"})
    assert res_dash.status_code == 200
    assert res_dash.json()["total_admins"] >= 2  # Includes both SUPER_ADMIN and ADMIN



def test_user_listing_api(client: TestClient, db_session: Session):
    # Create test users
    u1 = User(
        name="Alice Walker",
        email="alice@example.com",
        phone="9876541111",
        role=UserRole.FIELD_STAFF,
        is_active=True,
        is_verified=True,
    )
    u2 = User(
        name="Bob Builder",
        email="bob@example.com",
        phone="9876542222",
        role=UserRole.FIELD_STAFF,
        is_active=True,
        is_verified=False,
    )
    u3 = User(
        name="Charlie Admin",
        email="charlie@example.com",
        phone="9876543333",
        role=UserRole.ADMIN,
        is_active=False,
        is_verified=True,
    )
    db_session.add_all([u1, u2, u3])
    db_session.commit()

    # 1. List all users (default sorted by ID ascending: 1, 2, 3...)
    res = client.get("/api/v1/users")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["meta"]["total_items"] >= 3
    assert len(data["data"]) >= 3
    ids = [u["id"] for u in data["data"]]
    assert ids == sorted(ids)  # Verified ascending order

    # 1b. Test sort=desc
    res_desc = client.get("/api/v1/users?sort=desc")
    assert res_desc.status_code == 200
    ids_desc = [u["id"] for u in res_desc.json()["data"]]
    assert ids_desc == sorted(ids_desc, reverse=True)

    # 2. Filter by role
    res_role = client.get("/api/v1/users?role=FIELD_STAFF")
    assert res_role.status_code == 200
    assert any(u["email"] == "alice@example.com" for u in res_role.json()["data"])
    assert not any(u["email"] == "charlie@example.com" for u in res_role.json()["data"])

    # 3. Search keyword
    res_search = client.get("/api/v1/users?search=Alice")
    assert res_search.status_code == 200
    assert len(res_search.json()["data"]) == 1
    assert res_search.json()["data"][0]["name"] == "Alice Walker"

    # 4. Filter by is_active
    res_active = client.get("/api/v1/users?is_active=false")
    assert res_active.status_code == 200
    assert any(u["email"] == "charlie@example.com" for u in res_active.json()["data"])

    # 5. Get user by ID
    res_single = client.get(f"/api/v1/users/{u1.id}")
    assert res_single.status_code == 200
    assert res_single.json()["success"] is True
    assert res_single.json()["data"]["name"] == "Alice Walker"

    # 6. Non-existing user ID
    res_404 = client.get("/api/v1/users/99999")
    assert res_404.status_code == 404
    assert res_404.json()["success"] is False


def test_merchant_listing_api(client: TestClient, db_session: Session):
    # Create merchant user & profile
    user = User(
        name="Shop Owner",
        email="shop.owner@example.com",
        phone="9876544444",
        role=UserRole.FIELD_STAFF,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    db_session.commit()

    merchant = MerchantProfile(
        user_id=user.id,
        business_name="Green Grocery Store",
        categories=["Grocery", "Supermarket"],
        location="MG Road, Kochi",
        services=["Home Delivery", "Fresh Vegetables"],
        service_timing="07:00 AM - 10:00 PM",
        merchant_photos=[],
        contact_number="9876544444",
        address="100 MG Road, Kochi",
        is_verified=True,
        approval_status="APPROVED",
        is_active=True,
    )
    db_session.add(merchant)
    db_session.commit()

    # 1. Test /merchants/list
    res = client.get("/api/v1/merchants/list")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["meta"]["total_items"] >= 1
    assert any(m["business_name"] == "Green Grocery Store" for m in data["data"])

    # 2. Filter by location
    res_loc = client.get("/api/v1/merchants/list?location=Kochi")
    assert res_loc.status_code == 200
    assert any(m["business_name"] == "Green Grocery Store" for m in res_loc.json()["data"])

    # 3. Filter by category
    res_cat = client.get("/api/v1/merchants/list?category=Grocery")
    assert res_cat.status_code == 200
    assert any(m["business_name"] == "Green Grocery Store" for m in res_cat.json()["data"])

    # 4. Search keyword
    res_search = client.get("/api/v1/merchants/list?search=Green")
    assert res_search.status_code == 200
    assert len(res_search.json()["data"]) == 1
    assert res_search.json()["data"][0]["business_name"] == "Green Grocery Store"

    # 5. Pagination
    res_page = client.get("/api/v1/merchants/list?page=1&page_size=10")
    assert res_page.status_code == 200
    assert res_page.json()["meta"]["page"] == 1
    assert res_page.json()["meta"]["page_size"] == 10
