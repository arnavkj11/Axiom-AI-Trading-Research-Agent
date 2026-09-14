"""Tests for adding a company to the database by ticker.

Before this existed, a company could only be researched if someone had
inserted its row by hand — search returned nothing for anything else and
there was no way to fix that from the app.
"""

import pytest
from sqlalchemy import select

from app.company.dependencies import get_sec_ticker_lookup
from app.company.models import Company
from app.company.sec_lookup import SecTickerRecord, SecTickerLookupError
from app.financials.alpha_vantage_client import AlphaVantageError, CompanyOverview
from app.financials.dependencies import get_alpha_vantage_client
from app.main import app

TSLA = SecTickerRecord(ticker="TSLA", name="Tesla, Inc.", cik="0001318605")


class FakeSecTickerLookup:
    def __init__(self, records=None, raise_error=False):
        self._records = records if records is not None else {"TSLA": TSLA}
        self._raise_error = raise_error

    def get(self, ticker: str) -> SecTickerRecord | None:
        if self._raise_error:
            raise SecTickerLookupError("SEC unreachable")
        return self._records.get(ticker.upper())

    def search(self, query: str, limit: int = 10) -> list[SecTickerRecord]:
        if self._raise_error:
            raise SecTickerLookupError("SEC unreachable")
        needle = query.strip().lower()
        return [
            record
            for record in self._records.values()
            if needle in record.ticker.lower() or needle in record.name.lower()
        ][:limit]


class FakeOverviewClient:
    """Only the OVERVIEW endpoint matters for adding a company."""

    def __init__(self, overview=None, raise_error=False):
        self._overview = overview
        self._raise_error = raise_error
        self.calls = []

    def get_company_overview(self, symbol: str) -> CompanyOverview | None:
        self.calls.append(symbol)
        if self._raise_error:
            raise AlphaVantageError("rate limit reached")
        return self._overview


FULL_OVERVIEW = CompanyOverview(
    exchange="NASDAQ", sector="Consumer Cyclical", industry="Auto Manufacturers"
)


@pytest.fixture()
def wired(client):
    """Points the endpoint at fakes; returns a setter to swap them per test."""
    state = {
        "sec": FakeSecTickerLookup(),
        "overview": FakeOverviewClient(overview=FULL_OVERVIEW),
    }
    app.dependency_overrides[get_sec_ticker_lookup] = lambda: state["sec"]
    app.dependency_overrides[get_alpha_vantage_client] = lambda: state["overview"]

    def use(*, sec=None, overview=None):
        if sec is not None:
            state["sec"] = sec
        if overview is not None:
            state["overview"] = overview

    yield use
    app.dependency_overrides.clear()


def test_adds_a_company_the_database_did_not_have(client, db_session, wired):
    response = client.post("/companies", json={"ticker": "TSLA"})

    assert response.status_code == 201
    body = response.json()
    assert body["ticker"] == "TSLA"
    assert body["name"] == "Tesla, Inc."
    assert body["cik"] == "0001318605"

    stored = db_session.scalar(select(Company).where(Company.ticker == "TSLA"))
    assert stored is not None
    assert stored.cik == "0001318605"


def test_added_company_is_findable_by_search(client, db_session, wired):
    client.post("/companies", json={"ticker": "TSLA"})

    results = client.post("/companies/search", json={"query": "tesla"}).json()["results"]

    assert [company["ticker"] for company in results] == ["TSLA"]


def test_enriches_with_exchange_sector_and_industry(client, wired):
    body = client.post("/companies", json={"ticker": "TSLA"}).json()

    assert body["exchange"] == "NASDAQ"
    assert body["sector"] == "Consumer Cyclical"
    assert body["industry"] == "Auto Manufacturers"


def test_company_is_still_created_when_enrichment_fails(client, db_session, wired):
    # Alpha Vantage's free tier is 25 requests/day, so being rate-limited
    # mid-add is expected, not exceptional. The SEC data is what actually
    # gates research, so losing the display fields must not lose the company.
    wired(overview=FakeOverviewClient(raise_error=True))

    response = client.post("/companies", json={"ticker": "TSLA"})

    assert response.status_code == 201
    body = response.json()
    assert body["ticker"] == "TSLA"
    assert body["cik"] == "0001318605"
    assert body["sector"] is None
    assert db_session.scalar(select(Company).where(Company.ticker == "TSLA")) is not None


def test_ticker_is_normalized_to_uppercase(client, wired):
    body = client.post("/companies", json={"ticker": "tsla"}).json()

    assert body["ticker"] == "TSLA"


def test_unknown_ticker_is_rejected_and_creates_nothing(client, db_session, wired):
    response = client.post("/companies", json={"ticker": "ZZZZ"})

    assert response.status_code == 404
    assert db_session.scalar(select(Company)) is None


def test_adding_an_existing_company_returns_it_instead_of_duplicating(
    client, db_session, wired
):
    first = client.post("/companies", json={"ticker": "TSLA"}).json()

    second_response = client.post("/companies", json={"ticker": "TSLA"})

    assert second_response.status_code == 200
    assert second_response.json()["id"] == first["id"]
    assert len(db_session.scalars(select(Company)).all()) == 1


def test_existing_company_does_not_spend_an_alpha_vantage_request(client, wired):
    overview_client = FakeOverviewClient(overview=FULL_OVERVIEW)
    wired(overview=overview_client)
    client.post("/companies", json={"ticker": "TSLA"})

    client.post("/companies", json={"ticker": "TSLA"})

    # One call for the initial create, none for the repeat — the daily
    # request budget is 25.
    assert overview_client.calls == ["TSLA"]


def test_sec_outage_surfaces_as_a_gateway_error(client, wired):
    wired(sec=FakeSecTickerLookup(raise_error=True))

    response = client.post("/companies", json={"ticker": "TSLA"})

    assert response.status_code == 502


def test_lookup_suggests_registrants_matching_a_name(client, wired):
    # Searching by company name is the normal case — this is what lets the
    # UI offer "Tesla, Inc. (TSLA)" when the database has never heard of it.
    response = client.get("/companies/lookup", params={"q": "tesla"})

    assert response.status_code == 200
    candidates = response.json()["candidates"]
    assert candidates[0]["ticker"] == "TSLA"
    assert candidates[0]["name"] == "Tesla, Inc."


def test_lookup_marks_candidates_already_in_the_database(client, wired):
    client.post("/companies", json={"ticker": "TSLA"})

    candidates = client.get("/companies/lookup", params={"q": "tesla"}).json()["candidates"]

    assert candidates[0]["in_database"] is True


def test_lookup_marks_candidates_not_yet_added(client, wired):
    candidates = client.get("/companies/lookup", params={"q": "tesla"}).json()["candidates"]

    assert candidates[0]["in_database"] is False


def test_lookup_returns_empty_for_no_match(client, wired):
    assert client.get("/companies/lookup", params={"q": "zzzz"}).json()["candidates"] == []
