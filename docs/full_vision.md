# Axiom — Production-Grade Multi-Agent Investment Research Platform

> **Project goal:** Build an AI-native investment research platform that uses specialized agents, point-in-time financial data, adversarial thesis evaluation, persistent research memory, deterministic financial models, and quantitative backtesting to produce and evaluate institutional-style equity research.

---

## 1. Executive Summary

Axiom is not a "stock chatbot" and not a simple web application that asks an LLM whether a company is a good investment.

The finished product should behave more like a small AI-powered equity research team.

A user selects a company, chooses a research date and investment horizon, and asks Axiom to perform a full research cycle. Axiom then:

1. Collects structured company and financial data.
2. Retrieves SEC filings and supporting source material.
3. Runs multiple specialized research agents.
4. Forces agents to cite evidence instead of inventing claims.
5. Runs a bull-versus-bear debate.
6. Uses deterministic Python code for calculations and valuation models.
7. Produces a final investment thesis with confidence, risks, catalysts, scenarios, and valuation.
8. Stores the thesis in long-term research memory.
9. Tracks the thesis over time.
10. Later compares historical predictions against what actually happened.
11. Evaluates the performance of individual agents and the overall research system.

The project is intended to demonstrate:

- Multi-agent architecture
- LLM orchestration
- Reliable agent workflows
- Structured outputs
- Tool calling
- Retrieval-augmented generation
- Financial analysis
- Time-aware data systems
- Data engineering
- Distributed/background workflows
- Backtesting
- Evaluation
- Observability
- Model/prompt versioning
- API design
- Production-grade Python backend engineering
- Cloud deployment
- Human-readable product design

---

# 2. What Axiom Is — and What It Is Not

## Axiom Is

Axiom is an **AI-native institutional research platform**.

Its central idea is:

> AI agents should not simply generate an investment opinion. They should gather evidence, specialize in different research domains, challenge each other, produce structured forecasts, and later be evaluated against reality.

The platform should be able to answer questions such as:

- What is the investment thesis for Microsoft today?
- What changed in Apple's thesis since last quarter?
- What are the strongest arguments against an NVIDIA investment?
- How does Amazon compare with its closest peers?
- What assumptions are most important to the valuation?
- Which previous assumptions about a company turned out to be wrong?
- Which research agent has historically been most accurate?
- How would this company have looked using only information available two years ago?

---

## Axiom Is Not

Avoid turning Axiom into any of the following:

- A single LLM with a long system prompt
- A ChatGPT wrapper
- A stock recommendation chatbot
- A simple RAG project
- A Streamlit demo with no backend architecture
- A collection of agents that only exchange free-form text
- An LLM doing arithmetic that should be done in Python
- A system using future information in historical analysis
- A system where every component is artificially split into a microservice

A production-quality Axiom should deliberately separate:

```text
Agents              -> probabilistic reasoning
Python models       -> numerical calculations
Rules               -> deterministic constraints
Domain services     -> business logic
Workflow engine     -> durable execution
Database            -> system state
Object storage      -> raw documents
Vector search       -> semantic retrieval
Humans/users        -> final investment judgment
```

---

# 3. Main Design Philosophy

Axiom should follow several architectural rules from the beginning.

## Rule 1 — LLMs reason; code calculates

An LLM may decide that a terminal growth rate of 3% is a reasonable scenario assumption.

The LLM should **not manually calculate the DCF**.

Instead:

```text
Agent chooses assumptions
        ↓
Python valuation engine
        ↓
Deterministic result
        ↓
Agent interprets result
```

---

## Rule 2 — Every agent must use structured outputs

Agents should not communicate using uncontrolled prose.

Bad:

```text
"The company looks attractive because margins seem to be improving."
```

Better:

```json
{
  "agent": "fundamental_analyst",
  "stance": "BULLISH",
  "confidence": 0.81,
  "findings": [
    {
      "claim": "Operating margin expanded year-over-year",
      "importance": 0.88,
      "evidence": [
        "metric:operating_margin:2026Q2"
      ]
    }
  ],
  "risks": []
}
```

Pydantic models should validate these responses before they enter shared workflow state.

---

## Rule 3 — Evidence must be traceable

Every material claim should be traceable to one of:

- a structured financial metric
- an SEC filing section
- a market-data observation
- a macroeconomic data point
- a deterministic model output
- another versioned internal source

The final research report should make it possible to click a claim and see the evidence behind it.

---

## Rule 4 — Historical research must be point-in-time correct

If the user asks:

> Analyze this company as of January 15, 2024.

Axiom must not use information published after January 15, 2024.

This is one of the most important differentiators of the project.

---

## Rule 5 — Do not create microservices just to say "microservices"

Axiom should begin as a **modular monolith plus asynchronous workers**.

That gives you:

- clean boundaries
- rapid development
- simpler local setup
- easy refactoring
- fewer deployment problems

Components should become separate services only when they have genuinely different scaling, reliability, or deployment requirements.

---

# 4. Recommended Technology Stack

## Frontend

- Next.js
- React
- TypeScript
- Tailwind CSS
- Charting library such as Recharts or Plotly
- Graph/flow visualization if needed later

---

## Backend

- Python
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic

FastAPI is the preferred choice for Axiom because the project is heavily centered on:

- AI/LLM workflows
- financial modeling
- data science
- pandas
- NumPy
- Python SDKs
- LangGraph
- experimentation

Spring Boot is not required for production quality.

---

## Agent Framework

- LangGraph

LangGraph should own:

- reasoning graphs
- agent transitions
- shared research state
- conditional routing
- retries at the reasoning level
- debate flows
- critique/revision cycles

---

## Durable Workflow Engine

- Temporal

Temporal should own:

- long-running research jobs
- ingestion workflows
- retries
- timeouts
- workflow state
- background jobs
- human approval waits
- scheduled evaluations
- backtesting workflows
- crash recovery

The conceptual split is:

```text
Temporal = reliable workflow execution

LangGraph = probabilistic agent reasoning
```

---

## Data Layer

### PostgreSQL

Primary system of record.

Store:

