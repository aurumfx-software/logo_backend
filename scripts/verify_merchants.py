import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app.db.database import SessionLocal
from app.db.models.merchant import MerchantProfile

def verify():
    db = SessionLocal()
    total = db.query(MerchantProfile).count()
    with_photos = db.query(MerchantProfile).filter(MerchantProfile.photo_1.isnot(None)).count()
    with_cdn = db.query(MerchantProfile).filter(MerchantProfile.photo_1.like('%digitaloceanspaces%')).count()
    with_socials = db.query(MerchantProfile).filter(MerchantProfile.instagram.isnot(None)).count()
    with_coords = db.query(MerchantProfile).filter(MerchantProfile.latitude.isnot(None)).count()
    active_count = db.query(MerchantProfile).filter(MerchantProfile.is_active == True).count()

    print("========================================")
    print(f"Total Merchants in PostgreSQL: {total}")
    print(f"Merchants with Photo 1:        {with_photos}")
    print(f"Merchants with Spaces CDN URL: {with_cdn}")
    print(f"Merchants with Social Links:   {with_socials}")
    print(f"Merchants with Coordinates:    {with_coords}")
    print(f"Active / Approved Merchants:   {active_count}")
    print("========================================")

    sample = db.query(MerchantProfile).filter(MerchantProfile.photo_1.like('%digitaloceanspaces%')).order_by(MerchantProfile.id.desc()).limit(3).all()
    for m in sample:
        print(f"\nID: {m.id} | Code: {m.user_code} | Name: {m.business_name} | Cat: {m.category} | City: {m.city}")
        print(f"  Photo 1 (CDN): {m.photo_1}")
        print(f"  Photo 2 (Slider): {m.photo_2}")
        print(f"  Instagram: {m.instagram}")
        print(f"  Status: {m.status} | Verified: {m.is_verified}")

    db.close()

if __name__ == "__main__":
    verify()
