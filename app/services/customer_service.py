import math
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
from app.schemas.customer import (
    CustomerRegisterRequest,
    CustomerLoginRequest,
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
    def register_customer(db: Session, data: CustomerRegisterRequest) -> Tuple[User, str, str]:
        clean_email = data.email.strip().lower()

        # 1. Check existing email
        if db.query(User).filter(User.email == clean_email).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email address already exists.",
            )

        # 2. Check existing phone if provided
        clean_phone = data.phone.strip() if data.phone else None
        if clean_phone:
            if db.query(User).filter(User.phone == clean_phone).first():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An account with this phone number already exists.",
                )

        hashed = hash_password(data.password)

        new_user = User(
            name=data.name.strip(),
            email=clean_email,
            phone=clean_phone,
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
