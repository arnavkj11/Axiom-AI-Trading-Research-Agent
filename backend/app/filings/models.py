"""SEC filing ingestion models (full_vision.md §7.3)."""

import enum
import json
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.db.base import Base
from app.filings.voyage_client import EMBEDDING_DIMENSIONS


class EmbeddingType(TypeDecorator):  # pylint: disable=abstract-method,too-many-ancestors
    """pgvector's real Vector type on Postgres; JSON-encoded floats on SQLite.

    SQLite (used by the whole test suite — see tests/conftest.py) has no
    vector type, so this degrades to plain Text there. Production always
    runs on Neon/Postgres and gets true pgvector storage + similarity search.

    Not overriding python_type/process_literal_param is standard for a
    TypeDecorator that's only ever bound as a parameter, never rendered as
    an inline literal — pylint flags the unimplemented abstract methods
    regardless.
    """

    impl = Text
    cache_ok = True

    def __init__(self, dimensions: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dimensions = dimensions

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(self.dimensions))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is None or dialect.name == "postgresql":
            return value
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None or dialect.name == "postgresql":
            return value
        return json.loads(value)


class FilingStatus(str, enum.Enum):
    PENDING = "PENDING"
    FETCHED = "FETCHED"
    CHUNKED = "CHUNKED"
    EMBEDDED = "EMBEDDED"
    FAILED = "FAILED"


class Filing(Base):
    """One SEC filing (10-K/10-Q/8-K). Raw text stored directly in Postgres —
    no S3/object storage in V1 (AWS deployment is out of scope for V1).
    """

    __tablename__ = "filings"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    accession_number: Mapped[str] = mapped_column(String(25), unique=True, index=True)
    form_type: Mapped[str] = mapped_column(String(10))
    filing_date: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    # From EDGAR's acceptanceDateTime — when EDGAR actually published the
    # filing, distinct from filing_date (the nominal date the filer used).
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_url: Mapped[str] = mapped_column(String(500))
    raw_text: Mapped[str | None] = mapped_column(Text)
    status: Mapped[FilingStatus] = mapped_column(
        SAEnum(FilingStatus, name="filing_status"), default=FilingStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()  # pylint: disable=not-callable
    )


class FilingChunk(Base):
    """One embedded text chunk of a filing.

    filing_date and published_at are denormalized from the parent Filing
    onto every chunk (per CLAUDE.md: capturing timestamps now, even though
    point-in-time cutoff *enforcement* is a later phase) so future
    similarity search + cutoff filtering doesn't need a join back to
    filings for every chunk.
    """

    __tablename__ = "filing_chunks"
    __table_args__ = (UniqueConstraint("filing_id", "chunk_index", name="uq_filing_chunk_index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    filing_id: Mapped[int] = mapped_column(ForeignKey("filings.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(120))
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(EmbeddingType(EMBEDDING_DIMENSIONS))
    filing_date: Mapped[date] = mapped_column(Date)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()  # pylint: disable=not-callable
    )
