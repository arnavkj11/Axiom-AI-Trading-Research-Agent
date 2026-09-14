from app.company.models import Company


def _create_company(db_session, **overrides):
    defaults = dict(
        ticker="AAPL",
        name="Apple Inc.",
        exchange="NASDAQ",
        sector="Technology",
        industry="Consumer Electronics",
        cik="0000320193",
    )
    defaults.update(overrides)
    company = Company(**defaults)
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)
    return company


def test_get_company_by_ticker_returns_company(client, db_session):
    _create_company(db_session)

    response = client.get("/companies/AAPL")

    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "AAPL"
    assert body["name"] == "Apple Inc."


def test_get_company_by_ticker_404_when_missing(client):
    response = client.get("/companies/NOPE")

    assert response.status_code == 404


def test_search_companies_matches_ticker_or_name_case_insensitively(client, db_session):
    _create_company(db_session, ticker="AAPL", name="Apple Inc.", cik="0000320193")
    _create_company(db_session, ticker="MSFT", name="Microsoft Corporation", cik="0000789019")

    response = client.post("/companies/search", json={"query": "apple"})

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["ticker"] == "AAPL"


def test_search_companies_rejects_empty_query(client):
    response = client.post("/companies/search", json={"query": ""})

    assert response.status_code == 422
