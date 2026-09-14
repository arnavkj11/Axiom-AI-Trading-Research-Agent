"""ResearchState: the object that flows through the whole LangGraph pipeline.

Filing chunks are not preloaded here — the Filing Analyst retrieves them
live via a search_filings()-style tool call, so state only carries
orchestrator-level context plus each agent's finished output (None until
that node has run).
"""

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.agents.schemas import (
    BearCase,
    BullCase,
    FilingAnalysis,
    FundamentalAnalysis,
    JudgeVerdict,
    Stance,
    ValuationOutput,
)
from app.company.schemas import CompanyRead
from app.financials.schemas import FinancialMetricRecord
from app.research.models import ResearchRunStatus
from app.research.recommendation import Recommendation


class ResearchState(BaseModel):
    research_run_id: int
    company_id: int
    ticker: str
    research_date: date
    status: ResearchRunStatus = ResearchRunStatus.PENDING
    error: str | None = None

    company: CompanyRead | None = None
    financial_metrics: list[FinancialMetricRecord] = Field(default_factory=list)

    # Fetched once at the start of the run rather than cached like the
    # fundamentals: a quote goes stale in minutes where financials go stale
    # in months, so showing a cached price would mislead in a way cached
    # revenue doesn't. None when the quote couldn't be fetched — a run
    # proceeds without it rather than failing.
    current_price: float | None = None
    price_as_of: date | None = None

    fundamental_analysis: FundamentalAnalysis | None = None
    filing_analysis: FilingAnalysis | None = None
    valuation_output: ValuationOutput | None = None
    bull_case: BullCase | None = None
    bear_case: BearCase | None = None
    judge_verdict: JudgeVerdict | None = None

    # Derived from judge_verdict + valuation_output by a pure function at
    # save time, never by an agent. Persisted rather than recomputed on
    # read so a report keeps the call it actually gave, and carries the
    # thresholds it used so it stays interpretable if those change.
    recommendation: Recommendation | None = None


class ResearchRunCreated(BaseModel):
    """POST /companies/{ticker}/research — the run has been queued, not run.

    Returned before the background task starts, so status is always the
    starting status; poll /research/{id}/status to follow it from there.
    """

    research_run_id: int
    ticker: str
    status: ResearchRunStatus


class ResearchRunSummary(BaseModel):
    """One row of run history — deliberately without the report.

    A listing carries six JSONB blobs per row if it embeds reports, so this
    surfaces only what's needed to choose a run: when it ran, how it ended,
    and the verdict headline.
    """

    research_run_id: int
    ticker: str
    status: ResearchRunStatus
    research_date: date
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    # From the stored verdict; None for runs that never reached one.
    stance: Stance | None = None
    conviction: int | None = None
    # False for runs that stored no agent output at all — chiefly those
    # predating the persistence layer, which would otherwise open as an
    # empty report.
    has_report: bool = False


class ResearchRunListResponse(BaseModel):
    runs: list[ResearchRunSummary]


class ResearchRunStatusResponse(BaseModel):
    """GET /research/{id}/status — deliberately just the enum, so a frontend
    can poll every few seconds without pulling a whole report each time.
    """

    research_run_id: int
    status: ResearchRunStatus


class ResearchRunDetail(BaseModel):
    """GET /research/{id} — status plus, once the run reaches a terminal
    state, the persisted report.

    `report` is populated for FAILED runs too, not just COMPLETE ones: the
    agents that finished before the failure are already persisted, and
    showing partial work alongside the error beats showing nothing.
    """

    research_run_id: int
    ticker: str
    status: ResearchRunStatus
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    # How fresh this run's inputs were when it ran, so a report reopened
    # weeks later doesn't read as equally current.
    price_at_run: float | None = None
    price_as_of: date | None = None
    financials_as_of: datetime | None = None
    filings_as_of: datetime | None = None
    report: ResearchState | None = None
