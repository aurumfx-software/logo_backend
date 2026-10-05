from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_admin_user_flexible
from app.db.database import get_db
from app.db.models.user import User
from app.schemas.complaint import (
    ComplaintCreateRequest,
    ComplaintResolveRequest,
    ComplaintResponse,
    ComplaintUpdateRequest,
)
from app.schemas.response import (
    StandardListResponse,
    StandardResponse,
    list_response,
    success_response,
)
from app.services.complaint_service import ComplaintService

router = APIRouter(prefix="/complaints", tags=["Complaints & Disputes Management"])


@router.get("", response_model=StandardListResponse[ComplaintResponse], summary="List all complaints")
def list_complaints(
    status: Optional[str] = Query(None, description="Filter by status (open, in-progress, resolved, all)"),
    search: Optional[str] = Query(None, description="Search by subject, user, merchant, category"),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    complaints = ComplaintService.get_all(db, status_filter=status, search=search)
    return list_response(
        data=[ComplaintResponse.model_validate(c) for c in complaints],
        total_items=len(complaints),
        message="Complaints retrieved successfully",
    )


@router.get("/counts", response_model=StandardResponse[Dict[str, int]], summary="Get complaints count by status")
def get_complaints_counts(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    counts = ComplaintService.get_counts(db)
    return success_response(data=counts, message="Counts retrieved successfully")


@router.post("", response_model=StandardResponse[ComplaintResponse], status_code=status.HTTP_201_CREATED, summary="Create a new complaint")
def create_complaint(
    payload: ComplaintCreateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    complaint = ComplaintService.create(db, payload)
    return success_response(
        data=ComplaintResponse.model_validate(complaint),
        message="Complaint submitted successfully",
    )


@router.get("/{complaint_id}", response_model=StandardResponse[ComplaintResponse], summary="Get complaint details")
def get_complaint(
    complaint_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    complaint = ComplaintService.get_by_id(db, complaint_id)
    return success_response(
        data=ComplaintResponse.model_validate(complaint),
        message="Complaint details retrieved successfully",
    )


@router.put("/{complaint_id}", response_model=StandardResponse[ComplaintResponse], summary="Update complaint details")
def update_complaint(
    complaint_id: int,
    payload: ComplaintUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    complaint = ComplaintService.update(db, complaint_id, payload)
    return success_response(
        data=ComplaintResponse.model_validate(complaint),
        message="Complaint updated successfully",
    )


@router.patch("/{complaint_id}/resolve", response_model=StandardResponse[ComplaintResponse], summary="Resolve complaint")
def resolve_complaint(
    complaint_id: int,
    payload: ComplaintResolveRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    complaint = ComplaintService.resolve(db, complaint_id, payload)
    return success_response(
        data=ComplaintResponse.model_validate(complaint),
        message="Complaint resolved successfully",
    )


@router.delete("/{complaint_id}", response_model=StandardResponse[bool], summary="Delete complaint")
def delete_complaint(
    complaint_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    ComplaintService.delete(db, complaint_id)
    return success_response(
        data=True,
        message="Complaint deleted successfully",
    )
