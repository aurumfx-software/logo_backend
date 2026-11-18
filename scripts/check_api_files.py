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

api_candidates = [
    "get-bootstrap-table-data.php",
    "get-categories.php",
    "get-category.php",
    "get-places.php",
    "get-place.php",
    "get-slider.php",
    "get-sliders.php",
    "get-establisher.php",
    "get-establishers.php",
    "get-establishment.php",
    "get-establishments.php",
    "get-all-data.php",
    "establisher-data.php",
    "api.php",
    "slider.php",
    "functions.php"
]

found = []
for f in api_candidates:
    url = f"https://mylocalityinfo.com/mylocalityinfo/api-firebase/{f}"
    try:
        r = session.get(url, headers=headers, timeout=5)
        if r.status_code != 404:
            found.append((f, r.status_code, len(r.text)))
            print(f"Found: {f} -> {r.status_code} ({len(r.text)} bytes)")
    except Exception:
        pass
print("Found api files:", found)
