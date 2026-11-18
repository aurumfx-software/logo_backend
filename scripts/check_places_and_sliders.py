import socket
import urllib3
import urllib3.util.connection as uc
import requests
import re
from bs4 import BeautifulSoup
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

res = session.get("https://mylocalityinfo.com/mylocalityinfo/order-detail.php?id=1146", headers=headers, timeout=15)
soup = BeautifulSoup(res.text, "html.parser")

# Find all img tags or links in order-detail.php
for img in soup.find_all("img"):
    print("img src:", img.get("src"))

for a in soup.find_all("a", href=True):
    if "upload/" in a.get("href"):
        print("link:", a.get("href"))

# Also check place table: how many places, what are they?
place_res = session.get("https://mylocalityinfo.com/mylocalityinfo/api-firebase/get-bootstrap-table-data.php?table=place&limit=5&offset=0", headers=headers, timeout=15)
print("\nPlace table sample:")
print(place_res.json().get("rows", [])[:2])
