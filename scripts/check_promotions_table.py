import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from app.db.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    rows = conn.execute(text("SELECT id, title, placement, status, description FROM promotions WHERE placement ILIKE '%moving%' OR placement ILIKE '%ticker%' ORDER BY id ASC")).fetchall()
    print(f"Total Moving Text in PostgreSQL: {len(rows)}")
    for r in rows:
        print(f"ID {r[0]} | {r[1]} | Placement: {r[2]} | Status: {r[3]}")
