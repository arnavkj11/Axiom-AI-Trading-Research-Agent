"""Refreshing cached financial data.

get_company_financials caches permanently — once any row exists for a
company it never calls Alpha Vantage again, so without an explicit
refresh path a company's numbers stay frozen at whatever they were the
first time anyone looked.
"""

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select

from app.company.models import Company
from app.financials.alpha_vantage_client import (
    BalanceSheetPeriod,
    CashFlowPeriod,
    EarningsPeriod,
    IncomeStatementPeriod,
)
from app.financials.models import FinancialMetric, MetricName, PeriodType
from app.financials.service import get_company_financials, refresh_company_financials


class RevisableAlphaVantageClient:
    """Serves one set of numbers, then a revised set after `revise()`."""

    def __init__(self):
        self.revenue = 100.0
        self.calls = 0

    def revise(self, revenue: float):
        self.revenue = revenue

    def get_income_statement(self, symbol):
        self.calls += 1
        return [
            IncomeStatementPeriod(
                date(2025, 9, 30), PeriodType.ANNUAL, self.revenue, 40.0, 20.0, 15.0
            )
        ]

    def get_cash_flow(self, symbol):
        return [CashFlowPeriod(date(2025, 9, 30), PeriodType.ANNUAL, 40.0, -10.0)]

    def get_balance_sheet(self, symbol):
        return [BalanceSheetPeriod(date(2025, 9, 30), PeriodType.ANNUAL, 50.0, 30.0, 1000.0)]

    def get_earnings(self, symbol):
        return [EarningsPeriod(date(2025, 9, 30), PeriodType.ANNUAL, 1.8)]


@pytest.fixture()
def company(db_session) -> Company:
    company = Company(ticker="AAPL", name="Apple Inc.", cik="0000320193")
    db_session.add(company)
    db_session.commit()
    return company


def _naive(moment: datetime) -> datetime:
    # SQLite (the test database) doesn't persist tzinfo, so a timestamp
    # written as timezone-aware reads back naive; Postgres keeps it. Compare
    # on the instant alone so these tests assert ordering, not storage
    # trivia.
    return moment.replace(tzinfo=None)


def _revenue(db_session, company) -> float:
    return db_session.scalar(
        select(FinancialMetric.value).where(
            FinancialMetric.company_id == company.id,
            FinancialMetric.metric_name == MetricName.REVENUE.value,
        )
    )


def test_plain_read_keeps_serving_cached_numbers(db_session, company):
    # Documents the behavior refresh exists to work around.
    client = RevisableAlphaVantageClient()
    get_company_financials(db_session, company, client)
    client.revise(999.0)

    get_company_financials(db_session, company, client)

    assert client.calls == 1
    assert _revenue(db_session, company) == 100.0


def test_refresh_fetches_again_despite_the_cache(db_session, company):
    client = RevisableAlphaVantageClient()
    get_company_financials(db_session, company, client)
    client.revise(150.0)

    refresh_company_financials(db_session, company, client)

    assert client.calls == 2
    assert _revenue(db_session, company) == 150.0


def test_refresh_updates_in_place_rather_than_duplicating_periods(db_session, company):
    client = RevisableAlphaVantageClient()
    get_company_financials(db_session, company, client)
    client.revise(150.0)

    refresh_company_financials(db_session, company, client)

    rows = db_session.scalars(
        select(FinancialMetric).where(
            FinancialMetric.company_id == company.id,
            FinancialMetric.metric_name == MetricName.REVENUE.value,
        )
    ).all()
    assert len(rows) == 1


def test_first_fetch_records_when_it_happened(db_session, company):
    assert company.financials_refreshed_at is None

    get_company_financials(db_session, company, RevisableAlphaVantageClient())

    assert company.financials_refreshed_at is not None


def test_refresh_advances_the_recorded_timestamp(db_session, company):
    client = RevisableAlphaVantageClient()
    get_company_financials(db_session, company, client)
    stale = datetime(2020, 1, 1, tzinfo=timezone.utc)
    company.financials_refreshed_at = stale
    db_session.commit()

    refresh_company_financials(db_session, company, client)

    assert _naive(company.financials_refreshed_at) > _naive(stale)


def test_timestamp_advances_even_when_no_value_changed(db_session, company):
    # "Last checked" must reflect the check, not whether numbers moved —
    # otherwise a refresh that confirms nothing changed would still look
    # stale in the UI.
    client = RevisableAlphaVantageClient()
    get_company_financials(db_session, company, client)
    stale = datetime(2020, 1, 1, tzinfo=timezone.utc)
    company.financials_refreshed_at = stale
    db_session.commit()

    refresh_company_financials(db_session, company, client)  # same numbers

    assert _revenue(db_session, company) == 100.0
    assert _naive(company.financials_refreshed_at) > _naive(stale)