- companies
- users
- research runs
- financial metrics
- agent runs
- theses
- forecasts
- citations
- valuation results
- market prices
- portfolios
- evaluation results

### pgvector

Use pgvector initially instead of deploying a separate vector database.

Store embeddings for:

- filing chunks
- research notes
- historical theses
- research memory
- qualitative company evidence

### Redis

Use for:

- caching
- request throttling
- temporary research state
- short-lived agent context
- task deduplication where useful

### S3

Use object storage for:

- raw SEC filings
- parsed filing artifacts
- investor documents
- ingestion snapshots
- generated reports
- backtest result artifacts

---

## Observability

- OpenTelemetry
- Prometheus
- Grafana
- structured JSON logs
- LangSmith or equivalent agent tracing if desired

Every research and agent invocation should have a trace ID.

---

## Infrastructure

Recommended AWS services:

- ECS Fargate or EKS later
- RDS PostgreSQL
- ElastiCache Redis
- S3
- CloudFront
- Application Load Balancer
- Secrets Manager
- CloudWatch
- IAM
- ECR
- Route 53
- Bedrock or external LLM provider
- Temporal Cloud or self-hosted Temporal

For the first deployment, ECS Fargate is simpler than Kubernetes.

---

# 5. High-Level Product Architecture

```text
                         ┌────────────────────────┐
                         │     Next.js / React    │
                         │        Frontend        │
                         └────────────┬───────────┘
                                      │
                                      ▼
                         ┌────────────────────────┐
                         │       FastAPI API      │
                         │                        │
                         │ Auth / Research /      │
                         │ Companies / Portfolio  │
                         └────────────┬───────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
                    ▼                 ▼                 ▼
              Domain Modules      Temporal       Query / Read APIs
                    │             Workflows
                    │                 │
                    │                 ▼
                    │       Research Orchestrator
                    │             LangGraph
                    │                 │
                    │      ┌──────────┼───────────┐
                    │      ▼          ▼           ▼
                    │  Fundamental  Filing    Valuation
                    │      Agent      Agent       Agent
                    │
                    │      ┌──────────┼───────────┐
                    │      ▼          ▼           ▼
                    │    Bull        Bear       Judge
                    │
                    ▼
      ┌───────────────────────────────────────────────┐
      │                   Data Layer                  │
      │                                               │
      │ PostgreSQL │ pgvector │ Redis │ S3           │
      └───────────────────────┬───────────────────────┘
                              │
                              ▼
      ┌───────────────────────────────────────────────┐
      │               External Data Sources           │
      │                                               │
      │ SEC EDGAR │ Market Data │ Macro │ News       │
      └───────────────────────────────────────────────┘
```

---

# 6. User Experience — What the Finished Product Should Feel Like

Axiom should feel like a research terminal, not a chatbot.

## Main Dashboard

The user logs in and sees:

```text
AXIOM RESEARCH TERMINAL

Research Runs
------------------------------------------------
NVDA     Complete      Conviction 82       Today
MSFT     Complete      Conviction 74       Yesterday
AMZN     Running       Filing Agent 4/8     61%
GOOGL    Complete      Conviction 68       Aug 30

Watchlist
------------------------------------------------
Ticker    Price    Thesis    Last Research
NVDA      ...      Bullish   Today
MSFT      ...      Bullish   Yesterday
AMZN      ...      Neutral   8 days ago
```

---

## Starting a Research Run

The user selects:

```text
Company:       NVIDIA
Research Date: Current
Horizon:       12 months
Depth:         Full Research
```

Optional settings:

```text
Include macro analysis:       Yes
Include peer comparison:      Yes
Run bull/bear debate:         Yes
Run valuation scenarios:      Yes
```

Then the user clicks:

> Run Research

---

## Live Research Progress

The user sees a workflow timeline:

```text
Research Run AX-98123

✓ Company profile loaded
✓ Financial statements normalized
✓ SEC filings retrieved
✓ Fundamental Agent complete
✓ Filing Agent complete
✓ Valuation Agent complete
→ Bear Agent analyzing thesis
○ Bull Agent waiting
○ Judge Agent waiting
○ Final synthesis waiting
```

Each completed stage can be opened.

---

## Final Research Page

The result page should contain:

### Executive Thesis

```text
Overall Stance: BULLISH
Conviction: 78 / 100
Horizon: 12 months
```

### Core Thesis

Three to five evidence-backed reasons.

### Key Risks

Ordered by severity.

### Catalysts

Potential events that may strengthen the thesis.

### Valuation

```text
Bear Case:  $110
Base Case:  $138
Bull Case:  $165
```

### Financial Trends

Interactive charts for:

- revenue
- margins
- EPS
- free cash flow
- debt
- ROIC
- share count

### Bull vs Bear

Two clearly separated research cases.

### Agent Debate

Show:

- arguments
- rebuttals
- evidence
- confidence changes

### Sources

Every claim should link to its source.

### Forecasts

Show explicit predictions:

```text
12M Revenue Growth:    28%
Gross Margin:          72.5%
EPS Growth:            31%
Expected Price Range:  $120-$160
```

These predictions become backtestable later.

---

# 7. Core Domain Modules / Services

For V1, these can live inside one FastAPI repository as clean domain modules.

---

## 7.1 Company Service

Responsibilities:

- company metadata
- ticker mappings
- sector
- industry
- exchange
- identifiers
- peer relationships
- company profile

Example endpoints:

```http
GET /companies/{ticker}
GET /companies/{ticker}/peers
GET /companies/search?q=
```

---

## 7.2 Financial Data Service

Responsibilities:

- normalize financial statements
- store periodized metrics
- expose ratios and trends
- calculate derived metrics

Metrics include:

- revenue
- revenue growth
- gross margin
- operating margin
- net income
- EPS
- free cash flow
- capex
- ROIC
- debt
- cash
- working capital
- share count
- stock-based compensation

Important principle:

Agents should call this service instead of re-reading every filing whenever structured data already exists.

---

## 7.3 SEC Filing Ingestion Service

Responsibilities:

