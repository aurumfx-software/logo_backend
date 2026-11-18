import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import SessionLocal
from app.db.models.merchant import MerchantProfile

def remove_dummies():
    db = SessionLocal()
    dummy_ids = [7, 11, 12, 13, 14, 47, 48, 49, 50, 51, 52, 53, 54, 56, 57, 58, 59, 60]

    dummies = db.query(MerchantProfile).filter(MerchantProfile.id.in_(dummy_ids)).all()
    print(f"Found {len(dummies)} dummy merchant records to delete:")
    for d in dummies:
        print(f" - Deleting ID {d.id}: {d.business_name} ({d.category}, {d.city})")
        db.delete(d)

    db.commit()
    remaining = db.query(MerchantProfile).count()
    print("\n==========================================")
    print(f" Deleted {len(dummies)} dummy test merchants successfully!")
    print(f" Total remaining real merchants in DB: {remaining}")
    print("==========================================\n")
    db.close()

if __name__ == "__main__":
    remove_dummies()
