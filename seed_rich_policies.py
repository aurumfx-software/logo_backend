from app.db.database import engine
from sqlalchemy import text

TERMS_CONTENT = """Welcome to Logo Kerala (operated by AurumFX Pvt Ltd). By accessing or using the Logo Kerala mobile application, website, and hyperlocal discovery services, you agree to be bound by these Terms and Conditions.

1. Hyperlocal Platform Services
Logo Kerala connects consumers with verified local merchants, establishments, healthcare services, and retail stores across the 14 districts of Kerala. We provide contact facilitation via direct phone calling and WhatsApp with 0% platform commission on direct transactions.

2. Merchant Listings & Accuracy
• Merchants listed on the platform must be registered, legitimate enterprises operating in the state of Kerala.
• Store details, offers, pricing, operating hours, and location coordinates are provided by merchants and verified by our on-ground team. While we strive for 100% accuracy, users should verify critical information directly with the merchant before travel.

3. User Conduct
• Users agree to use the platform for lawful personal discovery purposes only.
• Any attempt to scrape, copy, or reverse-engineer directory content, merchant media, or phone numbers for automated mass-marketing is strictly prohibited.

4. 0% Commission & Third-Party Purchases
Logo Kerala is not a party to transactions entered into between users and independent local merchants. Product warranties, service quality, returns, and payments are the sole responsibility of the respective merchant.

5. Modifications
AurumFX Pvt Ltd reserves the right to amend these Terms of Service at any time. Continued use of the platform following updates constitutes acceptance of the amended terms."""

PRIVACY_CONTENT = """At Logo Kerala (AurumFX Pvt Ltd), your privacy is our utmost priority. This Privacy Policy outlines how we collect, handle, and protect your information across our website and mobile application.

1. Information We Collect
• Location Data: With your permission, we use your device's GPS or selected district/town to display merchants and services near you. We do not track background location when the app is closed.
• Direct Merchant Contact: When you initiate a phone call or WhatsApp message to a merchant, the communication happens through your device's native phone or WhatsApp app. Logo Kerala does not record or store your private calls or messages.
• Search Queries & Preferences: Anonymous search terms and saved wishlist items are stored locally or securely in your profile to provide personalized recommendations.

2. How We Use Your Data
• To calculate accurate road distances to local merchants.
• To display relevant festival offers, banners, and verified local shop listings.
• To improve search relevance and detect fraudulent merchant listings.

3. Information Sharing & Zero Spam
• We do not sell, rent, or trade your personal information to third-party advertisers or telemarketers.
• Merchant contact information is publicly displayed solely for genuine consumer communication.

4. Data Security
All data transmissions between your browser/app and our cloud servers are encrypted using industry-standard TLS/SSL protocols.

5. Contact Us
For questions regarding your privacy, contact our Data Protection Officer at privacy@logokerala.com or support@aurumfx.com."""

with engine.connect() as conn:
    conn.execute(text("""
        INSERT INTO app_policies (key, label, content, last_updated, created_at, updated_at)
        VALUES 
        ('terms', 'Terms and Conditions', :terms, '2026-10-11', NOW(), NOW()),
        ('privacy', 'Privacy Policy', :privacy, '2026-10-11', NOW(), NOW())
        ON CONFLICT (key) DO UPDATE 
        SET label = EXCLUDED.label,
            content = EXCLUDED.content,
            last_updated = EXCLUDED.last_updated,
            updated_at = NOW();
    """), {"terms": TERMS_CONTENT, "privacy": PRIVACY_CONTENT})
    conn.commit()
    print("Policies successfully updated in PostgreSQL app_policies table!")
