from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class RoiMoney(BaseModel):
    amount_inr: float
    source: str
    label: str = ""
    is_estimate: bool = False


class RoiComparePoint(BaseModel):
    deal_id: int
    brand: str
    invoiced_inr: float
    received_inr: float
    profit_inr: Optional[float] = None
    roi_pct: Optional[float] = None


class CampaignRoiOut(BaseModel):
    deal_id: int
    brand: str
    kind: str
    status: str
    invoiced_revenue: RoiMoney
    received_revenue: RoiMoney
    outstanding: RoiMoney
    actual_expenses: RoiMoney
    estimated_expenses: RoiMoney
    total_cost: RoiMoney
    net_cash_flow: RoiMoney
    profit_estimate: RoiMoney
    roi_pct: Optional[float] = None
    cost_per_engagement: Optional[float] = None
    revenue_per_deliverable: Optional[float] = None
    engagement_total: Optional[float] = None
    deliverable_count_actual: int = 0
    deliverable_count_estimated: int = 0
    estimated_vs_actual: dict = Field(default_factory=dict)
    data_gaps: list[str] = Field(default_factory=list)
    disclaimer: str = (
        "Figures use stored invoices, payments, and expenses only. "
        "Estimates are manual or deal-level placeholders — not accounting advice."
    )
    invoice_ids: list[int] = Field(default_factory=list)
    from_date: Optional[date] = None
    to_date: Optional[date] = None


class PortfolioRoiSummary(BaseModel):
    campaigns: list[CampaignRoiOut]
    compare: list[RoiComparePoint]
    totals: dict