- fetch filings
- track filing metadata
- store raw filings
- parse document sections
- chunk documents
- generate embeddings
- attach time metadata
- index chunks

Documents:

- 10-K
- 10-Q
- 8-K
- proxy filings where useful

Each chunk should store:

```json
{
  "ticker": "AAPL",
  "form": "10-Q",
  "filing_date": "2026-07-31",
  "period": "2026-Q2",
  "section": "Risk Factors",
  "chunk_id": "chunk_1821",
  "published_at": "..."
}
```

---

## 7.4 Market Data Service

Responsibilities:

- prices
- market capitalization
- historical prices
- returns
- volatility
- valuation multiples
- benchmark prices

Historical prices are essential for backtesting.

---

## 7.5 Research Service

This is the main application domain.

Responsibilities:

- create research runs
- track research status
- persist agent outputs
- manage final research reports
- retrieve prior research
- compare research versions

Important entities:

```text
ResearchRun
ResearchReport
AgentRun
Evidence
Finding
Forecast
```

---

## 7.6 Valuation Service

This must be deterministic Python.

Functions may include:

```python
run_dcf()
calculate_pe_multiple()
calculate_ev_ebitda()
calculate_fcf_yield()
calculate_terminal_value()
run_sensitivity_analysis()
run_scenario_analysis()
```

The LLM chooses or critiques assumptions.

Python calculates the result.

---

## 7.7 Thesis Service

Responsibilities:

- store investment theses
- store thesis version history
- compare thesis changes
- identify invalidated assumptions
- persist risks and catalysts

Example:

```text
NVDA Thesis V3
Created: 2026-09-05

Previous: V2
Changes:
+ Raised expected data-center growth
- Reduced margin expectation
+ Added export restriction risk
```

---

## 7.8 Research Memory Service

This is more than generic vector memory.

Memory should include:

- previous theses
- previous agent findings
- prior forecasts
- assumptions
- mistakes
- historical confidence
- thesis invalidations

Example query:

> What assumptions did we make about Microsoft six months ago?

Axiom should answer using its own stored research history.

---

## 7.9 Backtesting Service

Responsibilities:

- replay historical research
- enforce historical information cutoff
- compare forecasts with actual outcomes
- calculate prediction errors
- calculate agent performance
- evaluate strategy performance later

This becomes one of the project's strongest technical features.

---

## 7.10 Agent Evaluation Service

Responsibilities:

- evaluate agent runs
- run regression tests
- calculate agent metrics
- compare model/prompt versions
- detect performance degradation

Metrics may include:

- grounding accuracy
- unsupported-claim rate
- tool-selection accuracy
- forecast accuracy
- directional accuracy
- task completion
- latency
- token usage
- cost
- retry rate
- human override rate

---

## 7.11 Portfolio Service — Later Phase

Responsibilities:

- user holdings
- watchlists
- portfolio exposures
- portfolio research
- concentration
- sector exposure
- thesis coverage

This is not required for V1.

---

# 8. Agent Architecture

Axiom should not begin with ten agents.

Build the first working system using:

1. Research Orchestrator
2. Fundamental Analyst
3. Filing Analyst
4. Valuation Analyst
5. Bear Analyst
6. Final Synthesis / Judge

Then expand.

---

# 9. Research Orchestrator

The Research Orchestrator coordinates the research process.

It should not itself perform deep financial analysis.

Responsibilities:

- understand research request
- determine required agents
- create research plan
- track workflow state
- route results
- detect missing evidence
- trigger revision
- invoke debate
- assemble final state

Input:

```json
{
  "ticker": "MSFT",
  "research_date": "2026-09-05",
  "horizon_months": 12,
  "depth": "FULL"
}
```

Output:

A complete ResearchState.

---

# 10. Fundamental Analyst Agent

## Purpose

Analyze the company's quantitative financial health.

## Inputs

- normalized financial statements
- historical metrics
- company profile
- prior thesis if available

## Tools

```text
get_income_statement()
get_balance_sheet()
get_cash_flow()
get_financial_metric()
calculate_growth()
calculate_margin()
calculate_roic()
calculate_fcf()
compare_periods()
```

## Responsibilities

Analyze:

- growth
- profitability
- margin trends
- capital efficiency
- cash flow
- balance sheet
- dilution
- operating leverage

## Output Contract

```json
{
  "stance": "BULLISH",
  "confidence": 0.82,
  "findings": [],
  "risks": [],
  "forecasts": [],
  "evidence_ids": []
}
```

---

# 11. Filing Analyst Agent

## Purpose

Analyze qualitative information from SEC filings.

## Inputs

- relevant filing chunks
- research cutoff date
- previous filing observations

## Tools

```text
search_filings()
get_filing_section()
compare_filing_sections()
retrieve_risk_factors()
retrieve_management_discussion()
```

## Responsibilities

Find:

- new risks
- removed risks
- changing management tone
- customer concentration
- litigation
- strategic changes
- material events
- geographic exposure
- competitive commentary

## Output

Structured findings with citation IDs.

---

# 12. Valuation Analyst Agent

## Purpose

Create valuation assumptions and interpret deterministic valuation models.

## Agent Responsibilities

The agent may decide:

- revenue growth assumptions
- margin assumptions
- WACC range
- terminal growth rate
- valuation multiple assumptions

Then it calls deterministic functions.

## Tools

```text
run_dcf()
run_dcf_sensitivity()
calculate_forward_pe()
calculate_ev_ebitda()
run_multiple_scenario()
```

## Output

```json
{
  "bear_case": {
    "fair_value": 110,
    "assumptions": {}
  },
  "base_case": {
    "fair_value": 138,
    "assumptions": {}
  },
  "bull_case": {
    "fair_value": 165,
    "assumptions": {}
  },
  "confidence": 0.74
}
```

---

# 13. Bear Analyst Agent

This is one of the most important agents.

Its job is not to create a generic list of risks.

Its job is to **attack the emerging investment thesis**.

Input:

- fundamental findings
- filing findings
- valuation
- preliminary thesis

Responsibilities:

