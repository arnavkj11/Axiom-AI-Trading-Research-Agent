from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.company.models import Company
from app.financials.alpha_vantage_client import AlphaVantageClient
from app.financials.calculations import (
    free_cash_flow,
    gross_margin,
    operating_margin,
    revenue_growth,
)
from app.financials.models import FinancialMetric, MetricName, PeriodType

SOURCE = "ALPHA_VANTAGE"

# How many of the most recent periods (per period_type) to give agents.
# A live run against a company with 1,045 historical FinancialMetric rows
# (going back years, unfiltered) blew Fundamental Analyst's prompt up to
# 43K input tokens and 25.6s for one call — by far the single largest
# cost/latency driver in the whole pipeline. Agents only need enough
# history to reason about trends, not the entire ingested archive.
ANNUAL_PERIODS_LIMIT = 4
QUARTERLY_PERIODS_LIMIT = 4


@dataclass
class PeriodMetrics:
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


def _recent_period_ends(db: Session, company_id: int, period_type: PeriodType, limit: int) -> list:
    stmt = (
        select(FinancialMetric.period_end)
        .where(FinancialMetric.company_id == company_id, FinancialMetric.period_type == period_type)
        .distinct()
        .order_by(FinancialMetric.period_end.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def load_recent_financial_metrics(db: Session, company_id: int) -> list[FinancialMetric]:
    """All FinancialMetric rows for company_id, but only from the most
    recent ANNUAL_PERIODS_LIMIT annual periods and QUARTERLY_PERIODS_LIMIT
    quarterly periods — not the entire ingested history.

    Shared by two callers, which is why it lives here (a financial-data
    concern) rather than in the orchestrator: agents.orchestrator uses it
    to build the initial ResearchState for a live run, and
    research.service uses it to rehydrate that same metric window when
    loading a finished run back for display. Both must see the same
    window or a reloaded run wouldn't match what the agents actually saw.
    """
    annual_periods = _recent_period_ends(db, company_id, PeriodType.ANNUAL, ANNUAL_PERIODS_LIMIT)
    quarterly_periods = _recent_period_ends(
        db, company_id, PeriodType.QUARTERLY, QUARTERLY_PERIODS_LIMIT
    )

    stmt = select(FinancialMetric).where(
        FinancialMetric.company_id == company_id,
        or_(
            and_(
                FinancialMetric.period_type == PeriodType.ANNUAL,
                FinancialMetric.period_end.in_(annual_periods),
            ),
            and_(
                FinancialMetric.period_type == PeriodType.QUARTERLY,
                FinancialMetric.period_end.in_(quarterly_periods),
            ),
        ),
    )
    return list(db.scalars(stmt).all())


def get_company_financials(
    db: Session, company: Company, client: AlphaVantageClient
) -> list[PeriodMetrics]:
    """Cached metrics, fetching from Alpha Vantage only on a cache miss.

    The cache never expires on its own — once a company has any rows, this
    keeps serving them. Use refresh_company_financials() to pull current
    numbers; that's an explicit choice because each fetch costs 4 of the
    free tier's 25 daily requests.
    """
    cached = _load_cached(db, company)
    if cached:
        return cached
    return _fetch_and_store(db, company, client)


def refresh_company_financials(
    db: Session, company: Company, client: AlphaVantageClient
) -> list[PeriodMetrics]:
    """Refetch from Alpha Vantage, bypassing the cache.

    CAVEAT (compounds the restated-financials note on FinancialMetric):
    this overwrites existing periods in place, so a refresh silently
    replaces previously-stored numbers with Alpha Vantage's current view of
    them. Fine while point-in-time enforcement is out of scope, but it does
    mean the stored history is "as last fetched", not "as first reported".
    """
    return _fetch_and_store(db, company, client)


def _load_cached(db: Session, company: Company) -> list[PeriodMetrics]:
    stmt = select(FinancialMetric).where(FinancialMetric.company_id == company.id)
    rows = db.scalars(stmt).all()
    by_period: dict[tuple[date, PeriodType], PeriodMetrics] = {}
    for row in rows:
        key = (row.period_end, row.period_type)
        period = by_period.setdefault(
            key, PeriodMetrics(period_end=row.period_end, period_type=row.period_type)
        )
        setattr(period, row.metric_name, row.value)
    return _sorted_desc(by_period.values())


def _fetch_and_store(
    db: Session, company: Company, client: AlphaVantageClient
) -> list[PeriodMetrics]:
    by_period: dict[tuple[date, PeriodType], PeriodMetrics] = {}

    def _period(period_end: date, period_type: PeriodType) -> PeriodMetrics:
        key = (period_end, period_type)
        new_period = PeriodMetrics(period_end=period_end, period_type=period_type)
        return by_period.setdefault(key, new_period)

    for report in client.get_income_statement(company.ticker):
        period = _period(report.period_end, report.period_type)
        period.revenue = report.revenue
        period.net_income = report.net_income
        period.gross_margin = gross_margin(report.revenue, report.gross_profit)
        period.operating_margin = operating_margin(report.revenue, report.operating_income)

    for report in client.get_cash_flow(company.ticker):
        period = _period(report.period_end, report.period_type)
        period.capex = report.capex
        period.free_cash_flow = free_cash_flow(report.operating_cash_flow, report.capex)

    for report in client.get_balance_sheet(company.ticker):
        period = _period(report.period_end, report.period_type)
        period.debt = report.debt
        period.cash = report.cash
        period.share_count = report.share_count

    for report in client.get_earnings(company.ticker):
        period = _period(report.period_end, report.period_type)
        period.eps = report.eps

    # Year-over-year growth, ANNUAL periods only: computed by comparing
    # consecutive fiscal years. Not computed for QUARTERLY periods in V1 —
    # true YoY needs matching each quarter to the same quarter a year
    # earlier, which risks fiscal-quarter-end date drift; deferred rather
    # than risk a silently wrong number.
    annual_periods = sorted(
        (p for p in by_period.values() if p.period_type == PeriodType.ANNUAL),
        key=lambda p: p.period_end,
    )
    for previous, current in zip(annual_periods, annual_periods[1:]):
        current.revenue_growth = revenue_growth(current.revenue, previous.revenue)

    # Alpha Vantage's endpoints don't always agree on fiscalDateEnding for
    # what should be the same period (seen live: EARNINGS reported an
    # annual EPS entry dated after the matching INCOME_STATEMENT entry's
    # fiscal year end). Revenue only ever comes from INCOME_STATEMENT, so a
    # period without it isn't a real, cross-source-confirmed period —
    # drop it rather than expose a row that's mostly nulls.
    confirmed_periods = [p for p in by_period.values() if p.revenue is not None]

    _persist(db, company, confirmed_periods)
    _mark_financials_refreshed(db, company)
    return _sorted_desc(confirmed_periods)


def _mark_financials_refreshed(db: Session, company: Company) -> None:
    # Set on every fetch, whether or not any value actually moved — this
    # records that we checked, which is what "data as of" means.
    company.financials_refreshed_at = datetime.now(timezone.utc)
    db.commit()


def _persist(db: Session, company: Company, periods: Iterable[PeriodMetrics]) -> None:
    for period in periods:
        for metric in MetricName:
            value = getattr(period, metric.value)
            if value is None:
                continue
            existing = db.scalar(
                select(FinancialMetric).where(
                    FinancialMetric.company_id == company.id,
                    FinancialMetric.metric_name == metric.value,
                    FinancialMetric.period_end == period.period_end,
                    FinancialMetric.period_type == period.period_type,
                )
            )
            if existing is not None:
                existing.value = value
            else:
                db.add(
                    FinancialMetric(
                        company_id=company.id,
                        metric_name=metric.value,
                        period_end=period.period_end,
                        period_type=period.period_type,
                        value=value,
                        source=SOURCE,
                    )
                )
    db.commit()


def _sorted_desc(periods: Iterable[PeriodMetrics]) -> list[PeriodMetrics]:
    return sorted(periods, key=lambda p: p.period_end, reverse=True)
