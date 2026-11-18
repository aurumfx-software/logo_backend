import os
from dotenv import load_dotenv
import psycopg2

load_dotenv('logo-backend/.env')
conn = psycopg2.connect(
    dbname=os.getenv('DB_NAME'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    host=os.getenv('DB_HOST'),
    port=os.getenv('DB_PORT')
)
cur = conn.cursor()
cur.execute("SELECT id, title, placement, image_url, status FROM promotions WHERE placement = 'Home Top' AND image_url IS NULL;")
rows = cur.fetchall()
print(f"Home Top rows with NULL image count: {len(rows)}")
for r in rows:
    print(r)
cur.close()
conn.close()
