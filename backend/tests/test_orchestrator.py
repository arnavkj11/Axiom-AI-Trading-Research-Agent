from datetime import date

import pytest

from app.agents.debate_common import RebuttalAlreadyRecordedError, RebuttalResponse
from app.agents.orchestrator import build_research_graph, run_research
from app.agents.schemas import FinancialMetricEvidence, Finding, JudgeVerdict
from app.company.models import Company
from app.financials.models import FinancialMetric, MetricName, PeriodType
from app.financials.schemas import FinancialMetricRecord
from app.research.models import ResearchRun, ResearchRunStatus
from app.research.schemas import ResearchState
from tests.fakes import (
    FILING_CHUNK as CHUNK,
    FakeFilingSearchClient,
    RoutingFakeLLMClient as _RoutingFakeLLMClient,
    all_agent_responses as _all_agent_responses,
    bear_case as _bear_case,
    bull_case as _bull_case,
    filing_analysis as _filing_analysis,
    fundamental_analysis as _fundamental_analysis,
    judge_verdict as _judge_verdict,
    rebuttal_response as _rebuttal_response,
)


def _base_state() -> ResearchState:
    return ResearchState(
        research_run_id=1,
        company_id=7,
        ticker="AAPL",
        research_date=date(2026, 9, 6),
        financial_metrics=[
            FinancialMetricRecord(
                id=1,
                metric_name=MetricName.FREE_CASH_FLOW,
                period_end=date(2026, 6, 30),
                period_type=PeriodType.ANNUAL,
                value=100.0,
            ),
            FinancialMetricRecord(
                id=2,
                metric_name=MetricName.SHARE_COUNT,
                period_end=date(2026, 6, 30),
                period_type=PeriodType.ANNUAL,
                value=1000.0,
            ),
        ],
    )


def test_build_research_graph_runs_all_seven_agents_and_merges_output():
    llm_client = _RoutingFakeLLMClient(_all_agent_responses())
    filing_search_client = FakeFilingSearchClient(default=[CHUNK])

    graph = build_research_graph(llm_client, filing_search_client)
    result = graph.invoke(_base_state())

    assert result["fundamental_analysis"] == _fundamental_analysis()
    assert result["filing_analysis"] == _filing_analysis()
    assert result["valuation_output"] is not None
    assert result["bull_case"].thesis == _bull_case().thesis
    assert result["bull_case"].rebuttal == _rebuttal_response().rebuttal
    assert result["bull_case"].rebuttal_findings == _rebuttal_response().rebuttal_findings
    assert result["bear_case"].thesis == _bear_case().thesis
    assert result["bear_case"].rebuttal == _rebuttal_response().rebuttal
    assert result["bear_case"].rebuttal_findings == _rebuttal_response().rebuttal_findings
    assert result["judge_verdict"] == _judge_verdict()
    assert {call.__name__ for call in llm_client.calls} == {
        "FundamentalAnalysis",
        "FilingAnalysis",
        "ScenarioAssumptionsChoice",
        "BullCase",
        "BearCase",
        "RebuttalResponse",
        "JudgeVerdict",
    }


def test_graph_terminates_after_exactly_one_rebuttal_round_even_if_prompted_to_continue():
    # _rebuttal_response()'s text explicitly asks to "keep producing
    # further rebuttal rounds" — proving the cap isn't just a prompt
    # instruction the model could ignore: the graph has no edge that could
    # invoke either rebuttal node a second time, so no matter what the
    # (fake) model's response says, each rebuttal node fires exactly once
    # and judge fires exactly once.
    llm_client = _RoutingFakeLLMClient(_all_agent_responses())
    filing_search_client = FakeFilingSearchClient(default=[CHUNK])

    graph = build_research_graph(llm_client, filing_search_client)
    result = graph.invoke(_base_state())

    rebuttal_calls = [c for c in llm_client.calls if c is RebuttalResponse]
    judge_calls = [c for c in llm_client.calls if c is JudgeVerdict]
    assert len(rebuttal_calls) == 2  # exactly one bull_rebuttal + one bear_rebuttal call
    assert len(judge_calls) == 1

    # Not accumulated/concatenated across rounds — exactly the one canned
    # rebuttal text, verbatim.
    assert result["bull_case"].rebuttal == _rebuttal_response().rebuttal
    assert result["bear_case"].rebuttal == _rebuttal_response().rebuttal


