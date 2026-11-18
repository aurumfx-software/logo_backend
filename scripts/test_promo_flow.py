import urllib.request
import json

res = urllib.request.urlopen('http://168.144.18.149:8000/api/v1/promotions')
data = json.loads(res.read().decode('utf-8'))
items = data if isinstance(data, list) else data.get('data', [])
print(f'Total promotions in database: {len(items)}')

# Test creating banner
payload = {
    'title': 'Grand Festive Mega Banner',
    'category': 'Retail & Shopping',
    'type': 'Banner',
    'placement': 'Home Top',
    'location': 'Kerala',
    'image_url': 'https://aurumfx-images.sgp1.digitaloceanspaces.com/banners/f183f22512ae4d35990bbef9cbb018fe.jpeg',
    'status': 'active'
}

req = urllib.request.Request(
    'http://168.144.18.149:8000/api/v1/promotions',
    data=json.dumps(payload).encode('utf-8'),
    headers={'Content-Type': 'application/json'},
    method='POST'
)
with urllib.request.urlopen(req) as resp:
    res = json.loads(resp.read().decode('utf-8'))
    created = res['data']
    created_id = created['id']
    print(f"Created ID: {created_id}, Placement: {created['placement']}, Image: {created['image_url']}")

    if created['placement'] != 'Home Top':
        update_payload = {'placement': 'Home Top', 'category': 'Retail & Shopping'}
        up_req = urllib.request.Request(
            f'http://168.144.18.149:8000/api/v1/promotions/{created_id}',
            data=json.dumps(update_payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='PUT'
        )
        with urllib.request.urlopen(up_req) as up_resp:
            up_res = json.loads(up_resp.read().decode('utf-8'))
            print('Cleaned placement via PUT:', up_res['data']['placement'])

# Delete the test promo so we keep database clean
del_req = urllib.request.Request(
    f'http://168.144.18.149:8000/api/v1/promotions/{created_id}',
    method='DELETE'
)
with urllib.request.urlopen(del_req) as del_resp:
    print('Deleted test promo:', del_resp.status)
