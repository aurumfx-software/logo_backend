from typing import Optional
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_admin_user_flexible
from app.db.database import get_db
from app.db.models.user import User
from app.schemas.report import ReportOverviewResponse
from app.schemas.response import StandardResponse, success_response
from app.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["Reports & Analytics"])


@router.get("/overview", response_model=StandardResponse[ReportOverviewResponse], summary="Get overall reports data & monthly trends")
def get_reports_overview(
    from_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    overview = ReportService.get_overview(db, from_date=from_date, to_date=to_date)
    return success_response(
        data=ReportOverviewResponse(**overview),
        message="Reports overview generated successfully",
    )


@router.get("/export/csv", summary="Export report data as CSV")
def export_csv_report(
    type: str = Query("merchants", description="Report type (merchants, users, transactions)"),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    csv_content = ReportService.generate_csv_report(db, type)
    filename = f"logo_{type}_report.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