def test_rebuttal_node_itself_refuses_a_second_round_if_ever_invoked_again():
    # Defense-in-depth guard, exercised directly rather than through the
    # graph (the graph can't produce this state — there's no edge back
    # into bull_rebuttal): calling bull_rebuttal on a bull_case that
    # already has a recorded rebuttal must raise, not silently overwrite.
    from app.agents.bull_rebuttal import bull_rebuttal

    state = _base_state().model_copy(
        update={
            "bull_case": _bull_case().model_copy(
                update={"rebuttal": "Already rebutted once.", "rebuttal_findings": []}
            ),
            "bear_case": _bear_case(),
        }
    )
    llm_client = _RoutingFakeLLMClient(_all_agent_responses())

    with pytest.raises(RebuttalAlreadyRecordedError):
        bull_rebuttal(state, llm_client)


def _make_company_with_metrics(db_session) -> Company:
    company = Company(ticker="AAPL", name="Apple Inc.", cik="0000320193")
    db_session.add(company)
    db_session.flush()
    db_session.add_all(
        [
            FinancialMetric(
                company_id=company.id,
                metric_name=MetricName.FREE_CASH_FLOW.value,
                period_end=date(2026, 6, 30),
                period_type=PeriodType.ANNUAL,
                value=100.0,
                source="ALPHA_VANTAGE",
            ),
            FinancialMetric(
                company_id=company.id,
                metric_name=MetricName.SHARE_COUNT.value,
                period_end=date(2026, 6, 30),
                period_type=PeriodType.ANNUAL,
                value=1000.0,
                source="ALPHA_VANTAGE",
            ),
        ]
    )
    db_session.commit()
    return company


def _make_research_run(db_session, company) -> ResearchRun:
    run = ResearchRun(company_id=company.id, research_date=date(2026, 9, 6))
    db_session.add(run)
    db_session.commit()
    return run


def test_run_research_populates_all_seven_agent_outputs_for_a_real_db_company(db_session):
    company = _make_company_with_metrics(db_session)
    research_run = _make_research_run(db_session, company)

    llm_client = _RoutingFakeLLMClient(_all_agent_responses())
    filing_search_client = FakeFilingSearchClient(default=[CHUNK])

    final_state = run_research(db_session, research_run, llm_client, filing_search_client)

    assert final_state.fundamental_analysis == _fundamental_analysis()
    assert final_state.filing_analysis == _filing_analysis()
    assert final_state.valuation_output is not None
    assert final_state.bull_case.thesis == _bull_case().thesis
    assert final_state.bull_case.rebuttal == _rebuttal_response().rebuttal
    assert final_state.bear_case.thesis == _bear_case().thesis
    assert final_state.bear_case.rebuttal == _rebuttal_response().rebuttal
    assert final_state.judge_verdict == _judge_verdict()
    assert final_state.status == ResearchRunStatus.COMPLETE


def test_run_research_updates_research_run_row_status_and_timestamps(db_session):
    company = _make_company_with_metrics(db_session)
    research_run = _make_research_run(db_session, company)
    assert research_run.status == ResearchRunStatus.PENDING
    assert research_run.started_at is None

    llm_client = _RoutingFakeLLMClient(_all_agent_responses())
    filing_search_client = FakeFilingSearchClient(default=[CHUNK])

    run_research(db_session, research_run, llm_client, filing_search_client)

    assert research_run.status == ResearchRunStatus.COMPLETE
    assert research_run.started_at is not None
    assert research_run.completed_at is not None


def test_run_research_sets_status_running_before_invoking_graph(db_session, monkeypatch):
    # Captures the ResearchState.status handed to graph.invoke() at the call
    # site in the main thread, rather than reading the ORM research_run
    # object from inside agent node threads — Session objects aren't safe
    # for concurrent cross-thread access, so that would be a racy test, not
    # a meaningful one.
    company = _make_company_with_metrics(db_session)
    research_run = _make_research_run(db_session, company)
    captured = {}

    class _StubGraph:
        def invoke(self, state):
            captured["status"] = state.status
            return state.model_dump()

    monkeypatch.setattr(
        "app.agents.orchestrator.build_research_graph", lambda *args, **kwargs: _StubGraph()
    )

    run_research(db_session, research_run, llm_client=object(), filing_search_client=object())

    assert captured["status"] == ResearchRunStatus.RUNNING


