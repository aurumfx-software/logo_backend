from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models.user import User, UserRole


def get_token(client: TestClient, email: str, password: str) -> str:
    res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return res.json()["access_token"]


def setup_admin_and_users(client: TestClient, db_session: Session):
    admin = User(
        name="Super Admin",
        email="super.admin@example.com",
        password_hash=hash_password("SuperAdmin123!"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()
    admin_token = get_token(client, "super.admin@example.com", "SuperAdmin123!")

    client.post("/api/v1/auth/register", json={
        "name": "Regular Member",
        "email": "member@example.com",
        "password": "MemberPass123!",
    })
    member_token = get_token(client, "member@example.com", "MemberPass123!")

    return admin, admin_token, member_token


def test_admin_dashboard_stats(client: TestClient, db_session: Session):
    admin, admin_token, _ = setup_admin_and_users(client, db_session)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Create category and logo
    cat_res = client.post("/api/v1/categories", json={"name": "Gaming & Esports"}, headers=admin_headers)
    cat_id = cat_res.json()["id"]

    client.post("/api/v1/logos", json={"title": "Viper Gaming", "category_id": cat_id, "image_url": "https://example.com/viper.png"}, headers=admin_headers)

    # Fetch stats
    stats_res = client.get("/api/v1/admin/dashboard/stats", headers=admin_headers)
    assert stats_res.status_code == 200
    stats = stats_res.json()

    assert stats["total_users"] >= 2
    assert stats["total_admins"] >= 1
    assert stats["total_logos"] >= 1
    assert stats["pending_logos"] >= 1
    assert stats["total_categories"] >= 1
    assert len(stats["recent_pending_logos"]) >= 1
    assert len(stats["category_distribution"]) >= 1


def test_user_management_by_admin(client: TestClient, db_session: Session):
    admin, admin_token, member_token = setup_admin_and_users(client, db_session)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Non-admin can list users (SUPER_ADMIN, ADMIN, USER allowed)
    member_headers = {"Authorization": f"Bearer {member_token}"}
    member_list_res = client.get("/api/v1/admin/users", headers=member_headers)
    assert member_list_res.status_code == 200

    # 1b. Non-admin forbidden from role modification
    forbidden_res = client.patch(
        f"/api/v1/admin/users/{admin.id}/role",
        json={"role": "ADMIN"},
        headers=member_headers,
    )
    assert forbidden_res.status_code == 403

    # 2. Admin lists users
    list_res = client.get("/api/v1/admin/users", headers=admin_headers)
    assert list_res.status_code == 200
    users = list_res.json()["items"]
    member_user = next(u for u in users if u["email"] == "member@example.com")
    member_id = member_user["id"]

    # 3. Get user details
    detail_res = client.get(f"/api/v1/admin/users/{member_id}", headers=admin_headers)
    assert detail_res.status_code == 200
    assert detail_res.json()["email"] == "member@example.com"

    # 4. Update user role to FIELD_STAFF
    role_res = client.patch(
        f"/api/v1/admin/users/{member_id}/role",
        json={"role": "FIELD_STAFF"},
        headers=admin_headers,
    )
    assert role_res.status_code == 200
    assert role_res.json()["role"] == "FIELD_STAFF"

    # 5. Ban / deactivate user
    status_res = client.patch(
        f"/api/v1/admin/users/{member_id}/status",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert status_res.status_code == 200
    assert status_res.json()["is_active"] is False

    # 6. Admin cannot deactivate or demote self
    self_ban_res = client.patch(
        f"/api/v1/admin/users/{admin.id}/status",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert self_ban_res.status_code == 400
    assert "cannot deactivate" in self_ban_res.json()["detail"]

    self_demote_res = client.patch(
        f"/api/v1/admin/users/{admin.id}/role",
        json={"role": "FIELD_STAFF"},
        headers=admin_headers,
    )
    assert self_demote_res.status_code == 400
    assert "cannot demote" in self_demote_res.json()["detail"]

    # 7. Delete user
    del_res = client.delete(f"/api/v1/admin/users/{member_id}", headers=admin_headers)
    assert del_res.status_code == 200
    assert "successfully deleted" in del_res.json()["message"]

    # 8. Admin cannot delete self
    self_del_res = client.delete(f"/api/v1/admin/users/{admin.id}", headers=admin_headers)
    assert self_del_res.status_code == 400
    assert "cannot delete" in self_del_res.json()["detail"]


def test_admin_create_user_with_all_fields(client: TestClient, db_session: Session):
    admin, admin_token, _ = setup_admin_and_users(client, db_session)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    payload = {
        "name": "Field Executive Alpha",
        "email": "executive.alpha@example.com",
        "phone": "9876500001",
        "password": "ExecPassword123!",
        "role": "FIELD_STAFF",
        "district": "Ernakulam",
        "regions": ["Kochi Zone", "North Central"],
        "city": "Kochi",
        "module_access": ["merchants", "users", "categories"],
        "send_email": True,
        "status": "ACTIVE",
        "created_by": "ADM_1",
    }

    # 1. Test POST /api/v1/admin/users
    create_res = client.post("/api/v1/admin/users", json=payload, headers=admin_headers)
    assert create_res.status_code == 201
    created_user = create_res.json()

    assert created_user["name"] == "Field Executive Alpha"
    assert created_user["email"] == "executive.alpha@example.com"
    assert created_user["phone"] == "9876500001"
    assert created_user["role"] == "FIELD_STAFF"
    assert created_user["user_code"].startswith("FLS_")
    assert created_user["district"] == "Ernakulam"
    assert created_user["regions"] == ["Kochi Zone", "North Central"]
    assert created_user["city"] == "Kochi"
    assert created_user["module_access"] == ["merchants", "users", "categories"]
    assert created_user["send_email"] is True
    assert created_user["status"] == "ACTIVE"
    assert created_user["created_by"] == "ADM_1"
    assert created_user["created_at"] is not None

    # 2. Test duplicate email prevents creation
    dup_res = client.post("/api/v1/admin/users", json=payload, headers=admin_headers)
    assert dup_res.status_code == 409

    # 3. Test POST /api/v1/users endpoint
    payload2 = {
        "name": "Field Executive Beta",
        "email": "executive.beta@example.com",
        "phone": "9876500002",
        "password": "ExecPassword123!",
        "role": "FIELD_STAFF",
        "district": "Thrissur",
        "regions": ["Thrissur City", "Chalakudy"],
        "city": "Thrissur",
        "module_access": ["merchants"],
        "send_email": False,
        "status": "ACTIVE",
    }
    create_res2 = client.post("/api/v1/users", json=payload2, headers=admin_headers)
    assert create_res2.status_code == 201
    user2 = create_res2.json()["data"]
    assert user2["name"] == "Field Executive Beta"
    assert user2["user_code"].startswith("FLS_")
    assert user2["district"] == "Thrissur"
    assert user2["regions"] == ["Thrissur City", "Chalakudy"]
    assert user2["city"] == "Thrissur"
    assert user2["module_access"] == ["merchants"]
    assert user2["send_email"] is False

