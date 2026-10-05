from typing import Dict, List, Optional
from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models.geography import GeographyRegion
from app.schemas.geography import GeographyRegionCreateRequest, GeographyRegionUpdateRequest


class GeographyService:
    @staticmethod
    def get_all(
        db: Session,
        status_filter: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[GeographyRegion]:
        query = db.query(GeographyRegion)
        if status_filter and status_filter.lower() != "all":
            query = query.filter(GeographyRegion.status == status_filter.lower())
        if search:
            s = f"%{search}%"
            query = query.filter(
                or_(
                    GeographyRegion.city.ilike(s),
                    GeographyRegion.state.ilike(s),
                    GeographyRegion.geo_code.ilike(s),
                )
            )
        return query.order_by(GeographyRegion.id.asc()).all()

    @staticmethod
    def get_summary(db: Session) -> Dict[str, int]:
        total_cities = db.query(GeographyRegion).count()
        active_cities = db.query(GeographyRegion).filter(GeographyRegion.status == "active").count()
        regions = db.query(GeographyRegion).all()
        total_zones = sum(r.zones for r in regions)
        return {
            "total_cities": total_cities,
            "active_cities": active_cities,
            "total_zones": total_zones,
        }

    @staticmethod
    def get_by_id(db: Session, geo_id: int) -> GeographyRegion:
        region = db.query(GeographyRegion).filter(GeographyRegion.id == geo_id).first()
        if not region:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Region with ID {geo_id} not found",
            )
        return region

    @staticmethod
    def create(db: Session, data: GeographyRegionCreateRequest) -> GeographyRegion:
        count = db.query(GeographyRegion).count() + 1
        code = f"GEO-{count:03d}"

        region = GeographyRegion(
            geo_code=code,
            city=data.city,
            state=data.state,
            zones=data.zones if data.zones is not None else 1,
            merchants=data.merchants or 0,
            users=data.users or 0,
            status=data.status or "active",
        )
        db.add(region)
        db.commit()
        db.refresh(region)
        return region

    @staticmethod
    def update(db: Session, geo_id: int, data: GeographyRegionUpdateRequest) -> GeographyRegion:
        region = GeographyService.get_by_id(db, geo_id)
        if data.city is not None:
            region.city = data.city
        if data.state is not None:
            region.state = data.state
        if data.zones is not None:
            region.zones = data.zones
        if data.merchants is not None:
            region.merchants = data.merchants
        if data.users is not None:
            region.users = data.users
        if data.status is not None:
            region.status = data.status

        db.commit()
        db.refresh(region)
        return region

    @staticmethod
    def delete(db: Session, geo_id: int) -> bool:
        region = GeographyService.get_by_id(db, geo_id)
        db.delete(region)
        db.commit()
        return True
