import pytest

from app.company.models import Company
from app.filings.dependencies import get_edgar_client, get_voyage_client
from app.main import app
from tests.fakes import FakeEdgarClient, FakeVoyageClient


@pytest.fixture()
def filings_client(client, db_session):
    edgar = FakeEdgarClient()
    voyage = FakeVoyageClient()
    app.dependency_overrides[get_edgar_client] = lambda: edgar
    app.dependency_overrides[get_voyage_client] = lambda: voyage
    try:
        yield client, edgar, voyage
    finally:
        del app.dependency_overrides[get_edgar_client]
        del app.dependency_overrides[get_voyage_client]


def test_sync_404_when_company_missing(filings_client):
    test_client, _, _ = filings_client

    response = test_client.post("/companies/NOPE/filings/sync")

    assert response.status_code == 404
    assert response.json()["detail"] == "Company 'NOPE' not found"


def test_sync_ingests_and_returns_filings(filings_client, db_session):
    test_client, _, _ = filings_client
    db_session.add(Company(ticker="AAPL", name="Apple Inc.", cik="0000320193"))
    db_session.commit()

    response = test_client.post("/companies/AAPL/filings/sync")

    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "AAPL"
    assert len(body["filings"]) == 13
    assert all(f["status"] == "EMBEDDED" for f in body["filings"])


def test_sync_400_when_company_has_no_cik(filings_client, db_session):
    db_session.add(Company(ticker="NOCIK", name="No Cik Inc.", cik=None))
    db_session.commit()
    test_client, _, _ = filings_client

    response = test_client.post("/companies/NOCIK/filings/sync")

    assert response.status_code == 400


def test_list_filings_returns_empty_before_sync(filings_client, db_session):
    test_client, _, _ = filings_client
    db_session.add(Company(ticker="AAPL", name="Apple Inc.", cik="0000320193"))
    db_session.commit()

    response = test_client.get("/companies/AAPL/filings")

    assert response.status_code == 200
    assert response.json()["filings"] == []


def test_list_filings_returns_synced_filings(filings_client, db_session):
    test_client, _, _ = filings_client
    db_session.add(Company(ticker="AAPL", name="Apple Inc.", cik="0000320193"))
    db_session.commit()
    test_client.post("/companies/AAPL/filings/sync")

    response = test_client.get("/companies/AAPL/filings")

    assert len(response.json()["filings"]) == 13
