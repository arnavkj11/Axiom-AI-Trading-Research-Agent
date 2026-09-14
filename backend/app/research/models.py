import enum
from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Enum as SAEnum, Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Real JSONB on Neon/Postgres; plain JSON on SQLite, which the whole test
# suite runs against (see tests/conftest.py) and which has no JSONB type.
# Same Postgres-native/SQLite-degrade approach as EmbeddingType in
# filings/models.py, but JSON needs no custom (de)serialization, so
# SQLAlchemy's built-in with_variant does the job without a TypeDecorator.
AgentOutputJSON = JSON().with_variant(JSONB(), "postgresql")


class ResearchRunStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    FUNDAMENTAL_RUNNING = "FUNDAMENTAL_RUNNING"
    FILING_RUNNING = "FILING_RUNNING"
    VALUATION_RUNNING = "VALUATION_RUNNING"
    BULL_RUNNING = "BULL_RUNNING"
    BEAR_RUNNING = "BEAR_RUNNING"
    JUDGE_RUNNING = "JUDGE_RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class ResearchRun(Base):
    """One research run, plus the pipeline output it produced.

    Each agent's output is stored as its own JSONB column rather than
    normalized into tables: they're already validated Pydantic models that
    serialize cleanly, the frontend reads them whole to render the debate,
    and nothing queries *inside* them in V1. (full_vision.md's Phase 4+
    research-memory system is where per-finding normalization would earn
    its keep — out of scope here.)

    All output columns are nullable: they're empty until the run finishes,
    and a FAILED run keeps whatever its agents completed before dying.
    """

    __tablename__ = "research_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    status: Mapped[ResearchRunStatus] = mapped_column(
        SAEnum(ResearchRunStatus, name="research_run_status"),
        default=ResearchRunStatus.PENDING,
    )
    research_date: Mapped[date] = mapped_column(Date, default=date.today)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)

    # What this run actually analyzed, captured at run time so a report
    # reopened later is self-describing about the freshness of its own
    # evidence. Without these, an old verdict looks equally authoritative
    # whether its inputs were a day or a year stale.
    price_at_run: Mapped[float | None] = mapped_column(Float)
    price_as_of: Mapped[date | None] = mapped_column(Date)
    financials_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    filings_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    fundamental_analysis: Mapped[dict[str, Any] | None] = mapped_column(AgentOutputJSON)
    filing_analysis: Mapped[dict[str, Any] | None] = mapped_column(AgentOutputJSON)
    valuation_output: Mapped[dict[str, Any] | None] = mapped_column(AgentOutputJSON)
    bull_case: Mapped[dict[str, Any] | None] = mapped_column(AgentOutputJSON)
    bear_case: Mapped[dict[str, Any] | None] = mapped_column(AgentOutputJSON)
    judge_verdict: Mapped[dict[str, Any] | None] = mapped_column(AgentOutputJSON)
    # Not an agent output: computed deterministically from the verdict and
    # the valuation at save time. Stored beside them so a run keeps the
    # call it actually gave, thresholds included.
    recommendation: Mapped[dict[str, Any] | None] = mapped_column(AgentOutputJSON)
