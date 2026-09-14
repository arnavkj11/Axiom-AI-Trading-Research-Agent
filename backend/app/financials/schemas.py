from datetime import date

from pydantic import BaseModel, ConfigDict

from app.financials.models import MetricName, PeriodType


class FinancialMetricRecord(BaseModel):
    """One financial_metrics row, id included.

    Unlike FinancialPeriod (a per-period pivot for API responses), this is
    what agents consume: each metric is individually addressable by id, so
    a Finding can cite it via FinancialMetricEvidence.metric_id.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    metric_name: MetricName
    period_end: date
    period_type: PeriodType
    value: float


class FinancialPeriod(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    period_end: date
    period_type: PeriodType
    revenue: float | None = None
    revenue_growth: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    net_income: float | None = None
    eps: float | None = None
    free_cash_flow: float | None = None
    capex: float | None = None
    debt: float | None = None
    cash: float | None = None
    share_count: float | None = None


class CompanyFinancialsResponse(BaseModel):
    ticker: str
    periods: list[FinancialPeriod]
