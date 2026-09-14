"""Research Orchestrator — the LangGraph entry point.

Loads a research_runs row's company + financial data into a ResearchState,
fans out to Fundamental, Filing, and Valuation in parallel (LangGraph runs
same-superstep nodes concurrently), waits for all three, and merges their
outputs back into ResearchState. Bull and Bear then run in parallel off
that merge point (each waits for all three upstream agents, per
LangGraph's fan-in barrier semantics — a node only fires once every
predecessor with an edge into it has completed). bull_rebuttal and
bear_rebuttal each wait for BOTH bull and bear (they need both opening
cases), then run in parallel — each sees only the other side's opening
case, never the other's rebuttal, since they're siblings with no edge
between them. Judge waits for both rebuttal nodes and produces the final
JudgeVerdict. All seven agents (Fundamental, Filing, Valuation, Bull,
Bear, [rebuttals,] Judge) now run in one graph.invoke() call.

Status flow note: research_runs.status has per-agent RUNNING values
(FUNDAMENTAL_RUNNING, FILING_RUNNING, ...) for a *sequential* pipeline.
Since these three agents run concurrently here, there's no single
per-agent value that would be accurate while all three are in flight, so
this uses the generic RUNNING status for the whole fan-out phase. The
granular per-agent statuses remain meaningful for the future, sequential
Bull -> Bear -> Judge phase.
"""

import logging
from datetime import datetime, timezone
from functools import partial
from typing import Protocol

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.agents.bear import bear_analyst
from app.agents.bear_rebuttal import bear_rebuttal
from app.agents.bull import bull_analyst
from app.agents.bull_rebuttal import bull_rebuttal
from app.agents.filing import FilingSearchClient as _FilingSearchClientProtocol
from app.agents.filing import filing_analyst
from app.agents.fundamental import fundamental_analyst
from app.agents.judge import judge_agent
from app.agents.valuation import valuation_analyst
from app.company.models import Company
from app.company.schemas import CompanyRead
from app.financials.schemas import FinancialMetricRecord
from app.financials.service import load_recent_financial_metrics
from app.research.models import ResearchRun, ResearchRunStatus
from app.research.schemas import ResearchState


logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    def generate_structured(self, *, system: str, user_message: str, output_model): ...


def build_research_graph(llm_client: LLMClient, filing_search_client: _FilingSearchClientProtocol):
    graph_builder = StateGraph(ResearchState)
    graph_builder.add_node("fundamental", partial(fundamental_analyst, llm_client=llm_client))
    graph_builder.add_node(
        "filing",
        partial(filing_analyst, filing_search_client=filing_search_client, llm_client=llm_client),
    )
    graph_builder.add_node("valuation", partial(valuation_analyst, llm_client=llm_client))
    graph_builder.add_node("bull", partial(bull_analyst, llm_client=llm_client))
    graph_builder.add_node("bear", partial(bear_analyst, llm_client=llm_client))
    graph_builder.add_node("bull_rebuttal", partial(bull_rebuttal, llm_client=llm_client))
    graph_builder.add_node("bear_rebuttal", partial(bear_rebuttal, llm_client=llm_client))
    graph_builder.add_node("judge", partial(judge_agent, llm_client=llm_client))

    graph_builder.add_edge(START, "fundamental")
    graph_builder.add_edge(START, "filing")
    graph_builder.add_edge(START, "valuation")

    # bull/bear each wait for all three upstream agents (LangGraph fires a
    # node only once every predecessor with an edge into it has finished),
    # then run in parallel off that merge point.
    for upstream in ("fundamental", "filing", "valuation"):
        graph_builder.add_edge(upstream, "bull")
        graph_builder.add_edge(upstream, "bear")

    # bull_rebuttal/bear_rebuttal each need BOTH opening cases, so each
    # gets an edge from both bull and bear — not just "its own" side. They
    # are siblings with no edge between them, so neither sees the other's
    # rebuttal; and there is no edge anywhere back into either rebuttal
    # node, so each can only run once per graph.invoke() (the primary
    # enforcement of CLAUDE.md Rule 5's one-rebuttal-round cap — see
    # bull_rebuttal.py's module docstring for the other two layers).
    for case in ("bull", "bear"):
        graph_builder.add_edge(case, "bull_rebuttal")
        graph_builder.add_edge(case, "bear_rebuttal")

    graph_builder.add_edge("bull_rebuttal", "judge")
    graph_builder.add_edge("bear_rebuttal", "judge")
    graph_builder.add_edge("judge", END)

    return graph_builder.compile()


def _fetch_quote(quote_client, ticker: str):
    """Current price for the run, or None if it can't be had.

    Best-effort by design: Alpha Vantage's free tier is 25 requests/day, so
    a throttled quote is routine. A run without a price produces a report
    that can't compare value to market — degraded, but far better than
    failing the whole run over a missing number.
    """
    if quote_client is None:
        return None
    try:
        return quote_client.get_quote(ticker)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.warning("Could not fetch a quote for %s; run continues without a price", ticker)
        return None


def run_research(
    db: Session,
    research_run: ResearchRun,
    llm_client: LLMClient,
    filing_search_client: _FilingSearchClientProtocol,
    quote_client=None,
) -> ResearchState:
    company = db.get(Company, research_run.company_id)
    if company is None:
        raise ValueError(f"Company id={research_run.company_id} not found")

    metric_rows = load_recent_financial_metrics(db, company.id)
    # Fetched per run, not cached: a quote is stale in minutes where the
    # fundamentals it's compared against are stale in months.
    quote = _fetch_quote(quote_client, company.ticker)

    initial_state = ResearchState(
        research_run_id=research_run.id,
        company_id=company.id,
        ticker=company.ticker,
        research_date=research_run.research_date,
        status=ResearchRunStatus.RUNNING,
        company=CompanyRead.model_validate(company),
        financial_metrics=[FinancialMetricRecord.model_validate(m) for m in metric_rows],
        current_price=quote.price if quote else None,
        price_as_of=quote.as_of if quote else None,
    )

    research_run.status = ResearchRunStatus.RUNNING
    research_run.started_at = datetime.now(timezone.utc)
    # Snapshot what this run is about to analyze, so the finished report can
    # say how fresh its inputs were rather than looking equally current
    # whenever it's reopened.
    research_run.price_at_run = quote.price if quote else None
    research_run.price_as_of = quote.as_of if quote else None
    research_run.financials_as_of = company.financials_refreshed_at
    research_run.filings_as_of = company.filings_synced_at
    db.commit()

    graph = build_research_graph(llm_client, filing_search_client)
    try:
        result = graph.invoke(initial_state)
    except Exception:
        research_run.status = ResearchRunStatus.FAILED
        db.commit()
        raise

    research_run.status = ResearchRunStatus.COMPLETE
    research_run.completed_at = datetime.now(timezone.utc)
    db.commit()

    return ResearchState(**result).model_copy(update={"status": ResearchRunStatus.COMPLETE})
