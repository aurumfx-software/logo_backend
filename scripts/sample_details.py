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

# Test 5 order details
for eid in ["1146", "1145", "1144", "1143", "1142"]:
    r = session.get(f"https://mylocalityinfo.com/mylocalityinfo/order-detail.php?id={eid}", headers=headers, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    socials = {}
    sliders = []
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) >= 2:
            label = tds[0].get_text(strip=True).lower()
            val = tds[1].get_text(strip=True)
            if any(s in label for s in ["facebook", "instagram", "youtube", "website"]):
                socials[label] = val
    for a in soup.find_all("a", href=True):
        href = a.get("href")
        if "slider" in href:
            sliders.append(href)
    print(f"ID {eid}: Socials={socials}, Sliders={sliders}")
