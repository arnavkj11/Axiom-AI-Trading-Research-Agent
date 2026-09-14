from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.company.models import Company
from app.db.session import get_db
from app.filings.dependencies import get_edgar_client, get_voyage_client
from app.filings.edgar_client import EdgarClient, EdgarError
from app.filings.models import Filing
from app.filings.schemas import CompanyFilingsResponse
from app.filings.service import sync_company_filings
from app.filings.voyage_client import VoyageEmbeddingClient

router = APIRouter(prefix="/companies", tags=["filings"])


def _get_company_or_404(ticker: str, db: Session) -> Company:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if company is None:
        raise HTTPException(status_code=404, detail=f"Company '{ticker}' not found")
    return company


@router.post("/{ticker}/filings/sync", response_model=CompanyFilingsResponse)
def sync_filings(
    ticker: str,
    db: Session = Depends(get_db),
    edgar_client: EdgarClient = Depends(get_edgar_client),
    voyage_client: VoyageEmbeddingClient = Depends(get_voyage_client),
) -> CompanyFilingsResponse:
    company = _get_company_or_404(ticker, db)
    try:
        filings = sync_company_filings(db, company, edgar_client, voyage_client)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EdgarError as exc:
        raise HTTPException(status_code=502, detail=f"EDGAR error: {exc}") from exc
    return CompanyFilingsResponse(ticker=company.ticker, filings=filings)


@router.get("/{ticker}/filings", response_model=CompanyFilingsResponse)
def list_filings(ticker: str, db: Session = Depends(get_db)) -> CompanyFilingsResponse:
    company = _get_company_or_404(ticker, db)
    filings = db.scalars(
        select(Filing).where(Filing.company_id == company.id).order_by(Filing.filing_date.desc())
    ).all()
    return CompanyFilingsResponse(ticker=company.ticker, filings=list(filings))
