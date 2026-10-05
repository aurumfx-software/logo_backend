from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.db.models.complaint import Complaint
from app.db.models.content import Announcement, AppPolicy, PushNotification
from app.db.models.geography import GeographyRegion
from app.db.models.promotion import Promotion


def seed_operations_data(db: Session):
    """Seed initial Operations & Insights data into PostgreSQL if tables are empty."""
    # 1. Promotions
    if db.query(Promotion).count() == 0:
        initial_promotions = [
            Promotion(
                promo_code="BNR-001",
                title="Summer Sale 2024",
                category="Solar & Electricals",
                type="Banner",
                placement="Home Top",
                location="Payyanur, Kerala",
                start_date="2024-09-01",
                end_date="2024-09-30",
                status="active",
                impressions=45200,
                clicks=3240,
            ),
            Promotion(
                promo_code="BNR-002",
                title="New Restaurant Week",
                category="Food Category",
                type="Featured",
                placement="Food Category",
                location="Kochi, Kerala",
                start_date="2024-09-10",
                end_date="2024-09-17",
                status="active",
                impressions=28100,
                clicks=2180,
            ),
            Promotion(
                promo_code="BNR-003",
                title="Diwali Special Offers",
                category="Shopping & Fashion",
                type="Banner",
                placement="Home Top",
                location="Kannur, Kerala",
                start_date="2024-10-15",
                end_date="2024-11-05",
                status="pending",
                impressions=0,
                clicks=0,
            ),
            Promotion(
                promo_code="BNR-004",
                title="Health Check Camp",
                category="Healthcare & Medicals",
                type="Promotion",
                placement="Health Category",
                location="Calicut, Kerala",
                start_date="2024-08-15",
                end_date="2024-08-31",
                status="inactive",
                impressions=35600,
                clicks=2890,
            ),
            Promotion(
                promo_code="BNR-005",
                title="Back to School",
                category="Education & Training",
                type="Featured",
                placement="Education Category",
                location="Bangalore, Karnataka",
                start_date="2024-06-01",
                end_date="2024-06-30",
                status="inactive",
                impressions=42300,
                clicks=3560,
            ),
            Promotion(
                promo_code="BNR-006",
                title="Weekend Dining Deals",
                category="Hotels & Dining",
                type="Promotion",
                placement="Home Middle",
                location="Mumbai, Maharashtra",
                start_date="2024-09-13",
                end_date="2024-09-15",
                status="active",
                impressions=8900,
                clicks=720,
            ),
        ]
        db.add_all(initial_promotions)
        db.commit()

    # 2. Complaints
    if db.query(Complaint).count() == 0:
        initial_complaints = [
            Complaint(
                complaint_code="CMP-001",
                user="Rahul Sharma",
                merchant="Quick Fix Repairs",
                subject="Poor service quality",
                priority="high",
                status="open",
                date="2024-09-14",
                category="Service Quality",
                description="The technician arrived late and didn't solve the air conditioner water leakage problem.",
            ),
            Complaint(
                complaint_code="CMP-002",
                user="Priya Patel",
                merchant="Green Grocers",
                subject="Wrong items delivered",
                priority="medium",
                status="in-progress",
                date="2024-09-13",
                category="Order Issue",
                description="Ordered organic avocados and received standard grade ones.",
            ),
            Complaint(
                complaint_code="CMP-003",
                user="Amit Kumar",
                merchant="Book Haven",
                subject="Refund not processed",
                priority="high",
                status="open",
                date="2024-09-13",
                category="Payment",
                description="Cancelled order #4821 and the refund of Rs 1,450 hasn't been credited to UPI.",
            ),
            Complaint(
                complaint_code="CMP-004",
                user="Sneha Reddy",
                merchant="Metro Supermarket",
                subject="Misleading listing info",
                priority="low",
                status="resolved",
                date="2024-09-12",
                category="Listing Accuracy",
                description="Store hours listed as 24/7 but shop closed at 11 PM.",
                admin_response="Merchant verified and corrected their operating hours to 7 AM - 11 PM.",
                resolved_at=datetime.now(timezone.utc),
            ),
            Complaint(
                complaint_code="CMP-005",
                user="Vivek Joshi",
                merchant="City Eye Hospital",
                subject="Appointment scheduling issue",
                priority="medium",
                status="in-progress",
                date="2024-09-12",
                category="Service Quality",
                description="Doctor was not available despite confirmed morning slot.",
            ),
            Complaint(
                complaint_code="CMP-006",
                user="Anjali Singh",
                merchant="Fitness Zone Gym",
                subject="Membership charge dispute",
                priority="high",
                status="open",
                date="2024-09-11",
                category="Payment",
                description="Charged double for the quarterly subscription.",
            ),
            Complaint(
                complaint_code="CMP-007",
                user="Karthik Nair",
                merchant="Royal Jewellers",
                subject="Product authenticity concern",
                priority="high",
                status="open",
                date="2024-09-11",
                category="Product Quality",
                description="Requested BIS hallmark certificate for gold coin.",
            ),
            Complaint(
                complaint_code="CMP-008",
                user="Meera Gupta",
                merchant="Smart Learn Academy",
                subject="Course content not as described",
                priority="medium",
                status="resolved",
                date="2024-09-10",
                category="Listing Accuracy",
                description="Syllabus missed the advanced modules promised.",
                admin_response="Academy provided access to supplementary advanced video modules.",
                resolved_at=datetime.now(timezone.utc),
            ),
        ]
        db.add_all(initial_complaints)
        db.commit()

    # 3. Content Policies
    if db.query(AppPolicy).count() == 0:
        initial_policies = [
            AppPolicy(
                key="terms",
                label="Terms of Service",
                last_updated="2024-08-15",
                content=(
                    "These Terms of Service govern your use of the Logo App platform. By accessing or using our services, "
                    "you agree to be bound by these terms. Merchants must provide authentic business details, accurate pricing, "
                    "and maintain valid trade licenses. Users agree to respect community guidelines, provide genuine reviews, "
                    "and refrain from fraudulent transactions. Logo App reserves the right to suspend any account violating these terms."
                ),
            ),
            AppPolicy(
                key="privacy",
                label="Privacy Policy",
                last_updated="2024-08-10",
                content=(
                    "Your privacy is important to us. This Privacy Policy explains how we collect, use, disclose, and safeguard "
                    "your information when you use our platform. We collect contact details, GPS location with your consent, and "
                    "browsing interactions to connect you with nearby verified merchants. We do not sell your personal data to third "
                    "parties and employ industry-standard encryption to protect all stored information."
                ),
            ),
        ]
        db.add_all(initial_policies)
        db.commit()

    # 4. Push Notifications
    if db.query(PushNotification).count() == 0:
        initial_notifications = [
            PushNotification(
                title="Welcome new users",
                message="Welcome to Logo App! Discover local businesses near you.",
                status="active",
                sent="24,850",
            ),
            PushNotification(
                title="Festival Sale",
                message="Check out amazing Diwali deals from top merchants!",
                status="scheduled",
                sent="—",
            ),
            PushNotification(
                title="App Update",
                message="Update to the latest version for better performance.",
                status="sent",
                sent="22,100",
            ),
        ]
        db.add_all(initial_notifications)
        db.commit()

    # 5. Announcements
    if db.query(Announcement).count() == 0:
        initial_announcements = [
            Announcement(
                title="New City Launch — Goa",
                message="We are expanding to Goa! Merchants can now register.",
                date="2024-09-12",
                pinned=True,
            ),
            Announcement(
                title="Platform Maintenance",
                message="Scheduled maintenance on Sep 20, 2–4 AM IST.",
                date="2024-09-10",
                pinned=False,
            ),
            Announcement(
                title="Merchant Guidelines Updated",
                message="Please review the updated guidelines for listing your business.",
                date="2024-09-05",
                pinned=False,
            ),
        ]
        db.add_all(initial_announcements)
        db.commit()

    # 6. Geography Regions
    if db.query(GeographyRegion).count() == 0:
        initial_geography = [
            GeographyRegion(geo_code="GEO-001", city="Mumbai", state="Maharashtra", zones=12, merchants=820, users=5400, status="active"),
            GeographyRegion(geo_code="GEO-002", city="Bangalore", state="Karnataka", zones=10, merchants=650, users=4200, status="active"),
            GeographyRegion(geo_code="GEO-003", city="Delhi", state="Delhi", zones=8, merchants=580, users=3800, status="active"),
            GeographyRegion(geo_code="GEO-004", city="Chennai", state="Tamil Nadu", zones=7, merchants=420, users=2900, status="active"),
            GeographyRegion(geo_code="GEO-005", city="Hyderabad", state="Telangana", zones=6, merchants=380, users=2600, status="active"),
            GeographyRegion(geo_code="GEO-006", city="Pune", state="Maharashtra", zones=5, merchants=310, users=2100, status="active"),
            GeographyRegion(geo_code="GEO-007", city="Kolkata", state="West Bengal", zones=4, merchants=180, users=1200, status="active"),
            GeographyRegion(geo_code="GEO-008", city="Jaipur", state="Rajasthan", zones=3, merchants=120, users=800, status="active"),
            GeographyRegion(geo_code="GEO-009", city="Kochi", state="Kerala", zones=3, merchants=95, users=650, status="active"),
            GeographyRegion(geo_code="GEO-010", city="Goa", state="Goa", zones=2, merchants=65, users=400, status="pending"),
            GeographyRegion(geo_code="GEO-011", city="Lucknow", state="Uttar Pradesh", zones=0, merchants=0, users=0, status="pending"),
            GeographyRegion(geo_code="GEO-012", city="Ahmedabad", state="Gujarat", zones=0, merchants=0, users=0, status="inactive"),
        ]
        db.add_all(initial_geography)
        db.commit()
