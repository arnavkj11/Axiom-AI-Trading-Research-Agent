"""Persistence for a finished research run.

run_research() produces a ResearchState that only lives in memory — this
module writes it down and reads it back, which is what lets a finished
run be displayed after the fact instead of only at the moment it
completes.

Only the *outputs* are stored. The inputs (company, financial_metrics)
are rehydrated from their own tables on load, since every Evidence object
already embeds its own metric_name/period_end/value snapshot — a citation
stays accurate even if Alpha Vantage later restates the underlying row.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.schemas import (
    BearCase,
    BullCase,
    FilingAnalysis,
    FundamentalAnalysis,
    JudgeVerdict,
    ValuationOutput,
)
from app.company.models import Company
from app.company.schemas import CompanyRead
from app.financials.schemas import FinancialMetricRecord
from app.financials.service import load_recent_financial_metrics
from app.research.models import ResearchRun, ResearchRunStatus
from app.research.recommendation import Recommendation, recommend
from app.research.schemas import ResearchRunSummary, ResearchState

# ResearchState field -> the Pydantic model that validates it coming back
# out of JSON. Column names on research_runs match the state field names,
# so both directions can drive off this one mapping.
AGENT_OUTPUTS: dict[str, type] = {
    "fundamental_analysis": FundamentalAnalysis,
    "filing_analysis": FilingAnalysis,
    "valuation_output": ValuationOutput,
    "bull_case": BullCase,
    "bear_case": BearCase,
    "judge_verdict": JudgeVerdict,
}


def save_research_state(db: Session, state: ResearchState) -> ResearchRun:
    """Write every agent output on `state` to its research_runs row.

    A state carrying an error is persisted as FAILED with the message,
    keeping whatever outputs its agents did finish; otherwise the run is
    marked COMPLETE. Safe to call on a run the orchestrator already marked
    COMPLETE — it writes the same terminal state again rather than
    conflicting, so a retried save is a no-op.
    """
    run = db.get(ResearchRun, state.research_run_id)
    if run is None:
        raise ValueError(f"ResearchRun id={state.research_run_id} not found")

    for field, _model in AGENT_OUTPUTS.items():
        output = getattr(state, field)
        # mode="json" so dates and enums land as JSON primitives rather
        # than Python objects the driver can't serialize.
        setattr(run, field, output.model_dump(mode="json") if output is not None else None)

    # Derived here rather than by an agent, and stored rather than computed
    # on read, so the run keeps the call it actually gave.
    recommendation = recommend(state.judge_verdict, state.valuation_output)
    run.recommendation = recommendation.model_dump(mode="json")

    if state.error:
        run.status = ResearchRunStatus.FAILED
        run.error = state.error
    else:
        run.status = ResearchRunStatus.COMPLETE
        run.error = None
    run.completed_at = datetime.now(timezone.utc)

    db.commit()
    return run


def mark_research_run_failed(db: Session, run_id: int, error: str) -> ResearchRun | None:
    """Record a run that died mid-pipeline, keeping any outputs already saved.

    Separate from save_research_state because a graph that raises returns
    no ResearchState at all — there's nothing to serialize, only a failure
    to record. Returns None if the run row is gone.
    """
    run = db.get(ResearchRun, run_id)
    if run is None:
        return None

    run.status = ResearchRunStatus.FAILED
    run.error = error
    run.completed_at = datetime.now(timezone.utc)
    db.commit()
    return run


def list_research_runs(
    db: Session, company: Company | None = None, limit: int = 50
) -> list[ResearchRunSummary]:
    """Run history, newest first, optionally for one company.

    Reads the verdict's headline out of stored JSON rather than
    reconstructing every agent output — a history list shouldn't pay to
    deserialize six models per row when it renders two fields of one.
    """
    stmt = select(ResearchRun)
    if company is not None:
        stmt = stmt.where(ResearchRun.company_id == company.id)
    # research_date is a date, so id breaks ties within a day — several runs
    # of the same company on one day is the normal case while iterating.
    stmt = stmt.order_by(ResearchRun.research_date.desc(), ResearchRun.id.desc()).limit(limit)

    runs = list(db.scalars(stmt).all())
    tickers = _tickers_for(db, runs) if company is None else {company.id: company.ticker}

    return [
        ResearchRunSummary(
            research_run_id=run.id,
            ticker=tickers.get(run.company_id, ""),
            status=run.status,
            research_date=run.research_date,
            started_at=run.started_at,
            completed_at=run.completed_at,
            error=run.error,
            stance=(run.judge_verdict or {}).get("stance"),
            conviction=(run.judge_verdict or {}).get("conviction"),
            has_report=any(getattr(run, field) is not None for field in AGENT_OUTPUTS),
        )
        for run in runs
    ]


def _tickers_for(db: Session, runs: list[ResearchRun]) -> dict[int, str]:
    """One lookup for the whole page rather than a query per row."""
    company_ids = {run.company_id for run in runs}
    if not company_ids:
        return {}
    rows = db.execute(
        select(Company.id, Company.ticker).where(Company.id.in_(company_ids))
    ).all()
    return {company_id: ticker for company_id, ticker in rows}


def load_research_state(db: Session, run_id: int) -> ResearchState | None:
    """Rebuild the full ResearchState for a persisted run, or None if the
    run doesn't exist.
    """
    run = db.get(ResearchRun, run_id)
    if run is None:
        return None

    company = db.get(Company, run.company_id)
    if company is None:
        raise ValueError(f"Company id={run.company_id} not found for research run id={run_id}")

    outputs = {
        field: model.model_validate(stored)
        for field, model in AGENT_OUTPUTS.items()
        if (stored := getattr(run, field)) is not None
    }

    # Same metric window the agents actually saw during the run, so a
    # reloaded state matches what produced these outputs.
    metric_rows = load_recent_financial_metrics(db, company.id)

    return ResearchState(
        research_run_id=run.id,
        company_id=run.company_id,
        ticker=company.ticker,
        research_date=run.research_date,
        status=run.status,
        error=run.error,
        # From the run row, not the agent-output JSONB: the price describes
        # the run's inputs rather than any agent's output, and a reopened
        # report needs it to anchor its upside numbers.
        current_price=run.price_at_run,
        price_as_of=run.price_as_of,
        recommendation=(
            Recommendation.model_validate(run.recommendation)
            if run.recommendation is not None
            else None
        ),
        company=CompanyRead.model_validate(company),
        financial_metrics=[FinancialMetricRecord.model_validate(m) for m in metric_rows],
        **outputs,
    )
