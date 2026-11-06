from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models.geography import ServiceArea
from app.db.models.merchant import MerchantProfile
from app.db.models.user import User, UserRole
from app.schemas.geography import (
    GeographyCards,
    GeographyDistrictItem,
    GeographyResponse,
    GeographyTownCreateRequest,
    GeographyTownItem,
)

KERALA_DISTRICTS = [
    "Kannur",
    "Kozhikode",
    "Kasaragod",
    "Thrissur",
    "Ernakulam",
    "Thiruvananthapuram",
    "Malappuram",
    "Palakkad",
    "Kollam",
    "Kottayam",
    "Alappuzha",
    "Pathanamthitta",
    "Wayanad",
    "Idukki",
]


class GeographyService:
    @staticmethod
    def get_geography(
        db: Session,
        district: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> GeographyResponse:
        selected = GeographyService._canonical_district(district) if district else None
        if district and district.strip().lower() not in {"", "all", "all districts"} and selected is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="district must be one of the 14 Kerala districts.",
            )

        merchants = db.query(MerchantProfile).all()
        users = (
            db.query(User)
            .filter(User.is_active.is_(True), User.role == UserRole.FIELD_STAFF)
            .all()
        )
        areas = db.query(ServiceArea).filter(ServiceArea.is_active.is_(True)).all()
        towns = GeographyService._build_towns(areas, merchants, users)
        if selected:
            towns = [row for row in towns if row.district == selected]
        if search and search.strip():
            needle = search.strip().lower()
            towns = [
                row
                for row in towns
                if needle in row.town.lower()
                or needle in row.district.lower()
                or any(needle in zone.lower() for zone in row.zones)
            ]
        towns.sort(key=lambda row: (row.district, row.town.lower()))

        district_rows = GeographyService._district_rows(towns if not selected else GeographyService._build_towns(areas, merchants, users))
        cards = GeographyService._cards(merchants, users, towns if not selected else [row for row in GeographyService._build_towns(areas, merchants, users)])
        total = len(towns)
        start = (page - 1) * page_size
        return GeographyResponse(
            cards=cards,
            districts=district_rows,
            towns=towns[start : start + page_size],
            total=total,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def add_town(db: Session, payload: GeographyTownCreateRequest) -> GeographyTownItem:
        district = GeographyService._canonical_district(payload.district)
        if district is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="district must be one of the 14 Kerala districts.",
            )
        town = payload.town.strip()
        zones = [zone.strip() for zone in payload.zones if zone and zone.strip()]
        existing = (
            db.query(ServiceArea)
            .filter(ServiceArea.district == district, ServiceArea.town.ilike(town))
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This town is already listed in that district.",
            )
        area = ServiceArea(district=district, town=town, zones=zones, is_active=True)
        db.add(area)
        db.commit()
        db.refresh(area)
        report = GeographyService.get_geography(db, district=district, search=town, page=1, page_size=50)
        for row in report.towns:
            if row.town.lower() == town.lower():
                return row
        return GeographyTownItem(
            id=area.id,
            district=district,
            town=town,
            zones=zones,
            registered_merchants=0,
            customer_reach=0,
            coverage_status="NO_COVERAGE",
        )

    @staticmethod
    def _cards(merchants, users, towns) -> GeographyCards:
        verified = sum(
            1
            for merchant in merchants
            if merchant.is_verified or (merchant.approval_status or "").upper() in {"APPROVED", "VERIFIED"}
        )
        districts_with_merchants = sum(
            1
            for name in KERALA_DISTRICTS
            if any(GeographyService._same_district(merchant.district, name) for merchant in merchants)
        )
        active_municipalities = sum(1 for town in towns if town.registered_merchants > 0)
        return GeographyCards(
            kerala_districts_covered=len(KERALA_DISTRICTS),
            kerala_districts_total=len(KERALA_DISTRICTS),
            kerala_districts_percent=100,
            districts_with_merchants=districts_with_merchants,
            active_municipalities=active_municipalities,
            real_merchants=len(merchants),
            verified_merchants=verified,
            active_users_reach=len(users),
        )

    @staticmethod
    def _district_rows(towns: List[GeographyTownItem]) -> List[GeographyDistrictItem]:
        rows = []
        for name in KERALA_DISTRICTS:
            matched = [town for town in towns if town.district == name]
            merchants = sum(town.registered_merchants for town in matched)
            customers = sum(town.customer_reach for town in matched)
            rows.append(
                GeographyDistrictItem(
                    name=name,
                    merchants=merchants,
                    customers=customers,
                    towns=len(matched),
                    covered=merchants > 0,
                )
            )
        return rows

    @staticmethod
    def _build_towns(areas, merchants, users) -> List[GeographyTownItem]:
        buckets: Dict[Tuple[str, str], dict] = {}

        def bucket(district: str, town: str) -> dict:
            key = (district, town.strip().lower())
            if key not in buckets:
                buckets[key] = {
                    "id": None,
                    "district": district,
                    "town": town.strip(),
                    "zones": [],
                    "merchants": 0,
                    "customers": 0,
                }
            return buckets[key]

        for area in areas:
            row = bucket(area.district, area.town)
            row["id"] = area.id
            row["town"] = area.town
            for zone in area.zones or []:
                if zone not in row["zones"]:
                    row["zones"].append(zone)

        for merchant in merchants:
            district = GeographyService._canonical_district(merchant.district)
            town = (merchant.city or merchant.location or "").strip()
            if not district or not town:
                continue
            row = bucket(district, town)
            row["merchants"] += 1
            location = (merchant.location or "").strip()
            if location and location.lower() != town.lower() and location not in row["zones"]:
                row["zones"].append(location)

        for user in users:
            district = GeographyService._canonical_district(user.district)
            town = (user.city or user.location or "").strip()
            if not district or not town:
                continue
            if (district, town.lower()) in buckets:
                buckets[(district, town.lower())]["customers"] += 1

        items = []
        for row in buckets.values():
            items.append(
                GeographyTownItem(
                    id=row["id"],
                    district=row["district"],
                    town=row["town"],
                    zones=row["zones"],
                    registered_merchants=row["merchants"],
                    customer_reach=row["customers"],
                    coverage_status="COVERED" if row["merchants"] > 0 else "NO_COVERAGE",
                )
            )
        return items

    @staticmethod
    def _canonical_district(value: Optional[str]) -> Optional[str]:
        if not value or not str(value).strip():
            return None
        text = str(value).strip().lower()
        if text in {"all", "all districts"}:
            return None
        for name in KERALA_DISTRICTS:
            lowered = name.lower()
            if text == lowered or lowered in text or text in lowered:
                return name
        return None

    @staticmethod
    def _same_district(value: Optional[str], district: str) -> bool:
        return GeographyService._canonical_district(value) == district
