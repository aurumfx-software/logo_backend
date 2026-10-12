from app.db.database import engine
from sqlalchemy import text

def seed_above_footer():
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM promotions WHERE placement IN ('Above Footer', 'Home Bottom')")).scalar()
        print(f"Current Above Footer count before seed: {count}")
        
        conn.execute(text("""
            INSERT INTO promotions (
                title, description, category, type, placement, location, 
                start_date, end_date, status, impressions, clicks, 
                image_url, video_url, media_type, target_url, created_at, updated_at
            )
            VALUES 
            (
                'Discover Kerala''s Verified Local Businesses',
                'Explore 1,000+ top-rated stores, authentic restaurants, exclusive festival discounts, and verified services across all 14 districts.',
                'Retail & Shopping',
                'Banner',
                'Above Footer',
                'Kerala',
                '2026-10-01',
                '2027-12-31',
                'active',
                420,
                38,
                'https://images.unsplash.com/photo-1542838132-92c53300491e?w=1600&auto=format&fit=crop&q=80',
                'https://aurumfx-images.sgp1.digitaloceanspaces.com/merchants/videos/72552f800b674a65b72dbaf2093165a7.mp4',
                'video',
                '#establishments-section',
                NOW(),
                NOW()
            ),
            (
                'Exclusive Kerala Festive Shopping & Offers',
                'Get up to 60% off on top brands, fashion collections, wedding jewellery, and home essentials with direct merchant contact.',
                'Fashion & Lifestyle',
                'Banner',
                'Above Footer',
                'Kerala',
                '2026-10-01',
                '2027-12-31',
                'active',
                380,
                45,
                'https://images.unsplash.com/photo-1607082348824-0a96f2a4b9da?w=1600&auto=format&fit=crop&q=80',
                'https://aurumfx-images.sgp1.digitaloceanspaces.com/merchants/videos/72552f800b674a65b72dbaf2093165a7.mp4',
                'video',
                '#featured-section',
                NOW(),
                NOW()
            ),
            (
                'Authentic Malabar & Kerala Dining Guide',
                'Discover iconic cafes, authentic traditional cuisines, fine dining, and fast delivery spots near your exact location.',
                'Hotels & Dining',
                'Banner',
                'Above Footer',
                'Kerala',
                '2026-10-01',
                '2027-12-31',
                'active',
                510,
                62,
                'https://images.unsplash.com/photo-1555396273-367ea4eb4db5?w=1600&auto=format&fit=crop&q=80',
                'https://aurumfx-images.sgp1.digitaloceanspaces.com/merchants/videos/72552f800b674a65b72dbaf2093165a7.mp4',
                'video',
                '#establishments-section',
                NOW(),
                NOW()
            )
        """))
        conn.commit()
        
        new_count = conn.execute(text("SELECT COUNT(*) FROM promotions WHERE placement IN ('Above Footer', 'Home Bottom')")).scalar()
        print(f"New Above Footer count after seed: {new_count}")

if __name__ == '__main__':
    seed_above_footer()
