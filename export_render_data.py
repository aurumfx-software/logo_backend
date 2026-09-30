import json
import os
from sqlalchemy import create_engine, text

RENDER_URL = "postgresql+psycopg://logo_db_i1z5_user:XvLtPsH2xQhIDEZup0aDpv7uYEFaJzfW@dpg-daobo4egekts73bl9c9g-a.singapore-postgres.render.com/logo_db_i1z5"
OUTPUT_FILE = os.path.join(os.getcwd(), "render_live_data_backup.sql")

engine = create_engine(RENDER_URL)

TABLES_IN_ORDER = [
    "users",
    "categories",
    "merchant_profiles",
    "merchant_photos",
    "merchant_services",
    "user_otps",
    "audit_logs"
]

def format_val(val):
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, (list, dict)):
        # serialize to JSON string and escape single quotes for SQL
        json_str = json.dumps(val).replace("'", "''")
        return f"'{json_str}'"
    # string / datetime
    s = str(val).replace("'", "''")
    return f"'{s}'"

with engine.connect() as conn:
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("-- Render Live DB Data Backup --\n")
        f.write("SET session_replication_role = 'replica';\n\n")

        for table in TABLES_IN_ORDER:
            # check if table exists
            exists = conn.execute(text(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{table}')")).scalar()
            if not exists:
                continue

            cols_info = conn.execute(text(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}' ORDER BY ordinal_position")).fetchall()
            cols = [c[0] for c in cols_info]
            cols_str = ", ".join([f'"{c}"' for c in cols])

            rows = conn.execute(text(f'SELECT {cols_str} FROM "{table}" ORDER BY id')).fetchall()
            if not rows:
                continue

            f.write(f"-- Data for table: {table} ({len(rows)} rows) --\n")
            for row in rows:
                vals = [format_val(v) for v in row]
                vals_str = ", ".join(vals)
                f.write(f'INSERT INTO "{table}" ({cols_str}) VALUES ({vals_str}) ON CONFLICT DO NOTHING;\n')

            # update sequence if exists
            has_id = "id" in cols
            if has_id:
                f.write(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE((SELECT MAX(id) FROM \"{table}\"), 1), true);\n")
            f.write("\n")

        f.write("SET session_replication_role = 'origin';\n")

print(f"Backup exported successfully to: {OUTPUT_FILE}")
