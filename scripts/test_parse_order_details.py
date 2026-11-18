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

def parse_order_detail(establisher_id):
    url = f"https://mylocalityinfo.com/mylocalityinfo/order-detail.php?id={establisher_id}"
    r = session.get(url, headers=headers, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    data = {}
    slider_imgs = []
    main_imgs = []
    
    table = soup.find("table", class_="table")
    if table:
        for tr in table.find_all("tr"):
            th = tr.find("th")
            td = tr.find("td")
            if th and td:
                key = th.get_text(strip=True)
                val = td.get_text(strip=True)
                data[key] = val
                for img in td.find_all("img"):
                    src = img.get("src")
                    if "slider" in src:
                        slider_imgs.append(src)
                    elif "establisher" in src or "upload" in src:
                        main_imgs.append(src)
            elif td: # some rows might only have td
                tds = tr.find_all("td")
                if len(tds) >= 2:
                    k = tds[0].get_text(strip=True)
                    v = tds[1].get_text(strip=True)
                    data[k] = v
                    for img in tds[1].find_all("img"):
                        src = img.get("src")
                        if "slider" in src:
                            slider_imgs.append(src)
                        elif "establisher" in src or "upload" in src:
                            main_imgs.append(src)
    return data, main_imgs, slider_imgs

for eid in ["1146", "1145", "1144", "1143", "1142"]:
    d, m_imgs, s_imgs = parse_order_detail(eid)
    print(f"\n--- ESTAB {eid} ---")
    print(f"Name: {d.get('Est. Name')}")
    print(f"Main Images: {m_imgs}")
    print(f"Slider Images: {s_imgs}")
    print(f"Socials: Facebook={d.get('Facebook')}, Instagram={d.get('Instagram')}, Youtube={d.get('Youtube')}, Website={d.get('Website')}")
