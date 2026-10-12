from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class MonthlyOverviewItem(BaseModel):
    month: str
    merchants: int
    users: int
    transactions: int


class ReportOverviewResponse(BaseModel):
    total_merchants: int
    total_users: int
    total_searches: int
    total_revenue: float
    monthly_data: List[MonthlyOverviewItem]
    category_distribution: List[Dict[str, Any]]
    district_performance: Optional[List[Dict[str, Any]]] = None
    verification_stats: Optional[Dict[str, Any]] = None
    selected_year: Optional[int] = None
    available_years: Optional[List[int]] = None
    year_merchants: Optional[int] = None
