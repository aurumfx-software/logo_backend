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
