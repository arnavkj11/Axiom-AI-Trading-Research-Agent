from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    exchange: Mapped[str | None] = mapped_column(String(50))
    sector: Mapped[str | None] = mapped_column(String(100))
    industry: Mapped[str | None] = mapped_column(String(100))
    cik: Mapped[str | None] = mapped_column(String(10), unique=True)

    # When this company's cached research data was last pulled from its
    # source. Tracked here rather than derived from the rows themselves:
    # financial_metrics are updated in place, so an unchanged value leaves
    # no trace of the check that confirmed it, and max(created_at) would
    # keep reporting the original fetch forever. These answer "how stale is
    # this?", which is a property of the last check, not of the data.
    financials_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    filings_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
