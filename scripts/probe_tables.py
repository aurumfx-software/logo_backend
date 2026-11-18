import socket
import urllib3
import urllib3.util.connection as uc
import requests
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

uc.allowed_gai_family = lambda: socket.AF_INET
urllib3.disable_warnings()

LOGIN_URL = "https://mylocalityinfo.com/mylocalityinfo/index.php"
session = requests.Session()
session.verify = False
headers = {"User-Agent": "Mozilla/5.0", "Referer": LOGIN_URL}
session.post(LOGIN_URL, data={"username": "admin", "password": "Logotcr@123", "btnLogin": ""}, headers=headers, timeout=15)

candidate_tables = [
    "slider", "sliders", "establisher_slider", "establisher_sliders", "establisher_image", "establisher_images",
    "establishment_slider", "establishment_sliders", "establishment_image", "establishment_images",
    "tbl_slider", "tbl_establisher_slider", "establisher_photos", "photos",
    "social", "social_media", "branch", "branches", "review", "reviews",
    "users", "user", "area", "myarea", "franchise", "franchisee", "sections", "section",
    "news", "enquiry", "enquiries", "notification", "notifications"
]

found = []
for tbl in candidate_tables:
    try:
        url = f"https://mylocalityinfo.com/mylocalityinfo/api-firebase/get-bootstrap-table-data.php?table={tbl}&limit=2"
        r = session.get(url, headers=headers, timeout=5)
        if r.status_code == 200 and r.text.strip().startswith("{"):
            d = r.json()
            if "total" in d:
                found.append((tbl, d.get("total")))
                print(f"MATCH: table={tbl} -> total={d.get('total')}")
    except Exception:
        pass

print("\nAll matching tables found:", found)
