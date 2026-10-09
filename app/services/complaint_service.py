from datetime import datetime, timezone
from typing import Dict, List, Optional
from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models.complaint import Complaint
from app.schemas.complaint import ComplaintCreateRequest, ComplaintResolveRequest, ComplaintUpdateRequest


class ComplaintService:
    @staticmethod
    def get_all(
        db: Session,
        status_filter: Optional[str] = None,
        search: Optional[str] = None,
        category: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> List[Complaint]:
        query = db.query(Complaint)
        if status_filter and status_filter.lower() != "all":
            query = query.filter(Complaint.status == status_filter.lower())
        if category and category.lower() != "all":
            query = query.filter(Complaint.category.ilike(f"%{category}%"))
        if priority and priority.lower() != "all":
            query = query.filter(Complaint.priority == priority.lower())
        if search:
            s = f"%{search}%"
            query = query.filter(
                or_(
                    Complaint.subject.ilike(s),
                    Complaint.user.ilike(s),
                    Complaint.merchant.ilike(s),
                    Complaint.category.ilike(s),
                    Complaint.complaint_code.ilike(s),
                )
            )
        return query.order_by(Complaint.id.desc()).all()

    @staticmethod
    def get_counts(db: Session) -> Dict[str, int]:
        all_c = db.query(Complaint).count()
        open_c = db.query(Complaint).filter(Complaint.status == "open").count()
        in_prog_c = db.query(Complaint).filter(Complaint.status == "in-progress").count()
        resolved_c = db.query(Complaint).filter(Complaint.status == "resolved").count()
        return {
            "all": all_c,
            "open": open_c,
            "in-progress": in_prog_c,
            "resolved": resolved_c,
        }

    @staticmethod
    def get_by_id(db: Session, complaint_id: int) -> Complaint:
        complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
        if not complaint:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Complaint with ID {complaint_id} not found",
            )
        return complaint

    @staticmethod
    def create(
        db: Session,
        data: ComplaintCreateRequest,
        fallback_user: Optional[str] = None,
        fallback_email: Optional[str] = None,
        fallback_phone: Optional[str] = None,
    ) -> Complaint:
        last_complaint = db.query(Complaint).order_by(Complaint.id.desc()).first()
        next_num = (last_complaint.id + 1) if last_complaint else 1
        code = f"CMP-{next_num:03d}"
        while db.query(Complaint).filter(Complaint.complaint_code == code).first():
            next_num += 1
            code = f"CMP-{next_num:03d}"

        user_name = data.user or fallback_user or "Customer"
        user_email = data.user_email or fallback_email
        user_phone = data.user_phone or fallback_phone

        complaint = Complaint(
            complaint_code=code,
            user=user_name,
            user_email=user_email,
            user_phone=user_phone,
            merchant=data.merchant,
            subject=data.subject,
            category=data.category or "Service Quality",
            priority=data.priority or "medium",
            status=data.status or "open",
            date=data.date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            description=data.description,
        )
        db.add(complaint)
        db.commit()
        db.refresh(complaint)
        return complaint

    @staticmethod
    def update(db: Session, complaint_id: int, data: ComplaintUpdateRequest) -> Complaint:
        complaint = ComplaintService.get_by_id(db, complaint_id)
        if data.user is not None:
            complaint.user = data.user
        if data.user_email is not None:
            complaint.user_email = data.user_email
        if data.user_phone is not None:
            complaint.user_phone = data.user_phone
        if data.merchant is not None:
            complaint.merchant = data.merchant
        if data.subject is not None:
            complaint.subject = data.subject
        if data.category is not None:
            complaint.category = data.category
        if data.priority is not None:
            complaint.priority = data.priority
        if data.status is not None:
            complaint.status = data.status
            if data.status == "resolved" and not complaint.resolved_at:
                complaint.resolved_at = datetime.now(timezone.utc)
        if data.description is not None:
            complaint.description = data.description
        if data.admin_response is not None:
            complaint.admin_response = data.admin_response

        db.commit()
        db.refresh(complaint)
        return complaint

    @staticmethod
    def resolve(db: Session, complaint_id: int, data: ComplaintResolveRequest) -> Complaint:
        complaint = ComplaintService.get_by_id(db, complaint_id)
        complaint.status = data.status or "resolved"
        complaint.resolved_at = datetime.now(timezone.utc)
        if data.admin_response:
            complaint.admin_response = data.admin_response
        db.commit()
        db.refresh(complaint)
        return complaint

    @staticmethod
    def update_status(db: Session, complaint_id: int, status_val: str, admin_response: Optional[str] = None) -> Complaint:
        complaint = ComplaintService.get_by_id(db, complaint_id)
        complaint.status = status_val.lower()
        if complaint.status == "resolved" and not complaint.resolved_at:
            complaint.resolved_at = datetime.now(timezone.utc)
        if admin_response:
            complaint.admin_response = admin_response
        db.commit()
        db.refresh(complaint)
        return complaint

    @staticmethod
    def delete(db: Session, complaint_id: int) -> bool:
        complaint = ComplaintService.get_by_id(db, complaint_id)
        db.delete(complaint)
        db.commit()
        return True
