import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import SessionLocal
from app.db.models.merchant import MerchantProfile

db = SessionLocal()
all_merchants = db.query(MerchantProfile).all()
dummies = []
migrated = []

for m in all_merchants:
    hl = m.key_highlights or []
    is_migrated = any("Old ID" in str(h) for h in hl)
    if is_migrated:
        migrated.append(m)
    else:
        dummies.append(m)

print(f"Total in DB: {len(all_merchants)}")
print(f"Migrated real records: {len(migrated)}")
print(f"Dummy test records: {len(dummies)}")
print("\nDummy records list:")
for d in dummies:
    print(f"  ID {d.id}: {d.business_name} | {d.category} | {d.city} | Status: {d.status}")

db.close()
