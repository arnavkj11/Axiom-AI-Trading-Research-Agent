from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.company.models import Company
from app.filings.chunking import chunk_text
from app.filings.edgar_client import EdgarClient, EdgarError, FilingMetadata
from app.filings.models import Filing, FilingChunk, FilingStatus
from app.filings.voyage_client import VoyageEmbeddingClient, VoyageEmbeddingError

# V1 scope: most-recent-only, to keep embedding cost/time bounded rather
# than ingesting a company's entire filing history.
FORM_TYPE_LIMITS = {"10-K": 1, "10-Q": 4, "8-K": 8}
CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200


def sync_company_filings(
    db: Session, company: Company, edgar_client: EdgarClient, voyage_client: VoyageEmbeddingClient
) -> list[Filing]:
    if not company.cik:
        raise ValueError(f"Company {company.ticker} has no CIK on file; cannot fetch EDGAR filings")

    recent = edgar_client.get_recent_filings(company.cik, form_types=tuple(FORM_TYPE_LIMITS))
    target = _apply_scope_limits(recent)

    already_embedded = {
        f.accession_number
        for f in db.scalars(
            select(Filing).where(
                Filing.company_id == company.id, Filing.status == FilingStatus.EMBEDDED
            )
        ).all()
    }

    for metadata in target:
        if metadata.accession_number in already_embedded:
            continue
        _ingest_filing(db, company, metadata, edgar_client, voyage_client)

    # Records the check itself, not just the ingest: re-syncing to confirm
    # no new filings have landed is exactly as informative as finding some.
    company.filings_synced_at = datetime.now(timezone.utc)
    db.commit()

    stmt = (
        select(Filing).where(Filing.company_id == company.id).order_by(Filing.filing_date.desc())
    )
    return list(db.scalars(stmt).all())


def _apply_scope_limits(filings: list[FilingMetadata]) -> list[FilingMetadata]:
    counts: dict[str, int] = {}
    limited = []
    for filing in filings:  # EDGAR returns newest-first
        limit = FORM_TYPE_LIMITS.get(filing.form_type, 0)
        if counts.get(filing.form_type, 0) >= limit:
            continue
        counts[filing.form_type] = counts.get(filing.form_type, 0) + 1
        limited.append(filing)
    return limited


def _get_or_create_filing(db: Session, company: Company, metadata: FilingMetadata) -> Filing:
    existing = db.scalar(select(Filing).where(Filing.accession_number == metadata.accession_number))
    if existing is not None:
        return existing
    filing = Filing(
        company_id=company.id,
        accession_number=metadata.accession_number,
        form_type=metadata.form_type,
        filing_date=metadata.filing_date,
        period_end=metadata.period_end,
        published_at=metadata.published_at,
        source_url="",
        status=FilingStatus.PENDING,
    )
    db.add(filing)
    db.flush()
    return filing


def _ingest_filing(
    db: Session,
    company: Company,
    metadata: FilingMetadata,
    edgar_client: EdgarClient,
    voyage_client: VoyageEmbeddingClient,
) -> Filing:
    filing = _get_or_create_filing(db, company, metadata)
    filing.source_url = edgar_client.document_url(
        company.cik, metadata.accession_number, metadata.primary_document
    )

    try:
        raw_text = edgar_client.get_document_text(
            company.cik, metadata.accession_number, metadata.primary_document
        )
        filing.raw_text = raw_text
        filing.status = FilingStatus.FETCHED

        chunks = chunk_text(raw_text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
        filing.status = FilingStatus.CHUNKED

        if chunks:
            db.query(FilingChunk).filter(FilingChunk.filing_id == filing.id).delete()
            embeddings = voyage_client.embed([c.text for c in chunks])
            for chunk, embedding in zip(chunks, embeddings):
                db.add(
                    FilingChunk(
                        filing_id=filing.id,
                        chunk_index=chunk.chunk_index,
                        section=chunk.section,
                        text=chunk.text,
                        embedding=embedding,
                        filing_date=filing.filing_date,
                        published_at=filing.published_at,
                    )
                )
        filing.status = FilingStatus.EMBEDDED
    except (EdgarError, VoyageEmbeddingError):
        filing.status = FilingStatus.FAILED

    db.commit()
    return filing
