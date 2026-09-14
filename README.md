# Axiom

Axiom is a multi-agent AI equity research platform. A user picks a public
company, a team of specialized LLM agents gathers evidence, values the
company with deterministic Python (not LLM arithmetic), argues a bull case
against a bear case, and a judge agent produces a final thesis with a
stance, conviction score, and full evidence citations.

Core architectural rule, always:

> Agents reason and choose assumptions. Python code calculates. Every
> material claim in a report must cite a specific piece of evidence (a
> financial metric, a filing chunk, or a valuation output).

This is V1 of the project. See `CLAUDE.md` for the full scope/constraints
and `docs/full_vision.md` for the long-term product vision (reference
only — not all of it applies to V1).

---

## Tech stack

- **Backend**: FastAPI + SQLAlchemy 2.0 + Alembic, Python 3.12, managed
  with [uv](https://docs.astral.sh/uv/)
- **Database**: [Neon](https://neon.tech) (hosted Postgres + pgvector) —
  no local/Dockerized Postgres
- **Structured fundamentals**: Alpha Vantage
- **SEC filings**: EDGAR (fetch) + [Voyage AI](https://voyageai.com)
  (embeddings) + pgvector (storage/similarity search)
- **Agents**: LangGraph + Claude (Anthropic), structured tool-call outputs
- **Frontend**: Next.js 16 (App Router) + React 19 + TypeScript + Tailwind v4

---

## What's built so far

This section describes the system as designed. For a dated snapshot of
what has actually been exercised end-to-end — real runs, real data
counts, and the defects currently open — see `docs/status.md`.

### Foundation
- FastAPI app skeleton with domain module boundaries (`company/`,
  `financials/`, `filings/`, `research/`, `valuation/`, `agents/`)
- SQLAlchemy models + Alembic migrations against Neon (direct connection
  for migrations, pooled connection for the running app)
- pgvector extension enabled on the database

### Company Service (`app/company/`)
- `Company` model: ticker, name, exchange, sector, industry, CIK
- `GET /companies/{ticker}` — look up a company
- `POST /companies/search` — case-insensitive search by ticker or name,
  over companies already in the database
- **Adding a company by ticker** — two ranked sources: SEC's public
  registrant list (`company_tickers.json`, ~10.4k companies, no API key)
  supplies ticker/name/CIK and is required, since the CIK is what makes
  filing ingestion possible; Alpha Vantage's `OVERVIEW` fills in
  exchange/sector/industry and is best-effort, because the free tier's
  25 requests/day makes failure routine. A company is still created when
  enrichment fails — losing display fields must not lose the company.
- `GET /companies/lookup?q=` — searches SEC's registrant list by name or
  ticker, marking which results are already in the database. This is what
  turns "no results" into "add Tesla" instead of a dead end.

### Financial Data Service (`app/financials/`)
- `FinancialMetric` model — one row per (company, metric, period), so
  each metric is individually citable as evidence
- Alpha Vantage integration with rate-limit throttling (free tier: 25
  requests/day, 1 request/sec burst)
- Deterministic derived-metric calculations (margins, free cash flow,
  YoY revenue growth) — pure, unit-tested Python, no LLM arithmetic
- `GET /companies/{ticker}/financials` — fetches on first request, caches
  in Postgres afterward. Metrics: revenue, revenue growth, gross margin,
  operating margin, net income, EPS, free cash flow, capex, debt, cash,
  share count
- **The cache never expires on its own.** Once a company has any metric
  rows, the GET serves them forever — nothing re-checks Alpha Vantage on a
  timer, and a research run never fetches anything at all. Freshness is an
  explicit action: `POST /companies/{ticker}/financials/refresh` refetches,
  and `companies.financials_refreshed_at` / `filings_synced_at` record
  when each source was last checked so the UI can show the age.
- **Refreshing rewrites history.** `_persist` updates periods in place, and
  Alpha Vantage serves *restated* figures — so a refresh replaces stored
  numbers with today's view of them. Harmless in V1, but it means the
  stored series is "as last fetched", not "as first reported", which
  Phase 4's point-in-time engine will need to reckon with.
- **Caveat**: Alpha Vantage's free tier serves restated financials (today's
  numbers as currently reported), not what was known as of the period —
  fine for V1 since point-in-time cutoff enforcement is a later phase

### SEC Filing Ingestion Service (`app/filings/`)
- `Filing` / `FilingChunk` models — raw filing text stored directly in
  Postgres (no S3, since AWS deployment is out of scope for V1); each
  chunk carries a real pgvector embedding plus `filing_date` and
  `published_at` (captured now even though cutoff *enforcement* is later)
- EDGAR client: fetches 10-K/10-Q/8-K metadata + documents, with the
  identifying User-Agent SEC's fair-access policy requires
  - **V1 scope**: most-recent-only per company — latest 1 10-K, 4 10-Q,
    8 8-K (not full filing history)
- Deterministic chunker: overlapping fixed-size windows with best-effort
  section labeling (detects `Item N.` headers from real 10-K/10-Q text)
- Voyage AI embedding client (voyage-3, 1024 dimensions), batched and
  rate-limited (configurable — see `.env.example`)
- Sync is incremental: re-running for a company only fetches/chunks/embeds
  filings not already stored, keyed by EDGAR accession number
- `POST /companies/{ticker}/filings/sync` — trigger ingestion
- `GET /companies/{ticker}/filings` — list stored filing metadata
- Live-verified end-to-end against real Apple filings: 13 filings, 462
  chunks, real embeddings, correct section labels on ~80% of chunks

### Valuation Engine (`app/valuation/`)
- Deterministic Python, no LLM arithmetic: `run_dcf` (discounted FCF +
  terminal value), `calculate_pe_multiple`, `run_scenario_analysis`
  (bear/base/bull fair-value scenarios off one set of DCF assumptions
  each), `upside_pct`
- Pure functions, unit-tested directly against known inputs/outputs

### Price vs value
A fair value only means something next to what the stock actually costs,
so each run fetches a quote and compares:

- **Fetched per run, not cached.** A quote goes stale in minutes where
  fundamentals go stale in months, so `GLOBAL_QUOTE` is pulled when the run
  starts (1 Alpha Vantage request) and stamped onto `research_runs`
  alongside the vintage of the financials and filings it analyzed. A
  reopened report says what its inputs were worth *at the time*.
- **Best-effort.** A throttled or missing quote degrades the report (no
  upside comparison) rather than failing the run.
- **`upside_pct = (fair value − price) / price`, in Python.** The model
  never derives it (Rule 1), and it's `None` rather than guessed when no
  price is available.
- **The Valuation Analyst is deliberately blind to the price.** Shown the
  market price while choosing DCF assumptions, a model drifts toward
  assumptions that reproduce it — a valuation that looks independent but
  has been quietly reverse-engineered from the quote, which Bull, Bear and
  Judge would then inherit as evidence. The price is injected into the
  *result* afterwards instead. A DCF is only worth computing if it can
  disagree with the market. `tests/test_price_in_debate.py` guards this.
- **Bull, Bear and Judge do see it**, with each scenario's upside, so the
  debate is about the investment rather than just the business. Upside
  cites as `ValuationOutputEvidence` (an output field of
  `run_scenario_analysis`, carrying the price it was measured against), so
  price-based claims stay traceable without a new Evidence variant.

### Recommendation (`app/research/recommendation.py`)
BUY / SELL / HOLD / NOT_RATED, computed by a pure function from the
verdict and the price — deliberately not an eighth agent. The Judge has
already read everything; a model asked to re-read its own verdict would
add latency and drift without adding evidence. What remains is arithmetic
plus a threshold policy, and policy belongs in code where it's explicit,
testable, and identical every run.

```
NOT_RATED  if no verdict, or no price
BUY        if BULLISH and conviction >= 60 and base upside >= +20%
                     and bear-case upside >= -30%
SELL       if BEARISH and conviction >= 60 and base upside <= -20%
HOLD       otherwise
```

- **NEUTRAL always holds.** The judge saw the full debate and declined to
  call it; the rule never overrules the verdict it derives from. Your NVDA
  run is exactly this case — NEUTRAL at conviction 58 with the base case
  89% below market — and reads HOLD.
- **Both conditions required.** High conviction with thin upside is a good
  business already priced accordingly; big upside with low conviction is a
  debate that never settled. Both are HOLD.
- **The bear floor is a margin of safety**, applied to BUY only — never
  recommend buying when the run's own pessimistic scenario implies losing
  a third. As a condition on exiting it would make no sense, so SELL
  doesn't carry it.
- **NOT_RATED is distinct from HOLD**: we couldn't judge, rather than
  judged and chose to sit still.
- Every recommendation carries its inputs, the thresholds it used, and a
  plain-language rationale naming the comparison that decided it — so a
  reader sees a rule over two numbers rather than an oracle, and stored
  recommendations stay interpretable if the thresholds later change.

**On the thresholds**: they are a starting product decision, not a tuned
parameter. Conviction is self-reported and uncalibrated, nothing is
backtested, and these were set against a handful of runs. Revisit them
once there are enough runs to say anything.

### Agent Team (`app/agents/`) — all seven agents built, LangGraph-orchestrated
- Shared Pydantic contracts (`schemas.py`): `Finding`, the discriminated
  `Evidence` union (`FinancialMetricEvidence` / `FilingChunkEvidence` /
  `ValuationOutputEvidence`), and per-agent output models
  (`FundamentalAnalysis`, `FilingAnalysis`, `ValuationOutput`, `BullCase`,
  `BearCase`, `JudgeVerdict`). A `Finding` with `importance >= 0.5` fails
  validation if it has no `Evidence` — the "every material claim cites
  evidence" rule is enforced at the schema level, not by convention.
- `AnthropicLLMClient` (`llm_client.py`) — wraps Claude's structured
  tool-call output; every agent gets a validated Pydantic object back,
  never free-form prose
- **Fundamental Analyst** — quantitative read on the Financial Data
  Service's metrics, cites `metric_id`s
- **Filing Analyst** — pgvector similarity search over filing chunks,
  cites `chunk_id`s
- **Valuation Analyst** — the LLM picks/critiques DCF assumptions, then
  calls the deterministic valuation functions above; results come back as
  `ValuationOutputEvidence`
- **Bull / Bear Analysts** — build opposing cases from the three upstream
  agents' findings
- **Bull/Bear Rebuttal** — one hard-capped rebuttal round each (sees only
  the opposing side's opening case, never its own side twice)
- **Judge Agent** — final `Stance` (BULLISH/BEARISH/NEUTRAL), 0–100
  conviction score, and synthesis report
- **Orchestrator** (`orchestrator.py`) — a `StateGraph` that fans out
  Fundamental/Filing/Valuation in parallel, fans in to Bull/Bear in
  parallel, fans in again to the two rebuttal nodes in parallel, then
  Judge. Drives `research_runs.status` through the CLAUDE.md lifecycle
  and commits after each phase so runs are resumable/idempotent.
- **Run persistence** (`app/research/service.py`) —
  `save_research_state()` writes a finished run's six agent outputs to
  JSONB columns on `research_runs` (FAILED + error message if the state
  carries one, COMPLETE otherwise); `load_research_state()` reads a run
  back into a full `ResearchState`, rehydrating company/metrics from
  their live tables. Verified round-tripping through real Neon JSONB, not
  just the SQLite test suite.
- **Research API** (`app/research/router.py`) — `POST
  /companies/{ticker}/research` creates the run and kicks the pipeline off
  as a FastAPI `BackgroundTask` (CLAUDE.md: no Temporal in V1), returning
  the id immediately; `GET /research/{id}` returns status plus the
  persisted report once terminal; `GET /research/{id}/status` is a
  lightweight poll returning just the status enum. The background task
  opens its own DB session — the request's is already closed by the time
  it runs — and catches every exception so a failed run always lands in
  `FAILED` with a readable error rather than stranding in `RUNNING`.
- `scripts/run_research_live.py` — manual diagnostic runner that invokes
  the full pipeline against real Neon data with real Anthropic/Voyage API
  calls (costs money; not part of the request path) and prints the full
  final `ResearchState` JSON, including per-call token usage

### Quality
- **279 automated tests** across 42 files (pytest), all passing, TDD
  throughout. Coverage is concentrated where CLAUDE.md asks for it:
  valuation math, Pydantic schema validation (materiality → evidence
  requirement), and the debate round cap. Also covered: the
  orchestrator's fan-out/fan-in wiring, save/load round-trips with deep
  equality, the failure paths (agent errors, `RebuttalAlreadyRecordedError`,
  billing failures) that must leave a run `FAILED` rather than stranded,
  and the guard that keeps the price out of the Valuation Analyst's prompt.
- The whole suite runs against in-memory SQLite with faked clients — no
  network, no API keys, no cost. The tradeoff: it proves the logic but not
  real JSONB behaviour, so the persistence round-trip was separately
  verified by hand against live Neon.
- Pydantic schema validation on every API boundary.
- Modules are kept `pylint`-clean, modulo documented scoped disables for
  framework false positives (SQLAlchemy's `TypeDecorator`/`func.now`
  proxies, FastAPI's dependency-injection parameter counts, `Protocol`
  classes). A bare `pylint app` scores lower — that gap is
  missing-docstring policy (not enforced here) and expected duplicate-code
  warnings between internal dataclasses and their Pydantic schemas, not
  real defects.

### Frontend (`frontend/`)
- **Search page** (`/`) — searches the database first; if nothing matches,
  falls back to SEC's registrant list and offers to add what it finds, so
  searching "tesla" surfaces "TSLA · Tesla, Inc." with an **Add** button
  rather than a dead end
- **Company page** (`/companies/[ticker]`) — company details plus a
  research-readiness check (metric periods + filings ingested). If filings
  are missing, an **Ingest filings** action fetches them; if financial metrics
  are missing, research is blocked with an explanation rather than letting
  the run fail on `ValuationInputsMissingError`. Shows how long ago each
  source was last checked (flagged amber past 7 days) with a **Refresh
  data** button, since a run analyzes only what's stored and never fetches
  on its own.
- **Run history** — past runs listed on the company page, and recent runs
  across all companies on the search page, each linking to its stored
  report. Runs that predate the persistence layer are marked "no report
  stored" and aren't linked, rather than opening an empty page.
- **Run page** (`/research/[id]`) — polls `/research/{id}/status` every 3s
  (the lightweight endpoint), then fetches the full report once, on
  reaching a terminal state. Shows stance, conviction, synthesis, bull and
  bear cases with their rebuttals, the judge's read of the rebuttal round,
  valuation scenarios, key findings/risks/catalysts, and a sources panel.
- **Citations** — evidence is deduped across every agent and numbered once,
  so a `[3]` in the bull case and a `[3]` in the judge's verdict are the
  same source. Each source expands to show exactly what it points at: the
  metric value and period, the filing quote and accession number, or the
  valuation function, field, and assumptions. No extra API calls needed —
  every `Evidence` variant is self-describing.
- Backend `CORSMiddleware` allows the frontend origin (`frontend_origin`
  setting, default `http://localhost:3000`), with tests covering the
  allowed origin, the preflight for starting a run, and rejection of
  unknown origins.

#### Design

Dark, built around the two things that make this product distinct —
opposition and evidence — rather than the tickers-and-candlesticks
vernacular of a trading terminal.

- **Colour is semantic, not decorative.** Amber is the interactive accent
  specifically so green and red stay reserved for direction (bull/bear,
  upside/downside) and never appear as ornament. Deep blue-slate ground
  rather than near-black.
- **Two signature devices, both encoding real data.** The verdict is a
  position on a bearish↔bullish axis with conviction as distance from
  centre; the valuation is a number line placing bear/base/bull fair values
  against the actual share price, so cheap-or-expensive reads at a glance
  rather than requiring the reader to do the arithmetic.
- **Type**: Newsreader (serif) for verdicts and thesis prose — research
  notes are editorial documents; IBM Plex Sans for interface; Plex Mono for
  numerals only, where tabular alignment does real work.
- Hairlines and coloured edge-markers instead of uniform rounded cards.
  Motion is one orchestrated moment (the verdict settling in) plus the live
  status pulse; `prefers-reduced-motion` respected, visible focus rings,
  no horizontal overflow at 390px.

### Not built yet
- Nothing in V1 scope — see the Definition of Done in `CLAUDE.md`. Three
  defects in the financial-math layer are open, though; `docs/status.md`
  lists them.

---

## Getting started

### Prerequisites

1. **Python 3.12+** and [uv](https://docs.astral.sh/uv/getting-started/installation/)
2. A free [Neon](https://neon.tech) Postgres project — grab both
   connection strings (pooled + direct) from the dashboard
3. A free [Alpha Vantage API key](https://www.alphavantage.co/support/#api-key)
4. A free [Voyage AI API key](https://dashboard.voyageai.com/) (adding a
   payment method later unlocks much higher rate limits, still under the
   free token allowance — see `.env.example`)

### Setup

```bash
cd backend
uv sync                          # installs deps + creates .venv

cp .env.example .env             # then fill in your real values:
                                  #   DATABASE_URL, DIRECT_DATABASE_URL,
                                  #   ALPHA_VANTAGE_API_KEY, VOYAGE_AI_API_KEY

uv run alembic upgrade head      # creates all tables + enables pgvector
```

### Run the API

```bash
uv run uvicorn app.main:app --reload
```

Visit `http://127.0.0.1:8000/docs` for interactive Swagger docs.

### Run the frontend

In a second terminal, with the API already running:

```bash
cd frontend
npm install
cp .env.example .env.local   # NEXT_PUBLIC_API_BASE_URL, defaults to :8000
npm run dev
```

Then open `http://localhost:3000`. The browser calls the API directly, so
the backend's `frontend_origin` setting must match wherever the frontend
is served from (it defaults to `http://localhost:3000`).

### Run tests

```bash
uv run pytest
```

Tests run entirely against an in-memory SQLite database and mocked HTTP
clients — no live network calls, no real API keys needed to run the suite.

### Lint

```bash
uv run --with pylint pylint app
```

---

## API reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `GET` | `/companies/{ticker}` | Get a company by ticker |
| `POST` | `/companies/search` | Search companies already in the database (`{"query": "apple"}`) |
| `GET` | `/companies/lookup?q=` | Search SEC's registrant list for companies that *could* be added |
| `POST` | `/companies` | Add a company by ticker (`{"ticker": "TSLA"}`); idempotent, returns `200` if it already exists |
| `GET` | `/companies/{ticker}/financials` | Get structured fundamentals (fetches + caches on first call; never re-checks after) |
| `POST` | `/companies/{ticker}/financials/refresh` | Refetch current fundamentals, bypassing the cache |
| `POST` | `/companies/{ticker}/filings/sync` | Ingest the company's most recent 10-K/10-Q/8-K filings |
| `GET` | `/companies/{ticker}/filings` | List stored filing metadata |
| `POST` | `/companies/{ticker}/research` | Start a research run in the background; returns `202` + `research_run_id` |
| `GET` | `/research?ticker=&limit=` | Past runs, newest first — summaries only, no reports |
| `GET` | `/research/{id}` | Run status, plus the full report once the run is COMPLETE or FAILED |
| `GET` | `/research/{id}/status` | Just the status enum — for frequent polling |

Note: `/financials` and `/filings/sync` require the company to already
exist (`GET /companies/{ticker}` returns 404 otherwise) and, for filings,
to have a CIK on file.

---

## Data model

| Table | Purpose |
|---|---|
| `companies` | Ticker, name, sector/industry/exchange, CIK, plus `financials_refreshed_at` / `filings_synced_at` — when each source was last checked, tracked here because metric rows are updated in place and so leave no trace of a check that confirmed nothing changed |
| `financial_metrics` | One row per (company, metric, period) — narrow/EAV, so every number is individually citable |
| `filings` | One row per SEC filing — metadata + raw text |
| `filing_chunks` | One row per embedded chunk — text, pgvector embedding, section, `filing_date`, `published_at` |
| `research_runs` | Status lifecycle, plus everything one run produced and consumed: one JSONB column per agent output (`fundamental_analysis`, `filing_analysis`, `valuation_output`, `bull_case`, `bear_case`, `judge_verdict`), an `error` message for failed runs, and a snapshot of the inputs it analysed (`price_at_run`, `price_as_of`, `financials_as_of`, `filings_as_of`) so a report reopened weeks later is self-describing about its own freshness |

9 Alembic migrations, all applied to Neon.

---

## Roadmap

### What the output is, and isn't

The Judge produces a **stance** (BULLISH/BEARISH/NEUTRAL), a **conviction
score**, and a cited synthesis. That's a research verdict, not a
recommendation, and the distinction matters:

- The BUY/SELL/HOLD call is a **rule applied to that verdict**, not an
  independent judgement — and still carries no position sizing, entry/exit
  price, time horizon, or portfolio context.
- It does **not** predict a price. The DCF scenarios are conditional
  arithmetic on chosen assumptions, not forecasts.
- **Conviction is not calibrated.** It's the model's confidence in its own
  synthesis; nothing has measured whether a 78 outperforms a 55.
- **Nothing is backtested** (Phase 4+), so there is no evidence the stances
  predict returns.

The BUY/SELL/HOLD layer described above sits on top of this, and inherits
the same caveats: it is a deterministic reading of an unvalidated verdict,
not advice. It shows its own thresholds precisely so that's visible.

### Known gaps in V1

- **Status granularity.** `research_runs.status` has per-agent values
  (`FUNDAMENTAL_RUNNING`, …), but the orchestrator runs Fundamental,
  Filing and Valuation concurrently and uses the generic `RUNNING` for
  that whole phase — no single per-agent value is accurate while three are
  in flight. The UI shows the real status rather than faking a per-agent
  walk.
- **Alpha Vantage's 25 requests/day.** Adding a company spends 1 (the
  `OVERVIEW` call) and its first financials fetch spends 4. The clients are
  process-wide singletons so their self-throttling actually applies across
  concurrent requests — constructing one per request silently disabled it,
  which showed up live as two simultaneous `/financials` calls both failing
  with 502.

### Explicitly deferred past V1

Per `CLAUDE.md`, these are documented in `docs/full_vision.md` but
intentionally not started:

- Temporal (durable workflows) — `research_runs` + FastAPI background
  tasks for now, designed to be idempotent so Temporal can be swapped in
  later without rewriting agent logic
- Point-in-time cutoff *enforcement* — timestamps are already captured on
  every financial metric and filing chunk, just not filtered on yet
- Backtesting service, forecast tracking
- Research memory / thesis versioning
- Agent performance scorecards / prompt-version comparison
- Portfolio/watchlist features
- AWS deployment, OpenTelemetry/Prometheus/Grafana
- Additional agents beyond the seven above (Industry, Macro, Catalyst,
  Risk — Phase 7+ in the full vision)
