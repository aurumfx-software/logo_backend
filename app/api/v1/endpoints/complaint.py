from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_admin_user_flexible, get_current_user_optional
from app.db.database import get_db
from app.db.models.user import User
from app.schemas.complaint import (
    ComplaintCreateRequest,
    ComplaintFixRequest,
    ComplaintResolveRequest,
    ComplaintResponse,
    ComplaintStatusUpdateRequest,
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
    category: Optional[str] = Query(None, description="Filter by category (e.g. Service Quality, Order Issue)"),
    priority: Optional[str] = Query(None, description="Filter by priority (high, medium, low)"),
    search: Optional[str] = Query(None, description="Search by subject, user, merchant, category, complaint_code"),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    """List complaints with flexible status, category, priority, and text search filters."""
    complaints = ComplaintService.get_all(
        db,
        status_filter=status,
        search=search,
        category=category,
        priority=priority,
    )
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
    """Get metrics count of complaints (all, open, in-progress, resolved)."""
    counts = ComplaintService.get_counts(db)
    return success_response(data=counts, message="Counts retrieved successfully")


@router.post("", response_model=StandardResponse[ComplaintResponse], status_code=status.HTTP_201_CREATED, summary="Create a new complaint")
def create_complaint(
    payload: ComplaintCreateRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Create a new complaint.
    Can be submitted by authenticated users, customers, or admins.
    """
    fallback_user = current_user.name if current_user else None
    fallback_email = current_user.email if current_user else None
    fallback_phone = current_user.phone if current_user else None

    complaint = ComplaintService.create(
        db=db,
        data=payload,
        fallback_user=fallback_user,
        fallback_email=fallback_email,
        fallback_phone=fallback_phone,
    )
    return success_response(
        data=ComplaintResponse.model_validate(complaint),
        message="Complaint submitted successfully",
    )


@router.get("/{complaint_id}", response_model=StandardResponse[ComplaintResponse], summary="Get / View complaint details")
def get_complaint(
    complaint_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    """View single complaint details by ID."""
    complaint = ComplaintService.get_by_id(db, complaint_id)
    return success_response(
        data=ComplaintResponse.model_validate(complaint),
        message="Complaint details retrieved successfully",
    )


@router.put("/{complaint_id}", response_model=StandardResponse[ComplaintResponse], summary="Edit / Update complaint details")
@router.patch("/{complaint_id}", response_model=StandardResponse[ComplaintResponse], summary="Patch complaint details")
def update_complaint(
    complaint_id: int,
    payload: ComplaintUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    """Edit or update complaint fields (subject, user, merchant, phone, status, admin response, etc.)."""
    complaint = ComplaintService.update(db, complaint_id, payload)
    return success_response(
        data=ComplaintResponse.model_validate(complaint),
        message="Complaint updated successfully",
    )


@router.patch("/{complaint_id}/resolve", response_model=StandardResponse[ComplaintResponse], summary="Resolve complaint")
@router.patch("/{complaint_id}/fix", response_model=StandardResponse[ComplaintResponse], summary="Fix complaint (Alias)")
@router.post("/{complaint_id}/fix", response_model=StandardResponse[ComplaintResponse], summary="Fix complaint (POST Alias)")
@router.post("/{complaint_id}/resolve", response_model=StandardResponse[ComplaintResponse], summary="Resolve complaint (POST Alias)")
def resolve_complaint(
    complaint_id: int,
    payload: ComplaintResolveRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    """
    Fix or resolve a complaint.
    Marks status as 'resolved', records resolved_at timestamp, and attaches admin response.
    """
    complaint = ComplaintService.resolve(db, complaint_id, payload)
    return success_response(
        data=ComplaintResponse.model_validate(complaint),
        message="Complaint resolved and fixed successfully",
    )


@router.patch("/{complaint_id}/status", response_model=StandardResponse[ComplaintResponse], summary="Update complaint status")
@router.put("/{complaint_id}/status", response_model=StandardResponse[ComplaintResponse], summary="Update complaint status (PUT Alias)")
def update_complaint_status(
    complaint_id: int,
    payload: ComplaintStatusUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    """Update status of a complaint directly ('open', 'in-progress', 'resolved')."""
    complaint = ComplaintService.update_status(
        db,
        complaint_id=complaint_id,
        status_val=payload.status,
        admin_response=payload.admin_response,
    )
    return success_response(
        data=ComplaintResponse.model_validate(complaint),
        message=f"Complaint status updated to {payload.status} successfully",
    )


@router.delete("/{complaint_id}", response_model=StandardResponse[bool], summary="Delete complaint")
def delete_complaint(
    complaint_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    """Delete complaint record permanently."""
    ComplaintService.delete(db, complaint_id)
    return success_response(
        data=True,
        message="Complaint deleted successfully",
    )
