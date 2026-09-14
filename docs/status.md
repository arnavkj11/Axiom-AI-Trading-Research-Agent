# Axiom — build status

**Snapshot: 2026-09-09.** A dated, honest account of what exists, what has
actually been exercised end-to-end, and what is known to be wrong. The
README describes the system as designed; this file describes it as built.

Headline: **every V1 component in `CLAUDE.md` is implemented and the full
pipeline runs end-to-end against live data.** 279 backend tests pass. Three
verified defects in the financial-math layer are open — none break the
pipeline, all of them distort the numbers it produces.

---

## Built and working

### Data layer

| Piece | State |
|---|---|
| Neon Postgres + pgvector | 9 Alembic migrations applied, `vector` extension enabled |
| Company records | 5 companies (AAPL, TSLA, NVDA, GOOGL, SPCX) |
| Structured fundamentals (Alpha Vantage) | 4,072 `financial_metrics` rows, annual + quarterly |
| SEC filings (EDGAR → chunk → Voyage embed → pgvector) | 26 filings, 1,479 chunks (AAPL 462, GOOGL 1,017) |
| Research runs | 8 rows, 5 COMPLETE with full stored reports |

Company creation works from the SEC registrant list, so a ticker that
isn't in the database yet can be searched, added, and populated without a
manual insert. Freshness timestamps (`financials_refreshed_at`,
`filings_synced_at`) are recorded and surfaced in the UI.

### Backend API

Thirteen routes across five domain modules:

```
GET  /health
GET  /companies/lookup            POST /companies
GET  /companies/{ticker}          POST /companies/search
GET  /companies/{ticker}/financials        POST .../financials/refresh
GET  /companies/{ticker}/filings           POST .../filings/sync
POST /companies/{ticker}/research
GET  /research                    GET  /research/{id}
GET  /research/{id}/status
```

Runs execute in a FastAPI `BackgroundTask` against its own session factory,
with per-agent status written to the run row as the graph advances, so the
frontend can poll and show which agent is currently working.

### Agents

All seven are built and wired into a LangGraph `StateGraph`: orchestrator,
fundamental, filing, valuation (fan-out in parallel), then bull and bear,
one capped rebuttal round each, then judge. Every agent output is a
validated Pydantic model — no prose crosses the state boundary. The
debate round cap is enforced in code, not by prompt, and
`RebuttalAlreadyRecordedError` is raised if anything tries to record a
second one.

### Deterministic layers

- **Valuation** (`app/valuation/calculations.py`): DCF and multiples in
  Python. The valuation agent picks and critiques assumptions; it never
  does arithmetic. It is also deliberately blind to the stock price, so
  its fair values can't anchor to the market.
- **Upside/downside**: computed in Python after valuation, from the run's
  price snapshot, and handed to bull/bear/judge as an input.
- **Recommendation** (`app/research/recommendation.py`): BUY/SELL/HOLD
  derived from the verdict and the scenario spread against fixed
  thresholds (conviction ≥ 60, base upside ≥ +20%, bear downside ≥ −30%).
  The thresholds are stored on each run, so an old report stays readable
  if the product decision behind them changes.

### Frontend

Next.js 16 / React 19 / Tailwind v4, dark trading-desk theme. Search →
company page (financials, filings, freshness, past runs) → start run →
live per-agent status → report. The report renders the verdict scale,
BUY/SELL/HOLD with its rationale, the valuation number line, bull and bear
columns with the rebuttal round, and a sources panel where every citation
expands to the metric, filing quote, or valuation output behind it. Past
runs for a company are listed on its page and open the stored report.

### Tests

279 passing, all offline (in-memory SQLite, mocked HTTP). Weighted where
`CLAUDE.md` asks: valuation math, schema validation, the debate round cap,
and the failure paths — including a mid-pipeline LLM failure and a
`RebuttalAlreadyRecordedError`, both of which must land the run in FAILED
with a readable error rather than stuck in RUNNING.

---

## Verified end-to-end

Three complete reports rendered from live data, priced at run time:

| Run | Company | Price at run | Verdict | Call |
|---|---|---|---|---|
| 8 | NVDA | $225.73 | NEUTRAL 58 | HOLD |
| 11 | GOOGL | $338.36 | BEARISH 62 | SELL |
| 12 | SPCX | $153.47 | BEARISH 65 | SELL |

Run 11 is the one that exercises the filing path: 5 filing findings
carrying 8 chunk citations retrieved through pgvector. Runs 8 and 12 are
companies with no filings ingested — in both, the filing analyst returned
NEUTRAL at 0.2 confidence with zero findings rather than inventing any,
which is the correct behaviour, and the judge's synthesis made no
filing-based claims.

Failure handling is exercised too: run 10 died on an Anthropic 400 and is
stored as FAILED with the API's message intact, not left hanging.

---

## Known defects (open)

Found in the 2026-09-08 verification pass on run 8. None are fixed.

1. **Free cash flow is inverted.** `free_cash_flow()` in
   `app/financials/calculations.py` adds capex instead of subtracting it,
   on the strength of a comment claiming Alpha Vantage reports capex as
   negative. All 296 stored capex rows are positive and the client applies
   no negation. Every FCF figure in the database is overstated by 2×capex
   — NVDA FY2026 shows $108.8B where the true figure is $96.7B.

2. **The DCF used a quarterly FCF as its annual base.**
   `_latest_metric_value` in `app/agents/valuation.py` selects on
   `period_end` while ignoring `period_type`, so run 8 discounted
   $26.75B (one quarter) as if it were a full year. Rerunning with the
   annual figure moves the base-case fair value from $25.07 to $92.36 and
   the gap to market from −89% to −59%. The verdict direction survives;
   the magnitude the judge called "the single largest unresolved risk"
   does not.

3. **Filing quotes are never validated against chunk text.**
   `_validate_evidence_matches_retrieved_chunks` in `app/agents/filing.py`
   checks `chunk_id`, `filing_id` and `accession_number`, but never that
   `quote` appears in the chunk. A fabricated quote attached to a real
   chunk id passes the guard. This is the weakest point in the
   evidence-traceability guarantee, since it's the one citation type whose
   content is free text rather than a number copied from a row.

Bugs 1 and 2 push fair value in opposite directions and do not cancel.

---

## Not built (deferred past V1, per `CLAUDE.md`)

Temporal, point-in-time cutoff *enforcement* (timestamps are captured, not
filtered on), backtesting, research memory and thesis versioning, agent
scorecards, portfolio/watchlist features, AWS deployment and the
observability stack, and any agent beyond the seven above.
