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

# Check what get-bootstrap-table-data.php?table=establisher returns with full limit
res = session.get("https://mylocalityinfo.com/mylocalityinfo/api-firebase/get-bootstrap-table-data.php?table=establisher&limit=1&offset=0", headers=headers, timeout=20)
row = res.json()["rows"][0]
print("All fields in get-bootstrap-table-data.php?table=establisher row:")
for k, v in row.items():
    print(f"  {k}: {repr(v)[:100]}")

# Also check other tables that might exist
for tbl in ["slider", "establishment_slider", "establisher_slider", "gallery", "images", "social", "places", "place"]:
    r = session.get(f"https://mylocalityinfo.com/mylocalityinfo/api-firebase/get-bootstrap-table-data.php?table={tbl}&limit=1", headers=headers, timeout=10)
    if r.status_code == 200 and r.text.startswith("{") and "rows" in r.json():
        print(f"Found table: {tbl} with total={r.json().get('total')}")
