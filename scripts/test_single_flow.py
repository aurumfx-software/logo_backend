import os
import sys
import re
import socket
import json
import urllib3
import urllib3.util.connection as uc
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

# Ensure project root in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

uc.allowed_gai_family = lambda: socket.AF_INET
urllib3.disable_warnings()

from app.db.database import SessionLocal
from app.db.models.merchant import MerchantProfile
from app.db.models.user import User
from app.services.storage_service import SpacesStorageService

OLD_APP_BASE = "https://mylocalityinfo.com/mylocalityinfo"
LOGIN_URL = f"{OLD_APP_BASE}/index.php"

def test_single_flow():
    session = requests.Session()
    session.verify = False
    headers = {"User-Agent": "Mozilla/5.0", "Referer": LOGIN_URL}
    session.post(LOGIN_URL, data={"username": "admin", "password": "Logotcr@123", "btnLogin": ""}, headers=headers, timeout=15)
    
    url = f"{OLD_APP_BASE}/api-firebase/get-bootstrap-table-data.php?table=establisher&limit=3&offset=0"
    res = session.get(url, headers=headers, timeout=20)
    rows = res.json().get("rows", [])
    
    storage = SpacesStorageService()
    print(f"Testing 3 rows with Spaces CDN: bucket={storage.bucket}")
    
    for r in rows:
        print("\n--- Processing Establisher:", r.get("title"), "---")
        # Extract main image
        img_html = r.get("image") or ""
        m = re.search(r"href=['\"]([^'\"]+)['\"]", img_html)
        if not m:
            m = re.search(r"src=['\"]([^'\"]+)['\"]", img_html)
        img_path = m.group(1).strip() if m else ""
        if img_path and not img_path.startswith("http"):
            img_url = f"{OLD_APP_BASE}/{img_path.lstrip('/')}"
        else:
            img_url = img_path

        cdn_url = None
        if img_url:
            print("Downloading:", img_url)
            img_res = session.get(img_url, timeout=10)
            if img_res.status_code == 200 and len(img_res.content) > 100:
                cdn_url = storage.upload_bytes(
                    file_bytes=img_res.content,
                    filename=os.path.basename(img_path) or "photo.jpg",
                    folder="merchants/photos"
                )
                print("Uploaded to CDN:", cdn_url)
            else:
                print("Download failed or empty:", img_res.status_code)
                
        print("Final CDN URL:", cdn_url)

if __name__ == "__main__":
    test_single_flow()
