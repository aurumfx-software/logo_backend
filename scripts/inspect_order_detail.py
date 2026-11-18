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

res = session.get("https://mylocalityinfo.com/mylocalityinfo/order-detail.php?id=1146", headers=headers, timeout=15)
print("order-detail.php status:", res.status_code)
soup = BeautifulSoup(res.text, "html.parser")

# Find table or text inside content-wrapper
content = soup.find("div", class_="content-wrapper") or soup.find("section", class_="content")
if content:
    print("\nText in order-detail:\n", "\n".join([line.strip() for line in content.get_text().split("\n") if line.strip()][:30]))
    images = [img.get("src") for img in content.find_all("img") if img.get("src")]
    print("\nImages in order-detail:", images)
else:
    print("No content-wrapper found")
