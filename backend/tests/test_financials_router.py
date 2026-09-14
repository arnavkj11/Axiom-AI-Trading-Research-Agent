import pytest

from app.company.models import Company
from app.financials.alpha_vantage_client import AlphaVantageError
from app.financials.dependencies import get_alpha_vantage_client
from app.main import app
from tests.fakes import FakeAlphaVantageClient


class RaisingAlphaVantageClient:
    def get_income_statement(self, symbol):
        raise AlphaVantageError("Thank you for using Alpha Vantage! ... 25 requests per day")


@pytest.fixture()
def financials_client(client, db_session):
    fake = FakeAlphaVantageClient()

    def override():
        return fake

    app.dependency_overrides[get_alpha_vantage_client] = override
    try:
        yield client, fake
    finally:
        del app.dependency_overrides[get_alpha_vantage_client]


def test_get_financials_404_when_company_missing(financials_client):
    test_client, _ = financials_client

    response = test_client.get("/companies/NOPE/financials")

    assert response.status_code == 404
    assert response.json()["detail"] == "Company 'NOPE' not found"


def test_get_financials_fetches_and_returns_periods(financials_client, db_session):
    test_client, fake = financials_client
    db_session.add(Company(ticker="AAPL", name="Apple Inc."))
    db_session.commit()

    response = test_client.get("/companies/AAPL/financials")

    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "AAPL"
    latest = next(p for p in body["periods"] if p["period_end"] == "2024-09-28")
    assert latest["revenue"] == 120.0
    assert latest["revenue_growth"] == pytest.approx((120.0 - 100.0) / 100.0)
    assert fake.calls == 1


def test_get_financials_second_request_uses_cache(financials_client, db_session):
    test_client, fake = financials_client
    db_session.add(Company(ticker="AAPL", name="Apple Inc."))
    db_session.commit()

    test_client.get("/companies/AAPL/financials")
    test_client.get("/companies/AAPL/financials")

    assert fake.calls == 1


def test_get_financials_returns_502_on_alpha_vantage_error(client, db_session):
    db_session.add(Company(ticker="AAPL", name="Apple Inc."))
    db_session.commit()
    app.dependency_overrides[get_alpha_vantage_client] = RaisingAlphaVantageClient

    try:
        response = client.get("/companies/AAPL/financials")
    finally:
        del app.dependency_overrides[get_alpha_vantage_client]

    assert response.status_code == 502
    assert "Alpha Vantage" in response.json()["detail"]
