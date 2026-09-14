from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.company.dependencies import get_sec_ticker_lookup
from app.company.models import Company
from app.company.schemas import (
    CompanyCandidate,
    CompanyCreateRequest,
    CompanyLookupResponse,
    CompanyRead,
    CompanySearchRequest,
    CompanySearchResponse,
)
from app.company.sec_lookup import SecTickerLookup, SecTickerLookupError
from app.company.service import create_company, get_company_by_ticker
from app.db.session import get_db
from app.financials.alpha_vantage_client import AlphaVantageClient
from app.financials.dependencies import get_alpha_vantage_client

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("/lookup", response_model=CompanyLookupResponse)
def lookup_registrants(
    q: str,
    db: Session = Depends(get_db),
    sec_lookup: SecTickerLookup = Depends(get_sec_ticker_lookup),
) -> CompanyLookupResponse:
    """Search SEC's registrant list for companies that could be added.

    Distinct from /companies/search, which only covers what's already in
    the database. This is what a user gets offered when their search finds
    nothing locally.

    Declared before GET /{ticker} so "lookup" isn't captured as a ticker.
    """
    try:
        matches = sec_lookup.search(q)
    except SecTickerLookupError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach SEC: {exc}") from exc

    known = set(
        db.scalars(
            select(Company.ticker).where(
                Company.ticker.in_([record.ticker for record in matches])
            )
        ).all()
    )
    return CompanyLookupResponse(
        candidates=[
            CompanyCandidate(
                ticker=record.ticker,
                name=record.name,
                cik=record.cik,
                in_database=record.ticker in known,
            )
            for record in matches
        ]
    )


@router.post("", response_model=CompanyRead, status_code=201)
def add_company(
    payload: CompanyCreateRequest,
    response: Response,
    db: Session = Depends(get_db),
    sec_lookup: SecTickerLookup = Depends(get_sec_ticker_lookup),
    overview_client: AlphaVantageClient = Depends(get_alpha_vantage_client),
) -> Company:
    """Add a company by ticker, resolving its identity from SEC's registrant list.

    Idempotent: adding a company that already exists returns it with 200
    rather than erroring or duplicating, which also avoids spending an
    Alpha Vantage request on a company that's already enriched.
    """
    ticker = payload.ticker.upper()

    existing = get_company_by_ticker(db, ticker)
    if existing is not None:
        response.status_code = 200
        return existing

    try:
        record = sec_lookup.get(ticker)
    except SecTickerLookupError as exc:
        raise HTTPException(
            status_code=502, detail=f"Could not reach SEC to look up '{ticker}': {exc}"
        ) from exc

    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"'{ticker}' isn't listed as an SEC registrant, so it can't be researched",
        )

    return create_company(db, record, overview_client)


@router.get("/{ticker}", response_model=CompanyRead)
def get_company(ticker: str, db: Session = Depends(get_db)) -> Company:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if company is None:
        raise HTTPException(status_code=404, detail=f"Company '{ticker}' not found")
    return company


@router.post("/search", response_model=CompanySearchResponse)
def search_companies(payload: CompanySearchRequest, db: Session = Depends(get_db)) -> CompanySearchResponse:
    pattern = f"%{payload.query}%"
    companies = db.scalars(
        select(Company).where(or_(Company.ticker.ilike(pattern), Company.name.ilike(pattern)))
    ).all()
    return CompanySearchResponse(results=list(companies))
