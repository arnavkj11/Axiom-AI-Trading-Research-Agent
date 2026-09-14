from datetime import date

import pytest

from app.company.models import Company
from app.financials.alpha_vantage_client import EarningsPeriod, IncomeStatementPeriod
from app.financials.models import FinancialMetric, PeriodType
from app.financials.service import get_company_financials
from tests.fakes import FakeAlphaVantageClient


def _make_company(db_session):
    company = Company(ticker="AAPL", name="Apple Inc.")
    db_session.add(company)
    db_session.commit()
    return company


def test_fetches_and_computes_derived_metrics_when_uncached(db_session):
    company = _make_company(db_session)
    client = FakeAlphaVantageClient()

    periods = get_company_financials(db_session, company, client)

    latest = next(p for p in periods if p.period_end == date(2024, 9, 28))
    assert latest.revenue == 120.0
    assert latest.gross_margin == pytest.approx(50.0 / 120.0)
    assert latest.operating_margin == pytest.approx(25.0 / 120.0)
    assert latest.free_cash_flow == pytest.approx(30.0)
    assert latest.revenue_growth == pytest.approx((120.0 - 100.0) / 100.0)
    assert latest.eps == 1.8
    assert latest.debt == 50.0
    assert latest.cash == 30.0
    assert latest.share_count == 1000.0

    earliest_annual = next(p for p in periods if p.period_end == date(2023, 9, 30))
    assert earliest_annual.revenue_growth is None

    quarterly = next(p for p in periods if p.period_type == PeriodType.QUARTERLY)
    assert quarterly.revenue_growth is None


def test_persists_metrics_to_database(db_session):
    company = _make_company(db_session)
    client = FakeAlphaVantageClient()

    get_company_financials(db_session, company, client)

    stored = db_session.query(FinancialMetric).filter_by(company_id=company.id).all()
    revenue_rows = [m for m in stored if m.metric_name == "revenue"]
    assert any(r.value == 120.0 for r in revenue_rows)


def test_second_call_uses_cache_and_does_not_refetch(db_session):
    company = _make_company(db_session)
    client = FakeAlphaVantageClient()

    get_company_financials(db_session, company, client)
    get_company_financials(db_session, company, client)

    assert client.calls == 1


class _MismatchedEarningsDateClient:
    """Reproduces a real Alpha Vantage quirk: EARNINGS' annualEarnings
    fiscalDateEnding doesn't always match INCOME_STATEMENT's annualReports
    fiscalDateEnding for the same company (seen live for AAPL)."""

    def get_income_statement(self, symbol):
        return [
            IncomeStatementPeriod(date(2025, 9, 30), PeriodType.ANNUAL, 400.0, 190.0, 130.0, 110.0)
        ]

    def get_cash_flow(self, symbol):
        return []

    def get_balance_sheet(self, symbol):
        return []

    def get_earnings(self, symbol):
        return [EarningsPeriod(date(2026, 6, 30), PeriodType.ANNUAL, 6.87)]


def test_drops_periods_with_no_revenue_from_mismatched_source_dates(db_session):
    company = _make_company(db_session)

    periods = get_company_financials(db_session, company, _MismatchedEarningsDateClient())

    assert all(p.revenue is not None for p in periods)
    assert not any(p.period_end == date(2026, 6, 30) for p in periods)
