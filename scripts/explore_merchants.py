import socket
import urllib3
import urllib3.util.connection as uc
import requests
import re
from bs4 import BeautifulSoup
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

print("Logging in...")
login_res = session.post(LOGIN_URL, data={"username": "admin", "password": "Logotcr@123", "btnLogin": ""}, headers=headers, timeout=15)
print("Login status:", login_res.status_code)

print("Fetching home.php...")
home_res = session.get("https://mylocalityinfo.com/mylocalityinfo/home.php", headers=headers, timeout=15)
print("home.php status:", home_res.status_code)

soup = BeautifulSoup(home_res.text, "html.parser")

# Find all tables and their attributes
tables = soup.find_all("table")
print(f"Found {len(tables)} table(s)")
for i, t in enumerate(tables):
    print(f"Table {i}: id={t.get('id')}, class={t.get('class')}, data-url={t.get('data-url')}")

# Find all links in the sidebar/navigation
nav_links = []
for a in soup.find_all("a", href=True):
    href = a.get("href")
    text = a.get_text(strip=True)
    if href and not href.startswith("#") and not href.startswith("javascript"):
        nav_links.append((text, href))

print("\nNavigation Links:")
for text, href in nav_links:
    print(f"  {text} -> {href}")