- challenge assumptions
- identify missing evidence
- identify contradictory evidence
- test valuation sensitivity
- ask what could break the thesis
- identify concentration risk
- identify management optimism
- challenge growth sustainability

Example:

```text
Primary thesis:
AI demand supports 35% annual growth.

Bear challenge:
- How much of current growth depends on three hyperscalers?
- What happens if growth falls to 20%?
- What valuation multiple is justified under that scenario?
- Does current capex imply weaker future free cash flow?
```

---

# 14. Bull Analyst Agent — V2

The Bull Agent should create the strongest evidence-supported optimistic case.

Responsibilities:

- defend strong competitive advantages
- identify upside catalysts
- challenge conservative assumptions
- evaluate operating leverage
- identify optionality

The Bull Agent and Bear Agent should operate independently before seeing each other's final conclusions where possible.

---

# 15. Judge / Investment Committee Agent

The Judge evaluates competing research.

It should not select the better-written argument.

It should score arguments based on:

- evidence quality
- source reliability
- contradiction
- historical accuracy
- valuation sensitivity
- confidence calibration
- unanswered objections

Output:

```json
{
  "final_stance": "BULLISH",
  "conviction": 78,
  "key_reasons": [],
  "key_risks": [],
  "unresolved_questions": [],
  "recommended_monitoring_items": []
}
```

---

# 16. Future Agents

After V1 works, add the following.

## Industry Agent

Analyzes:

- peers
- market structure
- competitive positioning
- market share
- peer multiples
- peer growth

---

## Macro Agent

Analyzes only macro factors relevant to the company.

Examples:

- interest rates
- inflation
- unemployment
- commodity prices
- FX exposure

Avoid letting macro analysis become generic commentary.

---

## Catalyst Agent

Identifies events that could materially change the thesis.

Examples:

- earnings
- product launches
- regulatory decisions
- major contracts
- capex cycles
- mergers

---

## Risk Agent

Maintains a structured risk register.

```text
Risk
Probability
Impact
Evidence
Leading Indicators
Mitigation
Status
```

---

## Research Memory Agent

Compares current findings against prior Axiom research.

Example:

> Three months ago we expected gross margin expansion. Current results contradict that assumption.

---

# 17. Multi-Agent Debate Flow

A simplified research flow:

```text
User Request
     │
     ▼
Research Orchestrator
     │
     ├────────────┬─────────────┐
     ▼            ▼             ▼
Fundamental     Filing      Valuation
 Agent          Agent         Agent
     │            │             │
     └────────────┼─────────────┘
                  ▼
          Preliminary Thesis
                  │
          ┌───────┴────────┐
          ▼                ▼
       Bull Agent       Bear Agent
          │                │
          └───────┬────────┘
                  ▼
             Judge Agent
                  │
        Missing evidence?
           /             \
         Yes              No
          │                │
          ▼                ▼
    Re-research         Final Report
```

---

# 18. LangGraph Design

A possible graph:

```text
START
  │
  ▼
initialize_research
  │
  ▼
load_company_data
  │
  ├──────────────┬───────────────┐
  ▼              ▼               ▼
fundamental    filings        valuation
  │              │               │
  └──────────────┼───────────────┘
                 ▼
         preliminary_synthesis
                 │
        ┌────────┴────────┐
        ▼                 ▼
      bull              bear
        │                 │
        └────────┬────────┘
                 ▼
               judge
                 │
         sufficient evidence?
             /         \
           no           yes
           │             │
           ▼             ▼
     evidence_gap      finalize
           │             │
           └──────► research node
```

---

# 19. Shared Research State

A LangGraph state object may contain:

```python
class ResearchState(BaseModel):
    research_run_id: str
    ticker: str
    research_date: datetime
    horizon_months: int

    company_profile: CompanyProfile | None
    financial_context: FinancialContext | None
    filing_context: FilingContext | None

    fundamental_analysis: AgentAnalysis | None
    filing_analysis: AgentAnalysis | None
    valuation_analysis: ValuationAnalysis | None

    preliminary_thesis: Thesis | None
    bull_case: AgentAnalysis | None
    bear_case: AgentAnalysis | None

    evidence_gaps: list[EvidenceGap] = []
    final_decision: InvestmentDecision | None
```

---

# 20. Temporal Workflows

LangGraph should not be responsible for all system durability.

## ResearchWorkflow

```text
create research run
     ↓
ensure company data exists
     ↓
ensure latest filings exist
     ↓
ensure financial data exists
     ↓
execute LangGraph research
     ↓
persist results
     ↓
generate report
     ↓
mark completed
```

Temporal handles:

- retries
- timeouts
- crash recovery
- long jobs
- worker failures

---

## FilingIngestionWorkflow

```text
discover new filing
     ↓
download
     ↓
store raw document
     ↓
parse
     ↓
extract metadata
     ↓
chunk
     ↓
embed
     ↓
index
```

---

## BacktestWorkflow

```text
select historical date
     ↓
construct point-in-time dataset
     ↓
run historical research
     ↓
save forecasts
     ↓
load future actual results
     ↓
score predictions
```

---

## EvaluationWorkflow

Runs periodically or in CI:

```text
load benchmark cases
     ↓
execute selected agent version
     ↓
score grounding
     ↓
score output contract
     ↓
score predictions
     ↓
compare against previous version
```

---

# 21. Point-in-Time Research Engine

This is one of Axiom's defining features.

Every piece of data must include publication time.

Example:

```text
Data record:
revenue = $10.5B
period = 2024-Q4
published_at = 2025-02-03
```

Historical research query:

```text
research_cutoff = 2024-01-15 23:59:59
```

Every relevant query must enforce:

```sql
WHERE published_at <= :research_cutoff
```

This applies to:

- filings
- prices
- financial statements
- news
- macro data
- prior research memory

---

## Why This Matters

Without it, a historical backtest may accidentally use information that was not known at the time.

That creates **look-ahead bias**.

The system must be able to guarantee:

> This research output used only information available at the requested date.

---

# 22. Research Memory

Axiom should maintain long-term company memory.

Example:

