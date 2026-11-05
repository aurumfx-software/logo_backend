"""One-off script to normalize admin roles. Requires ADMIN_BOOTSTRAP_PASSWORD in the environment."""

import os
import sys

from sqlalchemy import text

from app.core.security import hash_password
from app.db.database import engine


def main() -> None:
    raw_password = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD", "").strip()
    if not raw_password:
        print("Set ADMIN_BOOTSTRAP_PASSWORD before running this script.", file=sys.stderr)
        sys.exit(1)

    pwd = hash_password(raw_password)

    with engine.connect() as conn:
        conn.execute(
            text("UPDATE users SET role = 'ADMIN', status = 'ACTIVE' WHERE LOWER(role) = 'admin'")
        )
        conn.execute(
            text(
                "UPDATE users SET password_hash = :pwd, password = :pwd, is_active = true "
                "WHERE email = 'admin@aurumfx.in'"
            ),
            {"pwd": pwd},
        )

        res = conn.execute(text("SELECT id FROM users WHERE email = 'admin@aurumfx.com'")).fetchone()
        if not res:
            conn.execute(
                text(
                    """
                    INSERT INTO users (
                        user_code, name, email, phone, password, password_hash,
                        role, status, is_active, is_verified, send_email, created_at, updated_at
                    )
                    VALUES (
                        'ADM_4', 'Admin', 'admin@aurumfx.com', '9876543200',
                        :pwd, :pwd, 'ADMIN', 'ACTIVE', true, true, false, NOW(), NOW()
                    )
                    """
                ),
                {"pwd": pwd},
            )
        else:
            conn.execute(
                text(
                    "UPDATE users SET password_hash = :pwd, password = :pwd, role = 'ADMIN', "
                    "status = 'ACTIVE', is_active = true WHERE email = 'admin@aurumfx.com'"
                ),
                {"pwd": pwd},
            )

        conn.commit()
        print("Users table updated successfully.")


if __name__ == "__main__":
    main()
