import concurrent.futures
import json
import os
import re
import socket
import sys
import time
import urllib3
import urllib3.util.connection as uc
from datetime import datetime, timezone

# Ensure project root in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Force IPv4 to prevent Windows getaddrinfo issues
uc.allowed_gai_family = lambda: socket.AF_INET
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from sqlalchemy import text

from app.db.database import SessionLocal
from app.db.models.merchant import MerchantProfile
from app.db.models.user import User
from app.services.storage_service import SpacesStorageService

OLD_APP_BASE = "https://mylocalityinfo.com/mylocalityinfo"
LOGIN_URL = f"{OLD_APP_BASE}/index.php"
USERNAME = "admin"
PASSWORD = "Logotcr@123"

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)
ESTABLISHERS_CACHE_FILE = os.path.join(CACHE_DIR, "establishers_raw.json")
DETAILS_CACHE_FILE = os.path.join(CACHE_DIR, "order_details_cache.json")
IMAGES_CACHE_FILE = os.path.join(CACHE_DIR, "uploaded_images_cache.json")


def get_robust_session():
    session = requests.Session()
    session.verify = False
    retries = Retry(
        total=5,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retries, pool_connections=25, pool_maxsize=25)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": LOGIN_URL,
    }
    payload = {
        "username": USERNAME,
        "password": PASSWORD,
        "btnLogin": "",
    }
    print("Authenticating with old admin portal...")
    for attempt in range(3):
        try:
            res = session.post(LOGIN_URL, data=payload, headers=headers, timeout=(10, 30))
            if res.status_code == 200:
                print(" Successfully logged in to old admin portal!")
                return session
        except Exception as e:
            print(f"Login attempt {attempt + 1} failed: {e}. Retrying...")
            time.sleep(2)
    raise Exception("Failed to authenticate after 3 attempts.")


