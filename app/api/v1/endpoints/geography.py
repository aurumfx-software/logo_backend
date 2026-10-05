from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_admin_user_flexible
from app.db.database import get_db
from app.db.models.user import User
from app.schemas.geography import (
    GeographyRegionCreateRequest,
    GeographyRegionResponse,
    GeographyRegionUpdateRequest,
    GeographySummaryResponse,
)
from app.schemas.response import (
    StandardListResponse,
    StandardResponse,
    list_response,
    success_response,
)
from app.services.geography_service import GeographyService

router = APIRouter(prefix="/geography", tags=["Geography & Service Area Management"])


@router.get("", response_model=StandardListResponse[GeographyRegionResponse], summary="List all geography regions")
def list_geography(
    status: Optional[str] = Query(None, description="Filter by status (active, pending, inactive, all)"),
    search: Optional[str] = Query(None, description="Search by city, state, geo_code"),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    regions = GeographyService.get_all(db, status_filter=status, search=search)
    return list_response(
        data=[GeographyRegionResponse.model_validate(r) for r in regions],
        total_items=len(regions),
        message="Geography regions retrieved successfully",
    )


@router.get("/summary", response_model=StandardResponse[GeographySummaryResponse], summary="Get geography stats summary")
def get_geography_summary(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    summary = GeographyService.get_summary(db)
    return success_response(
        data=GeographySummaryResponse(**summary),
        message="Geography summary retrieved successfully",
    )


@router.post("", response_model=StandardResponse[GeographyRegionResponse], status_code=status.HTTP_201_CREATED, summary="Add new city/region")
def create_region(
    payload: GeographyRegionCreateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    region = GeographyService.create(db, payload)
    return success_response(
        data=GeographyRegionResponse.model_validate(region),
        message="City/region added successfully",
    )


@router.get("/{geo_id}", response_model=StandardResponse[GeographyRegionResponse], summary="Get region by ID")
def get_region(
    geo_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    region = GeographyService.get_by_id(db, geo_id)
    return success_response(
        data=GeographyRegionResponse.model_validate(region),
        message="Region retrieved successfully",
    )


@router.put("/{geo_id}", response_model=StandardResponse[GeographyRegionResponse], summary="Update region")
def update_region(
    geo_id: int,
    payload: GeographyRegionUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    region = GeographyService.update(db, geo_id, payload)
    return success_response(
        data=GeographyRegionResponse.model_validate(region),
        message="Region updated successfully",
    )


@router.delete("/{geo_id}", response_model=StandardResponse[bool], summary="Delete region")
def delete_region(
    geo_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    GeographyService.delete(db, geo_id)
    return success_response(
        data=True,
        message="Region deleted successfully",
    )
