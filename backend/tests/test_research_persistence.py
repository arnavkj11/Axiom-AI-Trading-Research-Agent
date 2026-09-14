"""Round-trip tests for the research-run persistence layer.

A completed pipeline run only exists in memory until save_research_state
writes it down, so these tests assert the Pydantic models that come back
out of load_research_state are equal to the ones that went in — that's
the whole contract the frontend will depend on to render a finished
debate.
"""

from datetime import date

from app.agents.schemas import (
    BearCase,
    BullCase,
    FilingAnalysis,
    FilingChunkEvidence,
    FinancialMetricEvidence,
    Finding,
    FundamentalAnalysis,
    JudgeVerdict,
    ScenarioValuation,
    Stance,
    ValuationOutput,
    ValuationOutputEvidence,
)
from app.company.models import Company
from app.financials.models import FinancialMetric, MetricName, PeriodType
from app.research.models import ResearchRun, ResearchRunStatus
from app.research.schemas import ResearchState
from app.research.service import load_research_state, save_research_state

METRIC_EVIDENCE = FinancialMetricEvidence(
    metric_id=1, metric_name=MetricName.OPERATING_MARGIN, period_end=date(2026, 6, 30), value=0.34
)
CHUNK_EVIDENCE = FilingChunkEvidence(
    chunk_id=12,
    filing_id=3,
    accession_number="0000320193-26-000078",
    section="Item 1A. Risk Factors",
    quote="We depend on single-source suppliers for certain components.",
)
VALUATION_EVIDENCE = ValuationOutputEvidence(
    research_run_id=1,
    function_name="run_dcf",
    output_field="fair_value_per_share",
    value=47.84,
    assumptions={"growth_rate": 0.06, "discount_rate": 0.09},
)


def _company(db_session) -> Company:
    company = Company(ticker="AAPL", name="Apple Inc.", cik="0000320193")
    db_session.add(company)
    db_session.commit()
    return company


def _run(db_session, company: Company) -> ResearchRun:
    run = ResearchRun(company_id=company.id, research_date=date(2026, 9, 6))
    db_session.add(run)
    db_session.commit()
    return run


def _full_state(run: ResearchRun, company: Company) -> ResearchState:
    return ResearchState(
        research_run_id=run.id,
        company_id=company.id,
        ticker=company.ticker,
        research_date=run.research_date,
        status=ResearchRunStatus.RUNNING,
        fundamental_analysis=FundamentalAnalysis(
            stance=Stance.BULLISH,
            confidence=0.8,
            findings=[Finding(claim="Margins expanded", importance=0.8, evidence=[METRIC_EVIDENCE])],
            risks=[Finding(claim="Capex is rising", importance=0.4)],
        ),
        filing_analysis=FilingAnalysis(
            stance=Stance.NEUTRAL,
            confidence=0.5,
            findings=[Finding(claim="Supplier concentration", importance=0.7, evidence=[CHUNK_EVIDENCE])],
        ),
        valuation_output=ValuationOutput(
            method="dcf",
            scenarios=[
                ScenarioValuation(
                    scenario="bear",
                    fair_value_per_share=30.17,
                    assumptions={"growth_rate": 0.03, "discount_rate": 0.10},
                ),
                ScenarioValuation(
                    scenario="base",
                    fair_value_per_share=47.84,
                    assumptions={"growth_rate": 0.06, "discount_rate": 0.09},
                ),
                ScenarioValuation(
                    scenario="bull",
                    fair_value_per_share=76.38,
                    assumptions={"growth_rate": 0.09, "discount_rate": 0.08},
                ),
            ],
            current_price=41.20,
            evidence=[VALUATION_EVIDENCE],
            commentary="Base case assumes services monetization continues.",
        ),
        bull_case=BullCase(
            thesis="Margins are expanding.",
            confidence=0.75,
            findings=[Finding(claim="Margin expanded", importance=0.8, evidence=[METRIC_EVIDENCE])],
            rebuttal="Cash generation supports continued buybacks.",
            rebuttal_findings=[
                Finding(claim="FCF remains strong", importance=0.6, evidence=[METRIC_EVIDENCE])
            ],
        ),
        bear_case=BearCase(
            thesis="Growth is decelerating.",
            confidence=0.6,
            findings=[Finding(claim="Supplier risk", importance=0.7, evidence=[CHUNK_EVIDENCE])],
            rebuttal="Rising debt limits the runway.",
            rebuttal_findings=[
                Finding(claim="Debt has climbed", importance=0.6, evidence=[METRIC_EVIDENCE])
            ],
        ),
        judge_verdict=JudgeVerdict(
            stance=Stance.BULLISH,
            conviction=64,
            synthesis="Margin strength outweighs the disclosed supply-chain risk.",
            bull_summary="Margins expanding, strong FCF.",
            bear_summary="Growth decelerating, supplier concentration.",
            rebuttal_summary="The rebuttal round modestly favored the bull case.",
            key_findings=[Finding(claim="Margin expanded", importance=0.9, evidence=[METRIC_EVIDENCE])],
            risks=[Finding(claim="Supplier risk", importance=0.7, evidence=[CHUNK_EVIDENCE])],
            catalysts=[Finding(claim="New product cycle", importance=0.3)],
        ),
    )


