from app.db.database import engine
from sqlalchemy import text

def seed_placements():
    with engine.connect() as conn:
        # Check current count of Home Middle, Featured Offers, and Special Offer
        res_middle = conn.execute(text("SELECT COUNT(*) FROM promotions WHERE placement = 'Home Middle' AND image_url IS NOT NULL")).scalar()
        res_featured = conn.execute(text("SELECT COUNT(*) FROM promotions WHERE placement = 'Featured Offers'")).scalar()
        res_special = conn.execute(text("SELECT COUNT(*) FROM promotions WHERE placement = 'Special Offer'")).scalar()
        
        print(f"Current counts: Middle={res_middle}, Featured={res_featured}, Special={res_special}")
        
        # 1. Update row 6 or ensure Home Middle has valid ads
        conn.execute(text("""
            UPDATE promotions 
            SET title = 'Grand Malabar Food Festival', 
                category = 'Hotels & Dining',
                type = 'Banner',
                placement = 'Home Middle', 
                status = 'active',
                image_url = 'https://aurumfx-images.sgp1.digitaloceanspaces.com/banners/aa95cf6a6a1e4ca69e2ec8c7df871d92.jpg', 
                target_url = '#' 
            WHERE id = 6
        """))

        if res_middle < 2:
            conn.execute(text("""
                INSERT INTO promotions (title, category, type, placement, location, start_date, end_date, status, impressions, clicks, image_url, target_url, created_at, updated_at)
                VALUES 
                ('VR HERO MOTORS — Onam Mega Exchange', 'Automobile & Spares', 'Banner', 'Home Middle', 'Kerala', '2026-10-01', '2027-12-31', 'active', 120, 15, 'https://aurumfx-images.sgp1.digitaloceanspaces.com/banners/f8e526085d604b85a677e96cc18c00e7.png', '#', NOW(), NOW()),
                ('Life Medicals — 20% Health Discount', 'Healthcare & Medicals', 'Banner', 'Home Middle', 'Kerala', '2026-10-01', '2027-12-31', 'active', 95, 8, 'https://aurumfx-images.sgp1.digitaloceanspaces.com/banners/df515a74b6b746a8bb961f1b71097873.jpeg', '#', NOW(), NOW())
            """))

        if res_featured < 3:
            conn.execute(text("""
                INSERT INTO promotions (title, category, type, placement, location, start_date, end_date, status, impressions, clicks, image_url, target_url, created_at, updated_at)
                VALUES 
                ('BAG BAZAAR — Buy 1 Get 1 Free on Travel Bags', 'Retail & Shopping', 'Featured', 'Featured Offers', 'Kozhikode', '2026-10-01', '2027-12-31', 'active', 310, 42, 'https://aurumfx-images.sgp1.digitaloceanspaces.com/banners/f183f22512ae4d35990bbef9cbb018fe.jpeg', '#', NOW(), NOW()),
                ('Fatima Jewellery — 0% Making Charge on Gold', 'Shopping & Fashion', 'Featured', 'Featured Offers', 'Payyanur', '2026-10-01', '2027-12-31', 'active', 450, 68, 'https://aurumfx-images.sgp1.digitaloceanspaces.com/banners/7c6b1ef681754e98a7bf2a3f6d50cafa.jpeg', '#', NOW(), NOW()),
                ('Pavizham Associates — Free Interior Design Consultation', 'Interiors & Furniture', 'Featured', 'Featured Offers', 'Kochi', '2026-10-01', '2027-12-31', 'active', 280, 24, 'https://aurumfx-images.sgp1.digitaloceanspaces.com/banners/ef965d5520a7472dbf44707f49736de9.jpg', '#', NOW(), NOW())
            """))

        if res_special < 3:
            conn.execute(text("""
                INSERT INTO promotions (title, category, type, placement, location, start_date, end_date, status, impressions, clicks, image_url, target_url, created_at, updated_at)
                VALUES 
                ('Flash Mega Sale — Flat 50% Off at Bag Bazaar', 'Retail & Shopping', 'Special Offer', 'Special Offer', 'Kannur', '2026-10-01', '2027-12-31', 'active', 510, 89, 'https://aurumfx-images.sgp1.digitaloceanspaces.com/banners/f183f22512ae4d35990bbef9cbb018fe.jpeg', '#', NOW(), NOW()),
                ('Exclusive Festival Gold Discount — Fatima Jewellery', 'Shopping & Fashion', 'Special Offer', 'Special Offer', 'Kannur', '2026-10-01', '2027-12-31', 'active', 620, 110, 'https://aurumfx-images.sgp1.digitaloceanspaces.com/banners/7c6b1ef681754e98a7bf2a3f6d50cafa.jpeg', '#', NOW(), NOW()),
                ('Free Consultation & Service Voucher — Pavizham', 'Interiors & Furniture', 'Special Offer', 'Special Offer', 'Ernakulam', '2026-10-01', '2027-12-31', 'active', 390, 45, 'https://aurumfx-images.sgp1.digitaloceanspaces.com/banners/aa95cf6a6a1e4ca69e2ec8c7df871d92.jpg', '#', NOW(), NOW())
            """))

        conn.commit()
        print("Successfully synchronized all placement promotions in PostgreSQL!")

if __name__ == '__main__':
    seed_placements()
