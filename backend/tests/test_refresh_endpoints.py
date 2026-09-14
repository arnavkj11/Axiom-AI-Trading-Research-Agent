"""API surface for refreshing a company's cached research data."""

from datetime import date

import pytest

from app.company.models import Company
from app.filings.dependencies import get_edgar_client, get_voyage_client
from app.financials.dependencies import get_alpha_vantage_client
from app.main import app
from tests.fakes import FakeAlphaVantageClient, FakeEdgarClient, FakeVoyageClient


@pytest.fixture()
def company(db_session) -> Company:
    company = Company(ticker="AAPL", name="Apple Inc.", cik="0000320193")
    db_session.add(company)
    db_session.commit()
    return company


@pytest.fixture()
def wired():
    app.dependency_overrides[get_alpha_vantage_client] = FakeAlphaVantageClient
    app.dependency_overrides[get_edgar_client] = FakeEdgarClient
    app.dependency_overrides[get_voyage_client] = FakeVoyageClient
    yield
    app.dependency_overrides.clear()


def test_refresh_endpoint_returns_the_refreshed_financials(client, company, wired):
    client.get(f"/companies/{company.ticker}/financials")

    response = client.post(f"/companies/{company.ticker}/financials/refresh")

    assert response.status_code == 200
    assert response.json()["ticker"] == "AAPL"
    assert len(response.json()["periods"]) > 0


def test_refresh_endpoint_404s_for_an_unknown_company(client, wired):
    assert client.post("/companies/NOPE/financials/refresh").status_code == 404


def test_company_exposes_when_its_data_was_last_refreshed(client, company, wired):
    before = client.get(f"/companies/{company.ticker}").json()
    assert before["financials_refreshed_at"] is None
    assert before["filings_synced_at"] is None

    client.get(f"/companies/{company.ticker}/financials")
    client.post(f"/companies/{company.ticker}/filings/sync")

    after = client.get(f"/companies/{company.ticker}").json()
    assert after["financials_refreshed_at"] is not None
    assert after["filings_synced_at"] is not None


def test_filings_sync_records_when_it_last_ran(client, db_session, company, wired):
    client.post(f"/companies/{company.ticker}/filings/sync")
    db_session.refresh(company)
    first = company.filings_synced_at
    assert first is not None

    # Re-syncing is how new filings get picked up; the timestamp must move
    # even though every filing is already ingested and nothing new lands.
    company.filings_synced_at = None
    db_session.commit()
    client.post(f"/companies/{company.ticker}/filings/sync")
    db_session.refresh(company)

    assert company.filings_synced_at is not None
