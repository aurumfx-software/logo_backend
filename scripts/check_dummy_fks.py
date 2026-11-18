import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
dummy_ids = [7, 11, 12, 13, 14, 47, 48, 49, 50, 51, 52, 53, 54, 56, 57, 58, 59, 60]

# Check foreign keys to merchant_profiles
res = db.execute(text("""
    SELECT
        tc.table_name, kcu.column_name
    FROM
        information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
          ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage AS ccu
          ON ccu.constraint_name = tc.constraint_name
    WHERE tc.constraint_type = 'FOREIGN KEY' AND ccu.table_name='merchant_profiles';
""")).fetchall()
print("Tables referencing merchant_profiles:", res)

for tbl, col in res:
    cnt = db.execute(text(f"SELECT COUNT(*) FROM {tbl} WHERE {col} IN ({','.join(map(str, dummy_ids))})")).scalar()
    print(f"Table {tbl}.{col} has {cnt} rows referencing dummy merchants")

db.close()
