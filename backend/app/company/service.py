"""Creating a company from nothing but a ticker.

Two sources, deliberately ranked: the SEC registrant list supplies
ticker/name/CIK and is required (the CIK gates filing ingestion, so
without it the company can't be researched), while Alpha Vantage's
OVERVIEW supplies exchange/sector/industry and is best-effort — they're
display fields, and the free tier's 25 requests/day makes failure routine
rather than exceptional.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.company.models import Company
from app.company.sec_lookup import SecTickerRecord

logger = logging.getLogger(__name__)


def get_company_by_ticker(db: Session, ticker: str) -> Company | None:
    return db.scalar(select(Company).where(Company.ticker == ticker.upper()))


def create_company(db: Session, record: SecTickerRecord, overview_client) -> Company:
    """Persist a company from its SEC record, enriched where possible."""
    company = Company(ticker=record.ticker, name=record.name, cik=record.cik)

    overview = _try_overview(overview_client, record.ticker)
    if overview is not None:
        company.exchange = overview.exchange
        company.sector = overview.sector
        company.industry = overview.industry

    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def _try_overview(overview_client, ticker: str):
    """Alpha Vantage enrichment, downgraded to a log line on any failure.

    Rate limits, an unknown symbol, a network blip — none of them are a
    reason to refuse to add a company whose SEC identity we already have.
    """
    try:
        return overview_client.get_company_overview(ticker)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.warning(
            "Alpha Vantage overview unavailable for %s; "
            "adding company without exchange/sector/industry",
            ticker,
            exc_info=True,
        )
        return None
