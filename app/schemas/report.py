from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


class MerchantAdditionsCard(BaseModel):
    total: int = 0
    paid: int = 0
    paid_percent: float = 0
    free: int = 0
    free_percent: float = 0


class VerificationCard(BaseModel):
    approved: int = 0
    pending: int = 0
    rejected: int = 0
    total: int = 0
    rate_percent: float = 0
    label: str = "Approved"


class ReportCards(BaseModel):
    merchant_additions: MerchantAdditionsCard
    active_customers: int = 0
    customer_leads_and_calls: int = 0
    verification: VerificationCard


class MonthlyTrendPoint(BaseModel):
    month: int
    label: str
    paid: int = 0
    free: int = 0
    total: int = 0
    cumulative: int = 0


class DistrictReportItem(BaseModel):
    district: str
    merchants: int
    percent: float


class SectorReportItem(BaseModel):
    sector: str
    shops: int
    percent: float


class EngagementReport(BaseModel):
    active_customers: int = 0
    customers_added: int = 0
    districts_reached: int = 0
    searches: int = 0
    favorites: int = 0
    recently_active: int = 0


class LeadsReport(BaseModel):
    customer_leads_and_calls: int = 0
    searches: int = 0
    promotion_clicks: int = 0
    promotion_impressions: int = 0
    product_orders: int = 0
    whatsapp_merchants: int = 0
    zero_commission_deals: int = 0


class AdminReportsResponse(BaseModel):
    success: bool = True
    message: str = "Reports retrieved"
    year: Optional[int] = None
    all_years: bool = False
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    cards: ReportCards
    monthly_trend: List[MonthlyTrendPoint] = Field(default_factory=list)
    districts: List[DistrictReportItem] = Field(default_factory=list)
    sectors: List[SectorReportItem] = Field(default_factory=list)
    sector_count: int = 0
    engagement: EngagementReport
    leads: LeadsReport