```text
MICROSOFT
│
├── 2025 Q4 research
│   ├── thesis
│   ├── forecasts
│   └── risks
│
├── 2026 Q1 research
│   ├── thesis
│   ├── forecasts
│   └── risks
│
└── 2026 Q2 research
    ├── thesis
    ├── forecasts
    └── risks
```

The system should compare past beliefs against later outcomes.

Example:

```text
Previous prediction:
Azure growth would accelerate.

Actual result:
Azure growth decelerated.

Research lesson:
Cloud-demand assumptions were too optimistic.
```

---

# 23. Forecast Tracking

Every final thesis should include measurable forecasts.

Examples:

- revenue growth
- EPS growth
- gross margin
- operating margin
- free cash flow
- expected multiple
- expected price range
- thesis probability

Each forecast stores:

```text
forecast_id
research_run_id
metric
predicted_value
prediction_range
horizon
prediction_date
evaluation_date
actual_value
error
```

---

# 24. Backtesting

The user should eventually be able to run:

```text
Company: MSFT
Historical Date: 2022-01-15
Horizon: 12 months
```

Axiom runs as though it were January 2022.

Later it evaluates:

```text
Predicted revenue growth: 18%
Actual:                   15%

Forecast Error:            3 percentage points
```

---

# 25. Agent Performance Tracking

Each agent gets a historical scorecard.

Example:

```text
AGENT PERFORMANCE

Fundamental Agent
--------------------------------
Grounding Accuracy       97.2%
Forecast Direction       73.1%
Unsupported Claims        1.4%
Average Confidence       0.77
Average Latency          2.8 sec

Bear Agent
--------------------------------
Risk Recall              76.4%
Useful Objections        82.9%
Unsupported Claims        2.1%
```

Eventually, Axiom can use historical performance to weight agents.

Example:

```text
Fundamental Agent weight: 0.31
Bear Agent weight:        0.27
Industry Agent weight:    0.18
Macro Agent weight:       0.09
Valuation Agent weight:   0.15
```

This should be a later feature, not V1.

---

# 26. Evaluation Metrics

## Agent Quality

- schema-valid output rate
- task completion rate
- grounding accuracy
- citation correctness
- unsupported-claim rate
- tool-selection accuracy
- reasoning consistency

## Forecast Quality

- MAE
- MAPE where appropriate
- directional accuracy
- calibration
- prediction interval coverage

## System Quality

- research completion rate
- average latency
- workflow retry rate
- failed tool calls
- token consumption
- LLM cost
- cache hit rate

## User Quality

- thesis usefulness rating
- human override rate
- source click-through
- report completion rate

---

# 27. Agent Observability

Every agent execution should create a record similar to:

```json
{
  "trace_id": "tr_98123",
  "research_run_id": "rr_48211",
  "agent": "bear_analyst",
  "agent_version": "1.3.0",
  "prompt_version": "bear-v7",
  "model": "model-name",
  "started_at": "...",
  "completed_at": "...",
  "input_tokens": 4822,
  "output_tokens": 1134,
  "latency_ms": 3861,
  "tools_called": [
    "get_financial_metric",
    "run_dcf_sensitivity"
  ],
  "status": "SUCCESS",
  "confidence": 0.81
}
```

---

# 28. Model and Prompt Versioning

Every research run should store:

```text
agent version
prompt version
model version
tool version
data cutoff
valuation model version
```

This lets you answer:

> Why did the system produce a different thesis this month?

You should be able to determine whether the cause was:

- new data
- a new model
- changed prompts
- changed valuation logic
- a new agent version

---

# 29. Data Model

A suggested PostgreSQL schema.

---

## users

```text
id
email
name
created_at
```

---

## companies

```text
id
ticker
name
exchange
sector
industry
cik
created_at
updated_at
```

---

## filings

```text
id
company_id
form_type
filing_date
period_end
published_at
s3_path
source_url
status
```

---

## filing_chunks

```text
id
filing_id
section
chunk_index
text
embedding
published_at
metadata
```

---

## financial_metrics

```text
id
company_id
metric_name
value
period
period_type
currency
published_at
source_filing_id
```

---

## market_prices

```text
id
company_id
timestamp
open
high
low
close
volume
source
```

---

## research_runs

```text
id
user_id
company_id
research_date
horizon_months
depth
status
started_at
completed_at
workflow_id
```

---

## agent_runs

```text
id
research_run_id
agent_name
agent_version
prompt_version
model
status
input
output
confidence
latency_ms
input_tokens
output_tokens
created_at
```

---

## evidence

```text
id
research_run_id
evidence_type
source_entity
source_id
claim
metadata
```

---

## theses

```text
id
research_run_id
company_id
stance
conviction
summary
created_at
```

---

## thesis_findings

```text
id
thesis_id
type
claim
importance
confidence
```

Types:

```text
THESIS
RISK
CATALYST
QUESTION
```

---

## forecasts

```text
id
research_run_id
metric
predicted_value
lower_bound
upper_bound
horizon_months
target_date
actual_value
evaluated_at
error
```

---

## valuation_runs

```text
id
research_run_id
model
scenario
assumptions
fair_value
created_at
```

---

## evaluations

```text
id
agent_run_id
metric
score
evaluator_version
created_at
```

---

# 30. API Design

## Companies

```http
GET    /api/v1/companies/search
GET    /api/v1/companies/{ticker}
GET    /api/v1/companies/{ticker}/financials
GET    /api/v1/companies/{ticker}/filings
GET    /api/v1/companies/{ticker}/research-history
```

---

## Research

```http
POST   /api/v1/research
GET    /api/v1/research/{research_run_id}
GET    /api/v1/research/{research_run_id}/status
GET    /api/v1/research/{research_run_id}/agents
GET    /api/v1/research/{research_run_id}/report
GET    /api/v1/research/{research_run_id}/evidence
```

---

## Thesis

```http
GET    /api/v1/theses/{ticker}/latest
GET    /api/v1/theses/{ticker}/history
GET    /api/v1/theses/{ticker}/compare
```

---

## Backtesting

