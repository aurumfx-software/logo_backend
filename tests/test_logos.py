from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models.user import User, UserRole


def get_token(client: TestClient, email: str, password: str) -> str:
    res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return res.json()["access_token"]


def setup_admin_and_user(client: TestClient, db_session: Session):
    admin = User(
        name="Admin Reviewer",
        email="admin.reviewer@example.com",
        password_hash=hash_password("AdminPass123!"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()
    admin_tok = get_token(client, "admin.reviewer@example.com", "AdminPass123!")

    client.post("/api/v1/auth/register", json={
        "name": "Designer User",
        "email": "designer@example.com",
        "password": "DesignerPass123!",
    })
    user_tok = get_token(client, "designer@example.com", "DesignerPass123!")

    return admin_tok, user_tok


def test_logo_submission_and_public_search(client: TestClient, db_session: Session):
    admin_token, user_token = setup_admin_and_user(client, db_session)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    user_headers = {"Authorization": f"Bearer {user_token}"}

    # 1. Create a category
    cat_res = client.post(
        "/api/v1/categories",
        json={"name": "Fintech & Finance", "slug": "fintech-finance"},
        headers=admin_headers,
    )
    cat_id = cat_res.json()["id"]

    # 2. Submit a logo as User (status should be PENDING)
    sub_payload = {
        "title": "Quantum Pay Logo",
        "description": "Minimalist geometric logo for fintech mobile banking",
        "image_url": "https://example.com/logos/quantum.png",
        "tags": ["fintech", "banking", "minimal", "modern"],
        "category_id": cat_id,
    }
    sub_res = client.post("/api/v1/logos", json=sub_payload, headers=user_headers)
    assert sub_res.status_code == 201
    logo_data = sub_res.json()
    assert logo_data["title"] == "Quantum Pay Logo"
    assert logo_data["status"] == "PENDING"
    logo_id = logo_data["id"]

    # 3. Public search (unauthenticated) should NOT include the pending logo
    public_search = client.get("/api/v1/logos?q=Quantum")
    assert public_search.status_code == 200
    assert public_search.json()["total"] == 0

    # 4. Admin checks pending queue
    pending_res = client.get("/api/v1/admin/logos/pending", headers=admin_headers)
    assert pending_res.status_code == 200
    assert any(l["id"] == logo_id for l in pending_res.json()["items"])

    # 5. Admin approves the logo
    approve_res = client.post(f"/api/v1/admin/logos/{logo_id}/approve", headers=admin_headers)
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "APPROVED"

    # 6. Public search now finds the approved logo
    search_q = client.get("/api/v1/logos?q=Quantum")
    assert search_q.status_code == 200
    assert search_q.json()["total"] == 1
    found_logo = search_q.json()["items"][0]
    assert found_logo["id"] == logo_id
    assert found_logo["category"]["slug"] == "fintech-finance"

    # 7. Search by tag
    search_tag = client.get("/api/v1/logos?tag=banking")
    assert search_tag.status_code == 200
    assert search_tag.json()["total"] == 1

    # 8. Search by category_slug
    search_cat = client.get("/api/v1/logos?category_slug=fintech-finance")
    assert search_cat.status_code == 200
    assert search_cat.json()["total"] == 1

    # 9. Get Logo details (increments views count)
    get_res_1 = client.get(f"/api/v1/logos/{logo_id}")
    assert get_res_1.status_code == 200
    assert get_res_1.json()["views_count"] == 1

    get_res_2 = client.get(f"/api/v1/logos/{logo_id}")
    assert get_res_2.json()["views_count"] == 2


def test_logo_update_and_rejection_flow(client: TestClient, db_session: Session):
    admin_token, user_token = setup_admin_and_user(client, db_session)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    user_headers = {"Authorization": f"Bearer {user_token}"}

    # User submits logo
    sub_res = client.post(
        "/api/v1/logos",
        json={"title": "Draft Logo", "image_url": "https://example.com/draft.png"},
        headers=user_headers,
    )
    logo_id = sub_res.json()["id"]

    # Admin rejects logo with reason
    rej_res = client.post(
        f"/api/v1/admin/logos/{logo_id}/reject",
        json={"rejection_reason": "Low quality artwork and missing description"},
        headers=admin_headers,
    )
    assert rej_res.status_code == 200
    assert rej_res.json()["status"] == "REJECTED"
    assert rej_res.json()["rejection_reason"] == "Low quality artwork and missing description"

    # Submitter updates logo with better details -> status resets to PENDING
    update_res = client.patch(
        f"/api/v1/logos/{logo_id}",
        json={"title": "Polished Logo Artwork", "description": "High-res vectorized brand identity"},
        headers=user_headers,
    )
    assert update_res.status_code == 200
    assert update_res.json()["status"] == "PENDING"
    assert update_res.json()["title"] == "Polished Logo Artwork"

    # Submitter deletes logo
    del_res = client.delete(f"/api/v1/logos/{logo_id}", headers=user_headers)
    assert del_res.status_code == 200
    assert "successfully deleted" in del_res.json()["message"]
