from app.db.database import engine
from sqlalchemy import text
from app.core.security import hash_password

pwd = hash_password("admin123")

with engine.connect() as conn:
    conn.execute(text("UPDATE users SET role = 'ADMIN', status = 'ACTIVE' WHERE LOWER(role) = 'admin'"))
    conn.execute(text("UPDATE users SET password_hash = :pwd, password = :pwd, is_active = true WHERE email = 'admin@aurumfx.in'"), {"pwd": pwd})
    
    res = conn.execute(text("SELECT id FROM users WHERE email = 'admin@aurumfx.com'")).fetchone()
    if not res:
        conn.execute(text("""
            INSERT INTO users (user_code, name, email, phone, password, password_hash, role, status, is_active, is_verified, send_email, created_at, updated_at)
            VALUES ('ADM_4', 'Admin', 'admin@aurumfx.com', '9876543200', :pwd, :pwd, 'ADMIN', 'ACTIVE', true, true, false, NOW(), NOW())
        """), {"pwd": pwd})
    else:
        conn.execute(text("UPDATE users SET password_hash = :pwd, password = :pwd, role = 'ADMIN', status = 'ACTIVE', is_active = true WHERE email = 'admin@aurumfx.com'"), {"pwd": pwd})
        
    conn.commit()
    print("Users table updated successfully!")
    
    rows = conn.execute(text("SELECT id, user_code, name, email, role, status, is_active FROM users;")).fetchall()
    for r in rows:
        print(r)
