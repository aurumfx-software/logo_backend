from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import jwt

from app.core.config import settings
from app.core.security import create_token, hash_password
from app.db.models.otp import OTPPurpose, OTPVerification
from app.db.models.user import User, UserRole


# 1. Registration success
def test_registration_success(client: TestClient):
    payload = {
        "name": "Test User",
        "email": "test@example.com",
        "phone": "9876543210",
        "password": "TestPassword123",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["message"] == "User registered successfully"
    assert data["user"]["email"] == "test@example.com"
    assert data["user"]["role"] == "PUBLIC_USER"
    assert data["user"]["is_verified"] is False
    assert "password" not in data["user"]
    assert "password_hash" not in data["user"]


# 2. Duplicate email
def test_duplicate_email_rejection(client: TestClient):
    payload = {
        "name": "Test User",
        "email": "duplicate@example.com",
        "password": "TestPassword123",
    }
    res1 = client.post("/api/v1/auth/register", json=payload)
    assert res1.status_code == 201

    res2 = client.post("/api/v1/auth/register", json=payload)
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"]


# 3. Login success
def test_login_success(client: TestClient):
    reg_payload = {
        "name": "Login User",
        "email": "login@example.com",
        "password": "CorrectPassword123",
    }
    client.post("/api/v1/auth/register", json=reg_payload)

    login_payload = {
        "email": "login@example.com",
        "password": "CorrectPassword123",
    }
    response = client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


# 4. Wrong password
def test_login_wrong_password(client: TestClient):
    reg_payload = {
        "name": "User",
        "email": "wrongpwd@example.com",
        "password": "CorrectPassword123",
    }
    client.post("/api/v1/auth/register", json=reg_payload)

    login_payload = {
        "email": "wrongpwd@example.com",
        "password": "WrongPassword456",
    }
    response = client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["detail"]


# 5. JWT protected endpoint & Current user endpoint
def test_get_current_user_me(client: TestClient):
    reg_payload = {
        "name": "Profile User",
        "email": "me@example.com",
        "phone": "9998887776",
        "password": "SecurePassword123",
    }
    client.post("/api/v1/auth/register", json=reg_payload)

    login_res = client.post("/api/v1/auth/login", json={
        "email": "me@example.com",
        "password": "SecurePassword123",
    })
    token = login_res.json()["access_token"]

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Profile User"
    assert data["email"] == "me@example.com"
    assert data["phone"] == "9998887776"
    assert data["role"] == "PUBLIC_USER"
    assert "password_hash" not in data


# 6. Invalid JWT
def test_invalid_jwt_rejected(client: TestClient):
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer completely-invalid-jwt-token"},
    )
    assert response.status_code == 401


