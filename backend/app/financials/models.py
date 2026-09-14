"""Financial Data Service models (full_vision.md §7.2, trimmed to V1 metrics)."""

import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Float, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PeriodType(str, enum.Enum):
    ANNUAL = "ANNUAL"
    QUARTERLY = "QUARTERLY"


class MetricName(str, enum.Enum):
    """The V1-trimmed subset of full_vision.md §7.2's metric list.

    Dropped for V1: ROIC, working_capital, stock_based_compensation — all
    three need extra balance-sheet line items beyond the core set CLAUDE.md
    calls out ("revenue, margins, EPS, FCF, debt, share count").
    """

    REVENUE = "revenue"
    REVENUE_GROWTH = "revenue_growth"
    GROSS_MARGIN = "gross_margin"
    OPERATING_MARGIN = "operating_margin"
    NET_INCOME = "net_income"
    EPS = "eps"
    FREE_CASH_FLOW = "free_cash_flow"
    CAPEX = "capex"
    DEBT = "debt"
    CASH = "cash"
    SHARE_COUNT = "share_count"


class FinancialMetric(Base):
    """One (company, metric, period) data point.

    Modeled as narrow rows (entity-attribute-value) rather than a wide table
    with one column per metric, so each individual metric is addressable by
    id — required for CLAUDE.md's evidence-citation rule ("every material
    claim must cite a specific financial metric") and so new metrics can be
    added later without a schema migration.

    CAVEAT: values come from Alpha Vantage's free tier, which serves
    restated financials (today's numbers as currently reported), not what
    was known as of `period_end`. Fine for V1 since point-in-time cutoff
    enforcement is a later phase — but don't use these rows for historical,
    as-of-the-time research without revisiting this.
    """

    __tablename__ = "financial_metrics"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "metric_name",
            "period_end",
            "period_type",
            name="uq_financial_metric_period",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    metric_name: Mapped[str] = mapped_column(String(50), index=True)
    period_end: Mapped[date] = mapped_column(Date)
    period_type: Mapped[PeriodType] = mapped_column(
        SAEnum(PeriodType, name="financial_period_type")
    )
    value: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    source: Mapped[str] = mapped_column(String(50))
    # func.now is a dynamic SQL-expression proxy; pylint can't see it's callable.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()  # pylint: disable=not-callable
    )
