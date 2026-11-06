from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.database import get_db
from app.db.models.user import User
from app.schemas.report import AdminReportsResponse, EngagementReport, LeadsReport
from app.services.report_service import ReportService

router = APIRouter(prefix="/admin/reports", tags=["Admin Reports"])


def _reports(
    db: Session,
    year: Optional[int],
    date_from: Optional[date],
    date_to: Optional[date],
    all_years: bool,
    sector: Optional[str],
) -> AdminReportsResponse:
    return ReportService.build_reports(
        db=db,
        year=year,
        date_from=date_from,
        date_to=date_to,
        all_years=all_years,
        sector=sector,
    )


@router.get(
    "",
    response_model=AdminReportsResponse,
    summary="Admin reports dashboard",
    description=(
        "Live data for the Reports screen: merchant additions (paid vs free), "
        "12-month trend, Kerala district distribution, business sectors, "
        "active customers, verification rate, and leads."
    ),
)
def get_admin_reports(
    year: Optional[int] = Query(None, ge=2000, le=2100),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    all_years: bool = Query(False, description="Ignore the year and include every merchant"),
    sector: Optional[str] = Query(None, description="Filter the sectors table by name"),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminReportsResponse:
    return _reports(db, year, date_from, date_to, all_years, sector)


@router.get(
    "/merchants",
    response_model=AdminReportsResponse,
    summary="Merchant growth report",
)
def get_merchant_growth_report(
    year: Optional[int] = Query(None, ge=2000, le=2100),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    all_years: bool = Query(False),
    sector: Optional[str] = Query(None),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminReportsResponse:
    return _reports(db, year, date_from, date_to, all_years, sector)


@router.get(
    "/engagement",
    response_model=EngagementReport,
    summary="User engagement report",
)
def get_engagement_report(
    year: Optional[int] = Query(None, ge=2000, le=2100),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    all_years: bool = Query(False),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> EngagementReport:
    return _reports(db, year, date_from, date_to, all_years, None).engagement


@router.get(
    "/leads",
    response_model=LeadsReport,
    summary="Customer leads and direct calls report",
)
def get_leads_report(
    year: Optional[int] = Query(None, ge=2000, le=2100),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    all_years: bool = Query(False),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> LeadsReport:
    return _reports(db, year, date_from, date_to, all_years, None).leads


@router.get(
    "/export",
    summary="Export the reports screen as CSV",
)
def export_admin_reports(
    year: Optional[int] = Query(None, ge=2000, le=2100),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    all_years: bool = Query(False),
    sector: Optional[str] = Query(None),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    report = _reports(db, year, date_from, date_to, all_years, sector)
    label = "all-years" if report.all_years else str(report.year or "report")
    return Response(
        content=ReportService.to_csv(report),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="logo-reports-{label}.csv"'},
    )
