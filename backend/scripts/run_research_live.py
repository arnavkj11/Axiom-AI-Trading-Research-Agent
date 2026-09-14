"""One-off diagnostic runner: invokes the full 7-agent research pipeline
against REAL data in Neon using REAL Anthropic + Voyage API calls (no
mocks/fakes). Not part of the app's request path — this is a manual dev
tool for exercising the pipeline end-to-end and inspecting exactly what
happened.

Usage:
    uv run python scripts/run_research_live.py AAPL

What this does that production code doesn't:
- Wraps AnthropicLLMClient to capture response.usage (input/output token
  counts) per call, since the production client only returns the parsed
  Pydantic object today.
- Polls research_runs.status on a background thread over a SEPARATE DB
  connection, so status transitions are observed with real wall-clock
  timestamps rather than just read before/after run_research().
- Prints the full final ResearchState as JSON, un-truncated.

Costs real money (Anthropic + a few Voyage embedding calls) and writes a
real research_runs row to whatever DATABASE_URL points at.
"""

import json
import sys
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path

# Make the backend package importable when this script is invoked directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.agents.llm_client import DEFAULT_MAX_TOKENS, DEFAULT_MODEL, AnthropicLLMClient, LLMResponseError
from app.agents.orchestrator import run_research
from app.company.models import Company
from app.core.config import settings
from app.filings.search import VoyageFilingSearchClient
from app.filings.voyage_client import VoyageEmbeddingClient
from app.research.models import ResearchRun, ResearchRunStatus


class InstrumentedLLMClient(AnthropicLLMClient):
    """Same behavior as AnthropicLLMClient.generate_structured, but logs
    per-call token usage and latency. Duplicates the parent's request
    body rather than calling super() so it can reach the raw response
    object (usage isn't on the parsed return value).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.usage_log: list[dict] = []

    def generate_structured(self, *, system, user_message, output_model):
        tool_name = output_model.__name__
        start = time.monotonic()
        response = self._client.messages.create(
            model=self._model,
            max_tokens=DEFAULT_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user_message}],
            tools=[
                {
                    "name": tool_name,
                    "description": f"Return a structured {tool_name}.",
                    "input_schema": output_model.model_json_schema(),
                }
            ],
            tool_choice={"type": "tool", "name": tool_name},
        )
        elapsed = time.monotonic() - start
        usage = getattr(response, "usage", None)
        self.usage_log.append(
            {
                "output_model": tool_name,
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
                "elapsed_seconds": round(elapsed, 2),
                "stop_reason": response.stop_reason,
            }
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                return output_model.model_validate(block.input)
        raise LLMResponseError(f"Anthropic response had no {tool_name!r} tool_use block")


def poll_status(engine, research_run_id: int, log: list, stop_event: threading.Event):
    """Runs on a background thread with its own DB session — polling the
    main thread's session would be unsafe (Session objects aren't
    thread-safe for concurrent access, as we hit once already in testing).
    """
    PollSession = sessionmaker(bind=engine)
    poll_db = PollSession()
    last_status = None
    start = time.monotonic()
    try:
        while not stop_event.is_set():
            poll_db.expire_all()
            row = poll_db.get(ResearchRun, research_run_id)
            if row is not None and row.status != last_status:
                last_status = row.status
                log.append({"elapsed_seconds": round(time.monotonic() - start, 2), "status": row.status.value})
            time.sleep(0.5)
    finally:
        poll_db.close()


def main(ticker: str):
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    db = Session()

    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if company is None:
        print(f"No company found for ticker {ticker!r}. Aborting — nothing was created.")
        return

    research_run = ResearchRun(company_id=company.id, research_date=date.today())
    db.add(research_run)
    db.commit()
    print(f"Created research_runs row id={research_run.id} for {company.ticker} (company_id={company.id})")

    status_log: list[dict] = [{"elapsed_seconds": 0.0, "status": research_run.status.value}]
    stop_event = threading.Event()
    poller = threading.Thread(target=poll_status, args=(engine, research_run.id, status_log, stop_event), daemon=True)
    poller.start()

    llm_client = InstrumentedLLMClient(api_key=settings.anthropic_api_key, model=DEFAULT_MODEL)
    voyage_client = VoyageEmbeddingClient(
        api_key=settings.voyage_ai_api_key,
        batch_size=settings.voyage_batch_size,
        min_seconds_between_requests=settings.voyage_min_seconds_between_requests,
    )
    filing_search_client = VoyageFilingSearchClient(db=db, voyage_client=voyage_client)

    print(f"Running full pipeline for {company.ticker} against model {DEFAULT_MODEL} ...")
    wall_start = time.monotonic()
    error = None
    final_state = None
    try:
        final_state = run_research(db, research_run, llm_client, filing_search_client)
    except Exception as exc:  # deliberately broad — this is a diagnostic runner, report whatever happens
        error = exc
    wall_elapsed = time.monotonic() - wall_start

    time.sleep(0.6)  # let the poller catch the final status before we stop it
    stop_event.set()
    poller.join(timeout=2)

    print("\n" + "=" * 100)
    print("1. research_runs.status progression (observed via polling, separate DB connection)")
    print("=" * 100)
    for entry in status_log:
        print(f"  t+{entry['elapsed_seconds']:>6.2f}s  {entry['status']}")
    db.refresh(research_run)
    print(f"\n  Final DB row: status={research_run.status.value} started_at={research_run.started_at} completed_at={research_run.completed_at}")

    print("\n" + "=" * 100)
    print("3. Wall-clock time and per-call token usage")
    print("=" * 100)
    print(f"  Total wall-clock: {wall_elapsed:.2f}s")
    total_input = sum(u["input_tokens"] or 0 for u in llm_client.usage_log)
    total_output = sum(u["output_tokens"] or 0 for u in llm_client.usage_log)
    for u in llm_client.usage_log:
        print(
            f"  {u['output_model']:<28} input={u['input_tokens']:>6} output={u['output_tokens']:>6} "
            f"stop_reason={u['stop_reason']:<12} elapsed={u['elapsed_seconds']:>6.2f}s"
        )
    print(f"\n  TOTAL: input={total_input} output={total_output} calls={len(llm_client.usage_log)}")
    cost = total_input / 1_000_000 * 2.0 + total_output / 1_000_000 * 10.0
    print(f"  Approx cost at Sonnet 5 rates ($2/$10 per MTok): ${cost:.4f}")

    print("\n" + "=" * 100)
    print("4. Errors")
    print("=" * 100)
    if error is not None:
        import traceback

        print(f"  Pipeline FAILED: {type(error).__name__}: {error}")
        traceback.print_exception(type(error), error, error.__traceback__)
    else:
        print("  No exceptions raised.")

    print("\n" + "=" * 100)
    print("2. Full final ResearchState (un-truncated)")
    print("=" * 100)
    if final_state is not None:
        print(json.dumps(final_state.model_dump(mode="json"), indent=2, default=str))
    else:
        print("  (no final state — run failed before completion)")

    db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: uv run python scripts/run_research_live.py <TICKER>")
        sys.exit(1)
    main(sys.argv[1])
