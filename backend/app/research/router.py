"""Research run API: trigger a run, then poll it.

Paths are declared in full rather than under a shared prefix because the
trigger hangs off a company (POST /companies/{ticker}/research) while the
polling endpoints address the run itself (GET /research/{id}).
"""

from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.dependencies import get_llm_client
from app.company.models import Company
from app.db.session import get_db
from app.financials.alpha_vantage_client import AlphaVantageClient
from app.financials.dependencies import get_alpha_vantage_client
from app.research.dependencies import get_filing_search_client_factory, get_session_factory
from app.research.models import ResearchRun, ResearchRunStatus
from app.research.runner import execute_research_run
from app.research.schemas import (
    ResearchRunCreated,
    ResearchRunDetail,
    ResearchRunListResponse,
    ResearchRunStatusResponse,
)
from app.research.service import list_research_runs, load_research_state

router = APIRouter(tags=["research"])

# Statuses after which the persisted report is worth returning. FAILED is
# included on purpose — see ResearchRunDetail.
TERMINAL_STATUSES = frozenset({ResearchRunStatus.COMPLETE, ResearchRunStatus.FAILED})


def _get_run_or_404(research_run_id: int, db: Session) -> ResearchRun:
    run = db.get(ResearchRun, research_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Research run {research_run_id} not found")
    return run


@router.post(
    "/companies/{ticker}/research", response_model=ResearchRunCreated, status_code=202
)
# Six parameters, five of them FastAPI-injected dependencies — that's how
# DI is expressed in FastAPI, not an over-long signature to refactor.
def start_research(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    ticker: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    llm_client=Depends(get_llm_client),
    session_factory=Depends(get_session_factory),
    filing_search_client_factory=Depends(get_filing_search_client_factory),
    quote_client: AlphaVantageClient = Depends(get_alpha_vantage_client),
) -> ResearchRunCreated:
    """Queue a research run and return its id immediately.

    The pipeline takes minutes and costs real API calls, so it runs as a
    background task (CLAUDE.md: no Temporal in V1) and the caller follows
    it via /research/{id}/status.
    """
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if company is None:
        raise HTTPException(status_code=404, detail=f"Company '{ticker}' not found")

    run = ResearchRun(
        company_id=company.id,
        status=ResearchRunStatus.PENDING,
        research_date=date.today(),
    )
    db.add(run)
    db.commit()

    run_id = run.id
    background_tasks.add_task(
        execute_research_run,
        run_id=run_id,
        session_factory=session_factory,
        llm_client=llm_client,
        filing_search_client_factory=filing_search_client_factory,
        quote_client=quote_client,
    )

    return ResearchRunCreated(
        research_run_id=run_id, ticker=company.ticker, status=ResearchRunStatus.PENDING
    )


@router.get("/research", response_model=ResearchRunListResponse)
def list_runs(
    ticker: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> ResearchRunListResponse:
    """Past runs, newest first — the index that makes stored reports findable.

    Declared before /research/{research_run_id} so the bare path isn't
    captured as a run id.
    """
    company = None
    if ticker is not None:
        company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
        if company is None:
            raise HTTPException(status_code=404, detail=f"Company '{ticker}' not found")

    return ResearchRunListResponse(runs=list_research_runs(db, company=company, limit=limit))


@router.get("/research/{research_run_id}", response_model=ResearchRunDetail)
def get_research_run(research_run_id: int, db: Session = Depends(get_db)) -> ResearchRunDetail:
    run = _get_run_or_404(research_run_id, db)
    company = db.get(Company, run.company_id)

    report = load_research_state(db, research_run_id) if run.status in TERMINAL_STATUSES else None

    return ResearchRunDetail(
        research_run_id=run.id,
        ticker=company.ticker if company else "",
        status=run.status,
        error=run.error,
        started_at=run.started_at,
        completed_at=run.completed_at,
        price_at_run=run.price_at_run,
        price_as_of=run.price_as_of,
        financials_as_of=run.financials_as_of,
        filings_as_of=run.filings_as_of,
        report=report,
    )


@router.get("/research/{research_run_id}/status", response_model=ResearchRunStatusResponse)
def get_research_run_status(
    research_run_id: int, db: Session = Depends(get_db)
) -> ResearchRunStatusResponse:
    run = _get_run_or_404(research_run_id, db)
    return ResearchRunStatusResponse(research_run_id=run.id, status=run.status)