# 7. Expired JWT
def test_expired_jwt_rejected(client: TestClient, db_session: Session):
    user = User(
        name="Expired User",
        email="expired@example.com",
        password_hash=hash_password("Password123"),
        role=UserRole.PUBLIC_USER,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    # Issue an already expired token
    expired_token = create_token(
        data={"sub": str(user.id), "role": user.role.value},
        expires_delta=timedelta(seconds=-60),
        token_type="access",
    )

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


# 8. Refresh token flow
def test_refresh_token_flow(client: TestClient):
    reg_payload = {
        "name": "Refresh User",
        "email": "refresh@example.com",
        "password": "Password12345",
    }
    client.post("/api/v1/auth/register", json=reg_payload)

    login_res = client.post("/api/v1/auth/login", json={
        "email": "refresh@example.com",
        "password": "Password12345",
    })
    refresh_token = login_res.json()["refresh_token"]

    refresh_res = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_res.status_code == 200
    data = refresh_res.json()
    assert "access_token" in data
    assert "refresh_token" in data


# 9. Logout
def test_logout_endpoint(client: TestClient):
    reg_payload = {
        "name": "Logout User",
        "email": "logout@example.com",
        "password": "Password12345",
    }
    client.post("/api/v1/auth/register", json=reg_payload)
    login_res = client.post("/api/v1/auth/login", json={
        "email": "logout@example.com",
        "password": "Password12345",
    })
    token = login_res.json()["access_token"]

    response = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert "successfully logged out" in response.json()["message"].lower()


# 10. OTP generation and verification
def test_otp_generation_and_verification(client: TestClient):
    # Register user first
    client.post("/api/v1/auth/register", json={
        "name": "OTP User",
        "email": "otpuser@example.com",
        "password": "Password12345",
    })

    # Send OTP
    send_res = client.post("/api/v1/auth/send-otp", json={
        "email": "otpuser@example.com",
        "purpose": "ACCOUNT_VERIFICATION",
    })
    assert send_res.status_code == 200
    otp = send_res.json()["dev_otp"]
    assert otp is not None
    assert len(otp) == 6

    # Verify OTP
    verify_res = client.post("/api/v1/auth/verify-otp", json={
        "email": "otpuser@example.com",
        "otp": otp,
        "purpose": "ACCOUNT_VERIFICATION",
    })
    assert verify_res.status_code == 200
    assert verify_res.json()["is_verified"] is True

    # User should now be verified
    login_res = client.post("/api/v1/auth/login", json={
        "email": "otpuser@example.com",
        "password": "Password12345",
    })
    token = login_res.json()["access_token"]
    me_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.json()["is_verified"] is True


# 11. Expired OTP
def test_expired_otp_rejection(client: TestClient, db_session: Session):
    from app.core.security import hash_otp

    email = "expired_otp@example.com"
    otp_record = OTPVerification(
        identifier=email,
        otp_hash=hash_otp("654321"),
        purpose=OTPPurpose.ACCOUNT_VERIFICATION,
        attempts=0,
        max_attempts=3,
        is_used=False,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    db_session.add(otp_record)
    db_session.commit()

    res = client.post("/api/v1/auth/verify-otp", json={
        "email": email,
        "otp": "654321",
        "purpose": "ACCOUNT_VERIFICATION",
    })
    assert res.status_code == 400
    assert "expired" in res.json()["detail"].lower()


# 12. Invalid OTP and attempt count limit
def test_invalid_otp_attempts_limit(client: TestClient):
    email = "attempts@example.com"
    client.post("/api/v1/auth/send-otp", json={"email": email})

    # Send 3 wrong OTP attempts
    for _ in range(3):
        res = client.post("/api/v1/auth/verify-otp", json={
            "email": email,
            "otp": "000000",
            "purpose": "ACCOUNT_VERIFICATION",
        })
        assert res.status_code == 400

    # 4th attempt should be blocked due to maximum attempts exceeded or no active OTP
    res4 = client.post("/api/v1/auth/verify-otp", json={
        "email": email,
        "otp": "000000",
        "purpose": "ACCOUNT_VERIFICATION",
    })
    assert res4.status_code == 400


# 13. Password reset flow with OTP
def test_password_reset_flow(client: TestClient):
    client.post("/api/v1/auth/register", json={
        "name": "Reset User",
        "email": "reset@example.com",
        "password": "OldPassword123",
    })

    # Forgot password
    forgot_res = client.post("/api/v1/auth/forgot-password", json={"email": "reset@example.com"})
    assert forgot_res.status_code == 200
    otp = forgot_res.json()["dev_otp"]

    # Reset password with OTP
    reset_res = client.post("/api/v1/auth/reset-password", json={
        "email": "reset@example.com",
        "otp": otp,
        "new_password": "NewPassword789",
    })
    assert reset_res.status_code == 200
    assert "reset successfully" in reset_res.json()["message"]

    # Login with old password fails
    fail_login = client.post("/api/v1/auth/login", json={
        "email": "reset@example.com",
        "password": "OldPassword123",
    })
    assert fail_login.status_code == 401

    # Login with new password succeeds
    ok_login = client.post("/api/v1/auth/login", json={
        "email": "reset@example.com",
        "password": "NewPassword789",
    })
    assert ok_login.status_code == 200


# 14. Role-based authorization
def test_role_based_authorization(client: TestClient, db_session: Session):
    # 1. Normal user (PUBLIC_USER)
    client.post("/api/v1/auth/register", json={
        "name": "Public User",
        "email": "public@example.com",
        "password": "Password123",
    })
    public_login = client.post("/api/v1/auth/login", json={
        "email": "public@example.com",
        "password": "Password123",
    })
    public_token = public_login.json()["access_token"]

    # Accessing admin test endpoint with PUBLIC_USER -> 403 Forbidden
    res_public = client.get(
        "/api/v1/auth/admin-test",
        headers={"Authorization": f"Bearer {public_token}"},
    )
    assert res_public.status_code == 403

    # 2. Admin user (created directly in DB for testing admin access)
    admin_user = User(
        name="Admin User",
        email="admin@example.com",
        password_hash=hash_password("AdminPassword123"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(admin_user)
    db_session.commit()

    admin_login = client.post("/api/v1/auth/login", json={
        "email": "admin@example.com",
        "password": "AdminPassword123",
    })
    admin_token = admin_login.json()["access_token"]

    # Accessing admin test endpoint with ADMIN -> 200 OK
    res_admin = client.get(
        "/api/v1/auth/admin-test",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_admin.status_code == 200
    assert "Welcome, Administrator" in res_admin.json()["message"]


# 15. Google OAuth unconfigured error handling
def test_google_oauth_unconfigured_error(client: TestClient):
    # When GOOGLE_CLIENT_ID or SECRET is empty
    settings.GOOGLE_CLIENT_ID = ""
    settings.GOOGLE_CLIENT_SECRET = ""

    response = client.get("/api/v1/auth/google")
    assert response.status_code == 501
    assert "not configured" in response.json()["detail"]


# 16. Duplicate phone rejection
def test_duplicate_phone_rejection(client: TestClient):
    payload1 = {
        "name": "Phone User 1",
        "email": "phone1@example.com",
        "phone": "9123456780",
        "password": "Password123",
    }
    payload2 = {
        "name": "Phone User 2",
        "email": "phone2@example.com",
        "phone": "9123456780",
        "password": "Password123",
    }
    res1 = client.post("/api/v1/auth/register", json=payload1)
    assert res1.status_code == 201

    res2 = client.post("/api/v1/auth/register", json=payload2)
    assert res2.status_code == 409
    assert "phone number already exists" in res2.json()["detail"]


# 17. Missing Bearer header test
def test_missing_bearer_token(client: TestClient):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