def test_run_research_marks_failed_and_reraises_when_an_agent_errors(db_session):
    company = Company(ticker="MSFT", name="Microsoft Corp.", cik="0000789019")
    db_session.add(company)
    db_session.commit()
    # Deliberately no FinancialMetric rows -> valuation_analyst raises
    # ValuationInputsMissingError.
    research_run = _make_research_run(db_session, company)

    llm_client = _RoutingFakeLLMClient(_all_agent_responses())
    filing_search_client = FakeFilingSearchClient(default=[CHUNK])

    with pytest.raises(Exception):
        run_research(db_session, research_run, llm_client, filing_search_client)

    assert research_run.status == ResearchRunStatus.FAILED


def test_run_research_marks_failed_when_a_debate_node_fails_mid_run(db_session):
    # Confirms the same FAILED handling covers a failure specifically in
    # the debate phase (not just an upstream agent): here the rebuttal
    # response cites evidence that doesn't exist anywhere in the pool, so
    # bull_rebuttal raises EvidenceNotInPoolError mid-graph.
    company = _make_company_with_metrics(db_session)
    research_run = _make_research_run(db_session, company)

    fabricated_rebuttal = RebuttalResponse(
        rebuttal="This cites evidence that was never produced.",
        rebuttal_findings=[
            Finding(
                claim="Fabricated",
                importance=0.9,
                evidence=[
                    FinancialMetricEvidence(
                        metric_id=999,
                        metric_name=MetricName.DEBT,
                        period_end=date(2026, 6, 30),
                        value=1.0,
                    )
                ],
            )
        ],
    )
    responses = _all_agent_responses()
    responses[RebuttalResponse] = fabricated_rebuttal
    llm_client = _RoutingFakeLLMClient(responses)
    filing_search_client = FakeFilingSearchClient(default=[CHUNK])

    with pytest.raises(Exception):
        run_research(db_session, research_run, llm_client, filing_search_client)

    assert research_run.status == ResearchRunStatus.FAILED


def test_run_research_retry_after_failure_is_safe_since_state_is_rebuilt_fresh(db_session):
    # run_research never persists partial ResearchState anywhere — a retry
    # is just calling run_research again, which rebuilds ResearchState
    # from the research_runs/companies/financial_metrics rows only. So a
    # failed attempt's bull_case/bear_case (with any rebuttal already
    # recorded) never carries forward: retrying re-runs the whole graph
    # from scratch, and RebuttalAlreadyRecordedError can't fire on a
    # fresh bull_case/bear_case that both start with rebuttal=None.
    company = _make_company_with_metrics(db_session)
    research_run = _make_research_run(db_session, company)
    filing_search_client = FakeFilingSearchClient(default=[CHUNK])

    fabricated_rebuttal = RebuttalResponse(
        rebuttal="Fabricated.",
        rebuttal_findings=[
            Finding(
                claim="Fabricated",
                importance=0.9,
                evidence=[
                    FinancialMetricEvidence(
                        metric_id=999,
                        metric_name=MetricName.DEBT,
                        period_end=date(2026, 6, 30),
                        value=1.0,
                    )
                ],
            )
        ],
    )
    broken_responses = _all_agent_responses()
    broken_responses[RebuttalResponse] = fabricated_rebuttal
    broken_llm_client = _RoutingFakeLLMClient(broken_responses)

    with pytest.raises(Exception):
        run_research(db_session, research_run, broken_llm_client, filing_search_client)
    assert research_run.status == ResearchRunStatus.FAILED

    working_llm_client = _RoutingFakeLLMClient(_all_agent_responses())
    final_state = run_research(db_session, research_run, working_llm_client, filing_search_client)

    assert research_run.status == ResearchRunStatus.COMPLETE
    assert final_state.bull_case.rebuttal == _rebuttal_response().rebuttal
    assert final_state.bear_case.rebuttal == _rebuttal_response().rebuttal
    assert final_state.judge_verdict == _judge_verdict()
