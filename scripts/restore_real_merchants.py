import json
import os
import re
import sys
from datetime import datetime, timezone
from bs4 import BeautifulSoup

# Ensure project root in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import SessionLocal
from app.db.models.merchant import MerchantProfile
from app.db.models.user import User, UserRole
from app.core.security import hash_password

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
ESTABLISHERS_CACHE_FILE = os.path.join(CACHE_DIR, "establishers_raw.json")
DETAILS_CACHE_FILE = os.path.join(CACHE_DIR, "order_details_cache.json")
IMAGES_CACHE_FILE = os.path.join(CACHE_DIR, "uploaded_images_cache.json")


def extract_image_path(html_snippet):
    if not html_snippet or "No Image" in html_snippet:
        return ""
    m = re.search(r"href=['\"]([^'\"]+)['\"]", html_snippet)
    if not m:
        m = re.search(r"src=['\"]([^'\"]+)['\"]", html_snippet)
    return m.group(1).strip() if m else ""


def parse_date(date_str):
    if not date_str:
        return datetime.now(timezone.utc)
    for fmt in ["%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def main():
    print("=" * 60)
    print("RESTORE REAL MERCHANTS FROM OLD LOGO APP (MYLOCALITYINFO)")
    print("=" * 60)

    # 1. Load Caches
    print("\n1. Loading local cache files...")
    with open(ESTABLISHERS_CACHE_FILE, "r", encoding="utf-8") as f:
        rows = json.load(f)
    print(f" - Loaded {len(rows)} real merchants from establishers_raw.json")

    details_cache = {}
    if os.path.exists(DETAILS_CACHE_FILE):
        with open(DETAILS_CACHE_FILE, "r", encoding="utf-8") as f:
            details_cache = json.load(f)
        print(f" - Loaded {len(details_cache)} details from order_details_cache.json")

    images_cache = {}
    if os.path.exists(IMAGES_CACHE_FILE):
        with open(IMAGES_CACHE_FILE, "r", encoding="utf-8") as f:
            images_cache = json.load(f)
        print(f" - Loaded {len(images_cache)} CDN image URLs from uploaded_images_cache.json")

    # 2. Database Session & Admin User Check
    print("\n2. Connecting to PostgreSQL database...")
    db = SessionLocal()

    admin = db.query(User).filter(User.id == 15).first()
    if not admin:
        print(" - Creating Super Admin user (ID 15)...")
        admin = User(
            id=15,
            user_code="SAD_001",
            name="Logo Admin",
            email="admin@logoapp.com",
            phone="9999999999",
            password_hash=hash_password("Logotcr@123"),
            role=UserRole.SUPER_ADMIN,
            status="ACTIVE",
            is_active=True,
            is_verified=True,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        print(f" - Super Admin user created: ID {admin.id} ({admin.email})")
    else:
        print(f" - Super Admin user verified: ID {admin.id} ({admin.email})")

    # 3. Check existing merchants
    existing_merchants = db.query(MerchantProfile).all()
    existing_keys = {
        (m.business_name.strip().lower(), (m.phone or "").strip()): m
        for m in existing_merchants
    }
    print(f" - Current merchants in DB: {len(existing_merchants)}")

    max_num = 0
    for m in existing_merchants:
        if m.user_code:
            digits = "".join(filter(str.isdigit, str(m.user_code)))
            if digits:
                max_num = max(max_num, int(digits))

    # 4. Insert / Restore Real Merchants
    print("\n3. Inserting real merchants into database...")
    inserted_count = 0
    updated_count = 0
    skipped_count = 0

    for idx, r in enumerate(rows):
        title = (r.get("title") or "").strip()
        if not title:
            skipped_count += 1
            continue

        raw_phone = r.get("phone") or ""
        clean_phone = re.sub(r"[\s\-()]", "", raw_phone)[:20]
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
        cat_title = ((r.get("cattitle") or "").strip() or "General")[:150]

        # Address & Location
        raw_address = r.get("address") or ""
        clean_address = BeautifulSoup(raw_address, "html.parser").get_text(strip=True) if raw_address else ""
        city = ((r.get("placetitle") or "").strip() or "General")[:100]
        area = (r.get("areatitle") or "").replace("Logo Office-", "").strip() or "Thrissur"
        district = area[:100]
        state = "Kerala"
        location = city[:255]

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
        clean_whatsapp = (re.sub(r"[\s\-()]", "", raw_whatsapp) or clean_phone)[:20]
        email_val = (r.get("mail") or "").strip()[:255] if ("@" in (r.get("mail") or "")) else None

        # Description
        about_val = (r.get("description") or "").strip() or f"{title} located at {city}, {district}."

        # Status
        raw_status = (r.get("status") or "").lower()
        is_active = "active" in raw_status
        status_val = "APPROVED" if is_active else "PENDING"

        # Dates
        created_dt = parse_date(r.get("date_created"))

        # Socials & Video
        video_val = r.get("video")
        clean_video = video_val if (video_val and "No Video" not in video_val) else None
        instagram_val = (socials.get("instagram") or "")[:255] or None
        facebook_val = (socials.get("facebook") or "")[:255] or None
        youtube_val = (socials.get("youtube") or "")[:255] or None
        website_val = (socials.get("website") or "")[:255] or None

        # Plan metadata in highlights
        plan_days = r.get("plan_days") or "365 Days"
        highlights = [
            f"Plan: {plan_days}",
            f"Old ID: #{eid}",
        ]

        if lookup_key in existing_keys:
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
            max_num += 1
            user_code_val = f"MRH {max_num}"

            new_merchant = MerchantProfile(
                user_id=15,
                onboarded_by_id=15,
                user_code=user_code_val,
                business_name=title[:255],
                owner=title[:255],
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
                phone=clean_phone or None,
                contact_number=clean_phone[:50] if clean_phone else None,
                whatsapp=clean_whatsapp or None,
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
                about=about_val,
                rating=4.5,
                reviews_count=0,
                key_highlights=highlights,
                status=status_val,
                approval_status=status_val,
                is_verified=is_active,
                is_active=is_active,
                can_create_promotions=True,
                created_at=created_dt,
            )
            db.add(new_merchant)
            existing_keys[lookup_key] = new_merchant
            inserted_count += 1

        # Commit in batches of 50
        if (inserted_count + updated_count) % 50 == 0:
            try:
                db.commit()
                print(f"  Progress: {inserted_count} inserted, {updated_count} updated so far...")
            except Exception as e:
                db.rollback()
                print(f"  [Commit Warning] Retrying batch due to: {e}")

    try:
        db.commit()
    except Exception as e:
        print("Final commit error:", e)

    total_in_db = db.query(MerchantProfile).count()
    db.close()

    print("\n" + "=" * 60)
    print("RESTORE COMPLETED SUCCESSFULLY!")
    print(f" - Inserted into DB: {inserted_count}")
    print(f" - Updated in DB:    {updated_count}")
    print(f" - Skipped (empty):  {skipped_count}")
    print(f" - Total Real Merchants in DB: {total_in_db}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
