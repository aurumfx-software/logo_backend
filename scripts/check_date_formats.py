import socket
import urllib3
import urllib3.util.connection as uc
import requests
import sys
from datetime import datetime

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
rows = res.json().get("rows", [])

date_samples = set()
for r in rows:
    dc = r.get("date_created")
    if dc:
        date_samples.add(dc.strip())

print(f"Total unique dates: {len(date_samples)}")
print("Sample dates:", list(date_samples)[:15])
