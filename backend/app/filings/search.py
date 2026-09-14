"""Nearest-neighbor retrieval over a company's embedded filing chunks.

Requires Postgres/pgvector at runtime — the `<=>` cosine-distance operator
has no SQLite equivalent, same limitation as the rest of the filing-
embedding pipeline (see app/filings/models.py's EmbeddingType). Not
exercised against the SQLite test DB for that reason; agent-level tests
inject a fake FilingSearchClient instead (see tests/test_filing_agent.py).
"""

from pydantic import BaseModel
from sqlalchemy import Float, select
from sqlalchemy.orm import Session

from app.filings.models import Filing, FilingChunk
from app.filings.voyage_client import VoyageEmbeddingClient


class FilingChunkResult(BaseModel):
    chunk_id: int
    filing_id: int
    accession_number: str
    section: str | None
    text: str


def search_filing_chunks(
    db: Session, company_id: int, query_embedding: list[float], top_k: int = 5
) -> list[FilingChunkResult]:
    # .op() is used instead of pgvector's .cosine_distance() comparator:
    # FilingChunk.embedding is our EmbeddingType TypeDecorator (impl=Text),
    # so it doesn't inherit Vector's comparator_factory, but the <=>
    # operator itself is available generically via .op().
    distance = FilingChunk.embedding.op("<=>", return_type=Float)(query_embedding)
    stmt = (
        select(FilingChunk, Filing.accession_number)
        .join(Filing, FilingChunk.filing_id == Filing.id)
        .where(Filing.company_id == company_id)
        .order_by(distance)
        .limit(top_k)
    )
    return [
        FilingChunkResult(
            chunk_id=chunk.id,
            filing_id=chunk.filing_id,
            accession_number=accession_number,
            section=chunk.section,
            text=chunk.text,
        )
        for chunk, accession_number in db.execute(stmt).all()
    ]


class VoyageFilingSearchClient:
    """Embeds a text query with Voyage, then runs the pgvector search."""

    def __init__(self, db: Session, voyage_client: VoyageEmbeddingClient):
        self._db = db
        self._voyage_client = voyage_client

    def search(self, *, company_id: int, query: str, top_k: int) -> list[FilingChunkResult]:
        [query_embedding] = self._voyage_client.embed([query])
        return search_filing_chunks(self._db, company_id, query_embedding, top_k)