```http
POST   /api/v1/backtests
GET    /api/v1/backtests/{id}
GET    /api/v1/backtests/{id}/results
```

---

## Agents

```http
GET    /api/v1/agents
GET    /api/v1/agents/{agent}/performance
GET    /api/v1/agents/{agent}/runs
```

---

## Portfolio — Later

```http
GET    /api/v1/portfolio
POST   /api/v1/portfolio/positions
GET    /api/v1/portfolio/research
```

---

# 31. Repository Structure

A clean initial repository:

```text
axiom/
│
├── apps/
│   ├── api/
│   │   ├── main.py
│   │   ├── routers/
│   │   └── dependencies/
│   │
│   ├── worker/
│   │   ├── temporal_worker.py
│   │   └── tasks/
│   │
│   └── web/
│       └── Next.js frontend
│
├── axiom/
│   ├── agents/
│   │   ├── orchestrator/
│   │   ├── fundamental/
│   │   ├── filings/
│   │   ├── valuation/
│   │   ├── bull/
│   │   ├── bear/
│   │   └── judge/
│   │
│   ├── workflows/
│   │   ├── research.py
│   │   ├── ingestion.py
│   │   ├── backtest.py
│   │   └── evaluation.py
│   │
│   ├── domains/
│   │   ├── companies/
│   │   ├── financials/
│   │   ├── filings/
│   │   ├── research/
│   │   ├── theses/
│   │   ├── valuations/
│   │   ├── backtesting/
│   │   └── evaluation/
│   │
│   ├── models/
│   │   ├── database/
│   │   └── schemas/
│   │
│   ├── tools/
│   │   ├── sec/
│   │   ├── market_data/
│   │   ├── financial/
│   │   └── valuation/
│   │
│   ├── infrastructure/
│   │   ├── database/
│   │   ├── redis/
│   │   ├── storage/
│   │   ├── llm/
│   │   └── telemetry/
│   │
│   └── config/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── workflows/
│   ├── agents/
│   ├── evaluations/
│   └── e2e/
│
├── migrations/
├── infrastructure/
│   ├── terraform/
│   └── docker/
│
├── scripts/
├── docs/
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

---

# 32. Testing Strategy

Production-level quality requires more than testing API endpoints.

---

## Unit Tests

Test:

- financial calculations
- valuation functions
- transformations
- date filtering
- point-in-time logic
- Pydantic validation
- domain services

---

## Integration Tests

Test:

- PostgreSQL
- Redis
- SEC parser
- workflow activities
- filing ingestion
- vector retrieval

---

## Workflow Tests

Test Temporal workflows:

- normal success
- agent timeout
- data-source failure
- retry
- partial workflow recovery

---

## Agent Tests

Create benchmark cases.

For each agent, test:

- expected tools
- schema validity
- source grounding
- unsupported claims
- known financial interpretations

---

## End-to-End Tests

Example:

```text
research request
     ↓
data retrieval
     ↓
agents
     ↓
valuation
     ↓
debate
     ↓
final report
     ↓
database persistence
```

---

# 33. Security

Even though Axiom does not execute trades, treat it as a production SaaS application.

Include:

- authenticated users
- JWT or session-based auth
- role-based access
- rate limiting
- secrets management
- encrypted connections
- input validation
- output validation
- audit logs
- data-access boundaries

For agent security:

- allowlisted tools
- tool argument validation
- prompt injection defense
- document-source tagging
- no unrestricted shell execution
- no unrestricted network access
- token/cost limits
- maximum research depth

---

# 34. Failure Handling

Axiom should gracefully handle:

- SEC API unavailable
- market-data API unavailable
- LLM timeout
- malformed agent output
- insufficient source evidence
- duplicate research request
- valuation calculation error
- vector retrieval failure

Example behavior:

```text
Filing Agent failed
       ↓
Temporal retry
       ↓
second failure
       ↓
mark agent degraded
       ↓
continue only if minimum evidence threshold is satisfied
       ↓
final report includes degraded-data warning
```

---

# 35. Idempotency

Long-running workflows may be retried.

Axiom should ensure:

```text
same research request
+ same idempotency key
= one research run
```

Do not create duplicate:

- research jobs
- filing ingestions
- forecasts
- reports

---

# 36. Caching

Use caching for:

- company profiles
- normalized financial statements
- filing search results
- market data
- embeddings
- repeated valuation inputs

Do not cache final research blindly when the requested research cutoff or agent versions differ.

---

# 37. Data Freshness

Each data source should expose freshness metadata.

Example:

```text
Financial data updated: 2026-08-29
Market price updated:    2026-09-05 15:59
SEC filing index:        2026-09-05 15:45
```

The final report should record the actual data snapshot used.

---

# 38. Final Research Report Model

A final report could contain:

```json
{
  "ticker": "NVDA",
  "research_date": "2026-09-05",
  "horizon_months": 12,

  "stance": "BULLISH",
  "conviction": 78,

  "thesis": [],
  "risks": [],
  "catalysts": [],
  "unresolved_questions": [],

  "valuation": {
    "bear": 110,
    "base": 138,
    "bull": 165
  },

  "forecasts": [],
  "evidence_ids": [],

  "agent_versions": {},
  "model_versions": {},
  "data_cutoff": "2026-09-05T16:00:00Z"
}
```

---

# 39. Frontend Screens

The final application should eventually include the following pages.

## 1. Dashboard

Shows:

- recent research
- watchlist
- research status
- thesis changes

---

## 2. Company Page

Shows:

- company overview
- financial metrics
- filings
- current thesis
- research history
- forecasts

---

## 3. Research Run Page

Shows live agent execution.

---

## 4. Research Report Page

Shows:

- thesis
- risks
- catalysts
- valuation
- forecasts
- citations
- agent debate

---

## 5. Thesis History Page

Timeline of Axiom's opinions.

---

## 6. Backtest Page

Select:

- company
- historical date
- horizon

Then show historical research and actual outcome.

---

## 7. Agent Lab

Show:

- agent performance
- recent executions
- model versions
- prompt versions
- cost
- latency
- failure rates

This is particularly valuable for the portfolio/resume demonstration.

---

# 40. AWS Deployment Architecture

A practical production deployment:

```text
                        Internet
                           │
                           ▼
                     CloudFront
                           │
                           ▼
                 Application Load Balancer
                     /               \
                    /                 \
                   ▼                   ▼
            Next.js Web          FastAPI API
              ECS                    ECS
                                      │
                         ┌────────────┼────────────┐
                         ▼            ▼            ▼
                     Temporal      Redis        PostgreSQL
                     Workers     ElastiCache       RDS
                         │
                         ▼
                        S3

