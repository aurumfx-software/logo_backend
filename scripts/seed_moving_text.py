import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.db.database import engine
from sqlalchemy import text

def run():
    with engine.connect() as conn:
        exists = conn.execute(text("SELECT COUNT(*) FROM promotions WHERE placement = 'Moving Text'")).scalar()
        print(f"Existing Moving Text count: {exists}")
        if exists == 0:
            conn.execute(text("""
                INSERT INTO promotions (title, description, category, type, placement, location, start_date, end_date, status, impressions, clicks, created_at, updated_at)
                VALUES 
                ('⚡ Festive Season Offers — Check Out Exclusive Deals Near You', 'Special festive season offers across all districts', 'Shopping & Fashion', 'Text Carousel', 'Moving Text', 'Kerala', '2026-10-01', '2027-12-31', 'active', 1500, 320, NOW(), NOW()),
                ('📍 Explore 1000+ Local Shops, Restaurants & Services in Kerala', 'Find verified local businesses, restaurants and stores', 'Retail & Shopping', 'Text Carousel', 'Moving Text', 'Kerala', '2026-10-01', '2027-12-31', 'active', 2400, 410, NOW(), NOW()),
                ('💎 Gold & Jewellery Collections — Trending Now', 'Latest gold, diamond and jewellery collections', 'Shopping & Fashion', 'Text Carousel', 'Moving Text', 'Kerala', '2026-10-01', '2027-12-31', 'active', 1890, 275, NOW(), NOW()),
                ('🍕 Top Rated Restaurants & Cafes — Order or Visit Today', 'Best food and dining spots in your town', 'Hotels & Dining', 'Text Carousel', 'Moving Text', 'Kerala', '2026-10-01', '2027-12-31', 'active', 3100, 520, NOW(), NOW()),
                ('🔥 Mega Deals Festival — Up to 60% Off on Top Brands', 'Mega discounts and flash deals for a limited time', 'Retail & Shopping', 'Text Carousel', 'Moving Text', 'Kerala', '2026-10-01', '2027-12-31', 'active', 4200, 780, NOW(), NOW())
            """))
            conn.commit()
            print("Successfully seeded 5 Moving Text announcements in PostgreSQL!")
        else:
            print(f"Already have {exists} Moving Text announcements.")

if __name__ == '__main__':
    run()