def test_save_then_load_round_trips_every_agent_output(db_session):
    company = _company(db_session)
    run = _run(db_session, company)
    state = _full_state(run, company)

    save_research_state(db_session, state)
    loaded = load_research_state(db_session, run.id)

    assert loaded.fundamental_analysis == state.fundamental_analysis
    assert loaded.filing_analysis == state.filing_analysis
    assert loaded.valuation_output == state.valuation_output
    assert loaded.bull_case == state.bull_case
    assert loaded.bear_case == state.bear_case
    assert loaded.judge_verdict == state.judge_verdict


def test_save_marks_run_complete(db_session):
    company = _company(db_session)
    run = _run(db_session, company)

    save_research_state(db_session, _full_state(run, company))

    assert run.status == ResearchRunStatus.COMPLETE
    assert run.completed_at is not None
    assert run.error is None
    assert load_research_state(db_session, run.id).status == ResearchRunStatus.COMPLETE


def test_save_marks_run_failed_when_state_carries_an_error(db_session):
    company = _company(db_session)
    run = _run(db_session, company)
    # A run that died partway through: the Judge never produced a verdict,
    # but whatever the earlier agents finished is still worth persisting.
    state = _full_state(run, company).model_copy(
        update={"judge_verdict": None, "error": "judge agent timed out after 3 retries"}
    )

    save_research_state(db_session, state)

    assert run.status == ResearchRunStatus.FAILED
    assert run.error == "judge agent timed out after 3 retries"
    assert run.completed_at is not None

    loaded = load_research_state(db_session, run.id)
    assert loaded.status == ResearchRunStatus.FAILED
    assert loaded.error == "judge agent timed out after 3 retries"
    # The outputs that did complete survive the failure.
    assert loaded.bull_case == state.bull_case
    assert loaded.judge_verdict is None


def test_partial_state_round_trips_with_unfinished_outputs_as_none(db_session):
    company = _company(db_session)
    run = _run(db_session, company)
    state = ResearchState(
        research_run_id=run.id,
        company_id=company.id,
        ticker=company.ticker,
        research_date=run.research_date,
        fundamental_analysis=FundamentalAnalysis(
            stance=Stance.BULLISH, confidence=0.8, findings=[]
        ),
    )

    save_research_state(db_session, state)
    loaded = load_research_state(db_session, run.id)

    assert loaded.fundamental_analysis == state.fundamental_analysis
    assert loaded.filing_analysis is None
    assert loaded.valuation_output is None
    assert loaded.bull_case is None
    assert loaded.bear_case is None
    assert loaded.judge_verdict is None


def test_load_rehydrates_company_and_financial_metrics(db_session):
    company = _company(db_session)
    run = _run(db_session, company)
    db_session.add(
        FinancialMetric(
            company_id=company.id,
            metric_name=MetricName.REVENUE.value,
            period_end=date(2026, 9, 30),
            period_type=PeriodType.ANNUAL,
            value=391_035_000_000.0,
            source="ALPHA_VANTAGE",
        )
    )
    db_session.commit()
    save_research_state(db_session, _full_state(run, company))

    loaded = load_research_state(db_session, run.id)

    assert loaded.company.ticker == "AAPL"
    assert loaded.ticker == "AAPL"
    assert [m.metric_name for m in loaded.financial_metrics] == [MetricName.REVENUE]
    assert loaded.financial_metrics[0].value == 391_035_000_000.0


def test_load_returns_none_for_unknown_run_id(db_session):
    assert load_research_state(db_session, 4242) is None


def test_recommendation_is_computed_on_save_and_restored_on_load(db_session):
    # The state going in carries no recommendation — it's derived at save
    # time from the verdict and valuation, then read back as a model.
    company = _company(db_session)
    run = _run(db_session, company)
    state = _full_state(run, company)
    assert state.recommendation is None

    save_research_state(db_session, state)
    loaded = load_research_state(db_session, run.id)

    assert loaded.recommendation is not None
    assert loaded.recommendation.stance == state.judge_verdict.stance
    assert loaded.recommendation.conviction == state.judge_verdict.conviction
    # Thresholds travel with it, so an old run stays interpretable if the
    # product decision behind them later changes.
    assert loaded.recommendation.thresholds["min_conviction"] > 0


def test_partial_run_without_a_verdict_persists_a_not_rated_recommendation(db_session):
    company = _company(db_session)
    run = _run(db_session, company)
    state = _full_state(run, company).model_copy(
        update={"judge_verdict": None, "error": "judge timed out"}
    )

    save_research_state(db_session, state)
    loaded = load_research_state(db_session, run.id)

    assert loaded.recommendation.action.value == "NOT_RATED"


def test_load_restores_the_price_the_run_used(db_session):
    # Price lives on the run row rather than in the agent-output JSONB,
    # since it describes the run's inputs, not any one agent's output. A
    # reopened report must still show what the stock cost at the time —
    # otherwise its upside numbers have no visible anchor.
    company = _company(db_session)
    run = _run(db_session, company)
    run.price_at_run = 180.42
    run.price_as_of = date(2026, 9, 8)
    db_session.commit()
    save_research_state(db_session, _full_state(run, company))

    loaded = load_research_state(db_session, run.id)

    assert loaded.current_price == 180.42
    assert loaded.price_as_of == date(2026, 9, 8)
