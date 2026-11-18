import socket
import urllib3
import urllib3.util.connection as uc
import requests
import concurrent.futures
import time
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

def fetch_single_detail(eid):
    try:
        url = f"https://mylocalityinfo.com/mylocalityinfo/order-detail.php?id={eid}"
        r = session.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        socials = {}
        sliders = []
        table = soup.find("table", class_="table")
        if table:
            for tr in table.find_all("tr"):
                th = tr.find("th")
                td = tr.find("td")
                if th and td:
                    k = th.get_text(strip=True).lower()
                    v = td.get_text(strip=True)
                    if any(s in k for s in ["facebook", "instagram", "youtube", "website"]):
                        if v: socials[k] = v
                for img in tr.find_all("img"):
                    src = img.get("src")
                    if src and "slider" in src:
                        sliders.append(src)
        return eid, socials, sliders
    except Exception as e:
        return eid, {}, []

# Test 20 concurrent requests
t0 = time.time()
with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
    results = list(executor.map(fetch_single_detail, range(1125, 1146)))
t1 = time.time()

print(f"Fetched {len(results)} order details in {t1 - t0:.2f} seconds!")
for eid, soc, sld in results[:5]:
    print(f"ID {eid}: Socials={soc}, Sliders={sld}")
