from app.db.database import engine
from sqlalchemy import text

def update_banners():
    with engine.connect() as conn:
        # 1. Update Home Top promotions with the generated & high-res edge-to-edge banners
        conn.execute(text("""
            UPDATE promotions SET 
                title = 'Kerala Festive Grand Shopping Festival — Up to 50% Off', 
                image_url = '/banners/top_grand_festival.png' 
            WHERE id = 49;
        """))

        conn.execute(text("""
            UPDATE promotions SET 
                title = 'Exclusive Kerala Silk & Festive Designer Fashion', 
                image_url = '/banners/top_fashion_lifestyle.png' 
            WHERE id = 61;
        """))

        conn.execute(text("""
            UPDATE promotions SET 
                title = 'Kerala 5G Smart Tech & Mega Electronics Expo', 
                image_url = '/banners/kerala_electronics_fest.png' 
            WHERE id = 62;
        """))

        conn.execute(text("""
            UPDATE promotions SET 
                title = 'Kerala Bridal Gold & Diamond Jewellery Fest', 
                image_url = '/banners/kerala_gold_jewellery_fest.png' 
            WHERE id = 63;
        """))

        # 2. Update Home Middle promotions with proper widescreen banners matching the panoramic layout
        conn.execute(text("""
            UPDATE promotions SET 
                title = 'Kerala Smart Living & Electronics Expo', 
                image_url = '/banners/sponsored_banner_1_hd.jpg' 
            WHERE id = 56;
        """))

        conn.execute(text("""
            UPDATE promotions SET 
                title = 'Kerala Bridal Gold & Diamond Jewellery Festival', 
                image_url = '/banners/kerala_gold_jewellery_fest.png' 
            WHERE id = 68;
        """))

        conn.execute(text("""
            UPDATE promotions SET 
                title = 'Authentic Malabar Traditional Cuisine & Food Festival', 
                image_url = '/banners/malabar_food_fest.png' 
            WHERE id = 69;
        """))

        conn.execute(text("""
            UPDATE promotions SET 
                title = 'Modern Kerala Furniture, Decor & Home Interiors', 
                image_url = '/banners/sponsored_banner_2_hd.jpg' 
            WHERE id = 70;
        """))

        conn.commit()
        print("Successfully updated promotions in PostgreSQL database!")

if __name__ == '__main__':
    update_banners()
