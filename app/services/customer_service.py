import math
import re
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.db.models.user import User, UserRole
from app.db.models.merchant import MerchantProfile
from app.db.models.merchant_favorite import CustomerMerchantFavorite
from app.schemas.customer import (
    CustomerRegisterRequest,
    CustomerLoginRequest,
    CustomerPhoneLoginRequest,
    CustomerLocationUpdateRequest,
    NearbyMerchantItem,
)


def calculate_haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in kilometers between two lat/lon coordinates."""
    R = 6371.0  # Earth's radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 2)


class CustomerService:
    @staticmethod
    def _build_merchant_item(m: MerchantProfile, distance_km: Optional[float] = None) -> NearbyMerchantItem:
        photos = list(m.merchant_photos or [])
        if m.photo_1 and m.photo_1 not in photos:
            photos.insert(0, m.photo_1)

        categories_list = list(m.categories or [])
        if m.category and m.category not in categories_list:
            categories_list.insert(0, m.category)

        return NearbyMerchantItem(
            id=m.id,
            user_code=m.user_code,
            business_name=m.business_name,
            category=m.category or (categories_list[0] if categories_list else "Retail"),
            categories=categories_list,
            owner=m.owner or m.owner_name or "Business Owner",
            phone=m.phone or m.contact_number,
            whatsapp=m.whatsapp or m.phone or m.contact_number,
            email=m.email,
            district=m.district,
            city=m.city,
            location=m.location or m.city,
            address=m.address or f"{m.city or ''}, {m.district or ''}",
            latitude=float(m.latitude) if m.latitude is not None else None,
            longitude=float(m.longitude) if m.longitude is not None else None,
            distance_km=distance_km,
            rating=float(m.rating) if m.rating is not None else 4.5,
            reviews_count=m.reviews_count or 0,
            photo_1=m.photo_1 or (photos[0] if photos else None),
            merchant_photos=photos,
            video_url=m.video_url,
            services=list(m.services or []),
            service_timing=m.service_timing or "General Store Hours",
            status=m.status or "APPROVED",
        )

    @staticmethod
    def phone_or_quick_login(db: Session, data: CustomerPhoneLoginRequest) -> Tuple[User, str, str]:
        """
        Instant OTP-free phone login and auto-registration for Customer Web & Mobile App.
        """
        digits = re.sub(r"[^0-9]", "", data.phone.strip())
        if not digits or len(digits) < 7:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Please enter a valid phone number with at least 7 digits.",
            )
        local_10 = digits[-10:] if len(digits) >= 10 else digits

        # Search existing user by phone variations
        user = (
            db.query(User)
            .filter(
                or_(
                    User.phone == digits,
                    User.phone == f"+91{local_10}",
                    User.phone == f"+91 {local_10}",
                    User.phone == local_10,
                    User.phone.like(f"%{local_10}"),
                )
            )
            .first()
        )

        if user:
            # Update user info if newly provided
            if data.name and data.name.strip() and (not user.name or user.name.startswith("Customer (")):
                user.name = data.name.strip()
            if data.district and data.district.strip() and not user.district:
                user.district = data.district.strip()
            if data.city and data.city.strip() and not user.city:
                user.city = data.city.strip()
            if data.location and data.location.strip() and not user.location:
                user.location = data.location.strip()
            if data.latitude is not None and user.latitude is None:
                user.latitude = data.latitude
            if data.longitude is not None and user.longitude is None:
                user.longitude = data.longitude

            user.last_active = datetime.now(timezone.utc)
            db.commit()
            db.refresh(user)
        else:
            # Auto-register new Customer account
            clean_name = data.name.strip() if data.name and data.name.strip() else f"Customer ({local_10[-4:]})"
            fallback_email = f"customer_{local_10}@logokerala.in"
            counter = 1
            while db.query(User).filter(User.email == fallback_email).first():
                fallback_email = f"customer_{local_10}_{counter}@logokerala.in"
                counter += 1

            dummy_pass = hash_password(f"LogoCust@{local_10[-4:]}#98")

            user = User(
                name=clean_name,
                email=fallback_email,
                phone=f"+91 {local_10}",
                password=dummy_pass,
                password_hash=dummy_pass,
                role=UserRole.CUSTOMER,
                district=data.district.strip() if data.district else "Kannur",
                city=data.city.strip() if data.city else "Payyanur",
                location=data.location.strip() if data.location else None,
                latitude=data.latitude,
                longitude=data.longitude,
                status="ACTIVE",
                is_active=True,
                is_verified=True,
                send_email=False,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        role_str = user.role.value if hasattr(user.role, "value") else str(user.role)
        access_token = create_access_token(user_id=user.id, role=role_str)
        refresh_token = create_refresh_token(user_id=user.id, role=role_str)

        return user, access_token, refresh_token

    @staticmethod
    def register_customer(db: Session, data: CustomerRegisterRequest) -> Tuple[User, str, str]:
        # Clean phone
        clean_phone = data.phone.strip() if data.phone else None
        local_10 = None
        if clean_phone:
            digits = re.sub(r"[^0-9]", "", clean_phone)
            local_10 = digits[-10:] if len(digits) >= 10 else digits
            existing_phone_user = db.query(User).filter(
                or_(
                    User.phone == clean_phone,
                    User.phone == local_10,
                    User.phone == f"+91 {local_10}",
                    User.phone == f"+91{local_10}",
                )
            ).first()
            if existing_phone_user:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An account with this phone number already exists. Please log in.",
                )

        # Clean email or auto-generate fallback
        if data.email and data.email.strip():
            clean_email = data.email.strip().lower()
            if db.query(User).filter(User.email == clean_email).first():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An account with this email address already exists.",
                )
        else:
            ref_num = local_10 or str(int(datetime.now().timestamp()))
            clean_email = f"customer_{ref_num}@logokerala.in"
            counter = 1
            while db.query(User).filter(User.email == clean_email).first():
                clean_email = f"customer_{ref_num}_{counter}@logokerala.in"
                counter += 1

        raw_pass = data.password if data.password and data.password.strip() else (f"Logo@{local_10[-4:]}" if local_10 else "Customer@123")
        hashed = hash_password(raw_pass)

        new_user = User(
            name=data.name.strip(),
            email=clean_email,
            phone=f"+91 {local_10}" if local_10 else clean_phone,
            password=hashed,
            password_hash=hashed,
            role=UserRole.CUSTOMER,
            district=data.district.strip() if data.district else "Kannur",
            city=data.city.strip() if data.city else "Payyanur",
            location=data.location.strip() if data.location else None,
            address=data.address.strip() if data.address else None,
            latitude=data.latitude,
            longitude=data.longitude,
            status="ACTIVE",
            is_active=True,
            is_verified=True,
            send_email=True,
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        # Generate tokens
        role_str = "CUSTOMER"
        access_token = create_access_token(user_id=new_user.id, role=role_str)
        refresh_token = create_refresh_token(user_id=new_user.id, role=role_str)

        return new_user, access_token, refresh_token


    @staticmethod
    def login_customer(db: Session, data: CustomerLoginRequest) -> Tuple[User, str, str]:
        user = None
        if data.email:
            clean_email = data.email.strip().lower()
            user = db.query(User).filter(User.email == clean_email).first()

        if not user and data.phone:
            clean_phone = data.phone.strip()
            user = db.query(User).filter(User.phone == clean_phone).first()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not verify_password(data.password, user.password_hash or user.password or ""):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active or (user.status and user.status.upper() == "INACTIVE"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is inactive or suspended. Please contact support.",
            )

        user.last_active = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)

        role_str = user.role.value if hasattr(user.role, "value") else str(user.role)
        access_token = create_access_token(user_id=user.id, role=role_str)
        refresh_token = create_refresh_token(user_id=user.id, role=role_str)

        return user, access_token, refresh_token

    @staticmethod
    def update_location(
        db: Session, user: User, data: CustomerLocationUpdateRequest
    ) -> User:
        if data.district is not None:
            user.district = data.district.strip()
        if data.city is not None:
            user.city = data.city.strip()
        if data.location is not None:
            user.location = data.location.strip()
        if data.address is not None:
            user.address = data.address.strip()
        if data.latitude is not None:
            user.latitude = data.latitude
        if data.longitude is not None:
            user.longitude = data.longitude

        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def get_nearby_merchants(
        db: Session,
        customer_user: Optional[User] = None,
        district: Optional[str] = None,
        city: Optional[str] = None,
        location: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        radius_km: Optional[float] = 50.0,
        category: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """
        Finds approved merchants matching or closest to the customer's location.
        """
        target_district = (district or (customer_user.district if customer_user else None) or "").strip()
        target_city = (city or (customer_user.city if customer_user else None) or "").strip()
        target_loc = (location or (customer_user.location if customer_user else None) or "").strip()
        target_lat = latitude if latitude is not None else (customer_user.latitude if customer_user else None)
        target_lon = longitude if longitude is not None else (customer_user.longitude if customer_user else None)

        query = db.query(MerchantProfile).filter(
            or_(
                func.upper(MerchantProfile.approval_status).in_(["APPROVED", "ACTIVE"]),
                func.lower(MerchantProfile.status).in_(["active", "approved"]),
                MerchantProfile.approval_status == None,
            ),
            MerchantProfile.is_active == True,
        )

        if category and category.lower() != "all":
            clean_cat = category.strip()
            query = query.filter(
                or_(
                    MerchantProfile.category.ilike(f"%{clean_cat}%"),
                    MerchantProfile.categories.cast(func.text()).ilike(f"%{clean_cat}%"),
                )
            )

        if search and search.strip():
            clean_q = search.strip()
            query = query.filter(
                or_(
                    MerchantProfile.business_name.ilike(f"%{clean_q}%"),
                    MerchantProfile.category.ilike(f"%{clean_q}%"),
                    MerchantProfile.location.ilike(f"%{clean_q}%"),
                    MerchantProfile.city.ilike(f"%{clean_q}%"),
                    MerchantProfile.district.ilike(f"%{clean_q}%"),
                    MerchantProfile.address.ilike(f"%{clean_q}%"),
                )
            )

        candidates: List[MerchantProfile] = query.all()

        results_with_scores = []
        for m in candidates:
            dist_km = None
            if (
                target_lat is not None
                and target_lon is not None
                and m.latitude is not None
                and m.longitude is not None
            ):
                dist_km = calculate_haversine_distance(
                    target_lat, target_lon, m.latitude, m.longitude
                )

            loc_score = 0
            m_loc_str = f"{m.location or ''} {m.city or ''} {m.address or ''}".lower()
            m_dist_str = f"{m.district or ''}".lower()

            if target_loc and target_loc.lower() in m_loc_str:
                loc_score = 3
            elif target_city and target_city.lower() in m_loc_str:
                loc_score = 2
            elif target_district and target_district.lower() in m_dist_str:
                loc_score = 1

            results_with_scores.append({
                "merchant": m,
                "distance_km": dist_km,
                "loc_score": loc_score,
            })

        if target_lat is not None and target_lon is not None:
            results_with_scores.sort(
                key=lambda x: (
                    0 if x["distance_km"] is not None and x["distance_km"] <= (radius_km or 50.0) else 1,
                    x["distance_km"] if x["distance_km"] is not None else 999999,
                    -x["loc_score"],
                    -float(x["merchant"].rating or 0.0),
                )
            )
        else:
            results_with_scores.sort(
                key=lambda x: (
                    -x["loc_score"],
                    -float(x["merchant"].rating or 0.0),
                )
            )

        items: List[NearbyMerchantItem] = []
        for entry in results_with_scores[:limit]:
            m: MerchantProfile = entry["merchant"]
            photos = list(m.merchant_photos or [])
            if m.photo_1 and m.photo_1 not in photos:
                photos.insert(0, m.photo_1)

            categories_list = list(m.categories or [])
            if m.category and m.category not in categories_list:
                categories_list.insert(0, m.category)

            item = NearbyMerchantItem(
                id=m.id,
                user_code=m.user_code,
                business_name=m.business_name,
                category=m.category or (categories_list[0] if categories_list else "Retail"),
                categories=categories_list,
                owner=m.owner or "Business Owner",
                phone=m.phone or m.contact_number,
                whatsapp=m.whatsapp or m.phone or m.contact_number,
                email=m.email,
                district=m.district,
                city=m.city,
                location=m.location or m.city,
                address=m.address or f"{m.city or ''}, {m.district or ''}",
                latitude=m.latitude,
                longitude=m.longitude,
                distance_km=entry["distance_km"],
                rating=float(m.rating) if m.rating is not None else 4.5,
                reviews_count=m.reviews_count or 0,
                photo_1=m.photo_1 or (photos[0] if photos else None),
                merchant_photos=photos,
                video_url=m.video_url,
                services=list(m.services or []),
                service_timing=m.service_timing or "General Store Hours",
                status=m.status or "APPROVED",
            )
            items.append(item)

        return {
            "success": True,
            "total": len(items),
            "customer_location": {
                "district": target_district or None,
                "city": target_city or None,
                "location": target_loc or None,
                "latitude": target_lat,
                "longitude": target_lon,
            },
            "merchants": items,
        }

    @staticmethod
    def toggle_merchant_favorite(db: Session, user: User, merchant_id: int) -> Tuple[bool, List[int]]:
        """
        Toggle merchant in customer's favorites list.
        """
        merchant = db.query(MerchantProfile).filter(MerchantProfile.id == merchant_id).first()
        if not merchant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Merchant with ID {merchant_id} not found.",
            )

        existing = (
            db.query(CustomerMerchantFavorite)
            .filter(
                CustomerMerchantFavorite.user_id == user.id,
                CustomerMerchantFavorite.merchant_id == merchant_id,
            )
            .first()
        )

        if existing:
            db.delete(existing)
            db.commit()
            is_fav = False
        else:
            new_fav = CustomerMerchantFavorite(user_id=user.id, merchant_id=merchant_id)
            db.add(new_fav)
            db.commit()
            is_fav = True

        all_fav_ids = [
            r[0]
            for r in db.query(CustomerMerchantFavorite.merchant_id)
            .filter(CustomerMerchantFavorite.user_id == user.id)
            .all()
        ]
        return is_fav, all_fav_ids

    @staticmethod
    def sync_merchant_favorites(db: Session, user: User, merchant_ids: List[int]) -> List[int]:
        """
        Merge local guest wishlist into customer's cloud account.
        """
        existing_ids = set(
            r[0]
            for r in db.query(CustomerMerchantFavorite.merchant_id)
            .filter(CustomerMerchantFavorite.user_id == user.id)
            .all()
        )

        if merchant_ids:
            valid_merchants = (
                db.query(MerchantProfile.id)
                .filter(MerchantProfile.id.in_(merchant_ids))
                .all()
            )
            valid_ids = {r[0] for r in valid_merchants}

            for m_id in valid_ids:
                if m_id not in existing_ids:
                    new_fav = CustomerMerchantFavorite(user_id=user.id, merchant_id=m_id)
                    db.add(new_fav)
                    existing_ids.add(m_id)

            db.commit()

        return sorted(list(existing_ids))

    @staticmethod
    def get_user_merchant_favorites(db: Session, user: User) -> Tuple[List[int], List[NearbyMerchantItem]]:
        """
        Retrieve all merchant favorites for the customer.
        """
        fav_records = (
            db.query(CustomerMerchantFavorite)
            .filter(CustomerMerchantFavorite.user_id == user.id)
            .order_by(CustomerMerchantFavorite.created_at.desc())
            .all()
        )
        fav_ids = [f.merchant_id for f in fav_records]
        if not fav_ids:
            return [], []

        merchants = db.query(MerchantProfile).filter(MerchantProfile.id.in_(fav_ids)).all()
        merchant_map = {m.id: m for m in merchants}

        items: List[NearbyMerchantItem] = []
        for fid in fav_ids:
            if fid in merchant_map:
                items.append(CustomerService._build_merchant_item(merchant_map[fid]))

        return fav_ids, items

    @staticmethod
    def clear_user_merchant_favorites(db: Session, user: User) -> bool:
        """
        Clear all saved favorites for the customer.
        """
        db.query(CustomerMerchantFavorite).filter(
            CustomerMerchantFavorite.user_id == user.id
        ).delete()
        db.commit()
        return True

