import concurrent.futures
import os
import re
import socket
import sys
import time
import urllib3
import urllib3.util.connection as uc

# Force IPv4 to prevent Windows getaddrinfo issues
uc.allowed_gai_family = lambda: socket.AF_INET
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import requests
from bs4 import BeautifulSoup

from app.db.database import SessionLocal
from app.db.models.logo import LogoCategory
from app.services.category_service import slugify
from app.services.storage_service import SpacesStorageService


OLD_APP_BASE = "https://mylocalityinfo.com/mylocalityinfo"
LOGIN_URL = f"{OLD_APP_BASE}/index.php"
USERNAME = "admin"
PASSWORD = "Logotcr@123"


def get_authenticated_session():
    session = requests.Session()
    session.verify = False
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": LOGIN_URL,
    }
    payload = {
        "username": USERNAME,
        "password": PASSWORD,
        "btnLogin": "",
    }
    print("Logging into old admin panel...")
    res = session.post(LOGIN_URL, data=payload, headers=headers, timeout=15)
    if res.status_code != 200:
        raise Exception(f"Failed to log in: HTTP {res.status_code}")
    print("Successfully authenticated with old admin portal!")
    return session


def extract_image_url(html_snippet: str, base_url: str) -> str:
    if not html_snippet:
        return ""
    # Try finding href or src in snippet
    m = re.search(r"href=['\"]([^'\"]+)['\"]", html_snippet)
    if not m:
        m = re.search(r"src=['\"]([^'\"]+)['\"]", html_snippet)
    if m:
        path = m.group(1).strip()
        if path.startswith("http"):
            return path
        return f"{base_url}/{path.lstrip('/')}"
    return ""


def fetch_all_old_categories(session: requests.Session):
    tables = [
        ("category", 500),
        ("ec_category", 100),
        ("ec_subcategory", 100),
    ]
    all_categories = []
    seen_titles = set()

    for table_name, limit in tables:
        url = f"{OLD_APP_BASE}/api-firebase/get-bootstrap-table-data.php?table={table_name}&limit={limit}&offset=0"
        print(f"Fetching categories from {table_name}...")
        res = session.get(url, timeout=20)
        if res.status_code != 200:
            print(f"Warning: Failed to fetch {table_name}, HTTP {res.status_code}")
            continue

        try:
            data = res.json()
            rows = data.get("rows", [])
            print(f"  Found {len(rows)} rows in {table_name}")
            for row in rows:
                raw_title = row.get("title") or ""
                title = raw_title.strip()
                if not title or title.lower() in seen_titles:
                    continue
                seen_titles.add(title.lower())

                img_html = row.get("image") or ""
                image_url = extract_image_url(img_html, OLD_APP_BASE)
                status_html = row.get("status") or ""
                is_active = "active" in status_html.lower()

                all_categories.append({
                    "title": title,
                    "image_url": image_url,
                    "is_active": is_active,
                    "source_table": table_name,
                    "old_id": row.get("id"),
                })
        except Exception as e:
            print(f"Error parsing JSON from {table_name}: {e}")

    print(f"\nTotal unique categories collected: {len(all_categories)}")
    return all_categories


def process_single_category(cat: dict, storage: SpacesStorageService, session: requests.Session):
    """Download image and upload to DigitalOcean Spaces, returning processed category data."""
    title = cat["title"]
    image_url = cat["image_url"]
    cdn_icon_url = None

    if image_url:
        try:
            # Download image bytes
            img_res = session.get(image_url, timeout=15)
            if img_res.status_code == 200 and len(img_res.content) > 100:
                ext = os.path.splitext(image_url.split("?")[0])[1] or ".png"
                clean_slug = slugify(title)[:40]
                filename = f"{clean_slug}{ext}"
                
                # Upload to DigitalOcean Spaces CDN
                cdn_icon_url = storage.upload_bytes(
                    file_bytes=img_res.content,
                    filename=filename,
                    folder="categories/icons",
                )
            else:
                # Fallback to direct URL if download returned small or error
                cdn_icon_url = image_url
        except Exception as e:
            print(f"  [Icon Warning] Failed to process image for '{title}': {e}")
            cdn_icon_url = image_url
    
    return {
        **cat,
        "icon_url": cdn_icon_url,
    }


def migrate():
    session = get_authenticated_session()
    raw_categories = fetch_all_old_categories(session)
    if not raw_categories:
        print("No categories found to migrate!")
        return

    storage = SpacesStorageService()
    print("\nStarting parallel download of category icons and upload to DigitalOcean Spaces...")

    processed_categories = []
    # Process with 8 concurrent workers for speed
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(process_single_category, cat, storage, session): cat
            for cat in raw_categories
        }
        completed_count = 0
        for future in concurrent.futures.as_completed(futures):
            completed_count += 1
            res = future.result()
            processed_categories.append(res)
            if completed_count % 25 == 0 or completed_count == len(raw_categories):
                print(f"  Processed {completed_count}/{len(raw_categories)} icons...")

    print("\nSaving all categories into PostgreSQL database...")
    db = SessionLocal()
    existing_categories = {c.name.lower(): c for c in db.query(LogoCategory).all()}
    existing_slugs = {c.slug for c in existing_categories.values()}

    inserted_count = 0
    updated_count = 0

    for cat in processed_categories:
        name = cat["title"]
        name_lower = name.lower()
        icon_url = cat.get("icon_url")
        is_active = cat.get("is_active", True)

        if name_lower in existing_categories:
            # Update icon if current one is empty
            existing = existing_categories[name_lower]
            if icon_url and not existing.icon_url:
                existing.icon_url = icon_url
            existing.is_active = is_active
            updated_count += 1
        else:
            # Generate unique slug
            base_slug = slugify(name)
            slug = base_slug
            counter = 1
            while slug in existing_slugs:
                slug = f"{base_slug}-{counter}"
                counter += 1
            existing_slugs.add(slug)

            new_cat = LogoCategory(
                name=name,
                slug=slug,
                description=f"{name} services, stores & professionals directory",
                icon_url=icon_url,
                is_active=is_active,
            )
            db.add(new_cat)
            existing_categories[name_lower] = new_cat
            inserted_count += 1

    db.commit()
    total_db = db.query(LogoCategory).count()
    db.close()

    print("\n==========================================")
    print(" MIGRATION COMPLETED SUCCESSFULLY!")
    print(f" - Inserted into PostgreSQL: {inserted_count}")
    print(f" - Updated in PostgreSQL:    {updated_count}")
    print(f" - Total Categories in DB:   {total_db}")
    print("==========================================\n")


if __name__ == "__main__":
    migrate()
