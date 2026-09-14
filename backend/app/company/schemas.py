from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    name: str
    exchange: str | None
    sector: str | None
    industry: str | None
    cik: str | None
    # Null until the data has been pulled at all; the UI shows these as
    # "data as of" so staleness is visible rather than implicit.
    financials_refreshed_at: datetime | None = None
    filings_synced_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CompanyCreateRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=10)


class CompanyCandidate(BaseModel):
    """An SEC registrant that could be added, and whether it already was."""

    ticker: str
    name: str
    cik: str
    in_database: bool


class CompanyLookupResponse(BaseModel):
    candidates: list[CompanyCandidate]


class CompanySearchRequest(BaseModel):
    query: str = Field(min_length=1)


class CompanySearchResponse(BaseModel):
    results: list[CompanyRead]
