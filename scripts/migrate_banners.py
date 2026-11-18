import os
import sys
import re
import socket
import urllib3
import urllib3.util.connection as uc
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

uc.allowed_gai_family = lambda: socket.AF_INET
urllib3.disable_warnings()

from app.db.database import SessionLocal
from app.db.models.promotion import Promotion
from app.services.storage_service import SpacesStorageService

OLD_APP_BASE = "https://mylocalityinfo.com/mylocalityinfo"
LOGIN_URL = f"{OLD_APP_BASE}/index.php"

session = requests.Session()
session.verify = False
headers = {"User-Agent": "Mozilla/5.0"}
session.post(LOGIN_URL, data={"username": "admin", "password": "Logotcr@123", "btnLogin": ""}, headers=headers)

storage = SpacesStorageService()
db = SessionLocal()

r = session.get(f"{OLD_APP_BASE}/api-firebase/get-bootstrap-table-data.php?table=banner&limit=20", headers=headers)
rows = r.json().get("rows", [])
print(f"Found {len(rows)} banners in old system")

inserted = 0
for idx, b in enumerate(rows):
    img_html = b.get("image") or ""
    m = re.search(r"href=['\"]([^'\"]+)['\"]", img_html) or re.search(r"src=['\"]([^'\"]+)['\"]", img_html)
    if not m:
        continue
    img_path = m.group(1).strip()
    full_url = f"{OLD_APP_BASE}/{img_path.lstrip('/')}"
    shop_name = b.get("shope") or "Featured Promotion"
    if shop_name == "Not Available" or not shop_name:
        shop_name = f"Special Offer #{idx + 1}"

    # Check if already exists in promotions
    existing = db.query(Promotion).filter(Promotion.title == shop_name).first()
    if existing and existing.image_url:
        print(f"Banner '{shop_name}' already exists, skipping")
        continue

    print(f"Downloading banner: {full_url}")
    img_res = session.get(full_url, timeout=15)
    cdn_url = None
    if img_res.status_code == 200 and len(img_res.content) > 100:
        filename = os.path.basename(img_path.split("?")[0]) or "banner.jpg"
        cdn_url = storage.upload_bytes(img_res.content, filename=filename, folder="banners")
        print(f"  Uploaded to Spaces: {cdn_url}")

    if not existing:
        promo = Promotion(
            title=shop_name,
            category="Retail & Shopping",
            type="Banner",
            placement="Home Top",
            location="Kerala",
            start_date="2026-10-01",
            end_date="2027-12-31",
            status="active",
            image_url=cdn_url,
            target_url="#",
        )
        db.add(promo)
        inserted += 1
    else:
        existing.image_url = cdn_url
        existing.type = "Banner"
        existing.placement = "Home Top"
        existing.status = "active"

db.commit()
total_promos = db.query(Promotion).count()
print(f"\nMigration completed! Inserted {inserted} new banners. Total promotions in DB: {total_promos}")
for p in db.query(Promotion).all():
    print(f"  ID {p.id}: {p.title} | Type: {p.type} | Image: {p.image_url} | Status: {p.status}")
db.close()
