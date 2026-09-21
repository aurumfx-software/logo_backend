from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models.user import User, UserRole


def get_token(client: TestClient, email: str, password: str) -> str:
    res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return res.json()["access_token"]


def test_logo_favorites_full_flow(client: TestClient, db_session: Session):
    # Setup Admin
    admin = User(
        name="Admin Fav",
        email="admin.fav@example.com",
        password_hash=hash_password("AdminPass123!"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()
    admin_token = get_token(client, "admin.fav@example.com", "AdminPass123!")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Setup User
    client.post("/api/v1/auth/register", json={
        "name": "Favorite User",
        "email": "fav.user@example.com",
        "password": "FavUserPass123!",
    })
    user_token = get_token(client, "fav.user@example.com", "FavUserPass123!")
    user_headers = {"Authorization": f"Bearer {user_token}"}

    # Admin creates and approves a logo
    logo_res = client.post(
        "/api/v1/logos",
        json={"title": "Aurora Design Logo", "image_url": "https://example.com/aurora.png"},
        headers=admin_headers,
    )
    logo_id = logo_res.json()["id"]
    client.post(f"/api/v1/admin/logos/{logo_id}/approve", headers=admin_headers)

    # 1. Initially, is_favorite is False
    check_init = client.get(f"/api/v1/logos/{logo_id}/favorite", headers=user_headers)
    assert check_init.status_code == 200
    assert check_init.json()["is_favorite"] is False

    # 2. Toggle favorite -> Added
    toggle_1 = client.post(f"/api/v1/logos/{logo_id}/favorite", headers=user_headers)
    assert toggle_1.status_code == 200
    assert toggle_1.json()["is_favorite"] is True
    assert toggle_1.json()["favorites_count"] == 1

    # 3. Check favorite -> True
    check_after_add = client.get(f"/api/v1/logos/{logo_id}/favorite", headers=user_headers)
    assert check_after_add.json()["is_favorite"] is True

    # 4. View favorites list
    favs_list = client.get("/api/v1/favorites", headers=user_headers)
    assert favs_list.status_code == 200
    assert favs_list.json()["total"] == 1
    assert favs_list.json()["items"][0]["id"] == logo_id
    assert favs_list.json()["items"][0]["is_favorite"] is True

    # 5. Toggle favorite again -> Removed
    toggle_2 = client.post(f"/api/v1/logos/{logo_id}/favorite", headers=user_headers)
    assert toggle_2.status_code == 200
    assert toggle_2.json()["is_favorite"] is False
    assert toggle_2.json()["favorites_count"] == 0

    # 6. View favorites list -> Empty
    favs_list_empty = client.get("/api/v1/favorites", headers=user_headers)
    assert favs_list_empty.json()["total"] == 0