External:
SEC / Market Data / LLM APIs
```

---

# 41. CI/CD

A GitHub Actions pipeline could run:

```text
Pull Request
   │
   ├── lint
   ├── type check
   ├── unit tests
   ├── integration tests
   ├── agent evaluation suite
   ├── security scan
   └── Docker build
```

After merge:

```text
build image
   ↓
push ECR
   ↓
run migrations
   ↓
deploy API
   ↓
deploy worker
   ↓
health checks
```

---

# 42. Development Phases

The key is to get a working product early and add sophistication progressively.

---

# Phase 0 — Foundation

Goal:

Get the application running end-to-end without agents.

Build:

- FastAPI
- PostgreSQL
- Alembic
- company model
- research model
- basic SEC data retrieval
- financial data retrieval
- Docker Compose
- basic frontend

End state:

The user can search for a company and view basic financial data.

---

# Phase 1 — First AI Research Pipeline

Build only:

- Research Orchestrator
- Fundamental Agent
- Filing Agent
- Valuation Agent
- Bear Agent
- Final Synthesis

Workflow:

```text
Company
 ↓
Financial data
 ↓
Filings
 ↓
3 specialist agents
 ↓
Preliminary thesis
 ↓
Bear critique
 ↓
Final report
```

End state:

Axiom can generate a serious, evidence-backed research report.

This is the first resume-usable version.

---

# Phase 2 — Production Workflow Layer

Add:

- Temporal
- retries
- workflow status
- agent-run persistence
- observability
- error handling
- background research execution

Now research can survive backend restarts.

---

# Phase 3 — Bull / Bear / Judge

Add:

- Bull Agent
- Judge Agent
- explicit debate
- rebuttal
- evidence gap detection
- research revision

This becomes the strong multi-agent version.

---

# Phase 4 — Point-in-Time Research

Add:

- publication timestamps everywhere
- cutoff enforcement
- historical snapshots
- historical price data

Now Axiom can perform correct historical research.

---

# Phase 5 — Forecasting + Backtesting

Add:

- structured forecasts
- prediction tracking
- actual result evaluation
- agent performance metrics

This is where Axiom becomes substantially more unique.

---

# Phase 6 — Long-Term Research Memory

Add:

- thesis versions
- previous assumptions
- thesis comparison
- mistake analysis
- persistent semantic memory

---

# Phase 7 — More Specialized Agents

Add:

- Industry Agent
- Macro Agent
- Catalyst Agent
- Risk Agent
- Research Memory Agent

Only add agents when they create a meaningful specialization.

---

# Phase 8 — Portfolio Intelligence

Add:

- watchlist
- holdings
- portfolio risks
- sector exposure
- thesis coverage
- portfolio research

---

# 43. Fast Version vs Full Version

If you want the first useful build quickly, stop initially at:

```text
FastAPI
PostgreSQL
SEC ingestion
Financial data
Fundamental Agent
Filing Agent
Valuation Agent
Bear Agent
Final report
Basic Next.js UI
```

Do not begin with:

```text
Kafka
Kubernetes
10 agents
multi-region infrastructure
complex portfolio management
custom vector database
full backtesting
```

Those can come later.

The goal is:

> Build the smallest version that already demonstrates the core architectural idea.

---

# 44. Example End-to-End User Flow

A user opens Axiom.

## Step 1

Search:

```text
NVIDIA
```

## Step 2

Select:

```text
Research Date: Current
Horizon: 12 months
Research Depth: Full
```

## Step 3

Axiom starts a Temporal workflow.

## Step 4

The backend verifies:

- company metadata
- latest financial statements
- SEC filings
- market price

Missing data is ingested.

## Step 5

LangGraph starts research.

### Fundamental Agent

Finds:

```text
Revenue growth remains elevated.
Gross margin is strong.
Free cash flow generation is expanding.
```

### Filing Agent

Finds:

```text
Export restrictions remain a material risk.
Customer concentration remains important.
```

### Valuation Agent

Runs:

```text
Bear DCF
Base DCF
Bull DCF
multiple-based checks
```

## Step 6

A preliminary thesis is produced.

## Step 7

Bear Agent attacks it.

Example:

```text
The base case assumes data-center growth remains above 30%.
This assumption is highly sensitive to hyperscaler capex.
Under 20% growth, implied fair value declines materially.
```

## Step 8

The research system performs revision if required.

## Step 9

Judge Agent produces final conviction.

## Step 10

The user receives:

```text
STANCE: BULLISH
CONVICTION: 78/100

