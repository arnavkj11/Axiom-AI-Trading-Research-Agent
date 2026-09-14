from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.company.models import Company
from app.db.session import get_db
from app.financials.alpha_vantage_client import AlphaVantageClient, AlphaVantageError
from app.financials.dependencies import get_alpha_vantage_client
from app.financials.schemas import CompanyFinancialsResponse
from app.financials.service import get_company_financials, refresh_company_financials

router = APIRouter(prefix="/companies", tags=["financials"])


def _get_company_or_404(ticker: str, db: Session) -> Company:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if company is None:
        raise HTTPException(status_code=404, detail=f"Company '{ticker}' not found")
    return company


@router.get("/{ticker}/financials", response_model=CompanyFinancialsResponse)
def get_financials(
    ticker: str,
    db: Session = Depends(get_db),
    client: AlphaVantageClient = Depends(get_alpha_vantage_client),
) -> CompanyFinancialsResponse:
    """Cached metrics, fetched from Alpha Vantage only on a cache miss."""
    company = _get_company_or_404(ticker, db)
    try:
        periods = get_company_financials(db, company, client)
    except AlphaVantageError as exc:
        raise HTTPException(status_code=502, detail=f"Alpha Vantage error: {exc}") from exc
    return CompanyFinancialsResponse(ticker=company.ticker, periods=periods)


@router.post("/{ticker}/financials/refresh", response_model=CompanyFinancialsResponse)
def refresh_financials(
    ticker: str,
    db: Session = Depends(get_db),
    client: AlphaVantageClient = Depends(get_alpha_vantage_client),
) -> CompanyFinancialsResponse:
    """Refetch current numbers, bypassing the cache.

    A POST rather than a flag on the GET: it spends 4 of Alpha Vantage's
    25 daily requests and rewrites stored periods, so it shouldn't be
    reachable by anything that thinks it's making a safe read.
    """
    company = _get_company_or_404(ticker, db)
    try:
        periods = refresh_company_financials(db, company, client)
    except AlphaVantageError as exc:
        raise HTTPException(status_code=502, detail=f"Alpha Vantage error: {exc}") from exc
    return CompanyFinancialsResponse(ticker=company.ticker, periods=periods)
