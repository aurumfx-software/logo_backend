from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from app.db.models.activity_log import ActivityLog
from app.db.models.user import User


class ActivityLogService:
    @staticmethod
    def log_activity(
        db: Session,
        action: str,
        entity_type: str,
        entity_id: Optional[int] = None,
        user_id: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
    ) -> ActivityLog:
        log = ActivityLog(
            user_id=user_id,
            action=action.strip().upper(),
            entity_type=entity_type.strip().upper(),
            entity_id=entity_id,
            details=details,
            ip_address=ip_address,
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    @staticmethod
    def list_activity_logs(
        db: Session,
        action: Optional[str] = None,
        entity_type: Optional[str] = None,
        user_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[dict], int]:
        query = db.query(ActivityLog).outerjoin(User, ActivityLog.user_id == User.id)

        if action:
            query = query.filter(ActivityLog.action.ilike(f"%{action.strip()}%"))
        if entity_type:
            query = query.filter(ActivityLog.entity_type.ilike(f"%{entity_type.strip()}%"))
        if user_id is not None:
            query = query.filter(ActivityLog.user_id == user_id)

        total = query.count()
        logs = (
            query.order_by(ActivityLog.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

        items = []
        for log in logs:
            items.append({
                "id": log.id,
                "user_id": log.user_id,
                "user_name": log.user.name if log.user else None,
                "action": log.action,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "details": log.details,
                "ip_address": log.ip_address,
                "created_at": log.created_at,
            })

        return items, total

    @staticmethod
    def get_action_types(db: Session) -> List[str]:
        rows = db.query(ActivityLog.action).distinct().all()
        return sorted([r[0] for r in rows if r[0]])
