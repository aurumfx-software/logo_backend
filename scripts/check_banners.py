import socket
import urllib3
import urllib3.util.connection as uc
import requests

uc.allowed_gai_family = lambda: socket.AF_INET
urllib3.disable_warnings()

session = requests.Session()
session.verify = False
headers = {'User-Agent': 'Mozilla/5.0'}
session.post('https://mylocalityinfo.com/mylocalityinfo/index.php', data={'username': 'admin', 'password': 'Logotcr@123', 'btnLogin': ''}, headers=headers)

for tbl in ['banner', 'banners', 'slider', 'main_banner', 'ec_banner']:
    r = session.get(f'https://mylocalityinfo.com/mylocalityinfo/api-firebase/get-bootstrap-table-data.php?table={tbl}&limit=10', headers=headers)
    if r.status_code == 200 and r.text.startswith('{'):
        d = r.json()
        print(f"Table {tbl}: total={d.get('total')}, sample={d.get('rows', [])[:2]}")
