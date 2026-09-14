"""The run fetches its own quote, and records how fresh its inputs were.

Price is fetched per-run rather than cached (a quote goes stale in
minutes), and the data vintage is snapshotted onto the run so a report
reopened weeks later can say how old its evidence already was.
"""

from datetime import date, datetime, timezone

import pytest

from app.agents.orchestrator import run_research
from app.company.models import Company
from app.financials.alpha_vantage_client import AlphaVantageError, Quote
from app.financials.models import FinancialMetric, MetricName, PeriodType
from app.research.models import ResearchRun, ResearchRunStatus
from tests.fakes import (
    FILING_CHUNK,
    FakeFilingSearchClient,
    RoutingFakeLLMClient,
    all_agent_responses,
)

QUOTE = Quote(price=180.42, as_of=date(2026, 9, 8))


class FakeQuoteClient:
    def __init__(self, quote=QUOTE, raise_error=False):
        self._quote = quote
        self._raise_error = raise_error
        self.calls = []

    def get_quote(self, symbol):
        self.calls.append(symbol)
        if self._raise_error:
            raise AlphaVantageError("rate limit reached")
        return self._quote


@pytest.fixture()
def company(db_session) -> Company:
    company = Company(
        ticker="AAPL",
        name="Apple Inc.",
        cik="0000320193",
        financials_refreshed_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        filings_synced_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
    )
    db_session.add(company)
    db_session.flush()
    db_session.add_all(
        [
            FinancialMetric(
                company_id=company.id,
                metric_name=MetricName.FREE_CASH_FLOW.value,
                period_end=date(2026, 6, 30),
                period_type=PeriodType.ANNUAL,
                value=100.0,
                source="ALPHA_VANTAGE",
            ),
            FinancialMetric(
                company_id=company.id,
                metric_name=MetricName.SHARE_COUNT.value,
                period_end=date(2026, 6, 30),
                period_type=PeriodType.ANNUAL,
                value=1000.0,
                source="ALPHA_VANTAGE",
            ),
        ]
    )
    db_session.commit()
    return company


@pytest.fixture()
def research_run(db_session, company) -> ResearchRun:
    run = ResearchRun(company_id=company.id, research_date=date(2026, 9, 8))
    db_session.add(run)
    db_session.commit()
    return run


def _run(db_session, research_run, quote_client):
    return run_research(
        db_session,
        research_run,
        RoutingFakeLLMClient(all_agent_responses()),
        FakeFilingSearchClient(default=[FILING_CHUNK]),
        quote_client=quote_client,
    )


def test_run_fetches_a_quote_for_the_company(db_session, research_run):
    quote_client = FakeQuoteClient()

    state = _run(db_session, research_run, quote_client)

    assert quote_client.calls == ["AAPL"]
    assert state.current_price == 180.42
    assert state.price_as_of == date(2026, 9, 8)


def test_valuation_reflects_the_fetched_price(db_session, research_run):
    state = _run(db_session, research_run, FakeQuoteClient())

    assert state.valuation_output.current_price == 180.42
    assert all(s.upside_pct is not None for s in state.valuation_output.scenarios)


def test_a_failed_quote_does_not_fail_the_run(db_session, research_run):
    # Alpha Vantage's 25/day cap makes a throttled quote routine. Losing
    # the price comparison is a degraded report; losing the whole run over
    # it would be worse.
    state = _run(db_session, research_run, FakeQuoteClient(raise_error=True))

    assert state.status == ResearchRunStatus.COMPLETE
    assert state.current_price is None
    assert all(s.upside_pct is None for s in state.valuation_output.scenarios)


def test_an_unavailable_quote_does_not_fail_the_run(db_session, research_run):
    state = _run(db_session, research_run, FakeQuoteClient(quote=None))

    assert state.status == ResearchRunStatus.COMPLETE
    assert state.current_price is None


def test_run_records_the_price_it_used(db_session, research_run):
    _run(db_session, research_run, FakeQuoteClient())

    assert research_run.price_at_run == 180.42
    assert research_run.price_as_of == date(2026, 9, 8)


def test_run_snapshots_how_fresh_its_inputs_were(db_session, research_run):
    # So a report opened in October can say its financials were already a
    # month old when the Judge weighed them.
    _run(db_session, research_run, FakeQuoteClient())

    assert research_run.financials_as_of is not None
    assert research_run.filings_as_of is not None
