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

# 1. Delete test row 41
cur.execute('DELETE FROM promotions WHERE id = 41;')

# 2. Delete empty dummy test rows 39 and 40
cur.execute('DELETE FROM promotions WHERE id IN (39, 40);')

# 3. Clean up all placements that have 'Home Top (%)' -> set to 'Home Top'
cur.execute("UPDATE promotions SET placement = 'Home Top' WHERE placement ILIKE 'Home Top%';")

# 4. Clean up any other placements to standard clean names
cur.execute("UPDATE promotions SET placement = 'Home Middle' WHERE placement ILIKE '%middle%';")
cur.execute("UPDATE promotions SET placement = 'Featured Offers' WHERE (placement ILIKE '%featured%' OR placement ILIKE '%offer%') AND placement NOT ILIKE '%special%';")
cur.execute("UPDATE promotions SET placement = 'Special Offer' WHERE placement ILIKE '%special%';")
cur.execute("UPDATE promotions SET placement = 'Moving Text' WHERE placement ILIKE '%moving%' OR placement ILIKE '%ticker%';")

conn.commit()

# Print remaining rows grouped by placement
cur.execute('SELECT placement, count(*), count(image_url) FROM promotions GROUP BY placement ORDER BY placement;')
rows = cur.fetchall()
print('Database Placements summary:')
for r in rows:
    print(f'Placement: {r[0]} | Count: {r[1]} | With Images: {r[2]}')

cur.close()
conn.close()
