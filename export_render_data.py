"""Export selected tables from DATABASE_URL to a local SQL backup file."""

import json
import os
import sys

from sqlalchemy import create_engine, text

OUTPUT_FILE = os.environ.get(
    "DB_BACKUP_OUTPUT",
    os.path.join(os.getcwd(), "render_live_data_backup.sql"),
)


def _normalize_db_url(url: str) -> str:
    url = url.strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://") and not url.startswith("postgresql+psycopg://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        print("Set DATABASE_URL to the PostgreSQL connection string.", file=sys.stderr)
        sys.exit(1)
    return _normalize_db_url(url)


TABLES_IN_ORDER = [
    "users",
    "categories",
    "merchant_profiles",
    "merchant_photos",
    "merchant_services",
    "user_otps",
    "audit_logs",
]


def format_val(val):
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, (list, dict)):
        json_str = json.dumps(val).replace("'", "''")
        return f"'{json_str}'"
    s = str(val).replace("'", "''")
    return f"'{s}'"


def main() -> None:
    engine = create_engine(_database_url())

    with engine.connect() as conn:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("-- Database data backup --\n")
            f.write("SET session_replication_role = 'replica';\n\n")

            for table in TABLES_IN_ORDER:
                exists = conn.execute(
                    text(
                        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :table)"
                    ),
                    {"table": table},
                ).scalar()
                if not exists:
                    continue

                cols_info = conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = :table ORDER BY ordinal_position"
                    ),
                    {"table": table},
                ).fetchall()
                cols = [c[0] for c in cols_info]
                cols_str = ", ".join([f'"{c}"' for c in cols])

                rows = conn.execute(text(f'SELECT {cols_str} FROM "{table}" ORDER BY id')).fetchall()
                if not rows:
                    continue

                f.write(f"-- Data for table: {table} ({len(rows)} rows) --\n")
                for row in rows:
                    vals = [format_val(v) for v in row]
                    vals_str = ", ".join(vals)
                    f.write(
                        f'INSERT INTO "{table}" ({cols_str}) VALUES ({vals_str}) ON CONFLICT DO NOTHING;\n'
                    )

                if "id" in cols:
                    f.write(
                        f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                        f'COALESCE((SELECT MAX(id) FROM "{table}"), 1), true);\n'
                    )
                f.write("\n")

            f.write("SET session_replication_role = 'origin';\n")

    print(f"Backup exported successfully to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
