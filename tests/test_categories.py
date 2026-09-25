from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models.user import User, UserRole


def get_auth_token(client: TestClient, email: str, password: str) -> str:
    res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return res.json()["access_token"]


def create_admin(db_session: Session, client: TestClient, email: str = "admin@example.com") -> str:
    admin = User(
        name="Admin Test",
        email=email,
        password_hash=hash_password("AdminPass123!"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()
    return get_auth_token(client, email, "AdminPass123!")


def create_public_user(client: TestClient, email: str = "user@example.com") -> str:
    client.post("/api/v1/auth/register", json={
        "name": "Normal User",
        "email": email,
        "password": "UserPass123!",
    })
    return get_auth_token(client, email, "UserPass123!")


def test_category_crud_by_admin(client: TestClient, db_session: Session):
    admin_token = create_admin(db_session, client)
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Create Category
    create_payload = {
        "name": "Technology & AI",
        "slug": "technology-and-ai",
        "description": "Logos for modern tech and AI startups",
        "icon_url": "https://example.com/icons/tech.svg",
        "is_active": True,
    }
    create_res = client.post("/api/v1/categories", json=create_payload, headers=headers)
    assert create_res.status_code == 201
    cat_data = create_res.json()
    assert cat_data["name"] == "Technology & AI"
    assert cat_data["slug"] == "technology-and-ai"
    cat_id = cat_data["id"]

    # 2. Get Category by ID and by slug (Public)
    get_id_res = client.get(f"/api/v1/categories/{cat_id}")
    assert get_id_res.status_code == 200
    assert get_id_res.json()["name"] == "Technology & AI"

    get_slug_res = client.get("/api/v1/categories/technology-and-ai")
    assert get_slug_res.status_code == 200
    assert get_slug_res.json()["id"] == cat_id

    # 3. List Categories (Public)
    list_res = client.get("/api/v1/categories")
    assert list_res.status_code == 200
    items = list_res.json()["items"]
    assert any(c["id"] == cat_id for c in items)

    # 4. Update Category (Admin)
    update_res = client.patch(
        f"/api/v1/categories/{cat_id}",
        json={"name": "Tech, Robotics & AI", "description": "Expanded tech description"},
        headers=headers,
    )
    assert update_res.status_code == 200
    assert update_res.json()["name"] == "Tech, Robotics & AI"

    # 5. Delete Category (Admin)
    del_res = client.delete(f"/api/v1/categories/{cat_id}", headers=headers)
    assert del_res.status_code == 200
    assert "successfully deleted" in del_res.json()["message"]

    # Verify 404 after deletion
    get_after_del = client.get(f"/api/v1/categories/{cat_id}")
    assert get_after_del.status_code == 404


def test_category_rbac_enforcement(client: TestClient, db_session: Session):
    admin_token = create_admin(db_session, client, email="adm_rbac@example.com")
    user_token = create_public_user(client, email="user_rbac@example.com")
    user_headers = {"Authorization": f"Bearer {user_token}"}

    # Field staff can create category
    res_create = client.post("/api/v1/categories", json={"name": "Field Staff RBAC Cat"}, headers=user_headers)
    assert res_create.status_code == 201
    cat_id = res_create.json()["id"]

    # Non-admin (Field staff) attempts to delete category -> 403 Forbidden
    res_delete = client.delete(f"/api/v1/categories/{cat_id}", headers=user_headers)
    assert res_delete.status_code == 403

    # Unauthenticated attempt -> 401
    res_unauth = client.post("/api/v1/categories", json={"name": "Unauth Cat"})
    assert res_unauth.status_code == 401


def test_category_duplicate_rejection(client: TestClient, db_session: Session):
    admin_token = create_admin(db_session, client, email="adm_dup@example.com")
    headers = {"Authorization": f"Bearer {admin_token}"}

    client.post("/api/v1/categories", json={"name": "Healthcare & Wellness"}, headers=headers)

    # Duplicate name
    res_dup_name = client.post("/api/v1/categories", json={"name": "Healthcare & Wellness"}, headers=headers)
    assert res_dup_name.status_code == 409
    assert "already exists" in res_dup_name.json()["detail"]


def create_field_staff(db_session: Session, client: TestClient, email: str = "staff@example.com") -> str:
    staff = User(
        name="Field Staff One",
        email=email,
        password_hash=hash_password("StaffPass123!"),
        role=UserRole.FIELD_STAFF,
        is_active=True,
    )
    db_session.add(staff)
    db_session.commit()
    return get_auth_token(client, email, "StaffPass123!")


def test_field_staff_add_category_flow(client: TestClient, db_session: Session):
    staff_token = create_field_staff(db_session, client, email="staff.cat@example.com")
    headers = {"Authorization": f"Bearer {staff_token}"}

    # 1. Create Category with Emoji and status 'Active'
    payload1 = {
        "category_name": "Food & Dining",
        "icon": "🍔",
        "status": "Active",
    }
    res1 = client.post("/api/v1/categories", json=payload1, headers=headers)
    assert res1.status_code == 201, res1.text
    data1 = res1.json()
    assert data1["name"] == "Food & Dining"
    assert data1["category_name"] == "Food & Dining"
    assert data1["icon"] == "🍔"
    assert data1["icon_url"] == "🍔"
    assert data1["is_active"] is True
    assert data1["status"] == "Active"

    # 2. Create Category with icon png path and status 'Inactive'
    payload2 = {
        "name": "Luxury Watches",
        "icon": "/static/categories/icons/watch.png",
        "status": "Inactive",
    }
    res2 = client.post("/api/v1/categories", json=payload2, headers=headers)
    assert res2.status_code == 201
    data2 = res2.json()
    assert data2["name"] == "Luxury Watches"
    assert data2["icon"] == "/static/categories/icons/watch.png"
    assert data2["is_active"] is False
    assert data2["status"] == "Inactive"

    # 3. Upload icon PNG file
    import io
    fake_png = ("icon.png", io.BytesIO(b"\x89PNG\r\n\x1a\n fake png data"), "image/png")
    upload_res = client.post("/api/v1/categories/upload-icon", files={"file": fake_png}, headers=headers)
    assert upload_res.status_code == 200, upload_res.text
    icon_data = upload_res.json()
    assert "icon_url" in icon_data
    assert icon_data["icon_url"].startswith("/static/categories/icons/")

    # 4. Create category via form endpoint (/form) with file upload
    fake_png2 = ("bakery.png", io.BytesIO(b"\x89PNG\r\n\x1a\n bakery png data"), "image/png")
    form_res = client.post(
        "/api/v1/categories/form",
        data={"name": "Artisan Bakery", "status": "Active"},
        files={"icon_file": fake_png2},
        headers=headers,
    )
    assert form_res.status_code == 201, form_res.text
    form_data = form_res.json()
    assert form_data["name"] == "Artisan Bakery"
    assert form_data["icon"].startswith("/static/categories/icons/")
    assert form_data["status"] == "Active"

    # 5. Field staff can access via /field-staff/categories
    fs_res = client.get("/api/v1/field-staff/categories")
    assert fs_res.status_code == 200
