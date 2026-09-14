from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.filings.models import FilingStatus


class FilingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    accession_number: str
    form_type: str
    filing_date: date
    period_end: date | None
    published_at: datetime
    source_url: str
    status: FilingStatus


class CompanyFilingsResponse(BaseModel):
    ticker: str
    filings: list[FilingRead]