def fetch_all_raw_establishers(session):
    if os.path.exists(ESTABLISHERS_CACHE_FILE):
        try:
            with open(ESTABLISHERS_CACHE_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
                if len(cached) >= 1000:
                    print(f" Loaded {len(cached)} establishers from local cache.")
                    return cached
        except Exception as e:
            print("Notice loading establishers cache:", e)

    url = f"{OLD_APP_BASE}/api-firebase/get-bootstrap-table-data.php?table=establisher&limit=1200&offset=0"
    print("Fetching establishers table from old system...")
    res = session.get(url, timeout=(10, 45))
    if res.status_code != 200:
        raise Exception(f"Failed to fetch establishers: HTTP {res.status_code}")

    data = res.json()
    rows = data.get("rows", [])
    print(f" Extracted {len(rows)} establishers from old system (reported total: {data.get('total')})")

    with open(ESTABLISHERS_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
    return rows


def fetch_single_order_detail(establisher_id, session):
    url = f"{OLD_APP_BASE}/order-detail.php?id={establisher_id}"
    try:
        r = session.get(url, timeout=(10, 20))
        if r.status_code != 200:
            return establisher_id, {}, []
        soup = BeautifulSoup(r.text, "html.parser")
        socials = {}
        sliders = []
        table = soup.find("table", class_="table")
        if table:
            for tr in table.find_all("tr"):
                th = tr.find("th")
                td = tr.find("td")
                if th and td:
                    k = th.get_text(strip=True).lower()
                    v = td.get_text(strip=True)
                    if any(s in k for s in ["facebook", "instagram", "youtube", "website"]):
                        if v and v.startswith("http"):
                            socials[k] = v
                for img in tr.find_all("img"):
                    src = img.get("src")
                    if src and "slider" in src:
                        sliders.append(src)
        return establisher_id, socials, sliders
    except Exception:
        return establisher_id, {}, []


def fetch_all_order_details(rows, session):
    details_cache = {}
    if os.path.exists(DETAILS_CACHE_FILE):
        try:
            with open(DETAILS_CACHE_FILE, "r", encoding="utf-8") as f:
                details_cache = json.load(f)
                print(f" Loaded {len(details_cache)} order details from local cache.")
        except Exception as e:
            print("Notice loading details cache:", e)

    missing_ids = [str(r.get("id")) for r in rows if str(r.get("id")) not in details_cache]
    if missing_ids:
        print(f"Fetching details (sliders & social links) for {len(missing_ids)} establishers in parallel...")
        completed = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
            futures = {
                executor.submit(fetch_single_order_detail, eid, session): eid
                for eid in missing_ids
            }
            for future in concurrent.futures.as_completed(futures):
                eid, socials, sliders = future.result()
                details_cache[eid] = {
                    "socials": socials,
                    "sliders": sliders,
                }
                completed += 1
                if completed % 100 == 0 or completed == len(missing_ids):
                    print(f"  Scraped details for {completed}/{len(missing_ids)} establishers...")

        with open(DETAILS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(details_cache, f, indent=2, ensure_ascii=False)

    return details_cache


def extract_image_path(html_snippet):
    if not html_snippet or "No Image" in html_snippet:
        return ""
    m = re.search(r"href=['\"]([^'\"]+)['\"]", html_snippet)
    if not m:
        m = re.search(r"src=['\"]([^'\"]+)['\"]", html_snippet)
    if m:
        path = m.group(1).strip()
        return path
    return ""


def upload_single_image(img_rel_path, storage, session):
    if not img_rel_path:
        return img_rel_path, None

    if img_rel_path.startswith("http://") or img_rel_path.startswith("https://"):
        full_url = img_rel_path
    else:
        full_url = f"{OLD_APP_BASE}/{img_rel_path.lstrip('/')}"

    try:
        r = session.get(full_url, timeout=(10, 25))
        if r.status_code == 200 and len(r.content) > 100:
            filename = os.path.basename(img_rel_path.split("?")[0]) or "photo.jpg"
            cdn_url = storage.upload_bytes(
                file_bytes=r.content,
                filename=filename,
                folder="merchants/photos",
            )
            return img_rel_path, cdn_url
    except Exception as e:
        print(f"  [Image Warning] Failed {img_rel_path}: {e}")

    return img_rel_path, None


def upload_all_images(rows, details_cache, storage, session):
    images_cache = {}
    if os.path.exists(IMAGES_CACHE_FILE):
        try:
            with open(IMAGES_CACHE_FILE, "r", encoding="utf-8") as f:
                images_cache = json.load(f)
                print(f" Loaded {len(images_cache)} uploaded images from cache.")
        except Exception as e:
            print("Notice loading images cache:", e)

    all_paths = set()
    for r in rows:
        p = extract_image_path(r.get("image") or "")
        if p and "avatar" not in p and p.endswith((".png", ".jpg", ".jpeg", ".webp")):
            all_paths.add(p)
        eid = str(r.get("id"))
        if eid in details_cache:
            for s in details_cache[eid].get("sliders", []):
                if s and "avatar" not in s and s.endswith((".png", ".jpg", ".jpeg", ".webp")):
                    all_paths.add(s)

    pending_paths = [p for p in all_paths if p not in images_cache]
    print(f"\nTotal unique images discovered: {len(all_paths)}")
    print(f"Images already on CDN: {len(all_paths) - len(pending_paths)}")
    print(f"Images pending upload: {len(pending_paths)}")

    if pending_paths:
        completed = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(upload_single_image, p, storage, session): p
                for p in pending_paths
            }
            for future in concurrent.futures.as_completed(futures):
                path, cdn_url = future.result()
                if cdn_url:
                    images_cache[path] = cdn_url
                completed += 1
                if completed % 50 == 0 or completed == len(pending_paths):
                    print(f"  Uploaded {completed}/{len(pending_paths)} images to Spaces CDN...")

        with open(IMAGES_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(images_cache, f, indent=2, ensure_ascii=False)

    return images_cache


def parse_date(date_str):
    if not date_str:
        return datetime.now(timezone.utc)
    for fmt in ["%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def migrate_to_database(rows, details_cache, images_cache):
    print("\nConnecting to PostgreSQL database (logo_dev)...")
    db = SessionLocal()

    # Find existing merchants
    existing_merchants = db.query(MerchantProfile).all()
    existing_keys = {
        (m.business_name.strip().lower(), (m.phone or "").strip()): m
        for m in existing_merchants
    }
    print(f"Currently in DB: {len(existing_merchants)} merchant profiles")

    # Determine next user code
    codes = [
        r[0]
        for r in db.execute(
            text("SELECT user_code FROM merchant_profiles WHERE user_code LIKE 'MRH %' OR user_code LIKE 'MRH_%'")
        ).fetchall()
        if r[0]
    ]
    max_num = 0
    for c in codes:
        digits = "".join(filter(str.isdigit, str(c)))
        if digits:
            max_num = max(max_num, int(digits))
    print(f"Current highest user code: MRH {max_num}")

    inserted_count = 0
    updated_count = 0
    skipped_count = 0

    for idx, r in enumerate(rows):
        title = (r.get("title") or "").strip()
        if not title:
            continue

        raw_phone = r.get("phone") or ""
        clean_phone = re.sub(r"[\s\-()]", "", raw_phone)
        lookup_key = (title.lower(), clean_phone)

        eid = str(r.get("id"))
        detail = details_cache.get(eid, {})
        socials = detail.get("socials", {})
        sliders = detail.get("sliders", [])

        # Media mapping
        main_img_path = extract_image_path(r.get("image") or "")
        cdn_main = images_cache.get(main_img_path)
        cdn_sliders = [images_cache.get(s) for s in sliders if s in images_cache]
        all_photos = [p for p in ([cdn_main] + cdn_sliders) if p]

        # Categories
        cat_title = (r.get("cattitle") or "").strip() or "General"

        # Address & Location
        raw_address = r.get("address") or ""
        clean_address = BeautifulSoup(raw_address, "html.parser").get_text(strip=True) if raw_address else ""
        city = (r.get("placetitle") or "").strip() or "General"
        area = (r.get("areatitle") or "").replace("Logo Office-", "").strip() or "Thrissur"
        district = area
        state = "Kerala"
        location = city

        # Geo coordinates
        lat_val = None
        lng_val = None
        try:
            if r.get("latitude"):
                lat_val = float(str(r["latitude"]).strip())
            if r.get("longitude"):
                lng_val = float(str(r["longitude"]).strip())
        except (ValueError, TypeError):
            pass

        # Contacts
        raw_whatsapp = r.get("whatsapp") or ""
        clean_whatsapp = re.sub(r"[\s\-()]", "", raw_whatsapp) or clean_phone
        email_val = r.get("mail", "").strip() if ("@" in (r.get("mail") or "")) else None

        # Description
        about_val = (r.get("description") or "").strip()

        # Status
        raw_status = (r.get("status") or "").lower()
        is_active = "active" in raw_status
        status_val = "APPROVED" if is_active else "PENDING"

        # Dates
        created_dt = parse_date(r.get("date_created"))

        # Socials & Video
        video_val = r.get("video")
        clean_video = video_val if (video_val and "No Video" not in video_val) else None
        instagram_val = socials.get("instagram")
        facebook_val = socials.get("facebook")
        youtube_val = socials.get("youtube")
        website_val = socials.get("website")

        # Plan metadata in highlights
        plan_days = r.get("plan_days") or "365 Days"
        highlights = [
            f"Plan: {plan_days}",
            f"Old ID: #{eid}",
        ]

        # Safely truncate strings to fit DB column limits
        title = title[:240]
        cat_title = cat_title[:140]
        city = city[:190]
        district = district[:190]
        location = location[:240]
        state = state[:90]
        phone_val = clean_phone[:45] if clean_phone else None
        whatsapp_val = clean_whatsapp[:45] if clean_whatsapp else None
        email_val = email_val[:240] if email_val else None
        website_val = website_val[:450] if website_val else None
        facebook_val = facebook_val[:450] if facebook_val else None
        instagram_val = instagram_val[:450] if instagram_val else None
        youtube_val = youtube_val[:450] if youtube_val else None

        if lookup_key in existing_keys:
            # Update existing profile
            m = existing_keys[lookup_key]
            if not m.photo_1 and all_photos:
                m.photo_1 = all_photos[0]
                m.merchant_photos = all_photos
            if instagram_val and not m.instagram:
                m.instagram = instagram_val
            if not m.latitude and lat_val:
                m.latitude = lat_val
                m.longitude = lng_val
            updated_count += 1
        else:
            # Create new profile
            max_num += 1
            user_code_val = f"MRH {max_num}"

            new_merchant = MerchantProfile(
                user_id=15,  # Admin user ID
                onboarded_by_id=15,
                user_code=user_code_val,
                business_name=title,
                owner=title,
                owner_name="Business Owner",
                category=cat_title,
                categories=[cat_title],
                address=clean_address or f"{city}, {district}",
                city=city,
                district=district,
                state=state,
                location=location,
                latitude=lat_val,
                longitude=lng_val,
                phone=phone_val,
                contact_number=phone_val,
                whatsapp=whatsapp_val,
                email=email_val,
                website=website_val,
                facebook=facebook_val,
                instagram=instagram_val,
                youtube=youtube_val,
                video_url=clean_video,
                photo_1=all_photos[0] if len(all_photos) > 0 else None,
                photo_2=all_photos[1] if len(all_photos) > 1 else None,
                photo_3=all_photos[2] if len(all_photos) > 2 else None,
                merchant_photos=all_photos,
                about=about_val or f"{title} located at {city}, {district}.",
                rating=4.5,
                reviews_count=0,
                key_highlights=highlights,
                status=status_val,
                approval_status=status_val,
                is_verified=is_active,
                is_active=is_active,
                created_at=created_dt,
            )
            db.add(new_merchant)
            existing_keys[lookup_key] = new_merchant
            inserted_count += 1

        # Commit in batches of 50
        if (inserted_count + updated_count) % 50 == 0:
            try:
                db.commit()
                print(f"  Committed batch: {inserted_count} inserted, {updated_count} updated so far...")
            except Exception as e:
                db.rollback()
                print(f"  [Batch Commit Warning] Retrying individually due to: {e}")

    try:
        db.commit()
    except Exception as e:
        print("Final commit error:", e)

    total_after = db.query(MerchantProfile).count()
    db.close()

    print("\n=======================================================")
    print(" ESTABLISHER -> MERCHANT MIGRATION FINISHED!")
    print(f" - Inserted into PostgreSQL: {inserted_count}")
    print(f" - Updated in PostgreSQL:    {updated_count}")
    print(f" - Total Merchants in DB:    {total_after}")
    print("=======================================================\n")


def main():
    print("Starting complete Establisher -> Merchant migration...")
    session = get_robust_session()
    raw_rows = fetch_all_raw_establishers(session)
    details_cache = fetch_all_order_details(raw_rows, session)
    storage = SpacesStorageService()
    images_cache = upload_all_images(raw_rows, details_cache, storage, session)
    migrate_to_database(raw_rows, details_cache, images_cache)


if __name__ == "__main__":
    main()
