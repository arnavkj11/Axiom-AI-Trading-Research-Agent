"""The background-task entry point for a research run.

CLAUDE.md's V1 rule: no Temporal — a run is a FastAPI BackgroundTask
driving the LangGraph pipeline, with research_runs.status as the only
durable record of where it got to. That makes this function's error
handling load-bearing: a background task has no caller to propagate to,
so anything that escapes here disappears silently and strands the run in
RUNNING forever, which a polling frontend would wait on indefinitely.
"""

import logging
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.agents.orchestrator import run_research
from app.research.models import ResearchRun
from app.research.service import mark_research_run_failed, save_research_state

logger = logging.getLogger(__name__)


def execute_research_run(
    run_id: int,
    session_factory: Callable[[], Session],
    llm_client,
    filing_search_client_factory: Callable[[Session], object],
    quote_client=None,
) -> None:
    """Run the full seven-agent pipeline for `run_id` and persist the result.

    Always leaves the run in a terminal state — COMPLETE with its report,
    or FAILED with a readable error — never mid-flight.
    """
    db = session_factory()
    try:
        run = db.get(ResearchRun, run_id)
        if run is None:
            logger.error("research run id=%s disappeared before it could start", run_id)
            return

        state = run_research(
            db, run, llm_client, filing_search_client_factory(db), quote_client=quote_client
        )
        save_research_state(db, state)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Deliberately broad: every agent error (RebuttalAlreadyRecordedError,
        # EvidenceNotInPoolError, ValuationInputsMissingError, LLMResponseError,
        # ...) plus anything unforeseen must still leave a terminal status
        # behind. Narrowing this would let an unanticipated exception type
        # strand the run.
        logger.exception("research run id=%s failed", run_id)
        # The failure may have left the transaction unusable (e.g. a DB
        # error); rolling back first makes the FAILED write itself safe.
        db.rollback()
        mark_research_run_failed(db, run_id, f"{type(exc).__name__}: {exc}")
    finally:
        db.close()
