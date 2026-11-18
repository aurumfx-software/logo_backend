import socket
import urllib3
import urllib3.util.connection as uc
import requests
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

for page in ["edit-establishment.php?id=1146", "edit-establisher.php?id=1146", "establishment-detail.php?id=1146"]:
    r = session.get(f"https://mylocalityinfo.com/mylocalityinfo/{page}", headers=headers, timeout=10)
    print(page, "status:", r.status_code, "length:", len(r.text))
    if r.status_code == 200 and len(r.text) > 1000:
        soup = BeautifulSoup(r.text, "html.parser")
        inputs = [(inp.get("name"), inp.get("value")) for inp in soup.find_all(["input", "select", "textarea"])]
        print(f"  Inputs in {page}:", inputs[:15])
