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

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": LOGIN_URL,
}

session.post(LOGIN_URL, data={"username": "admin", "password": "Logotcr@123", "btnLogin": ""}, headers=headers, timeout=15)

# 1. Check establisher table
url = "https://mylocalityinfo.com/mylocalityinfo/api-firebase/get-bootstrap-table-data.php?table=establisher&limit=5&offset=0"
res = session.get(url, headers=headers, timeout=20)
print("establisher API HTTP:", res.status_code)
data = res.json()
print("Total rows:", data.get("total"))
rows = data.get("rows", [])
print(f"Sample row keys: {list(rows[0].keys()) if rows else []}")
if rows:
    print("\nSample Row 0:")
    print(json.dumps(rows[0], indent=2))

# 2. Check establishment.php to see if there is another table or details
est_res = session.get("https://mylocalityinfo.com/mylocalityinfo/establishment.php", headers=headers, timeout=15)
import re
urls_in_est = re.findall(r'data-url=[\'\"]([^\'\"]+)[\'\"]', est_res.text)
print("\ndata-urls in establishment.php:", urls_in_est)
tables_in_est = re.findall(r'table=([a-zA-Z0-9_-]+)', est_res.text)
print("tables in establishment.php:", set(tables_in_est))