Base Fair Value: $138
Bear Fair Value: $110
Bull Fair Value: $165
```

with:

- thesis
- risks
- catalysts
- forecasts
- source citations
- bull argument
- bear argument
- debate history
- agent confidence

## Step 11

The research run becomes part of company memory.

## Step 12

Months later Axiom evaluates:

- what predictions were correct
- what assumptions failed
- which agents were accurate

---

# 45. What Makes the Project Resume-Worthy

The real value is not "I used LangGraph."

The resume value comes from being able to discuss architectural decisions such as:

### Why FastAPI?

Because Python integrates naturally with financial models, AI tools, LangGraph, pandas, and data pipelines.

### Why not microservices immediately?

Because independent deployment boundaries were not yet justified.

### Why Temporal and LangGraph?

Temporal handles workflow reliability.

LangGraph handles reasoning.

### Why PostgreSQL + pgvector?

Because one durable data system is simpler and sufficient at the initial scale.

### Why are calculations outside the LLM?

For determinism, accuracy, testability, and reproducibility.

### Why store publication timestamps?

To prevent look-ahead bias.

### Why a Bear Agent?

To introduce adversarial reasoning instead of cooperative hallucination.

### Why agent evaluation?

Because agent quality must be measured rather than judged from a few demos.

---

# 46. Example Resume Bullet

A future polished bullet could look like:

> Built Axiom, a production-grade multi-agent equity research platform using FastAPI, LangGraph, Temporal, PostgreSQL/pgvector and AWS; orchestrated specialized fundamental, filing, valuation and adversarial research agents over point-in-time SEC/financial data, implemented deterministic valuation models, citation-grounded thesis generation, historical research memory and quantitative backtesting of agent forecasts.

A second bullet could emphasize backend architecture:

> Designed durable asynchronous research workflows with Temporal, typed Pydantic agent contracts, versioned prompts/models, traceable evidence lineage and OpenTelemetry-based agent observability; added automated evaluation for grounding accuracy, forecast error, latency and token cost.

---

# 47. Interview Story

If an interviewer asks:

> Tell me about Axiom.

A strong answer would be:

Axiom is an AI-native equity research platform I built to explore what a production multi-agent architecture should actually look like. Instead of using one LLM to generate a stock recommendation, I separated the research process into specialized agents for fundamentals, SEC filings, valuation, and adversarial analysis. The agents communicate using typed contracts and can only make material claims when they attach evidence.

I also intentionally separated probabilistic reasoning from deterministic computation. The agents can choose assumptions, but all valuation and financial calculations run through normal Python functions so they are reproducible and testable.

LangGraph manages the reasoning graph, while Temporal manages the durable workflow so long-running research can retry and recover from failures. PostgreSQL stores structured state and pgvector stores filing and research embeddings.

The part I am especially interested in is the point-in-time research engine. Every source has a publication timestamp, which lets me replay research historically without leaking future information. The system records explicit forecasts, and later I can backtest those forecasts to measure both overall research quality and the accuracy of individual agents.

That moves the project from simply generating AI output to actually evaluating whether the agents are useful.

---

# 48. How Axiom Helps Build Sentinel Later

Axiom prepares much of the infrastructure required for Sentinel.

Skills and infrastructure learned in Axiom:

```text
FastAPI
Pydantic
PostgreSQL
LangGraph
Temporal
agent orchestration
tool calling
structured outputs
evaluation
observability
Docker
AWS
CI/CD
```

Sentinel can then add:

```text
Kafka
high-volume event streaming
transaction simulation
fraud rules
Neo4j
graph algorithms
anomaly detection
case management
financial crime investigation
```

This makes the order:

```text
Axiom
  ↓
learn production agent architecture
  ↓
Sentinel
  ↓
apply architecture to a harder event-driven fintech system
```

a strong progression.

---

# 49. Recommended Initial Scope

For the first serious build, focus on:

## Backend

- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- basic Redis
- SEC ingestion
- financial data service

## AI

- LangGraph
- Fundamental Agent
- Filing Agent
- Valuation Agent
- Bear Agent
- Final Synthesis Agent

## Deterministic Logic

- financial ratios
- DCF
- scenario analysis

## Frontend

- company search
- run research
- live research status
- final report
- sources

## DevOps

- Docker
- GitHub Actions
- one AWS deployment

This gives you a meaningful production-style V1 without spending weeks on unnecessary infrastructure.

---

# 50. Definition of Done for Axiom V1

Axiom V1 is complete when:

- [ ] A user can search for a public company.
- [ ] A user can start a research run.
- [ ] The backend retrieves structured financial data.
- [ ] The backend retrieves SEC filings.
- [ ] Filing content is indexed and searchable.
- [ ] Fundamental Agent produces structured analysis.
- [ ] Filing Agent produces evidence-grounded analysis.
- [ ] Valuation Agent calls deterministic valuation tools.
- [ ] Bear Agent challenges the preliminary thesis.
- [ ] Final synthesis produces a structured report.
- [ ] Every important claim links to evidence.
- [ ] Research runs are stored in PostgreSQL.
- [ ] Agent runs are individually logged.
- [ ] The user can view research progress.
- [ ] The user can view the final report.
- [ ] Unit and integration tests exist.
- [ ] Docker-based local development works.
- [ ] The system can be deployed to AWS.

---

# 51. Definition of Done for the Full Axiom Product

The full project is complete when Axiom can:

- [ ] Produce complete institutional-style research.
- [ ] Run multiple specialized research agents.
- [ ] Conduct Bull vs Bear debate.
- [ ] Detect missing evidence and trigger additional research.
- [ ] Store long-term company research memory.
- [ ] Track thesis versions.
- [ ] Run research using historical information cutoffs.
- [ ] Prevent look-ahead bias.
- [ ] Generate explicit measurable forecasts.
- [ ] Backtest historical forecasts.
- [ ] Measure agent performance.
- [ ] Compare prompt/model versions.
- [ ] Show tracing and observability.
- [ ] Handle workflow failures and retries.
- [ ] Deploy as a production-style cloud application.
- [ ] Support user watchlists and portfolios.
- [ ] Compare companies and peers.
- [ ] Explain why Axiom's opinion changed over time.

---

# 52. Final Product Vision

The finished version of Axiom should feel like an AI research terminal where the user can:

1. Search any supported public company.
2. Run a new research investigation.
3. Watch specialized agents work.
4. Inspect each agent's evidence.
5. Read the final thesis.
6. Compare Bull and Bear arguments.
7. Review valuation scenarios.
8. See explicit forecasts.
9. Compare current research with previous research.
10. Ask what assumptions changed.
11. Run a historical research simulation.
12. Evaluate what Axiom would have predicted in the past.
13. Score those predictions against reality.
14. Inspect which agents are historically strongest.
15. Maintain a watchlist or portfolio.
16. Use Axiom as an actual personal investment-research assistant.

The key objective is:

> **Axiom should not merely generate investment research. It should create research, remember it, challenge it, measure it, and learn from its past mistakes.**

That is the architectural idea that makes the project meaningfully different from a normal AI finance application.
