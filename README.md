# LOGO Backend — Trial Authentication & Discovery Platform Service

A clean, production-ready trial backend implementation for the **LOGO — Local Service & Merchant Discovery Platform**, built with **Python**, **FastAPI**, **PostgreSQL**, **SQLAlchemy**, and **Alembic**.

> **Note:** This is an isolated, standalone trial implementation built for demonstration and testing of the core authentication APIs. It does **not** touch or alter any production LOGO systems or user data.

---

## Table of Contents
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [PostgreSQL Database Setup](#postgresql-database-setup)
- [Local Installation & Setup](#local-installation--setup)
- [Environment Configuration](#environment-configuration)
- [Database Migrations (Alembic)](#database-migrations-alembic)
- [Running the Server](#running-the-server)
- [Interactive API Documentation (Swagger)](#interactive-api-documentation-swagger)
- [API Walkthrough & Testing Examples](#api-walkthrough--testing-examples)
  - [1. Health Check](#1-health-check)
  - [2. User Registration](#2-user-registration)
  - [3. User Login](#3-user-login)
  - [4. Authenticated Profile (GET /me)](#4-authenticated-profile-get-me)
  - [5. Token Refresh](#5-token-refresh)
  - [6. OTP Flow (Send & Verify)](#6-otp-flow-send--verify)
  - [7. Password Reset Flow](#7-password-reset-flow)
  - [8. Role-Based Authorization](#8-role-based-authorization)
  - [9. Google OAuth 2.0](#9-google-oauth-20)
- [Running Automated Tests](#running-automated-tests)
- [Git Commands & Safety](#git-commands--safety)

---

## Tech Stack
- **Framework:** [FastAPI](https://fastapi.tiangolo.com/) (Python 3.10+)
- **Server:** [Uvicorn](https://www.uvicorn.org/)
- **Database:** [PostgreSQL](https://www.postgresql.org/) with [psycopg](https://www.psycopg.org/psycopg3/) driver
- **ORM:** [SQLAlchemy 2.0](https://www.sqlalchemy.org/)
- **Migrations:** [Alembic](https://alembic.sqlalchemy.org/)
- **Security & Tokens:** [PyJWT](https://pyjwt.readthedocs.io/), [bcrypt](https://pypi.org/project/bcrypt/)
- **Validation:** [Pydantic v2](https://docs.pydantic.dev/), `pydantic-settings`
- **Testing:** [pytest](https://docs.pytest.org/), `FastAPI TestClient`, `httpx`

---

## Project Structure

```text
logo-backend/
│
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI application entry point, CORS, OpenAPI setup
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py              # JWT authentication & role-based authorization dependencies
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py        # Aggregator for v1 API endpoints
│   │       └── endpoints/
│   │           ├── __init__.py
│   │           ├── health.py    # Health check endpoint (GET /api/v1/health)
│   │           └── auth.py      # Auth, OTP, OAuth, and Role testing endpoints
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py            # Pydantic Settings configuration from .env
│   │   └── security.py          # Password hashing, JWT signing/decoding, OTP hashing
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py          # SQLAlchemy engine, session maker, get_db dependency
│   │   └── models/
│   │       ├── __init__.py
│   │       ├── user.py          # User SQLAlchemy model (PUBLIC_USER, MERCHANT, ADMIN)
│   │       └── otp.py           # OTPVerification SQLAlchemy model
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── auth.py              # Pydantic input/output schemas
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── auth_service.py      # User registration, login, token issuance, password reset
│   │   ├── otp_service.py       # OTP generation, storage, attempt limiting, verification
│   │   └── oauth_service.py     # Google OAuth 2.0 URL generation and token exchange
│   │
│   └── utils/
│       └── __init__.py
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Test client fixtures with isolated test database
│   ├── test_health.py           # Health endpoint tests
│   └── test_auth.py             # Complete test suite (registration, login, tokens, OTP, RBAC)
│
├── alembic/
│   ├── env.py                   # Alembic environment linked to SQLAlchemy models
│   ├── script.py.mako           # Migration template
│   └── versions/
│       └── 001_initial_auth_tables.py # Initial migration creating users & otp_verifications
│
├── .env                         # Local environment configuration (git ignored)
├── .env.example                 # Example environment variables template
├── .gitignore                   # Git ignore file ensuring secrets & environments stay local
├── requirements.txt             # Pinned project dependencies
├── alembic.ini                  # Alembic CLI configuration
└── README.md                    # Project documentation
```

---

## Prerequisites
- **Python:** 3.10, 3.11, or 3.12
- **PostgreSQL:** 14+ running locally (or via Docker/service)
- **Git**

---

## PostgreSQL Database Setup

1. Start your local PostgreSQL service (on Windows via Services or pgAdmin).
2. Connect to PostgreSQL using `psql` or pgAdmin:
   ```bash
   psql -U postgres
   ```
3. Create the trial database:
   ```sql
   CREATE DATABASE logo_trial_db;
   ```
4. Verify connection:
   ```bash
   psql -U postgres -d logo_trial_db
   ```

---

## Local Installation & Setup

1. Navigate to the `logo-backend` directory:
   ```bash
   cd logo-backend
   ```

2. Create a virtual environment:
   ```bash
   # Windows PowerShell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1

   # Linux/macOS
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install project dependencies:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

---

## Environment Configuration

Copy the example file `.env.example` to `.env`:
```bash
cp .env.example .env
```

Ensure the variables in `.env` match your local environment:
```env
APP_NAME=LOGO Backend
ENVIRONMENT=development

# Configure your local PostgreSQL username, password, host, and port
DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/logo_trial_db

# JWT Configuration (generate a 32+ char random string)
JWT_SECRET_KEY=9f8e7d6c5b4a3210987654321fedcba0123456789abcdef0123456789abcdef0
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# OTP Configuration
OTP_EXPIRE_MINUTES=5

# Google OAuth 2.0 (Optional for trial dev, set when ready)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback
```

> **Security Note:** `.env` is listed in `.gitignore` and must never be committed to source control.

---

## Database Migrations (Alembic)

Run the initial migration to create the `users` and `otp_verifications` tables:

```bash
# Upgrade database to latest revision
alembic upgrade head
```

To roll back a migration:
```bash
alembic downgrade -1
```

---

## Running the Server

Start the FastAPI application using Uvicorn with auto-reload:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The server will be available at: `http://127.0.0.1:8000`

---

## Interactive API Documentation (Swagger)

Once the server is running, visit:
- **Swagger UI:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc:** [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
- **OpenAPI JSON:** [http://127.0.0.1:8000/openapi.json](http://127.0.0.1:8000/openapi.json)

In Swagger UI:
- Click the **Authorize** button (padlock icon) at the top right.
- Paste your Bearer `access_token` to authenticate protected endpoints (such as `GET /api/v1/auth/me` and `GET /api/v1/auth/admin-test`).

---

## API Walkthrough & Testing Examples

### 1. Health Check
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/health"
```
**Response (200 OK):**
```json
{
  "status": "ok",
  "service": "LOGO Backend"
}
```

---

### 2. User Registration
Registers a new user. The default role assigned is **`PUBLIC_USER`**. Passwords are encrypted with bcrypt.
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test User",
    "email": "test@example.com",
    "phone": "9876543210",
    "password": "TestPassword123"
  }'
```
**Response (201 Created):**
```json
{
  "message": "User registered successfully",
  "user": {
    "id": 1,
    "name": "Test User",
    "email": "test@example.com",
    "phone": "9876543210",
    "role": "PUBLIC_USER",
    "is_verified": false
  }
}
```

---

### 3. User Login
Authenticates email and password, returning an access and refresh token pair.
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "TestPassword123"
  }'
```
**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsIn...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsIn...",
  "token_type": "bearer"
}
```

---

### 4. Authenticated Profile (`GET /me`)
Retrieves the logged-in user profile using the Bearer token:
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/auth/me" \
  -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>"
```
**Response (200 OK):**
```json
{
  "id": 1,
  "name": "Test User",
  "email": "test@example.com",
  "phone": "9876543210",
  "role": "PUBLIC_USER",
  "is_verified": false
}
```

---

### 5. Token Refresh
Exchanges a valid refresh token for a newly issued access token:
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/auth/refresh" \
  -H "Content-Type: application/json" \
  -d '{
    "refresh_token": "<YOUR_REFRESH_TOKEN>"
  }'
```

---

### 6. OTP Flow (Send & Verify)
For local development, when `ENVIRONMENT=development`, generated OTPs are printed to the server console and provided in the `dev_otp` field for convenient trial testing.

1. **Request OTP:**
   ```bash
   curl -X POST "http://127.0.0.1:8000/api/v1/auth/send-otp" \
     -H "Content-Type: application/json" \
     -d '{
       "email": "test@example.com",
       "purpose": "ACCOUNT_VERIFICATION"
     }'
   ```
2. **Verify OTP:**
   ```bash
   curl -X POST "http://127.0.0.1:8000/api/v1/auth/verify-otp" \
     -H "Content-Type: application/json" \
     -d '{
       "email": "test@example.com",
       "otp": "123456",
       "purpose": "ACCOUNT_VERIFICATION"
     }'
   ```
   Upon successful verification of `ACCOUNT_VERIFICATION`, the user's `is_verified` column is automatically set to `true`.

---

### 7. Password Reset Flow
1. **Request Reset OTP:**
   ```bash
   curl -X POST "http://127.0.0.1:8000/api/v1/auth/forgot-password" \
     -H "Content-Type: application/json" \
     -d '{
       "email": "test@example.com"
     }'
   ```
2. **Submit New Password with OTP:**
   ```bash
   curl -X POST "http://127.0.0.1:8000/api/v1/auth/reset-password" \
     -H "Content-Type: application/json" \
     -d '{
       "email": "test@example.com",
       "otp": "123456",
       "new_password": "NewSecurePassword123"
     }'
   ```

---

### 8. Role-Based Authorization
The endpoint `GET /api/v1/auth/admin-test` is protected by `require_role(UserRole.ADMIN)`:
- Calling with a `PUBLIC_USER` or `MERCHANT` token results in **`403 Forbidden`**.
- Calling with an `ADMIN` token returns **`200 OK`**.

---

### 9. Google OAuth 2.0
- If unconfigured, calling `GET /api/v1/auth/google` returns HTTP 501 with instructions.
- To configure:
  1. Visit Google Cloud Console -> APIs & Credentials -> Create OAuth 2.0 Client IDs.
  2. Set Authorized Redirect URI to: `http://localhost:8000/api/v1/auth/google/callback`
  3. Add `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` to `.env`.
  4. Access `GET /api/v1/auth/google` to receive the authorization redirect URL.

---

## Running Automated Tests

Run the complete test suite with pytest:

```bash
pytest -v
```

The test suite runs with an isolated in-memory test database, thoroughly testing:
- Health check
- User registration & duplicate email constraints
- Authentication, wrong passwords, and inactive user rejection
- JWT creation, decoding, expiration handling, and invalid token rejection
- Token refresh rotation
- OTP generation, secure hashing, expiration, attempt limit enforcement, and account verification
- Password reset flow with OTP
- Role-based access control (Admin vs Public user)
- Google OAuth configuration handling

---

## Git Commands & Safety

1. Check repository status:
   ```bash
   git status
   ```
2. Confirm `.env` is ignored:
   ```bash
   git status --ignored
   ```
3. Stage and commit:
   ```bash
   git add .
   git commit -m "feat: add LOGO trial backend authentication"
   ```
