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

LOGIN_URL = "https://mylocalityinfo.com/mylocalityinfo/index.php"
session = requests.Session()
session.verify = False
headers = {"User-Agent": "Mozilla/5.0", "Referer": LOGIN_URL}
session.post(LOGIN_URL, data={"username": "admin", "password": "Logotcr@123", "btnLogin": ""}, headers=headers, timeout=15)

url = "https://mylocalityinfo.com/mylocalityinfo/api-firebase/get-bootstrap-table-data.php?table=establisher&limit=1100&offset=0"
res = session.get(url, headers=headers, timeout=30)
print("Fetch status:", res.status_code)
data = res.json()
total = data.get("total")
rows = data.get("rows", [])
print(f"Total reported: {total}, Rows returned: {len(rows)}")

# Check distinct categories among establishers
categories = set()
for r in rows:
    c = r.get("cattitle")
    if c:
        categories.add(c.strip())
print(f"Unique categories in establishers: {len(categories)}")

# Check how many have images
has_image = 0
for r in rows:
    img = r.get("image") or ""
    if "src=" in img or "href=" in img or ".png" in img or ".jpg" in img or ".jpeg" in img:
        has_image += 1
print(f"Establishers with image: {has_image}/{len(rows)}")
