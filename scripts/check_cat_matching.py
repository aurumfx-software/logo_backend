import socket
import urllib3
import urllib3.util.connection as uc
import requests
import json
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

uc.allowed_gai_family = lambda: socket.AF_INET
urllib3.disable_warnings()

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import SessionLocal
from app.db.models.logo import LogoCategory

db = SessionLocal()
existing_cats = {c.name.lower().strip(): c.name for c in db.query(LogoCategory).all()}
db.close()

LOGIN_URL = "https://mylocalityinfo.com/mylocalityinfo/index.php"
session = requests.Session()
session.verify = False
headers = {"User-Agent": "Mozilla/5.0", "Referer": LOGIN_URL}
session.post(LOGIN_URL, data={"username": "admin", "password": "Logotcr@123", "btnLogin": ""}, headers=headers, timeout=15)

url = "https://mylocalityinfo.com/mylocalityinfo/api-firebase/get-bootstrap-table-data.php?table=establisher&limit=1100&offset=0"
res = session.get(url, headers=headers, timeout=30)
rows = res.json().get("rows", [])

missing_cats = set()
matched_count = 0
for r in rows:
    c = (r.get("cattitle") or "").strip()
    if c:
        if c.lower() in existing_cats:
            matched_count += 1
        else:
            missing_cats.add(c)

print(f"Total rows: {len(rows)}")
print(f"Matched establishers: {matched_count}/{len(rows)}")
print(f"Missing categories count: {len(missing_cats)}")
print("Missing categories:", missing_cats)
