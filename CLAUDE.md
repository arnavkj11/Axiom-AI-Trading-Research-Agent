# Axiom — Project Brief for Claude Code

## What this project is

Axiom is a multi-agent AI equity research platform. A user picks a public
company, Axiom runs a team of specialized LLM agents that gather evidence,
value the company with deterministic Python (not LLM arithmetic), argue a
bull case against a bear case, and a judge agent produces a final thesis
with a stance, conviction score, and full evidence citations.

This is **not** a chatbot wrapper. The core architectural rule, always:

> Agents reason and choose assumptions. Python code calculates. Every
> material claim in a report must cite a specific piece of evidence
> (a financial metric, a filing chunk, or a valuation output).

## Current phase: V1 only

Do not build anything outside this list unless explicitly asked. V1 is
deliberately scoped to be finishable, not maximal. Later phases (Temporal,
point-in-time backtesting, research memory, portfolio features, AWS
deployment, full observability stack) are documented in
`docs/full_vision.md` for reference only — do not start on them.

### V1 must include

**Backend**
- FastAPI + PostgreSQL + SQLAlchemy + Alembic
- **Database is hosted, not local.** Use Neon (free-tier Postgres with
  pgvector support) rather than a local/Dockerized Postgres instance. The
  connection string goes in `.env` as `DATABASE_URL`. Neon gives you two
  connection strings — a pooled one (via PgBouncer) and a direct one.
  Use the **direct** connection for Alembic migrations and the **pooled**
  connection for the running FastAPI app. Enable the `vector` extension
  on the Neon database (`CREATE EXTENSION IF NOT EXISTS vector;`) before
  the first migration that creates embedding columns.
- No Temporal in V1. Use a `research_runs` table with a status enum
  (`PENDING`, `RUNNING`, `<AGENT_NAME>_RUNNING`, `COMPLETE`, `FAILED`) and
  FastAPI `BackgroundTasks` (or a simple asyncio task) to run research
  asynchronously. Design the step functions so they are idempotent and can
  be safely retried — this matters because we may swap in Temporal later
  without rewriting agent logic.
- SEC EDGAR ingestion for 10-K/10-Q/8-K filings: fetch, store raw text,
  chunk, embed, store in pgvector. Store `filing_date` and `published_at`
  on every chunk even though point-in-time cutoff *enforcement* is not a
  V1 feature — capturing the timestamp now costs nothing and saves a
  painful backfill later.
- One financial-data source for structured fundamentals (revenue, margins,
  EPS, FCF, debt, share count, etc). **Known caveat to flag to the user
  before picking one**: most cheap/free market-data APIs silently serve
  *restated* financials, not what was known at the original publication
  date. That's fine for V1 (we're not enforcing point-in-time cutoffs
  yet), but note it in code comments so it isn't forgotten when Phase 4
  (point-in-time engine) starts.

**Agents (LangGraph)**
1. Research Orchestrator — plans the run, routes state, does not do
   analysis itself.
2. Fundamental Analyst — quantitative financial health, structured output.
3. Filing Analyst — evidence-grounded findings from SEC filings via
   pgvector retrieval, must cite chunk IDs.
4. Valuation Analyst — calls deterministic Python functions (`run_dcf`,
   `calculate_pe_multiple`, `run_scenario_analysis`, etc). The LLM chooses
   or critiques assumptions; it never performs the arithmetic itself.
5. **Bull Analyst** — builds the strongest evidence-backed bull case from
   the preliminary thesis and the other agents' findings.
6. **Bear Analyst** — builds the strongest evidence-backed bear case the
   same way.
7. **Judge Agent** — runs the debate: Bull and Bear each get to see the
   other's argument and produce at most one rebuttal round (hard cap —
   do not let debate rounds grow unbounded, this controls both cost and
   latency). Judge then produces the final stance (BULLISH/BEARISH/
   NEUTRAL), a conviction score (0-100), and the synthesis report.

All agent inputs/outputs are Pydantic models, validated before entering
shared LangGraph state. No agent communicates in free-form prose. Every
`Finding` with meaningful `importance` must carry at least one `evidence`
reference.

**Frontend**
- Next.js + React + TypeScript + Tailwind
- Company search → start research run → poll/display live status
  (which agent is running) → final report view
- Final report shows: stance, conviction, core thesis, bull case, bear
  case, judge's rebuttal summary, valuation scenarios (bear/base/bull
  fair value), risks, catalysts, and a sources panel where every citation
  is clickable back to its evidence.

**Dev/Test**
- No local Postgres container. Docker (if used at all) is optional and
  only for containerizing the FastAPI app itself later, not required for
  V1 local development — running `uvicorn` directly against the hosted DB
  is sufficient.
- pytest coverage prioritized on: valuation math (deterministic, must be
  exactly right), Pydantic schema validation, and the debate round cap
  logic. Do not chase high coverage % on frontend or glue code.

### Explicitly deferred — do not build in V1

- Temporal (durable workflows)
- Point-in-time cutoff *enforcement* (we store timestamps now, we don't
  filter on them yet)
- Backtesting service
- Research memory / thesis versioning
- Agent performance scorecards / prompt-version comparison
- Portfolio/watchlist features
- AWS deployment, OpenTelemetry/Prometheus/Grafana
- Additional agents beyond the seven listed above (Industry, Macro,
  Catalyst, Risk agents are Phase 7+)

If a task seems to require one of these, stop and ask rather than
building it partially.

## Design rules that always apply (from Phase 0 onward)

1. **LLMs reason, code calculates.** Never let an agent do financial
   arithmetic in free text — call a Python function and pass the result
   back.
2. **Structured outputs only.** Every agent response is a validated
   Pydantic model. No shared state is prose.
3. **Evidence must be traceable.** Any claim with material importance
   needs a citation to a metric, filing chunk, or valuation output.
4. **Modular monolith, not microservices.** Everything lives in one
   FastAPI repo with clean domain module boundaries (`company/`,
   `financials/`, `filings/`, `research/`, `valuation/`, `agents/`).
   Do not split into separate deployable services in V1.
5. **Bound the debate.** Bull/Bear/Judge must have a hard round limit
   (default: 1 rebuttal round each) to keep cost and latency predictable.

## Repository structure (target)

```
axiom/
  backend/
    app/
      company/
      financials/
      filings/
      research/
      valuation/
      agents/
        orchestrator.py
        fundamental.py
        filing.py
        valuation.py
        bull.py
        bear.py
        judge.py
        debate_graph.py
      api/
      db/
        models.py
        migrations/
    tests/
  frontend/
    app/
    components/
  docker-compose.yml
  docs/
    full_vision.md   # the original 52-section blueprint, reference only
```

## Definition of Done for V1

- [ ] User can search a public company and see basic financial data
- [ ] User can start a research run and see live per-agent status
- [ ] Fundamental, Filing, and Valuation agents each produce structured,
      cited output
- [ ] Bull and Bear agents each produce a structured case with at least
      one rebuttal round between them
- [ ] Judge agent produces a final stance, conviction score, and synthesis
- [ ] Every material claim in the final report links to evidence
- [ ] Valuation numbers come from Python functions, never LLM arithmetic
- [ ] Research runs and all agent outputs are persisted in PostgreSQL
- [ ] App runs locally against the hosted Postgres instance (no local DB
      install required)
- [ ] Core valuation logic and schema validation have passing tests

## When in doubt

Prefer the smaller, shippable version of a feature over the more
architecturally impressive one. This is a portfolio project that needs to
actually finish. Ask before expanding scope, even if the original
blueprint (`docs/full_vision.md`) describes a larger version of the same
feature.
