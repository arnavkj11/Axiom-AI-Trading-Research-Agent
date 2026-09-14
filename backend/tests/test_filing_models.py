from datetime import date, datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.company.models import Company
from app.filings.models import Filing, FilingChunk, FilingStatus


def test_filing_chunk_embedding_round_trips_through_the_database(db_session):
    company = Company(ticker="AAPL", name="Apple Inc.")
    db_session.add(company)
    db_session.commit()

    filing = Filing(
        company_id=company.id,
        accession_number="0000320193-24-000123",
        form_type="10-K",
        filing_date=date(2024, 11, 1),
        period_end=date(2024, 9, 28),
        published_at=datetime(2024, 11, 1, 18, 5, tzinfo=timezone.utc),
        source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl.htm",
        raw_text="full filing text",
        status=FilingStatus.EMBEDDED,
    )
    db_session.add(filing)
    db_session.commit()

    embedding = [0.1, -0.2, 0.3]
    chunk = FilingChunk(
        filing_id=filing.id,
        chunk_index=0,
        section="Item 1A. Risk Factors",
        text="We face risks.",
        embedding=embedding,
        filing_date=filing.filing_date,
        published_at=filing.published_at,
    )
    db_session.add(chunk)
    db_session.commit()
    db_session.refresh(chunk)

    assert chunk.embedding == embedding
    assert chunk.filing_date == date(2024, 11, 1)
    # SQLite doesn't preserve tzinfo on read-back (Postgres/Neon does) — the
    # wall-clock value round-trips correctly, which is what we're checking.
    assert chunk.published_at.replace(tzinfo=timezone.utc) == datetime(
        2024, 11, 1, 18, 5, tzinfo=timezone.utc
    )


def test_filing_chunk_unique_constraint_on_filing_and_index(db_session):
    company = Company(ticker="AAPL", name="Apple Inc.")
    db_session.add(company)
    db_session.commit()
    filing = Filing(
        company_id=company.id,
        accession_number="0000320193-24-000123",
        form_type="10-K",
        filing_date=date(2024, 11, 1),
        period_end=date(2024, 9, 28),
        published_at=datetime(2024, 11, 1, 18, 5, tzinfo=timezone.utc),
        source_url="https://example.com/filing.htm",
    )
    db_session.add(filing)
    db_session.commit()
    db_session.add(
        FilingChunk(
            filing_id=filing.id,
            chunk_index=0,
            section=None,
            text="a",
            embedding=[0.0],
            filing_date=filing.filing_date,
            published_at=filing.published_at,
        )
    )
    db_session.commit()

    db_session.add(
        FilingChunk(
            filing_id=filing.id,
            chunk_index=0,
            section=None,
            text="b",
            embedding=[0.0],
            filing_date=filing.filing_date,
            published_at=filing.published_at,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
